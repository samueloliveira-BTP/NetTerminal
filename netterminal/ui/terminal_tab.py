"""Aba de terminal: exibe a sessão SSH/Telnet e envia o que o técnico digita.

Fluxo de dados:
    thread da Sessao --(fila de eventos)--> _consumir_eventos() [thread da UI]
    teclado/macros/colar --> _enviar() --> Sessao.enviar()

Controles de segurança implementados aqui:
  * Desconexão automática por inatividade (SESSION_IDLE_TIMEOUT_MIN no .env).
  * O que é digitado quando o equipamento pede senha NÃO vai para o histórico.
  * Colagem de várias linhas pede confirmação antes de enviar.
  * Chave SSH alterada: o técnico precisa confirmar explicitamente.

Atalhos dentro do terminal:
    Ctrl+Shift+F  localizar texto na aba      Ctrl+roda do mouse  tamanho da fonte
    Ctrl+V / Shift+Insert / botão direito    colar
"""
import logging
import queue
import re
import time
import tkinter as tk

import customtkinter as ctk

from netterminal import config
from netterminal.core.redaction import eh_prompt_de_senha
from netterminal.net.sessao import SessaoSSH, SessaoTelnet
from netterminal.services import auditoria
from netterminal.ui.dialogs.login_manual import pedir_credenciais
from netterminal.ui.tema import COR_DESCONHECIDO, COR_OFFLINE, COR_ONLINE, COR_SISTEMA, paleta_atual
from netterminal.ui.utils import msgbox

log = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
_CURSOR_ESQUERDA_RE = re.compile(r"\x1b\[(\d*)D")
_CONTROLE_RE = re.compile(r"([\b\x7f\r\x07\x00])")
_LINHAS_REDESTACADAS = 300   # só recolore o final do buffer, não o histórico inteiro
_MAX_RESULTADOS_BUSCA = 5000
_INTERVALO_ENVIO_LINHAS_MS = 400

_TECLAS_ESPECIAIS = {"Up": b"\x1b[A", "Down": b"\x1b[B", "Right": b"\x1b[C", "Left": b"\x1b[D",
                     "BackSpace": b"\x08", "Delete": b"\x7f"}


class TerminalTab(ctk.CTkFrame):
    INTERVALO_FILA_MS = 30

    def __init__(self, master, app, equipamento):
        super().__init__(master, fg_color="transparent", border_width=2, border_color=paleta_atual()["divisoria"])
        self.app = app
        self.db = app.db
        self.eq = equipamento
        self.sessao = None
        self.hora_conexao = None
        self.falha_local = False      # ex.: técnico cancelou o login manual
        self._fechada = False
        self._buffer_comando = ""
        self._modo_senha = False      # True enquanto o equipamento estiver pedindo senha
        self._timer_destaque = None
        self._timer_busca = None
        self._resultados_busca = []
        self._indice_busca = -1
        self.last_activity = time.time()
        self.usar_cores = str(self.db.get_config("syntax_highlighting", "True")) == "True"

        self._montar_interface()
        self.aplicar_regras_destaque()
        self.after(50, self._iniciar_conexao)
        self.after(self.INTERVALO_FILA_MS, self._consumir_eventos)
        self.after(30000, self._verificar_inatividade)

    # ================================================================ estado
    @property
    def conectado(self):
        return bool(self.sessao and self.sessao.conectado)

    @property
    def falhou(self):
        return self.falha_local or bool(self.sessao and self.sessao.falhou)

    # ============================================================= interface
    def _montar_interface(self):
        """Uma única barra compacta (≈34 px) por terminal:
        [● status] [marca] [macros que couberem … +N ▾] [🔍 ONU Ping Tracert ↻]
        Antes eram duas linhas (≈110 px) com barra de rolagem — na tela
        dividida em 4, isso comia boa parte da área útil."""
        cores = self.app.cores
        self.barra = ctk.CTkFrame(self, height=34, corner_radius=0, fg_color="transparent")
        self.barra.pack(fill="x", padx=4, pady=(4, 2))
        self.barra.grid_columnconfigure(2, weight=1)

        status = ctk.CTkFrame(self.barra, fg_color="transparent")
        status.grid(row=0, column=0, sticky="w", padx=(2, 6))
        self.status_dot = ctk.CTkLabel(status, text="●", width=14, text_color=COR_DESCONHECIDO,
                                       font=ctk.CTkFont(size=15))
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(status, text="Conectando...", font=ctk.CTkFont(size=12, weight="bold"))
        self.status_label.pack(side="left", padx=(2, 0))

        self.combo_marca = ctk.CTkComboBox(self.barra, values=["Nenhuma"], width=118, height=26,
                                           command=self.carregar_botoes_macro)
        self.combo_marca.grid(row=0, column=1, padx=4)

        # Área das macros: tamanho vem da barra (não dos botões), para não "empurrar" o layout
        self.macro_buttons_frame = ctk.CTkFrame(self.barra, height=30, width=1, fg_color="transparent")
        self.macro_buttons_frame.grid(row=0, column=2, sticky="ew", padx=4)
        self.macro_buttons_frame.pack_propagate(False)
        self.macro_buttons_frame.bind("<Configure>", self._agendar_distribuir_macros)
        self._botoes_macro, self._macros_ocultas, self._timer_macros = [], [], None

        acoes = ctk.CTkFrame(self.barra, fg_color="transparent")
        acoes.grid(row=0, column=3, sticky="e")
        estilo = dict(height=26, fg_color="transparent", border_width=1, border_color="#555555",
                      font=ctk.CTkFont(size=12))
        from netterminal.ui.dialogs import ferramentas_rede, provisionar_onu  # import tardio (evita ciclo)
        self.btn_reconectar = ctk.CTkButton(acoes, text="↻ Reconectar", width=96, height=26,
                                            fg_color=cores["btn_bg"], hover_color=cores["btn_hover"],
                                            font=ctk.CTkFont(size=12), command=self.reconectar)
        self._btn_lupa = ctk.CTkButton(acoes, text="🔍", width=30, command=self.mostrar_busca, **estilo)
        self._btn_lupa.pack(side="left", padx=1)
        ctk.CTkButton(acoes, text="ONU", width=46, command=lambda: provisionar_onu.abrir(self.app, self),
                      **estilo).pack(side="left", padx=1)
        ctk.CTkButton(acoes, text="Ping", width=46, command=lambda: ferramentas_rede.abrir(self.app, self.eq.ip, "ping"),
                      **estilo).pack(side="left", padx=1)
        self._btn_tracert = ctk.CTkButton(acoes, text="Tracert", width=58,
                                          command=lambda: ferramentas_rede.abrir(self.app, self.eq.ip, "tracert"),
                                          **estilo)
        self._btn_tracert.pack(side="left", padx=1)
        self._acoes = acoes
        self._compacto = False

        # Painel para preencher variáveis [VAR] das macros (fica oculto até precisar)
        self.dynamic_bar = ctk.CTkFrame(self, height=35)
        self._montar_barra_busca()
        self.atualizar_marcas()

        self.terminal_text = tk.Text(self, bg=cores["term_bg"], fg=cores["term_fg"],
                                     insertbackground=cores["term_fg"], font=("Consolas", self.app.fonte_terminal),
                                     bd=0, highlightthickness=0,
                                     # Tamanho mínimo: o espaço real vem do painel (pack expand),
                                     # senão 4 painéis com fonte grande "estouram" a tela dividida.
                                     width=1, height=1)
        self.terminal_text.pack(expand=True, fill="both", padx=4, pady=(0, 4))
        self.terminal_text.tag_configure("sistema_tag", foreground=COR_SISTEMA)
        self._configurar_tags_busca()

        t = self.terminal_text
        t.bind("<Key>", self._ao_digitar)
        t.bind("<Button-1>", self._ao_clicar)
        t.bind("<MouseWheel>", self._registrar_atividade)
        t.bind("<Control-MouseWheel>", self._zoom_fonte)
        t.bind("<ButtonRelease-1>", self._auto_copiar_selecao)
        t.bind("<Button-3>", self.colar)
        t.bind("<Control-v>", self.colar)
        t.bind("<Control-V>", self.colar)
        t.bind("<Shift-Insert>", self.colar)
        t.bind("<Control-c>", self._ctrl_c)
        t.bind("<Control-F>", lambda e: self.mostrar_busca() or "break")  # Ctrl+Shift+F
        t.bind("<FocusIn>", lambda e: self.app.ao_focar_terminal(self))

    def _definir_status(self, texto):
        """Status curto com bolinha colorida (o IP/nome já aparece na aba)."""
        if not self.winfo_exists():
            return
        # Sempre curto: o motivo detalhado já aparece como mensagem dentro do terminal
        if texto.startswith("Conectado a "):
            curto, cor = f"Conectado · {self.eq.protocolo}", COR_ONLINE
        elif texto.startswith("Conectando"):
            curto, cor = "Conectando...", COR_DESCONHECIDO
        elif texto.startswith("BLOQUEADO"):
            curto, cor = "BLOQUEADO", COR_OFFLINE
        elif texto.startswith("Falha: equipamento usa SSH antigo"):
            curto, cor = "SSH antigo", COR_OFFLINE
        elif texto.startswith("Falha"):
            curto, cor = "Falha", COR_OFFLINE
        elif texto.startswith("Desconectado"):
            curto, cor = "Desconectado", COR_DESCONHECIDO
        else:
            curto, cor = texto[:20], COR_DESCONHECIDO
        self.status_label.configure(text=curto)
        self.status_dot.configure(text_color=cor)
        self._agendar_distribuir_macros()

    def _mostrar_reconectar(self, visivel):
        if visivel:
            self.btn_reconectar.pack(side="left", padx=(1, 4), before=self._btn_lupa)
        else:
            self.btn_reconectar.pack_forget()
        self._agendar_distribuir_macros()

    def marcar_ativo(self, ativo):
        self.configure(border_color=self.app.cores["btn_bg"] if ativo else paleta_atual()["divisoria"])

    def aplicar_cores(self):
        cores = self.app.cores
        self.terminal_text.configure(bg=cores["term_bg"], fg=cores["term_fg"], insertbackground=cores["term_fg"])
        self.btn_reconectar.configure(fg_color=cores["btn_bg"], hover_color=cores["btn_hover"])
        self.usar_cores = str(self.db.get_config("syntax_highlighting", "True")) == "True"
        self._configurar_tags_busca()
        self.carregar_botoes_macro(self.combo_marca.get())

    def aplicar_fonte(self, tamanho):
        self.terminal_text.configure(font=("Consolas", tamanho))
        self.aplicar_regras_destaque()  # regras em negrito usam o tamanho da fonte

    def _zoom_fonte(self, event):
        self.app.alterar_fonte_terminal(1 if event.delta > 0 else -1)
        return "break"

    # ========================================================== realce
    def aplicar_regras_destaque(self):
        """(Re)configura as tags de cor a partir das regras do usuário e recolore."""
        t = self.terminal_text
        for tag in t.tag_names():
            if tag.startswith("regra_"):
                t.tag_remove(tag, "1.0", "end")
        for regra, _ in self.app.regras_destaque:
            fonte = ("Consolas", self.app.fonte_terminal, "bold") if regra.negrito else ""
            t.tag_configure(regra.tag, foreground=regra.cor, font=fonte)
        # A busca tem prioridade visual sobre as regras
        t.tag_raise("busca")
        t.tag_raise("busca_atual")
        t.tag_raise("sel")
        self._destacar_sintaxe(tudo=True)

    def _destacar_sintaxe(self, tudo=False):
        self._timer_destaque = None
        if not self.usar_cores or not self.winfo_exists():
            return
        t = self.terminal_text
        inicio = "1.0" if tudo else t.index(f"end-1c linestart - {_LINHAS_REDESTACADAS} lines")
        conteudo = t.get(inicio, "end-1c")
        for regra, regex in self.app.regras_destaque:
            for m in regex.finditer(conteudo):
                if m.end() > m.start():
                    t.tag_add(regra.tag, f"{inicio} + {m.start()} chars", f"{inicio} + {m.end()} chars")

    # ======================================================= localizar
    def _montar_barra_busca(self):
        self.barra_busca = ctk.CTkFrame(self, height=34)
        ctk.CTkLabel(self.barra_busca, text="Localizar:").pack(side="left", padx=(8, 4))
        self.entry_busca = ctk.CTkEntry(self.barra_busca, width=260, placeholder_text="texto na aba (Enter = próximo)")
        self.entry_busca.pack(side="left", padx=4, pady=4)
        self.var_maiusculas = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.barra_busca, text="Aa", width=50, variable=self.var_maiusculas,
                        command=self._executar_busca).pack(side="left", padx=4)
        ctk.CTkButton(self.barra_busca, text="▲", width=32, command=lambda: self._navegar_busca(-1)).pack(side="left", padx=2)
        ctk.CTkButton(self.barra_busca, text="▼", width=32, command=lambda: self._navegar_busca(1)).pack(side="left", padx=2)
        self.lbl_busca = ctk.CTkLabel(self.barra_busca, text="", width=90)
        self.lbl_busca.pack(side="left", padx=6)
        ctk.CTkButton(self.barra_busca, text="✖", width=30, fg_color="transparent",
                      command=self.fechar_busca).pack(side="right", padx=6)
        self.entry_busca.bind("<KeyRelease>", self._agendar_busca)
        self.entry_busca.bind("<Return>", lambda e: self._navegar_busca(1))
        self.entry_busca.bind("<Shift-Return>", lambda e: self._navegar_busca(-1))
        self.entry_busca.bind("<Escape>", lambda e: self.fechar_busca())

    def _configurar_tags_busca(self):
        paleta = paleta_atual()
        self.terminal_text.tag_configure("busca", background=paleta["busca_bg"], foreground="black")
        self.terminal_text.tag_configure("busca_atual", background=paleta["busca_atual_bg"], foreground="black")

    def mostrar_busca(self):
        if not self.barra_busca.winfo_ismapped():
            self.barra_busca.pack(fill="x", padx=5, pady=(0, 4), before=self.terminal_text)
        try:  # já preenche com o texto selecionado, se houver
            selecao = self.terminal_text.get("sel.first", "sel.last")
            if selecao and "\n" not in selecao:
                self.entry_busca.delete(0, "end")
                self.entry_busca.insert(0, selecao)
        except tk.TclError:
            pass
        self.entry_busca.focus_set()
        self.entry_busca.select_range(0, "end")
        self._executar_busca()

    def fechar_busca(self):
        self.barra_busca.pack_forget()
        self.terminal_text.tag_remove("busca", "1.0", "end")
        self.terminal_text.tag_remove("busca_atual", "1.0", "end")
        self._resultados_busca, self._indice_busca = [], -1
        self.terminal_text.focus_set()

    def _agendar_busca(self, event=None):
        if event is not None and event.keysym in ("Return", "Escape", "Shift_L", "Shift_R"):
            return
        if self._timer_busca:
            self.after_cancel(self._timer_busca)
        self._timer_busca = self.after(150, self._executar_busca)

    def _executar_busca(self):
        self._timer_busca = None
        t = self.terminal_text
        t.tag_remove("busca", "1.0", "end")
        t.tag_remove("busca_atual", "1.0", "end")
        termo = self.entry_busca.get()
        self._resultados_busca, self._indice_busca = [], -1
        if not termo:
            self.lbl_busca.configure(text="")
            return
        pos, tamanho = "1.0", tk.IntVar()
        while len(self._resultados_busca) < _MAX_RESULTADOS_BUSCA:
            pos = t.search(termo, pos, stopindex="end", nocase=not self.var_maiusculas.get(), count=tamanho)
            if not pos or tamanho.get() == 0:
                break
            fim = f"{pos} + {tamanho.get()} chars"
            t.tag_add("busca", pos, fim)
            self._resultados_busca.append((pos, fim))
            pos = fim
        if self._resultados_busca:
            self._indice_busca = len(self._resultados_busca)  # o próximo "▲" vai para o mais recente
            self._navegar_busca(-1)
        else:
            self.lbl_busca.configure(text="0 resultados")

    def _navegar_busca(self, direcao):
        if not self._resultados_busca:
            self._executar_busca()
            return "break"
        self._indice_busca = (self._indice_busca + direcao) % len(self._resultados_busca)
        inicio, fim = self._resultados_busca[self._indice_busca]
        self.terminal_text.tag_remove("busca_atual", "1.0", "end")
        self.terminal_text.tag_add("busca_atual", inicio, fim)
        self.terminal_text.see(inicio)
        self.lbl_busca.configure(text=f"{self._indice_busca + 1} de {len(self._resultados_busca)}")
        return "break"

    # ============================================================== conexão
    def _iniciar_conexao(self):
        if self._fechada:
            return
        self.falha_local = False
        self._mostrar_reconectar(False)
        self._definir_status(f"Conectando a {self.eq.rotulo}...")

        if self.eq.login_manual and self.eq.protocolo == "SSH":
            credenciais = pedir_credenciais(self.app, self.eq)
            if credenciais is None:
                self.falha_local = True
                self._definir_status("Conexão cancelada")
                self._mostrar_reconectar(True)
                self.app.atualizar_indicadores_abas()
                return
            usuario, senha = credenciais
        elif self.eq.login_manual:
            usuario, senha = "", ""
            self._mensagem_sistema("Modo login manual: digite usuário e senha quando o equipamento pedir.")
        else:
            usuario = self.db.get_config("default_user", "")
            senha = self.db.get_config_secreto("default_pass")
            if not usuario:
                self._mensagem_sistema("Credencial global não configurada (Configurações > Credenciais Globais).")

        if self.eq.protocolo == "SSH":
            self.sessao = SessaoSSH(self.eq, usuario, senha, self.app.hostkeys)
        else:
            self.sessao = SessaoTelnet(self.eq, usuario, senha, login_automatico=not self.eq.login_manual)
        log.info(f"Abrindo sessão {self.eq.protocolo} com {self.eq.ip}:{self.eq.porta} "
                 f"({self.eq.nome}, login manual: {self.eq.login_manual})")
        self.sessao.iniciar()

    def reconectar(self):
        self.encerrar()
        self.sessao = None
        self._mensagem_sistema("Reconectando...")
        self._iniciar_conexao()

    def encerrar(self, motivo=None):
        """Fecha a conexão (a aba continua aberta mostrando o histórico)."""
        self._registrar_duracao()
        if self.sessao is not None:
            self.sessao.fechar()
        if motivo:
            self._definir_status(f"Desconectado ({motivo})")
            self._mostrar_reconectar(True)

    def destroy(self):
        self._fechada = True
        self.encerrar()
        super().destroy()

    def _registrar_duracao(self):
        if self.hora_conexao:
            auditoria.registrar_sessao(self.eq.ip, self.eq.nome, self.eq.protocolo,
                                       round(time.time() - self.hora_conexao))
            self.hora_conexao = None

    # ==================================================== eventos da sessão
    def _consumir_eventos(self):
        if self._fechada or not self.winfo_exists():
            return
        if self.sessao is not None:
            dados_pendentes = []
            for _ in range(500):
                try:
                    tipo, valor = self.sessao.eventos.get_nowait()
                except queue.Empty:
                    break
                if tipo == "dados":
                    dados_pendentes.append(valor)
                    continue
                if dados_pendentes:
                    self._exibir("".join(dados_pendentes))
                    dados_pendentes = []
                self._tratar_evento(tipo, valor)
            if dados_pendentes:
                self._exibir("".join(dados_pendentes))
        self.after(self.INTERVALO_FILA_MS, self._consumir_eventos)

    def _tratar_evento(self, tipo, valor):
        if tipo == "conectado":
            self.hora_conexao = time.time()
            self.last_activity = time.time()
            self._definir_status(valor)
            self.app.atualizar_indicadores_abas()
        elif tipo == "aviso":
            self._mensagem_sistema(valor)
        elif tipo == "erro":
            self._definir_status("Falha na conexão")
            self._mensagem_sistema(f"ERRO: {valor}")
            self._mostrar_reconectar(True)
            self.app.atualizar_indicadores_abas()
        elif tipo == "encerrada":
            self._registrar_duracao()
            self._definir_status("Desconectado")
            self._mensagem_sistema(valor)
            self._mostrar_reconectar(True)
            self.app.atualizar_indicadores_abas()
        elif tipo == "hostkey_mudou":
            self._tratar_hostkey_mudou(valor)
        elif tipo == "ssh_legado_necessario":
            self._tratar_ssh_legado()

    def _tratar_ssh_legado(self):
        """Equipamento só fala SSH antigo (ssh-rsa/SHA-1). Pergunta antes de liberar,
        e libera SOMENTE para este equipamento."""
        self._definir_status("Falha: equipamento usa SSH antigo")
        self._mostrar_reconectar(True)
        self.app.atualizar_indicadores_abas()
        self._mensagem_sistema(
            "Este equipamento só aceita algoritmos SSH antigos (chave ssh-rsa com SHA-1), "
            "desativados por padrão por serem mais fracos.")
        liberar = msgbox(
            self.app, "askyesno", "SSH antigo",
            f"{self.eq.rotulo} usa SSH antigo (ssh-rsa/SHA-1), comum em OLTs de firmware mais velho.\n\n"
            "Permitir SSH legado SOMENTE para este equipamento?\n"
            "A conexão continua criptografada e com verificação de chave — é bem mais seguro que Telnet.\n\n"
            "(Pode ser desmarcado depois em Editar equipamento.)")
        if not liberar:
            return
        self.eq.ssh_legado = True
        if self.eq.cadastrado:
            self.db.definir_ssh_legado(self.eq.id, True)
            self.app.carregar_lista()  # a árvore passa a ter o equipamento com a opção marcada
        log.warning(f"{auditoria.usuario_atual()} liberou SSH legado para {self.eq.rotulo}")
        self.reconectar()

    def _tratar_hostkey_mudou(self, info):
        self._definir_status("BLOQUEADO: chave SSH do equipamento mudou")
        self._mostrar_reconectar(True)
        self.app.atualizar_indicadores_abas()
        self._mensagem_sistema(
            "ALERTA DE SEGURANÇA: a identidade (chave SSH) deste equipamento é diferente da registrada.\n"
            f"  Registrada: {info['esperada']}\n  Recebida:   {info['recebida']}\n"
            "Isso acontece se o equipamento foi trocado/reinstalado, mas também pode ser uma interceptação.")
        aceitar = msgbox(
            self.app, "askyesno", "Chave SSH alterada",
            f"A chave SSH de {info['host']} mudou.\n\n"
            f"Registrada: {info['esperada']}\nRecebida: {info['recebida']}\n\n"
            "Só aceite se você tem certeza de que o equipamento foi substituído ou reconfigurado.\n\n"
            "Confiar na nova chave e reconectar?", icon="warning")
        if aceitar:
            self.app.hostkeys.remover(info["host"])
            log.warning(f"Técnico {auditoria.usuario_atual()} aceitou nova chave SSH para {info['host']}")
            self.reconectar()

    def _verificar_inatividade(self):
        if self._fechada or not self.winfo_exists():
            return
        if self.conectado and time.time() - self.last_activity >= config.SESSAO_INATIVIDADE_SEG:
            minutos = config.SESSAO_INATIVIDADE_SEG // 60
            self._mensagem_sistema(f"Conexão encerrada após {minutos} minutos de inatividade "
                                   "para liberar o usuário no equipamento.")
            log.info(f"Sessão com {self.eq.ip} encerrada por inatividade.")
            self.encerrar(motivo="inatividade")
            self.app.atualizar_indicadores_abas()
        self.after(30000, self._verificar_inatividade)

    # ============================================================ exibição
    def _mensagem_sistema(self, texto):
        if not self.winfo_exists():
            return
        inicio = self.terminal_text.index("end-1c")
        self.terminal_text.insert(tk.END, f"\n[NetTerminal] {texto}\n")
        self.terminal_text.tag_add("sistema_tag", inicio, "end-1c")
        self.terminal_text.see(tk.END)

    def _exibir(self, texto):
        """Renderiza a saída do equipamento tratando os controles de terminal
        que Huawei/ZTE/Datacom usam (backspace, \\r para reescrever o prompt etc.)."""
        if not self.winfo_exists():
            return
        t = self.terminal_text
        texto = texto.replace("\r\n", "\n")
        texto = _CURSOR_ESQUERDA_RE.sub(lambda m: "\b" * (int(m.group(1)) if m.group(1) else 1), texto)
        texto = texto.replace("\x1b[1D \x1b[1D", "\b")
        texto = _ANSI_RE.sub("", texto)

        for parte in _CONTROLE_RE.split(texto):
            if not parte:
                continue
            if parte in ("\b", "\x7f"):
                if t.get("end-2c", "end-1c") != "\n":  # nunca apaga a quebra de linha
                    t.delete("end-2c", "end-1c")
            elif parte == "\r":
                t.delete("end-1c linestart", "end-1c")  # equipamento vai reescrever a linha
            elif parte in ("\x07", "\x00"):
                pass
            else:
                t.insert(tk.END, parte)

        self._limitar_scrollback()
        if not self.barra_busca.winfo_ismapped():
            t.see(tk.END)  # com a busca aberta, não "pula" para o fim a cada saída
        self._modo_senha = eh_prompt_de_senha(t.get("end-1c linestart", "end-1c"))

        if self._timer_destaque:
            self.after_cancel(self._timer_destaque)
        self._timer_destaque = self.after(200, self._destacar_sintaxe)

    def _limitar_scrollback(self):
        linhas = int(self.terminal_text.index("end-1c").split(".")[0])
        excesso = linhas - config.SCROLLBACK_LINHAS
        if excesso > 0:
            self.terminal_text.delete("1.0", f"{excesso + 1}.0")

    # ============================================================ entrada
    def _registrar_atividade(self, event=None):
        self.last_activity = time.time()

    def _ao_clicar(self, event):
        """Clicar no meio do texto antigo não move o cursor de digitação."""
        self._registrar_atividade()
        self.terminal_text.focus_set()
        self.terminal_text.after(10, lambda: self.terminal_text.mark_set("insert", "end-1c")
                                 if not self.terminal_text.tag_ranges("sel") else None)

    def _auto_copiar_selecao(self, event):
        """Copia automaticamente o texto selecionado (estilo MobaXterm/PuTTY)."""
        try:
            texto = self.terminal_text.get("sel.first", "sel.last")
        except tk.TclError:
            return
        if texto:
            self.clipboard_clear()
            self.clipboard_append(texto)

    def _ctrl_c(self, event):
        """Com seleção: copia. Sem seleção: envia Ctrl+C (interromper) ao equipamento."""
        if self.terminal_text.tag_ranges("sel"):
            self.clipboard_clear()
            self.clipboard_append(self.terminal_text.get("sel.first", "sel.last"))
            self.update()
            return "break"
        self._enviar(b"\x03")
        return "break"

    def _enviar(self, dados):
        if not self.conectado:
            return False
        try:
            self.sessao.enviar(dados)
            return True
        except Exception as e:
            log.warning(f"Falha ao enviar dados para {self.eq.ip}: {e}")
            return False

    def enviar_linhas(self, linhas, origem):
        """Envia comandos um por vez (com pausa), como um técnico digitando —
        evita estourar o buffer de CLIs mais lentas. Cada linha é auditada."""
        if not self.conectado or not linhas:
            return False
        self._registrar_atividade()

        def proxima(i=0):
            if i >= len(linhas) or not self.conectado:
                return
            if self._enviar(linhas[i] + "\n"):
                auditoria.log_comando(self.eq.ip, self.eq.nome, self.eq.protocolo, linhas[i], origem=origem)
            self.after(_INTERVALO_ENVIO_LINHAS_MS, proxima, i + 1)

        proxima()
        return True

    def _ao_digitar(self, event):
        if not self.conectado:
            return "break"
        self._registrar_atividade()

        # Trava de cursor: digitação sempre no final
        if event.keysym not in ("Left", "Right", "Up", "Down", "Prior", "Next", "Control_L", "Control_R"):
            if self.terminal_text.compare("insert", "<", "end-1c"):
                self.terminal_text.mark_set("insert", "end-1c")

        if event.keysym in _TECLAS_ESPECIAIS:
            if event.keysym == "BackSpace":
                self._buffer_comando = self._buffer_comando[:-1]
            self._enviar(_TECLAS_ESPECIAIS[event.keysym])
        elif event.keysym in ("Return", "KP_Enter"):
            if not self._modo_senha:
                auditoria.log_comando(self.eq.ip, self.eq.nome, self.eq.protocolo, self._buffer_comando)
            self._buffer_comando = ""
            self._modo_senha = False
            self._enviar(b"\n")
            self.terminal_text.insert(tk.END, "\n")
            self.terminal_text.see(tk.END)
        elif event.char:
            if event.char.isprintable() and not self._modo_senha:
                self._buffer_comando += event.char
            self._enviar(event.char.encode("utf-8"))
        return "break"

    def colar(self, event=None):
        if not self.conectado:
            return "break"
        self._registrar_atividade()
        try:
            texto = self.clipboard_get()
        except tk.TclError:
            return "break"  # área de transferência vazia
        if not texto:
            return "break"

        linhas = [l for l in texto.replace("\r\n", "\n").split("\n") if l.strip()]
        if config.CONFIRMAR_COLAGEM_MULTILINHA and len(linhas) > 1:
            previa = "\n".join(l[:80] for l in linhas[:8])
            if len(linhas) > 8:
                previa += f"\n... (+{len(linhas) - 8} linhas)"
            if not msgbox(self.app, "askyesno", "Confirmar colagem",
                          f"Você vai enviar {len(linhas)} linhas para {self.eq.rotulo}.\n"
                          f"Cada linha será executada como comando:\n\n{previa}\n\nEnviar?"):
                return "break"

        if self._enviar(texto.encode("utf-8")) and not self._modo_senha:
            auditoria.log_comando(self.eq.ip, self.eq.nome, self.eq.protocolo, texto, origem="COLADO")
        return "break"

    # ============================================================== macros
    def atualizar_marcas(self):
        marcas = sorted({m.marca for m in self.db.listar_macros()})
        if not marcas:
            return
        self.combo_marca.configure(values=marcas)
        self.combo_marca.set(self.eq.marca if self.eq.marca in marcas else marcas[0])
        self.carregar_botoes_macro(self.combo_marca.get())

    def carregar_botoes_macro(self, marca):
        for widget in self.macro_buttons_frame.winfo_children():
            widget.destroy()
        cores = self.app.cores
        self._botoes_macro = []
        for m in self.db.listar_macros():
            if m.marca == marca:
                botao = ctk.CTkButton(self.macro_buttons_frame, text=m.nome, width=40, height=26,
                                      fg_color=cores["btn_bg"], hover_color=cores["btn_hover"],
                                      font=ctk.CTkFont(size=12),
                                      command=lambda cmd=m.comando: self._processar_macro(cmd))
                self._botoes_macro.append((botao, m))
        self._btn_mais_macros = ctk.CTkButton(self.macro_buttons_frame, text="▾", width=50, height=26,
                                              fg_color="transparent", border_width=1, border_color="#555555",
                                              font=ctk.CTkFont(size=12), command=self._menu_macros_ocultas)
        self._agendar_distribuir_macros()

    def _agendar_distribuir_macros(self, event=None):
        if self._timer_macros:
            self.after_cancel(self._timer_macros)
        self._timer_macros = self.after(60, self._distribuir_macros)

    def _distribuir_macros(self):
        """Mostra as macros que cabem na largura; o resto vai para o botão "+N ▾".
        Recalculado sempre que o painel muda de tamanho (tela dividida, janela)."""
        self._timer_macros = None
        if not self.winfo_exists():
            return
        self._ajustar_modo_compacto()
        if not self._botoes_macro:
            return
        disponivel = self.macro_buttons_frame.winfo_width()
        if disponivel <= 1:
            return
        for botao, _ in self._botoes_macro:
            botao.pack_forget()
        self._btn_mais_macros.pack_forget()
        largura_mais = self._btn_mais_macros.winfo_reqwidth() + 8
        usado, self._macros_ocultas = 0, []
        for indice, (botao, macro) in enumerate(self._botoes_macro):
            largura = botao.winfo_reqwidth() + 6
            sobram = len(self._botoes_macro) - indice - 1
            limite = disponivel - (largura_mais if sobram else 0)
            if not self._macros_ocultas and usado + largura <= limite:
                botao.pack(side="left", padx=3, pady=2)
                usado += largura
            else:
                self._macros_ocultas.append(macro)
        if self._macros_ocultas:
            if usado:
                texto = f"+{len(self._macros_ocultas)} ▾"
            elif disponivel >= 100:
                texto = f"Macros ({len(self._macros_ocultas)}) ▾"
            else:
                texto = "Macros ▾" if disponivel >= 76 else "▾"
            self._btn_mais_macros.configure(text=texto, width=30)
            self._btn_mais_macros.pack(side="left", padx=3, pady=2)

    def _ajustar_modo_compacto(self):
        """Painéis estreitos (tela dividida): botões de ação encolhem para sobrar
        espaço para as macros."""
        compacto = self.winfo_width() < 760
        if compacto == self._compacto:
            return
        self._compacto = compacto
        self.btn_reconectar.configure(text="↻" if compacto else "↻ Reconectar", width=30 if compacto else 96)
        self._btn_tracert.configure(text="Trace" if compacto else "Tracert", width=46 if compacto else 58)
        self.combo_marca.configure(width=96 if compacto else 118)

    def _menu_macros_ocultas(self):
        menu = tk.Menu(self, tearoff=0)
        for macro in self._macros_ocultas:
            menu.add_command(label=macro.nome, command=lambda cmd=macro.comando: self._processar_macro(cmd))
        botao = self._btn_mais_macros
        menu.tk_popup(botao.winfo_rootx(), botao.winfo_rooty() + botao.winfo_height())

    def _processar_macro(self, comando):
        if not self.conectado:
            return
        self._registrar_atividade()
        variaveis = list(dict.fromkeys(re.findall(r"\[(.*?)\]", comando)))  # sem duplicadas, na ordem
        if variaveis:
            self._mostrar_painel_variaveis(comando, variaveis)
        else:
            self._executar_macro(comando)

    def _mostrar_painel_variaveis(self, comando, variaveis):
        """Variável [NOME] vira caixa de texto; [NOME|op1,op2] vira lista de opções."""
        for widget in self.dynamic_bar.winfo_children():
            widget.destroy()
        self.dynamic_bar.pack(fill="x", padx=5, pady=(0, 5), before=self.terminal_text)
        campos, primeiro = {}, None
        enviar = lambda e=None: self._montar_e_enviar_macro(comando, campos)

        ctk.CTkLabel(self.dynamic_bar, text="Preencha: ", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        for var in variaveis:
            if "|" in var:
                rotulo, opcoes = var.split("|", 1)
                opcoes = opcoes.split(",")
                ctk.CTkLabel(self.dynamic_bar, text=f"{rotulo}:").pack(side="left", padx=(5, 2))
                widget = ctk.CTkComboBox(self.dynamic_bar, values=opcoes, width=140, height=24)
                if opcoes:
                    widget.set(opcoes[0])
            else:
                ctk.CTkLabel(self.dynamic_bar, text=f"{var}:").pack(side="left", padx=(5, 2))
                widget = ctk.CTkEntry(self.dynamic_bar, width=80, height=24)
                widget.bind("<Return>", enviar)
                primeiro = primeiro or widget
            widget.pack(side="left", padx=(0, 10))
            campos[var] = widget

        ctk.CTkButton(self.dynamic_bar, text="Enviar (Enter)", width=80, height=24, fg_color="#006400",
                      hover_color="green", command=enviar).pack(side="left", padx=5)
        ctk.CTkButton(self.dynamic_bar, text="Cancelar", width=70, height=24, fg_color="#8B0000",
                      hover_color="red", command=self.dynamic_bar.pack_forget).pack(side="left", padx=5)
        if primeiro:
            primeiro.focus_set()

    def _montar_e_enviar_macro(self, comando, campos):
        for var, widget in campos.items():
            # Valor de uma linha só: impede injetar comandos extras via quebra de linha
            valor = widget.get().replace("\r", "").replace("\n", "")
            comando = comando.replace(f"[{var}]", valor)
        self.dynamic_bar.pack_forget()
        self.terminal_text.focus_set()
        self._executar_macro(comando)

    def _executar_macro(self, comando):
        if self._enviar(comando + "\n"):
            auditoria.log_comando(self.eq.ip, self.eq.nome, self.eq.protocolo, comando, origem="MACRO")
