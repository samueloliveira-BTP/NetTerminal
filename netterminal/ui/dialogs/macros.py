"""Cadastro de macros (comandos prontos por marca).

Sintaxe de variáveis no comando:
    [VLAN]              -> caixa de texto preenchida antes de enviar
    [MODO|trunk,access] -> lista de opções
"""
import logging
from tkinter import filedialog, ttk

import customtkinter as ctk

from netterminal.services import transferencia
from netterminal.ui.dialogs.admin import exigir_permissao
from netterminal.ui.utils import msgbox, nova_janela

log = logging.getLogger(__name__)


def abrir(app):
    if not exigir_permissao(app, "macros"):
        return
    top = nova_janela(app, "Macros", "680x700")
    macros_por_id = {}
    selecionada = {"id": None}

    card = ctk.CTkFrame(top, corner_radius=10)
    card.pack(fill="both", expand=True, padx=10, pady=10)

    form = ctk.CTkFrame(card, fg_color="transparent")
    form.pack(pady=(15, 5), padx=20, fill="x")
    linha1 = ctk.CTkFrame(form, fg_color="transparent")
    linha1.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(linha1, text="Marca:").pack(side="left", padx=(0, 10))
    e_marca = ctk.CTkEntry(linha1, width=160)
    e_marca.pack(side="left", padx=(0, 20))
    ctk.CTkLabel(linha1, text="Rótulo:").pack(side="left", padx=(0, 10))
    e_rotulo = ctk.CTkEntry(linha1)
    e_rotulo.pack(side="left", fill="x", expand=True)

    linha2 = ctk.CTkFrame(form, fg_color="transparent")
    linha2.pack(fill="x")
    ctk.CTkLabel(linha2, text="Comando\nScript:", justify="right").pack(side="left", anchor="n", padx=(0, 10))
    e_comando = ctk.CTkTextbox(linha2, height=90, corner_radius=6)
    e_comando.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(form, text="Variáveis: [NOME] vira caixa de texto; [NOME|op1,op2] vira lista de opções.",
                 text_color="gray", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 0))

    tabela_frame = ctk.CTkFrame(card)
    tabela = ttk.Treeview(tabela_frame, columns=("n", "marca", "rotulo", "comando"), show="headings",
                          style="Macros.Treeview")
    for col, titulo, largura, ancora in (("n", "#", 40, "center"), ("marca", "Marca", 110, "center"),
                                         ("rotulo", "Rótulo", 170, "w"), ("comando", "Prévia do Script", 260, "w")):
        tabela.heading(col, text=titulo)
        tabela.column(col, width=largura, anchor=ancora)

    def limpar():
        selecionada["id"] = None
        e_marca.delete(0, "end")
        e_rotulo.delete(0, "end")
        e_comando.delete("1.0", "end")
        tabela.selection_remove(*tabela.selection())

    def recarregar():
        tabela.delete(*tabela.get_children())
        macros_por_id.clear()
        for n, m in enumerate(sorted(app.db.listar_macros(), key=lambda m: m.id), start=1):
            macros_por_id[str(m.id)] = m
            previa = m.comando.replace("\n", " ↵ ").replace("\r", "")
            tabela.insert("", "end", iid=str(m.id), values=(n, m.marca, m.nome, previa))

    def ao_selecionar(event):
        sel = tabela.selection()
        if not sel:
            return
        m = macros_por_id[sel[0]]
        selecionada["id"] = m.id
        e_marca.delete(0, "end"); e_marca.insert(0, m.marca)
        e_rotulo.delete(0, "end"); e_rotulo.insert(0, m.nome)
        e_comando.delete("1.0", "end"); e_comando.insert("1.0", m.comando)

    tabela.bind("<<TreeviewSelect>>", ao_selecionar)

    def campos():
        marca, rotulo = e_marca.get().strip(), e_rotulo.get().strip()
        comando = e_comando.get("1.0", "end-1c").strip()
        if not marca or not rotulo or not comando:
            msgbox(app, "warning", "Aviso", "Preencha Marca, Rótulo e Comando!", parent=top)
            return None
        return marca, rotulo, comando

    def concluir(mensagem):
        recarregar()
        limpar()
        app.atualizar_macros_nas_abas()
        msgbox(app, "info", "Sucesso", mensagem, parent=top)

    def adicionar():
        valores = campos()
        if valores:
            app.db.adicionar_macro(*valores)
            concluir("Macro adicionada!")

    def salvar_edicao():
        if selecionada["id"] is None:
            msgbox(app, "warning", "Aviso", "Selecione uma macro na tabela para editar!", parent=top)
            return
        valores = campos()
        if valores:
            app.db.atualizar_macro(selecionada["id"], *valores)
            concluir("Edição salva!")

    def excluir():
        if selecionada["id"] is None:
            msgbox(app, "warning", "Aviso", "Selecione uma macro na tabela para excluir!", parent=top)
            return
        if msgbox(app, "askyesno", "Confirmar", "Excluir a macro selecionada?", parent=top):
            app.db.excluir_macro(selecionada["id"])
            concluir("Macro excluída!")

    def exportar():
        caminho = filedialog.asksaveasfilename(parent=top, title="Exportar macros", defaultextension=".csv",
                                               filetypes=[("CSV", "*.csv")], initialfile="macros_export.csv")
        if not caminho:
            return
        try:
            n = transferencia.exportar_macros(caminho, app.db.listar_macros())
            msgbox(app, "info", "Exportar", f"{n} macro(s) exportada(s) com sucesso!", parent=top)
        except Exception as e:
            log.error(f"Falha ao exportar macros: {e}")
            msgbox(app, "error", "Erro", "Não foi possível exportar (detalhes no app.log).", parent=top)

    def importar():
        caminho = filedialog.askopenfilename(parent=top, title="Importar macros",
                                             filetypes=[("CSV", "*.csv"), ("Todos os arquivos", "*.*")])
        if not caminho:
            return
        try:
            res = transferencia.importar_macros(caminho, app.db)
        except Exception as e:
            log.error(f"Falha ao importar macros de {caminho}: {e}")
            msgbox(app, "error", "Erro", f"Não foi possível importar: {e}", parent=top)
            return
        recarregar()
        app.atualizar_macros_nas_abas()
        msgbox(app, "info", "Importar", res.resumo("marca+nome já existiam"), parent=top)

    botoes = ctk.CTkFrame(card, fg_color="transparent")
    botoes.pack(pady=10)
    estilo = dict(width=120, height=32, fg_color="transparent", border_width=1, border_color="#555555", text_color="#cccccc")
    ctk.CTkButton(botoes, text="Adicionar", hover_color="#1f538d", command=adicionar, **estilo).pack(side="left", padx=8)
    ctk.CTkButton(botoes, text="Salvar Edição", hover_color="#8b5a2b", command=salvar_edicao, **estilo).pack(side="left", padx=8)
    ctk.CTkButton(botoes, text="Excluir", hover_color="#8b0000", command=excluir, **estilo).pack(side="left", padx=8)
    ctk.CTkButton(botoes, text="Limpar", hover_color="#333333", command=limpar, **estilo).pack(side="left", padx=8)
    botoes2 = ctk.CTkFrame(card, fg_color="transparent")
    botoes2.pack(pady=(0, 5))
    estilo["width"] = 150
    ctk.CTkButton(botoes2, text="⬇️ Exportar Macros", hover_color="#1f538d", command=exportar, **estilo).pack(side="left", padx=8)
    ctk.CTkButton(botoes2, text="⬆️ Importar Macros", hover_color="#1f538d", command=importar, **estilo).pack(side="left", padx=8)

    tabela_frame.pack(pady=(5, 15), padx=20, fill="both", expand=True)
    tabela.pack(fill="both", expand=True, side="left")
    barra = ttk.Scrollbar(tabela_frame, orient="vertical", command=tabela.yview)
    tabela.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y")

    recarregar()
