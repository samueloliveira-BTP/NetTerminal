"""Histórico de comandos (auditoria) com filtros e exportação."""
import logging
import re
from tkinter import filedialog

import customtkinter as ctk

from netterminal.services import auditoria, transferencia
from netterminal.ui.utils import msgbox, nova_janela

log = logging.getLogger(__name__)
_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_LINHAS_TELA = 500


def abrir(app):
    top = nova_janela(app, "Histórico de Comandos", "960x560")

    filtros = ctk.CTkFrame(top, fg_color="transparent")
    filtros.pack(fill="x", padx=10, pady=(10, 0))
    ctk.CTkLabel(filtros, text="Equipamento (nome ou IP):").pack(side="left", padx=(0, 5))
    e_termo = ctk.CTkEntry(filtros, width=150, placeholder_text="opcional")
    e_termo.pack(side="left", padx=(0, 15))
    ctk.CTkLabel(filtros, text="De:").pack(side="left", padx=(0, 5))
    e_ini = ctk.CTkEntry(filtros, width=105, placeholder_text="AAAA-MM-DD")
    e_ini.pack(side="left", padx=(0, 15))
    ctk.CTkLabel(filtros, text="Até:").pack(side="left", padx=(0, 5))
    e_fim = ctk.CTkEntry(filtros, width=105, placeholder_text="AAAA-MM-DD")
    e_fim.pack(side="left", padx=(0, 15))

    texto = ctk.CTkTextbox(top, font=("Consolas", 12))
    texto.pack(expand=True, fill="both", padx=10, pady=10)

    def filtrados():
        ini, fim = e_ini.get().strip(), e_fim.get().strip()
        for valor in (ini, fim):
            if valor and not _DATA_RE.match(valor):
                msgbox(app, "warning", "Data inválida", f"Use o formato AAAA-MM-DD (recebido: {valor}).", parent=top)
                return None
        return auditoria.ler_historico(e_termo.get(), ini, fim)

    def carregar():
        resultado = filtrados()
        if resultado is None:
            return
        texto.configure(state="normal")
        texto.delete("1.0", "end")
        if resultado:
            conteudo = "\n".join(" | ".join(r) for r in resultado[-_MAX_LINHAS_TELA:])
            if len(resultado) > _MAX_LINHAS_TELA:
                conteudo = f"(mostrando os últimos {_MAX_LINHAS_TELA} de {len(resultado)}; exporte para ver tudo)\n" + conteudo
        else:
            conteudo = "Nenhum comando encontrado (arquivo vazio ou filtro sem resultado)."
        texto.insert("1.0", conteudo)
        texto.configure(state="disabled")
        texto.see("end")

    def limpar_filtros():
        for e in (e_termo, e_ini, e_fim):
            e.delete(0, "end")
        carregar()

    def exportar():
        resultado = filtrados()
        if not resultado:
            if resultado is not None:
                msgbox(app, "info", "Exportar", "Nenhum comando encontrado com esse filtro.", parent=top)
            return
        destino = filedialog.asksaveasfilename(parent=top, title="Exportar histórico filtrado",
                                               defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                               initialfile="historico_comandos_filtrado.csv")
        if not destino:
            return
        try:
            n = transferencia.exportar_historico(destino, resultado)
            msgbox(app, "info", "Exportar", f"{n} linha(s) exportada(s) com sucesso!", parent=top)
        except Exception as e:
            log.error(f"Falha ao exportar histórico: {e}")
            msgbox(app, "error", "Erro", "Não foi possível exportar (detalhes no app.log).", parent=top)

    ctk.CTkButton(filtros, text="🔍 Filtrar", width=90, command=carregar).pack(side="left")
    rodape = ctk.CTkFrame(top, fg_color="transparent")
    rodape.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkButton(rodape, text="🔄 Limpar Filtro", width=120, command=limpar_filtros).pack(side="left")
    ctk.CTkButton(rodape, text="⬇️ Exportar Filtrado (.csv)", width=180, command=exportar).pack(side="left", padx=10)
    ctk.CTkLabel(rodape, text="Senhas e segredos são mascarados automaticamente (******).",
                 text_color="gray").pack(side="right")
    carregar()
