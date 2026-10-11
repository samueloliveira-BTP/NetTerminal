"""Busca de ONU por serial ou descrição em várias OLTs ao mesmo tempo.

Conecta em paralelo (no máximo 8 OLTs por vez), executa o modelo de busca da
marca de cada OLT e mostra onde o termo apareceu. Só executa comandos de
consulta definidos em Configurações > Modelos de ONU, e cada comando
executado fica no histórico com a marca [BUSCA].
"""
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

import customtkinter as ctk

from netterminal.core import onu, saida
from netterminal.net import executor
from netterminal.ui.tema import COR_DESCONHECIDO, COR_OFFLINE, COR_ONLINE
from netterminal.ui.utils import msgbox, nova_janela

log = logging.getLogger(__name__)
_PARALELO = 8
_ESCOPO_TODAS = "Todas as OLTs com modelo"
_ESCOPO_SELECIONADAS = "Selecionadas na árvore"


def abrir(app):
    top = nova_janela(app, "Buscar ONU em todas as OLTs", "1050x680")
    estado = {"cancelar": threading.Event(), "fila": queue.Queue(), "resultados": {}, "total": 0, "feitos": 0,
              "rodando": False}

    linha1 = ctk.CTkFrame(top, fg_color="transparent")
    linha1.pack(fill="x", padx=12, pady=(12, 4))
    ctk.CTkLabel(linha1, text="Procurar:").pack(side="left")
    e_termo = ctk.CTkEntry(linha1, width=230, placeholder_text="serial ou descrição")
    e_termo.pack(side="left", padx=6)
    var_tipo = ctk.StringVar(value="buscar_serial")
    ctk.CTkRadioButton(linha1, text="Serial", variable=var_tipo, value="buscar_serial").pack(side="left", padx=6)
    ctk.CTkRadioButton(linha1, text="Descrição/nome", variable=var_tipo, value="buscar_descricao").pack(side="left", padx=6)

    grupos = sorted({e.grupo for e in app.db.listar_equipamentos()})
    marcas = sorted(app.db.listar_modelos_onu().keys())
    n_sel = len(app.equipamentos_selecionados())
    escopos = [_ESCOPO_TODAS] + [f"Marca: {m}" for m in marcas] + [f"Grupo: {g}" for g in grupos]
    if n_sel:
        escopos.insert(1, f"{_ESCOPO_SELECIONADAS} ({n_sel})")
    ctk.CTkLabel(linha1, text="Onde:").pack(side="left", padx=(16, 4))
    combo_escopo = ctk.CTkComboBox(linha1, values=escopos, width=260, state="readonly")
    combo_escopo.set(escopos[0])
    combo_escopo.pack(side="left")

    linha2 = ctk.CTkFrame(top, fg_color="transparent")
    linha2.pack(fill="x", padx=12, pady=4)
    btn_buscar = ctk.CTkButton(linha2, text="🔎 Buscar", width=110)
    btn_buscar.pack(side="left")
    btn_cancelar = ctk.CTkButton(linha2, text="■ Cancelar", width=100, fg_color="#8B0000", hover_color="red",
                                 state="disabled", command=lambda: estado["cancelar"].set())
    btn_cancelar.pack(side="left", padx=8)
    var_so_achados = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(linha2, text="Mostrar só onde encontrou", variable=var_so_achados,
                    command=lambda: redesenhar()).pack(side="left", padx=8)
    barra = ctk.CTkProgressBar(linha2, width=220)
    barra.set(0)
    barra.pack(side="left", padx=8)
    lbl_progresso = ctk.CTkLabel(linha2, text="")
    lbl_progresso.pack(side="left")

    painel = ctk.CTkFrame(top, fg_color="transparent")
    painel.pack(expand=True, fill="both", padx=12, pady=6)
    colunas = (("olt", 200, "OLT"), ("ip", 120, "IP"), ("marca", 90, "Marca"),
               ("resultado", 130, "Resultado"), ("trecho", 460, "Trecho encontrado"))
    tabela = ttk.Treeview(painel, columns=[c[0] for c in colunas], show="headings", height=12)
    for chave, largura, titulo in colunas:
        tabela.heading(chave, text=titulo)
        tabela.column(chave, width=largura, anchor="w")
    tabela.tag_configure("achou", foreground=COR_ONLINE)
    tabela.tag_configure("erro", foreground=COR_OFFLINE)
    tabela.tag_configure("nao", foreground=COR_DESCONHECIDO)
    tabela.pack(fill="both", expand=True)
    ctk.CTkLabel(painel, text="Saída completa da OLT selecionada (duplo clique abre o terminal):",
                 text_color="gray").pack(anchor="w", pady=(6, 0))
    detalhe = ctk.CTkTextbox(painel, height=170, font=("Consolas", 11))
    detalhe.pack(fill="x")

    def equipamentos_do_escopo():
        escopo = combo_escopo.get()
        todos = app.db.listar_equipamentos()
        if escopo.startswith(_ESCOPO_SELECIONADAS):
            return app.equipamentos_selecionados()
        if escopo.startswith("Marca: "):
            return [e for e in todos if e.marca == escopo[len("Marca: "):]]
        if escopo.startswith("Grupo: "):
            return [e for e in todos if e.grupo == escopo[len("Grupo: "):]]
        return [e for e in todos if e.marca in marcas]

    def redesenhar():
        tabela.delete(*tabela.get_children())
        for chave, (eq, status, trecho, _) in estado["resultados"].items():
            if var_so_achados.get() and status != "Encontrado":
                continue
            tag = "achou" if status == "Encontrado" else "nao" if status == "Não encontrado" else "erro"
            tabela.insert("", "end", iid=chave, values=(eq.nome, eq.ip, eq.marca, status, trecho), tags=(tag,))

    def ao_selecionar(event=None):
        sel = tabela.selection()
        if sel:
            detalhe.delete("1.0", "end")
            detalhe.insert("1.0", estado["resultados"][sel[0]][3] or "(sem saída)")

    def ao_duplo_clique(event=None):
        sel = tabela.selection()
        if sel:
            eq = estado["resultados"][sel[0]][0]
            app.abrir_aba(eq, eq.rotulo)

    tabela.bind("<<TreeviewSelect>>", ao_selecionar)
    tabela.bind("<Double-1>", ao_duplo_clique)

    def buscar():
        termo = e_termo.get().strip()
        tipo = var_tipo.get()
        try:
            onu.validar_valor(onu.VAR_TERMO[tipo], termo)
        except ValueError as e:
            msgbox(app, "warning", "Termo inválido", str(e), parent=top)
            return
        usuario = app.db.get_config("default_user", "")
        senha = app.db.get_config_secreto("default_pass")
        if not usuario:
            msgbox(app, "warning", "Credencial", "Configure a credencial global antes de buscar.", parent=top)
            return
        modelos = app.db.listar_modelos_onu()
        alvos = equipamentos_do_escopo()
        executaveis = [e for e in alvos if modelos.get(e.marca, {}).get(tipo) and not e.login_manual]
        if not executaveis:
            msgbox(app, "info", "Nada a buscar", "Nenhuma OLT do escopo tem modelo de busca configurado.", parent=top)
            return
        if not msgbox(app, "askyesno", "Confirmar busca",
                      f"Conectar em {len(executaveis)} OLT(s) e executar o comando de busca de cada marca?\n"
                      f"(Somente consulta. Até {_PARALELO} conexões simultâneas.)", parent=top):
            return

        estado.update(resultados={}, total=len(alvos), feitos=0, rodando=True)
        estado["cancelar"].clear()
        for eq in alvos:  # quem não pode ser consultado já entra com o motivo
            if eq.login_manual:
                estado["resultados"][str(eq.id)] = (eq, "Login manual", "", "")
                estado["feitos"] += 1
            elif not modelos.get(eq.marca, {}).get(tipo):
                estado["resultados"][str(eq.id)] = (eq, "Sem modelo", f"Configure o modelo da marca {eq.marca}", "")
                estado["feitos"] += 1
        redesenhar()
        btn_buscar.configure(state="disabled")
        btn_cancelar.configure(state="normal")
        log.info(f"Busca global de ONU ({tipo}) em {len(executaveis)} OLT(s).")

        def tarefa(eq):
            comandos = onu.preencher_termo(modelos[eq.marca][tipo], tipo, termo)
            res = executor.executar(eq, comandos, usuario, senha, app.hostkeys, cancelado=estado["cancelar"])
            if not res.ok:
                estado["fila"].put((eq, res.erro or "Erro", "", res.saida))
                return
            achadas = saida.linhas_com_termo(res.saida, termo, comandos)
            status = "Encontrado" if achadas else "Não encontrado"
            estado["fila"].put((eq, status, " | ".join(achadas)[:300], res.saida))

        def trabalhador():
            with ThreadPoolExecutor(max_workers=_PARALELO) as pool:
                list(pool.map(tarefa, executaveis))
            estado["fila"].put(None)

        threading.Thread(target=trabalhador, daemon=True, name="busca-onu").start()

    def consumir():
        if not top.winfo_exists():
            estado["cancelar"].set()
            return
        mudou = False
        try:
            while True:
                item = estado["fila"].get_nowait()
                if item is None:
                    estado["rodando"] = False
                    btn_buscar.configure(state="normal")
                    btn_cancelar.configure(state="disabled")
                    achados = sum(1 for r in estado["resultados"].values() if r[1] == "Encontrado")
                    lbl_progresso.configure(text=f"Concluído: encontrado em {achados} OLT(s).")
                    continue
                eq, status, trecho, texto = item
                estado["resultados"][str(eq.id)] = (eq, status, trecho, texto)
                estado["feitos"] += 1
                mudou = True
        except queue.Empty:
            pass
        if mudou:
            redesenhar()
            if estado["rodando"]:
                barra.set(estado["feitos"] / max(1, estado["total"]))
                lbl_progresso.configure(text=f"{estado['feitos']} de {estado['total']}")
        top.after(150, consumir)

    btn_buscar.configure(command=buscar)
    e_termo.bind("<Return>", lambda e: buscar())
    top.protocol("WM_DELETE_WINDOW", lambda: (estado["cancelar"].set(), top.destroy()))
    top.after(150, e_termo.focus_set)
    consumir()
