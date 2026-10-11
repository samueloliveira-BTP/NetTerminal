"""Janela principal: árvore de equipamentos, abas de terminal (com tela
dividida) e menu."""
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import customtkinter as ctk

from netterminal import APP_NAME, APP_VERSION, config
from netterminal.core import destaque as destaque_core
from netterminal.core.models import MARCAS, PROTOCOLOS
from netterminal.net.monitor import MonitorStatus
from netterminal.security.admin import ControleAdmin
from netterminal.services import auditoria, transferencia, updater
from netterminal.ui.dialogs import acesso_rapido, equipamento, ferramentas_rede
from netterminal.ui.dialogs.admin import exigir_permissao
from netterminal.ui.menu import BarraMenu
from netterminal.ui.splash import mostrar_splash
from netterminal.ui.tema import (COR_DESCONHECIDO, COR_OFFLINE, COR_ONLINE, FONTE_MAX, FONTE_MIN,
                                 aplicar_estilo_ttk, carregar_cores, carregar_fonte, carregar_tema, paleta_atual)
from netterminal.ui.terminal_tab import TerminalTab
from netterminal.ui.utils import centralizar_e_topo, msgbox

log = logging.getLogger(__name__)

# Prefixos dos ids na árvore: evita colisão entre o nome de um grupo e o id de um equipamento
_PREFIXO_GRUPO = "g::"
_PREFIXO_EQUIP = "e::"
_FILTRO_TODAS_MARCAS = "Todas as Marcas"
_FILTRO_TODOS_PROTOS = "Todos"

# Tela dividida: rótulo do botão -> (máximo de terminais visíveis, orientação)
LAYOUTS = {"▣ 1": (1, "lado"), "◫ 2": (2, "lado"), "⬒ 2": (2, "empilhado"), "⊞ 4": (4, "lado")}


def posicoes_paineis(quantidade, orientacao):
    """Grade adaptativa: devolve ([(linha, coluna, altura, largura)], (linhas, colunas)).

    1 terminal  -> ocupa tudo
    2 terminais -> lado a lado (ou empilhados, no modo ⬒)
    3 terminais -> dois em cima e um embaixo ocupando a largura toda
    4 terminais -> grade 2x2
    """
    if quantidade <= 1:
        return [(0, 0, 1, 1)][:quantidade], (1, 1)
    if quantidade == 2:
        if orientacao == "empilhado":
            return [(0, 0, 1, 1), (1, 0, 1, 1)], (2, 1)
        return [(0, 0, 1, 1), (0, 1, 1, 1)], (1, 2)
    if quantidade == 3:
        return [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 2)], (2, 2)
    return [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)], (2, 2)

_ATALHOS = """Na janela principal:
  Ctrl+F            buscar equipamento
  Ctrl+T / Enter    conectar no(s) equipamento(s) selecionado(s)
  Ctrl+W            fechar a aba ativa
  Delete            excluir equipamento(s) selecionado(s)

Dentro do terminal:
  Ctrl+Shift+F      localizar texto na aba (Enter = próximo, Shift+Enter = anterior, Esc = fechar)
  Ctrl+roda mouse   aumentar/diminuir a fonte
  Selecionar texto  copia automaticamente
  Botão direito / Ctrl+V / Shift+Insert   colar
  Ctrl+C            copia se houver seleção; senão envia "interromper" ao equipamento

Tela dividida: escolha 1, 2 ou 4 painéis no canto superior direito.
Clique num terminal para torná-lo o painel ativo; a próxima aba abre nele."""


class OLTManagerApp(ctk.CTk):
    def __init__(self, db, hostkeys):
        super().__init__()
        self.withdraw()
        self.title(f"{APP_NAME} - Gerenciador de Ativos de Rede")
        self.geometry("1280x760")
        try:
            self.iconbitmap(config.resource_path("assets/icone.ico"))
        except tk.TclError:
            log.warning("Ícone do aplicativo não encontrado.")

        self.db = db
        self.hostkeys = hostkeys
        self.admin = ControleAdmin(db)
        self.cores = carregar_cores(db)
        self.tema = carregar_tema(db)
        self.fonte_terminal = carregar_fonte(db)
        self.regras_destaque = []      # [(RegraDestaque, regex compilada)] — só as ativas
        self._carregar_regras_destaque()
        self.abas = {}                 # nome_da_aba -> {"btn", "lbl", "dot", "frame"}
        self.paineis = []              # abas visíveis na tela dividida, em ordem (sem buracos)
        self.painel_ativo = 0
        self.max_paineis, self.orientacao = LAYOUTS["▣ 1"]
        self._janelas_destacadas = []  # TerminalTab em janelas separadas
        self._equipamentos = {}        # id -> Equipamento (o que está na árvore)
        self._fila_ui = queue.Queue()  # funções vindas de threads, executadas na thread da UI
        self._status_mudou = threading.Event()

        ctk.set_appearance_mode(self.tema)
        aplicar_estilo_ttk(self.cores)
        self.monitor = MonitorStatus(db, config.MONITOR_INTERVALO_SEG, config.MONITOR_WORKERS,
                                     config.MONITOR_TIMEOUT_SEG, ao_atualizar=self._status_mudou.set,
                                     metodo=config.MONITOR_METODO)
        self.menu_barra = BarraMenu(self)
        self._criar_layout()
        self.definir_layout(self.db.get_config("layout_modo", "▣ 1"), salvar=False)
        self.carregar_lista()
        self.monitor.iniciar()
        self.after(100, self._processar_fila_ui)
        self.after(3000, self._verificar_atualizacao)

        # Atalhos globais. O terminal intercepta (e "quebra") as teclas digitadas
        # dentro dele, então estes só disparam com o foco fora do terminal.
        self.bind_all("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind_all("<Control-t>", lambda e: self.conectar_selecionado())
        self.bind_all("<Control-w>", lambda e: self._fechar_aba_atual())
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        mostrar_splash(self)

    # ================================================================ infra
    def report_callback_exception(self, exc, val, tb):
        """Erros em botões/eventos: detalhe vai para o app.log, o técnico vê só um aviso."""
        log.error("Erro em ação da interface:", exc_info=(exc, val, tb))
        msgbox(self, "error", "Erro inesperado",
               "Ocorreu um erro inesperado nesta ação.\nOs detalhes foram registrados no app.log.")

    def executar_na_ui(self, funcao):
        """Use a partir de threads: agenda `funcao` para rodar na thread da interface."""
        self._fila_ui.put(funcao)

    def _processar_fila_ui(self):
        while True:
            try:
                funcao = self._fila_ui.get_nowait()
            except queue.Empty:
                break
            funcao()
        if self._status_mudou.is_set():
            self._status_mudou.clear()
            self._atualizar_cores_arvore()
            self.atualizar_indicadores_abas()
        self.after(100, self._processar_fila_ui)

    def _ao_fechar(self):
        self.monitor.parar()
        for dados in list(self.abas.values()):
            dados["frame"].encerrar()
        for term in self._janelas_destacadas:
            if term.winfo_exists():
                term.encerrar()
        log.info("Aplicativo encerrado pelo usuário.")
        self.destroy()

    def _todos_terminais(self):
        terminais = [d["frame"] for d in self.abas.values()]
        return terminais + [t for t in self._janelas_destacadas if t.winfo_exists()]

    # =============================================================== layout
    def _criar_layout(self):
        self.paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, bd=0, sashwidth=6)
        self.paned_window.pack(expand=True, fill="both", padx=5, pady=5)

        self.sidebar = ctk.CTkFrame(self.paned_window, width=320, corner_radius=0)
        self.paned_window.add(self.sidebar, minsize=280)
        ctk.CTkLabel(self.sidebar, text="Ativos de Rede", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=10, padx=10)

        self.search_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Buscar equipamento ou IP... (Ctrl+F)")
        self.search_entry.pack(fill="x", padx=10, pady=(5, 10))
        self.search_entry.bind("<KeyRelease>", self._agendar_busca)

        filtros = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        filtros.pack(fill="x", padx=10, pady=(0, 10))
        self.filter_marca = ctk.CTkComboBox(filtros, values=[_FILTRO_TODAS_MARCAS] + MARCAS, width=140,
                                            state="readonly", command=lambda e: self.carregar_lista())
        self.filter_marca.set(_FILTRO_TODAS_MARCAS)
        self.filter_marca.pack(side="left", padx=(0, 2))
        self.filter_proto = ctk.CTkComboBox(filtros, values=[_FILTRO_TODOS_PROTOS] + PROTOCOLOS, width=100,
                                            state="readonly", command=lambda e: self.carregar_lista())
        self.filter_proto.set(_FILTRO_TODOS_PROTOS)
        self.filter_proto.pack(side="right", padx=(2, 0))

        botoes_cadastro = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        botoes_cadastro.pack(pady=5, padx=10, fill="x")
        self.btn_nova_olt = ctk.CTkButton(botoes_cadastro, text="+ Cadastrar Equipamento",
                                          command=lambda: equipamento.abrir(self))
        self.btn_nova_olt.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_acesso_rapido = ctk.CTkButton(botoes_cadastro, text="⚡ Rápido", width=90,
                                               command=lambda: acesso_rapido.abrir(self))
        self.btn_acesso_rapido.pack(side="right")

        arvore_frame = ctk.CTkFrame(self.sidebar)
        arvore_frame.pack(expand=True, fill="both", padx=10, pady=5)
        self.tree = ttk.Treeview(arvore_frame, show="tree", selectmode="extended")
        self.tree.pack(expand=True, fill="both", side="left")
        barra = ttk.Scrollbar(arvore_frame, orient="vertical", command=self.tree.yview)
        barra.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.bind("<Double-1>", lambda e: self.conectar_selecionado())
        self.tree.bind("<Return>", lambda e: self.conectar_selecionado())
        self.tree.bind("<Delete>", lambda e: self.excluir_selecionados())
        self.tree.bind("<Button-3>", self._menu_contexto)
        self.tree.bind("<<TreeviewOpen>>", self._agendar_salvar_pastas)
        self.tree.bind("<<TreeviewClose>>", self._agendar_salvar_pastas)
        self.tree.tag_configure("status_online", foreground=COR_ONLINE)
        self.tree.tag_configure("status_offline", foreground=COR_OFFLINE)
        self.tree.tag_configure("status_unknown", foreground=COR_DESCONHECIDO)

        acoes = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        acoes.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(acoes, text="✏️ Editar", width=120, command=self.editar_selecionado).pack(side="left", expand=True, padx=2)
        ctk.CTkButton(acoes, text="❌ Excluir", width=120, fg_color="#8B0000", hover_color="red",
                      command=self.excluir_selecionados).pack(side="right", expand=True, padx=2)

        self.main_area = ctk.CTkFrame(self.paned_window)
        self.paned_window.add(self.main_area, minsize=400)
        topo_abas = ctk.CTkFrame(self.main_area, fg_color="transparent")
        topo_abas.pack(fill="x", padx=5, pady=2)
        self.seletor_layout = ctk.CTkSegmentedButton(topo_abas, values=list(LAYOUTS), command=self.definir_layout)
        self.seletor_layout.pack(side="right", padx=(6, 0))
        self.tab_bar_frame = ctk.CTkScrollableFrame(topo_abas, height=45, orientation="horizontal", fg_color="transparent")
        self.tab_bar_frame.pack(side="left", fill="x", expand=True)

        rodape = ctk.CTkFrame(self.main_area, height=20, fg_color="transparent")
        rodape.pack(side="bottom", fill="x", padx=10, pady=(2, 5))
        ctk.CTkLabel(rodape, text=f"Usuário: {auditoria.usuario_atual()}", font=("Consolas", 11),
                     text_color="gray").pack(side="left", padx=5)
        ctk.CTkLabel(rodape, text=f"{APP_NAME} v{APP_VERSION} | Desenvolvido por Samuel Luiz",
                     font=("Consolas", 11), text_color="gray").pack(side="right", padx=5)
        self.tab_content_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.tab_content_frame.pack(expand=True, fill="both")
        self._aplicar_cores_moldura()

    def _aplicar_cores_moldura(self):
        for btn in (self.btn_nova_olt, self.btn_acesso_rapido):
            btn.configure(fg_color=self.cores["btn_bg"], hover_color=self.cores["btn_hover"])
        self.paned_window.configure(bg=paleta_atual()["divisoria"])
        self.seletor_layout.configure(selected_color=self.cores["btn_bg"], selected_hover_color=self.cores["btn_hover"])

    # ======================================================= aparência
    def aplicar_aparencia(self):
        """Reaplica tema, cores e fonte em tudo que está aberto."""
        self.cores = carregar_cores(self.db)
        self.tema = carregar_tema(self.db)
        ctk.set_appearance_mode(self.tema)
        aplicar_estilo_ttk(self.cores)
        self.menu_barra.aplicar_paleta()
        self._aplicar_cores_moldura()
        self.fonte_terminal = carregar_fonte(self.db)
        for term in self._todos_terminais():
            term.aplicar_cores()
            term.aplicar_fonte(self.fonte_terminal)
        self._redesenhar_paineis()

    def alterar_fonte_terminal(self, passo):
        nova = max(FONTE_MIN, min(FONTE_MAX, self.fonte_terminal + passo))
        if nova == self.fonte_terminal:
            return
        self.fonte_terminal = nova
        self.db.set_config("fonte_terminal", str(nova))
        for term in self._todos_terminais():
            term.aplicar_fonte(nova)

    def _carregar_regras_destaque(self):
        regras = []
        for regra in self.db.listar_regras_destaque():
            if not regra.ativo:
                continue
            try:
                regras.append((regra, destaque_core.compilar(regra.padrao, regra.tipo)))
            except Exception as e:
                log.warning(f"Regra de realce '{regra.nome}' ignorada: {e}")
        self.regras_destaque = regras

    def recarregar_regras_destaque(self):
        self._carregar_regras_destaque()
        for term in self._todos_terminais():
            term.usar_cores = str(self.db.get_config("syntax_highlighting", "True")) == "True"
            term.aplicar_regras_destaque()

    # =========================================================== árvore
    def _agendar_busca(self, event=None):
        """Espera 200 ms após a última tecla antes de redesenhar a árvore."""
        if getattr(self, "_timer_busca", None):
            self.after_cancel(self._timer_busca)
        self._timer_busca = self.after(200, self.carregar_lista)

    def carregar_lista(self):
        self.tree.delete(*self.tree.get_children())
        termo = self.search_entry.get().strip().lower()
        marca = self.filter_marca.get()
        proto = self.filter_proto.get()

        equipamentos = self.db.listar_equipamentos()
        self._equipamentos = {e.id: e for e in equipamentos}
        if termo:
            equipamentos = [e for e in equipamentos if termo in e.nome.lower() or termo in e.ip.lower()]
        if marca != _FILTRO_TODAS_MARCAS:
            equipamentos = [e for e in equipamentos if e.marca == marca]
        if proto != _FILTRO_TODOS_PROTOS:
            equipamentos = [e for e in equipamentos if e.protocolo == proto]

        estados = self.db.estados_pastas()
        for grupo in sorted({e.grupo for e in equipamentos}):
            # Com busca ativa, abre todas as pastas para mostrar os resultados
            aberta = True if termo else estados.get(grupo, False)
            self.tree.insert("", "end", _PREFIXO_GRUPO + grupo, text=f"📁 {grupo}", open=aberta)
        for eq in equipamentos:
            texto, tag = self._texto_e_tag(eq)
            self.tree.insert(_PREFIXO_GRUPO + eq.grupo, "end", iid=f"{_PREFIXO_EQUIP}{eq.id}", text=texto, tags=(tag,))

    def _texto_e_tag(self, eq):
        info = self.monitor.status.get(eq.id)
        if info is None:
            tag = "status_unknown"
        else:
            tag = "status_online" if info["online"] else "status_offline"
        return f" ● {eq.ip} - {eq.nome}", tag

    def _atualizar_cores_arvore(self):
        """Só troca a cor das linhas existentes (preserva seleção, scroll e pastas)."""
        for grupo_iid in self.tree.get_children(""):
            for iid in self.tree.get_children(grupo_iid):
                eq = self._equipamento_do_iid(iid)
                if eq:
                    texto, tag = self._texto_e_tag(eq)
                    self.tree.item(iid, text=texto, tags=(tag,))

    def _equipamento_do_iid(self, iid):
        if not iid.startswith(_PREFIXO_EQUIP):
            return None
        try:
            return self._equipamentos.get(int(iid[len(_PREFIXO_EQUIP):]))
        except ValueError:
            return None

    def equipamentos_selecionados(self):
        return [eq for eq in (self._equipamento_do_iid(i) for i in self.tree.selection()) if eq]

    def _agendar_salvar_pastas(self, event=None):
        if getattr(self, "_timer_pastas", None):
            self.after_cancel(self._timer_pastas)
        self._timer_pastas = self.after(300, self._salvar_pastas)

    def _salvar_pastas(self):
        if self.search_entry.get().strip():
            return  # durante a busca as pastas são abertas automaticamente; não grava esse estado
        pares = []
        for iid in self.tree.get_children(""):
            aberta = str(self.tree.item(iid, "open")).lower() in ("true", "1")
            pares.append((f"pasta_{iid[len(_PREFIXO_GRUPO):]}", "True" if aberta else "False"))
        if pares:
            self.db.set_config_lote(pares)

    def _menu_contexto(self, event):
        iid = self.tree.identify_row(event.y)
        eq = self._equipamento_do_iid(iid) if iid else None
        if not eq:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="🔌 Conectar", command=self.conectar_selecionado)
        menu.add_separator()
        menu.add_command(label="📶 Ping", command=lambda: ferramentas_rede.abrir(self, eq.ip, "ping"))
        menu.add_command(label="📶 Ping contínuo", command=lambda: ferramentas_rede.abrir(self, eq.ip, "ping_continuo"))
        menu.add_command(label="🧭 Traceroute", command=lambda: ferramentas_rede.abrir(self, eq.ip, "tracert"))
        menu.add_separator()
        menu.add_command(label="📋 Copiar IP", command=lambda: self._copiar(eq.ip))
        menu.add_command(label="📋 Copiar Nome", command=lambda: self._copiar(eq.nome))
        menu.add_separator()
        menu.add_command(label="✏️ Editar", command=lambda: equipamento.abrir(self, eq))
        menu.add_command(label="❌ Excluir", command=self.excluir_selecionados)
        menu.tk_popup(event.x_root, event.y_root)

    def _copiar(self, texto):
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()

    def editar_selecionado(self):
        selecionados = self.equipamentos_selecionados()
        if selecionados:
            equipamento.abrir(self, selecionados[0])

    def excluir_selecionados(self):
        selecionados = self.equipamentos_selecionados()
        if not selecionados or not exigir_permissao(self, "excluir_olt"):
            return
        if len(selecionados) == 1:
            pergunta = f"Apagar {selecionados[0].rotulo}?"
        else:
            nomes = "\n".join(f"• {e.rotulo}" for e in selecionados[:10])
            extra = f"\n... e mais {len(selecionados) - 10}" if len(selecionados) > 10 else ""
            pergunta = f"Apagar {len(selecionados)} equipamentos?\n\n{nomes}{extra}"
        if msgbox(self, "askyesno", "Confirmar exclusão", pergunta):
            self.db.excluir_equipamentos([e.id for e in selecionados])
            log.info(f"{auditoria.usuario_atual()} excluiu: " + ", ".join(e.rotulo for e in selecionados))
            self.carregar_lista()

    # ======================================================= import/export
    def exportar_cadastro(self):
        caminho = filedialog.asksaveasfilename(title="Exportar cadastro", defaultextension=".csv",
                                               filetypes=[("CSV", "*.csv")], initialfile="equipamentos_export.csv")
        if not caminho:
            return
        try:
            n = transferencia.exportar_equipamentos(caminho, self.db.listar_equipamentos())
            msgbox(self, "info", "Exportar", f"{n} equipamento(s) exportado(s) com sucesso!")
        except Exception as e:
            log.error(f"Falha ao exportar cadastro: {e}")
            msgbox(self, "error", "Erro", "Não foi possível exportar (detalhes no app.log).")

    def importar_cadastro(self, parent=None):
        if not exigir_permissao(self, "importar_cadastro"):
            return
        caminho = filedialog.askopenfilename(parent=parent or self, title="Importar cadastro",
                                             filetypes=[("CSV", "*.csv"), ("Todos os arquivos", "*.*")])
        if not caminho:
            return
        try:
            res = transferencia.importar_equipamentos(caminho, self.db)
        except Exception as e:
            log.error(f"Falha ao importar cadastro de {caminho}: {e}")
            msgbox(self, "error", "Erro", f"Não foi possível importar: {e}", parent=parent)
            return
        self.carregar_lista()
        self.monitor.forcar_agora()
        msgbox(self, "info", "Importar", res.resumo("IP já existia"), parent=parent)

    # ================================================== abas e tela dividida
    def conectar_selecionado(self):
        for eq in self.equipamentos_selecionados()[:10]:  # limite de segurança para seleção grande
            self.abrir_aba(eq, eq.rotulo)

    def abrir_aba(self, eq, nome_base):
        nome, n = nome_base, 1
        while nome in self.abas:
            nome = f"{nome_base} - {n}"
            n += 1

        moldura = ctk.CTkFrame(self.tab_bar_frame, corner_radius=15)
        moldura.pack(side="left", padx=4, pady=2)
        dot = ctk.CTkLabel(moldura, text="●", font=ctk.CTkFont(size=14), text_color=COR_DESCONHECIDO, width=8)
        dot.pack(side="left", padx=(10, 2), pady=2)
        lbl = ctk.CTkLabel(moldura, text=nome, font=ctk.CTkFont(weight="bold"))
        lbl.pack(side="left", padx=(0, 5), pady=2)
        lbl.bind("<Button-1>", lambda e: self.selecionar_aba(nome))
        ctk.CTkButton(moldura, text="✖", width=20, height=20, corner_radius=10, fg_color="transparent",
                      hover_color="#8B0000", command=lambda: self.fechar_aba(nome)).pack(side="right", padx=(0, 5), pady=2)
        ctk.CTkButton(moldura, text="↗", width=20, height=20, corner_radius=10, fg_color="transparent",
                      hover_color="#1f538d", command=lambda: self.destacar_aba(nome)).pack(side="right", padx=(0, 2), pady=2)

        term = TerminalTab(self.tab_content_frame, self, eq)
        self.abas[nome] = {"btn": moldura, "lbl": lbl, "dot": dot, "frame": term}
        self.selecionar_aba(nome)

    def definir_layout(self, rotulo, salvar=True):
        """Define o MÁXIMO de terminais visíveis ao mesmo tempo. A grade em si se
        adapta à quantidade de abas abertas (ver posicoes_paineis)."""
        if rotulo not in LAYOUTS:
            rotulo = "▣ 1"
        self.seletor_layout.set(rotulo)
        self.max_paineis, self.orientacao = LAYOUTS[rotulo]
        # Mantém as visíveis e completa com as demais abas, na ordem em que foram abertas
        visiveis = [n for n in self.paineis if n in self.abas]
        visiveis += [n for n in self.abas if n not in visiveis]
        self.paineis = visiveis[:self.max_paineis]
        self.painel_ativo = min(self.painel_ativo, max(0, len(self.paineis) - 1))
        if salvar:
            self.db.set_config("layout_modo", rotulo)
        self._redesenhar_paineis()

    def _redesenhar_paineis(self):
        frame = self.tab_content_frame
        for dados in self.abas.values():
            dados["frame"].grid_forget()
        posicoes, (linhas, colunas) = posicoes_paineis(len(self.paineis), self.orientacao)
        for i in range(2):  # zera a grade anterior e liga só as linhas/colunas usadas
            frame.grid_rowconfigure(i, weight=1 if i < linhas else 0, uniform="linhas" if i < linhas else "")
            frame.grid_columnconfigure(i, weight=1 if i < colunas else 0, uniform="colunas" if i < colunas else "")
        varios = len(self.paineis) > 1
        for indice, (nome, (linha, coluna, alt, larg)) in enumerate(zip(self.paineis, posicoes)):
            term = self.abas[nome]["frame"]
            term.grid(row=linha, column=coluna, rowspan=alt, columnspan=larg, sticky="nsew", padx=2, pady=2)
            term.marcar_ativo(varios and indice == self.painel_ativo)

        paleta = paleta_atual()
        ativo = self.paineis[self.painel_ativo] if self.paineis else None
        for nome, dados in self.abas.items():
            if nome == ativo:
                cor = self.cores["btn_bg"]
            elif nome in self.paineis:
                cor = paleta["aba_visivel"]
            else:
                cor = paleta["aba"]
            dados["btn"].configure(fg_color=cor)

    def selecionar_aba(self, nome):
        """Mostra a aba: se já está visível, só ativa o painel; se há painel livre,
        ocupa o livre; senão, troca pelo conteúdo do painel ativo."""
        if nome not in self.abas:
            return
        if nome in self.paineis:
            self.painel_ativo = self.paineis.index(nome)
        elif len(self.paineis) < self.max_paineis:
            self.paineis.append(nome)
            self.painel_ativo = len(self.paineis) - 1
        else:
            self.paineis[self.painel_ativo] = nome
        self._redesenhar_paineis()
        self.abas[nome]["frame"].terminal_text.focus_set()

    def ao_focar_terminal(self, term):
        """Clicar dentro de um terminal torna o painel dele o ativo."""
        for nome, dados in self.abas.items():
            if dados["frame"] is term and nome in self.paineis:
                indice = self.paineis.index(nome)
                if indice != self.painel_ativo:
                    self.painel_ativo = indice
                    self._redesenhar_paineis()
                return

    def fechar_aba(self, nome):
        dados = self.abas.pop(nome, None)
        if not dados:
            return
        dados["frame"].destroy()  # encerra a conexão e registra a duração
        dados["btn"].destroy()
        if nome in self.paineis:
            self.paineis.remove(nome)
            # Reaproveita o espaço com a aba oculta mais recente (sem deixar buraco)
            ocultas = [n for n in self.abas if n not in self.paineis]
            if ocultas and len(self.paineis) < self.max_paineis:
                self.paineis.append(ocultas[-1])
            self.painel_ativo = min(self.painel_ativo, max(0, len(self.paineis) - 1))
        self._redesenhar_paineis()

    def _fechar_aba_atual(self):
        nome = self.paineis[self.painel_ativo] if self.paineis else None
        if nome in self.abas:
            self.fechar_aba(nome)

    def destacar_aba(self, nome):
        """Abre a sessão numa janela separada. A conexão é refeita na janela
        nova (mover uma conexão viva entre janelas é arriscado)."""
        dados = self.abas.get(nome)
        if not dados:
            return
        eq = dados["frame"].eq
        self.fechar_aba(nome)
        janela = ctk.CTkToplevel(self)
        janela.title(f"{APP_NAME} — {nome}")
        janela.geometry("900x600")
        centralizar_e_topo(self, janela)
        term = TerminalTab(janela, self, eq)
        term.pack(expand=True, fill="both")
        self._janelas_destacadas.append(term)

        def ao_fechar():
            if term in self._janelas_destacadas:
                self._janelas_destacadas.remove(term)
            term.destroy()
            janela.destroy()
        janela.protocol("WM_DELETE_WINDOW", ao_fechar)

    def atualizar_indicadores_abas(self):
        """Bolinha da aba: verde = conectado, vermelho = falhou, cinza = conectando/encerrada."""
        for dados in self.abas.values():
            term = dados["frame"]
            if not term.winfo_exists():
                continue
            cor = COR_ONLINE if term.conectado else COR_OFFLINE if term.falhou else COR_DESCONHECIDO
            dados["dot"].configure(text_color=cor)

    def atualizar_macros_nas_abas(self):
        for term in self._todos_terminais():
            term.atualizar_marcas()

    # ========================================================= atualização
    def _verificar_atualizacao(self):
        def worker():
            info = updater.verificar_atualizacao()
            if info:
                self.executar_na_ui(lambda: self._oferecer_atualizacao(info))
        threading.Thread(target=worker, daemon=True, name="verifica-update").start()

    def verificar_atualizacao_manual(self):
        """Ajuda > Verificar atualizações agora: consulta e SEMPRE dá um retorno."""
        def worker():
            resultado = updater.consultar_atualizacao()
            self.executar_na_ui(lambda: self._mostrar_resultado_consulta(resultado))
        threading.Thread(target=worker, daemon=True, name="verifica-update-manual").start()

    def _mostrar_resultado_consulta(self, resultado):
        if resultado.status == "nova":
            self._oferecer_atualizacao(resultado.info)
        elif resultado.status == "atualizado":
            msgbox(self, "info", "Atualizações", f"Você já está na versão mais recente ({APP_VERSION}).")
        elif resultado.status == "sem_url":
            msgbox(self, "info", "Atualizações",
                   f"Você está na versão {APP_VERSION}.\n\n"
                   "As atualizações do NetTerminal são distribuídas pela equipe responsável: quando houver "
                   "versão nova, você receberá o instalador. Basta executá-lo — ele substitui a versão "
                   "atual e mantém seus dados e configurações.")
        elif resultado.status == "recusada":
            msgbox(self, "error", "Atualizações",
                   "O servidor respondeu, mas a atualização foi recusada por segurança.\nDetalhes no app.log.")
        else:
            msgbox(self, "warning", "Atualizações",
                   "Não foi possível consultar o servidor de atualizações agora.\n"
                   "Verifique a conexão com a internet e tente de novo mais tarde.")

    def _oferecer_atualizacao(self, info):
        notas = f"\n\n{info.notas}" if info.notas else ""
        if info.obrigatoria:
            msgbox(self, "info", "Atualização obrigatória",
                   f"A versão {info.versao} é obrigatória e será instalada agora.{notas}")
        elif not msgbox(self, "askyesno", "Atualização disponível",
                        f"Versão {info.versao} disponível (você está na {APP_VERSION}).{notas}\n\n"
                        "Atualizar agora? O NetTerminal fecha, instala e abre de novo sozinho."):
            return
        log.info(f"Iniciando atualização para a versão {info.versao}.")

        def worker():
            try:
                caminho = updater.baixar_e_verificar(info)
            except Exception as e:
                log.error(f"Atualização cancelada: {e}")
                self.executar_na_ui(lambda: msgbox(
                    self, "error", "Falha na atualização",
                    "Não foi possível baixar ou confirmar a autenticidade do instalador.\n"
                    "A atualização foi cancelada por segurança; o app continua na versão atual."))
                return
            self.executar_na_ui(lambda: self._instalar_atualizacao(caminho))
        threading.Thread(target=worker, daemon=True, name="baixa-update").start()

    def _instalar_atualizacao(self, caminho):
        reabrir = sys.executable if getattr(sys, "frozen", False) else None
        try:
            updater.executar_instalador(caminho, reabrir)
        except OSError as e:
            log.error(f"Falha ao executar o instalador: {e}")
            msgbox(self, "error", "Erro", "Não foi possível iniciar o instalador (detalhes no app.log).")
            return
        self._ao_fechar()

    # ================================================================ ajuda
    def mostrar_atalhos(self):
        msgbox(self, "info", "Atalhos de teclado", _ATALHOS)

    def mostrar_sobre(self):
        msgbox(self, "info", f"Sobre o {APP_NAME}",
               f"{APP_NAME} — Gerenciador de Ativos de Rede\nVersão {APP_VERSION}\n\n"
               f"Desenvolvido por Samuel Luiz\n\nUsuário: {auditoria.usuario_atual()}\n"
               f"Dados salvos em:\n{config.get_data_dir()}")

    def abrir_pasta_dados(self):
        os.startfile(config.get_data_dir())
