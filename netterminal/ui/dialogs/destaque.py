"""Realce de sintaxe: o técnico define palavras, nomes ou regex e a cor de cada um."""
import tkinter as tk
from tkinter import colorchooser, ttk

import customtkinter as ctk

from netterminal.core import destaque
from netterminal.ui.utils import msgbox, nova_janela

_AMOSTRA = (
    "OLT# show interface gpon 1/1/1 onu\n"
    "ID  Serial         Status   Name            IP\n"
    "1   DACM00000001   up       CLIENTE_EXEMPLO 192.0.2.10\n"
    "2   DACM00000002   down     LOJA_CENTRO     192.0.2.11\n"
    "3   HWTC00000003   LOS      dying-gasp      unassigned\n"
    "MAC: 00:11:22:33:44:55  /  0011-2233-4455\n"
)
_ROTULO_TIPO = destaque.TIPOS
_TIPO_DO_ROTULO = {v: k for k, v in destaque.TIPOS.items()}


def abrir(app):
    top = nova_janela(app, "Realce de Sintaxe", "980x700")
    selecionada = {"id": None}

    topo = ctk.CTkFrame(top, fg_color="transparent")
    topo.pack(fill="x", padx=12, pady=(12, 4))
    var_ligado = ctk.StringVar(value=app.db.get_config("syntax_highlighting", "True"))

    def alternar_global():
        app.db.set_config("syntax_highlighting", var_ligado.get())
        app.recarregar_regras_destaque()

    ctk.CTkCheckBox(topo, text="Realce automático ligado", variable=var_ligado, onvalue="True", offvalue="False",
                    command=alternar_global).pack(side="left")
    ctk.CTkLabel(topo, text="As regras são aplicadas de cima para baixo; a de baixo vence quando duas se sobrepõem.",
                 text_color="gray").pack(side="left", padx=12)

    corpo = ctk.CTkFrame(top, fg_color="transparent")
    corpo.pack(expand=True, fill="both", padx=12, pady=6)

    # --- lista de regras ------------------------------------------------------
    esquerda = ctk.CTkFrame(corpo)
    esquerda.pack(side="left", expand=True, fill="both", padx=(0, 8))
    tabela = ttk.Treeview(esquerda, columns=("ativo", "nome", "tipo", "padrao"), show="headings", height=14)
    for col, titulo, largura in (("ativo", "Ativa", 50), ("nome", "Nome", 170), ("tipo", "Tipo", 120), ("padrao", "Padrão", 220)):
        tabela.heading(col, text=titulo)
        tabela.column(col, width=largura, anchor="w")
    tabela.pack(expand=True, fill="both", padx=6, pady=6)
    ordem_frame = ctk.CTkFrame(esquerda, fg_color="transparent")
    ordem_frame.pack(fill="x", padx=6, pady=(0, 6))

    # --- formulário -------------------------------------------------------------
    form = ctk.CTkFrame(corpo, width=340)
    form.pack(side="left", fill="y")
    ctk.CTkLabel(form, text="Regra", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
    ctk.CTkLabel(form, text="Nome (só para você identificar):").pack(anchor="w", padx=12)
    e_nome = ctk.CTkEntry(form, width=300)
    e_nome.pack(padx=12)
    ctk.CTkLabel(form, text="Tipo:").pack(anchor="w", padx=12, pady=(8, 0))
    combo_tipo = ctk.CTkComboBox(form, values=list(_ROTULO_TIPO.values()), width=300, state="readonly")
    combo_tipo.set(_ROTULO_TIPO["palavra"])
    combo_tipo.pack(padx=12)
    ctk.CTkLabel(form, text="Texto / padrão a destacar:").pack(anchor="w", padx=12, pady=(8, 0))
    e_padrao = ctk.CTkEntry(form, width=300, placeholder_text="ex.: LOS, dying-gasp, nome do cliente")
    e_padrao.pack(padx=12)
    ctk.CTkLabel(form, text="Cor:").pack(anchor="w", padx=12, pady=(8, 0))
    linha_cor = ctk.CTkFrame(form, fg_color="transparent")
    linha_cor.pack(fill="x", padx=12)
    e_cor = ctk.CTkEntry(linha_cor, width=110)
    e_cor.insert(0, "#ff5555")
    e_cor.pack(side="left")
    amostra_cor = tk.Label(linha_cor, text="  Aa  ", bg=app.cores["term_bg"], fg="#ff5555", font=("Consolas", 12, "bold"))
    amostra_cor.pack(side="left", padx=8)

    def atualizar_amostra(*_):
        cor = e_cor.get().strip()
        if destaque._COR_RE.match(cor):
            amostra_cor.configure(fg=cor)

    def escolher_cor():
        _, cor = colorchooser.askcolor(color=e_cor.get().strip() or "#ffffff", parent=top, title="Escolha a cor")
        if cor:
            e_cor.delete(0, "end")
            e_cor.insert(0, cor.lower())
            atualizar_amostra()

    e_cor.bind("<KeyRelease>", atualizar_amostra)
    ctk.CTkButton(linha_cor, text="🎨 Escolher...", width=110, command=escolher_cor).pack(side="left")
    var_negrito = ctk.BooleanVar(value=False)
    var_ativo = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(form, text="Negrito", variable=var_negrito).pack(anchor="w", padx=12, pady=(10, 2))
    ctk.CTkCheckBox(form, text="Ativa", variable=var_ativo).pack(anchor="w", padx=12, pady=2)

    botoes = ctk.CTkFrame(form, fg_color="transparent")
    botoes.pack(fill="x", padx=12, pady=12)

    # --- prévia -------------------------------------------------------------------
    ctk.CTkLabel(top, text="Prévia (edite o texto para testar com saídas reais):").pack(anchor="w", padx=12)
    previa = tk.Text(top, height=8, bg=app.cores["term_bg"], fg=app.cores["term_fg"], font=("Consolas", 12),
                     insertbackground=app.cores["term_fg"], bd=0)
    previa.pack(fill="x", padx=12, pady=(2, 12))
    previa.insert("1.0", _AMOSTRA)

    def regra_do_formulario():
        tipo = _TIPO_DO_ROTULO[combo_tipo.get()]
        padrao, cor = e_padrao.get().strip(), e_cor.get().strip().lower()
        destaque.validar(padrao, tipo, cor)
        return destaque.RegraDestaque(selecionada["id"], e_nome.get().strip() or padrao, padrao, tipo, cor,
                                      var_negrito.get(), var_ativo.get())

    def pintar_previa(regra_extra=None):
        for tag in previa.tag_names():
            if tag.startswith("regra_") or tag == "rascunho":
                previa.tag_remove(tag, "1.0", "end")
        regras = [r for r in app.db.listar_regras_destaque() if r.ativo and r.id != selecionada["id"]]
        texto = previa.get("1.0", "end-1c")
        itens = [(r, r.tag) for r in regras] + ([(regra_extra, "rascunho")] if regra_extra else [])
        for regra, tag in itens:
            previa.tag_configure(tag, foreground=regra.cor, font=("Consolas", 12, "bold") if regra.negrito else "")
            for m in destaque.compilar(regra.padrao, regra.tipo).finditer(texto):
                if m.end() > m.start():
                    previa.tag_add(tag, f"1.0 + {m.start()} chars", f"1.0 + {m.end()} chars")

    def recarregar(manter=None):
        tabela.delete(*tabela.get_children())
        for r in app.db.listar_regras_destaque():
            tag = f"cor_{r.id}"
            tabela.tag_configure(tag, foreground=r.cor)
            tabela.insert("", "end", iid=str(r.id), tags=(tag,),
                          values=("✔" if r.ativo else "✖", r.nome, _ROTULO_TIPO.get(r.tipo, r.tipo), r.padrao))
        if manter and tabela.exists(str(manter)):
            tabela.selection_set(str(manter))
        pintar_previa()

    def ao_selecionar(event=None):
        sel = tabela.selection()
        if not sel:
            return
        regra = next((r for r in app.db.listar_regras_destaque() if str(r.id) == sel[0]), None)
        if not regra:
            return
        selecionada["id"] = regra.id
        for entrada, valor in ((e_nome, regra.nome), (e_padrao, regra.padrao), (e_cor, regra.cor)):
            entrada.delete(0, "end")
            entrada.insert(0, valor)
        combo_tipo.set(_ROTULO_TIPO.get(regra.tipo, _ROTULO_TIPO["palavra"]))
        var_negrito.set(regra.negrito)
        var_ativo.set(regra.ativo)
        atualizar_amostra()

    def nova():
        selecionada["id"] = None
        tabela.selection_remove(*tabela.selection())
        for entrada in (e_nome, e_padrao):
            entrada.delete(0, "end")
        var_negrito.set(False)
        var_ativo.set(True)
        e_padrao.focus_set()

    def testar():
        try:
            pintar_previa(regra_do_formulario())
        except ValueError as e:
            msgbox(app, "warning", "Regra inválida", str(e), parent=top)

    def salvar():
        try:
            regra = regra_do_formulario()
        except ValueError as e:
            msgbox(app, "warning", "Regra inválida", str(e), parent=top)
            return
        novo_id = app.db.salvar_regra_destaque(regra)
        selecionada["id"] = novo_id
        app.recarregar_regras_destaque()
        recarregar(manter=novo_id)

    def excluir():
        if selecionada["id"] is None:
            return
        if msgbox(app, "askyesno", "Excluir", "Excluir a regra selecionada?", parent=top):
            app.db.excluir_regra_destaque(selecionada["id"])
            app.recarregar_regras_destaque()
            nova()
            recarregar()

    def mover(direcao):
        ids = [int(i) for i in tabela.get_children()]
        if selecionada["id"] not in ids:
            return
        i = ids.index(selecionada["id"])
        j = i + direcao
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            app.db.reordenar_regras_destaque(ids)
            app.recarregar_regras_destaque()
            recarregar(manter=selecionada["id"])

    for texto, comando, cor in (("➕ Nova", nova, None), ("💾 Salvar", salvar, app.cores["btn_bg"]),
                                ("👁 Testar", testar, None), ("🗑 Excluir", excluir, "#8B0000")):
        ctk.CTkButton(botoes, text=texto, width=70, command=comando,
                      **({"fg_color": cor} if cor else {})).pack(side="left", padx=2)
    ctk.CTkButton(ordem_frame, text="▲ Subir", width=90, command=lambda: mover(-1)).pack(side="left", padx=2)
    ctk.CTkButton(ordem_frame, text="▼ Descer", width=90, command=lambda: mover(1)).pack(side="left", padx=2)

    tabela.bind("<<TreeviewSelect>>", ao_selecionar)
    previa.bind("<KeyRelease>", lambda e: pintar_previa())
    recarregar()
