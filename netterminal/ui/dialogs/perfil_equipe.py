"""Exportar/importar o perfil da equipe (configurações do app em JSON)."""
import logging
from tkinter import filedialog

import customtkinter as ctk

from netterminal.services import perfil
from netterminal.ui.dialogs.admin import exigir_permissao
from netterminal.ui.utils import msgbox, nova_janela

log = logging.getLogger(__name__)


def _escolher_secoes(app, titulo, secoes, botao, extras=None):
    """Janela modal com uma caixa por seção. Devolve (lista_de_secoes, extras) ou None."""
    resultado = {}
    top = nova_janela(app, titulo, "430x430", modal=True)
    ctk.CTkLabel(top, text=titulo, font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(15, 5))
    ctk.CTkLabel(top, text="Usuário, senhas, senha de admin e chaves SSH\nnunca fazem parte do perfil.",
                 text_color="gray").pack(pady=(0, 10))
    variaveis = {}
    for s in secoes:
        var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top, text=perfil.SECOES[s], variable=var).pack(anchor="w", padx=40, pady=4)
        variaveis[s] = var
    var_extra = {}
    for chave, rotulo in (extras or {}).items():
        var_extra[chave] = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(top, text=rotulo, variable=var_extra[chave]).pack(anchor="w", padx=40, pady=(12, 4))

    def confirmar():
        escolhidas = [s for s, v in variaveis.items() if v.get()]
        if escolhidas:
            resultado["ok"] = (escolhidas, {k: v.get() for k, v in var_extra.items()})
        top.destroy()

    ctk.CTkButton(top, text=botao, command=confirmar).pack(pady=18)
    app.wait_window(top)
    return resultado.get("ok")


def exportar(app):
    escolha = _escolher_secoes(app, "Exportar perfil da equipe", list(perfil.SECOES), "Escolher arquivo e exportar")
    if not escolha:
        return
    caminho = filedialog.asksaveasfilename(title="Salvar perfil", defaultextension=".json",
                                           filetypes=[("Perfil NetTerminal", "*.json")],
                                           initialfile="perfil_netterminal.json")
    if not caminho:
        return
    try:
        perfil.exportar(caminho, app.db, escolha[0])
        msgbox(app, "info", "Exportar", "Perfil exportado com sucesso!\nDistribua o arquivo para a equipe importar.")
    except Exception as e:
        log.error(f"Falha ao exportar perfil: {e}")
        msgbox(app, "error", "Erro", "Não foi possível exportar (detalhes no app.log).")


def importar(app):
    if not exigir_permissao(app, "importar_cadastro"):
        return
    caminho = filedialog.askopenfilename(title="Importar perfil", filetypes=[("Perfil NetTerminal", "*.json")])
    if not caminho:
        return
    try:
        dados = perfil.ler(caminho)
    except (ValueError, OSError) as e:
        msgbox(app, "error", "Arquivo inválido", str(e))
        return
    disponiveis = perfil.secoes_disponiveis(dados)
    if not disponiveis:
        msgbox(app, "info", "Importar", "O arquivo não contém nenhuma seção reconhecida.")
        return
    escolha = _escolher_secoes(
        app, f"Importar perfil (de {str(dados.get('gerado_por', '?'))[:40]})", disponiveis, "Importar",
        extras={"substituir_destaque": "Substituir minhas regras de realce (em vez de somar)"}
        if "destaque" in disponiveis else None)
    if not escolha:
        return
    secoes, extras = escolha
    try:
        resultado = perfil.importar(dados, app.db, secoes, substituir_destaque=extras.get("substituir_destaque", False))
    except Exception as e:
        log.error(f"Falha ao importar perfil: {e}")
        msgbox(app, "error", "Erro", "Não foi possível importar (detalhes no app.log).")
        return
    app.aplicar_aparencia()
    app.recarregar_regras_destaque()
    app.atualizar_macros_nas_abas()
    app.carregar_lista()
    msgbox(app, "info", "Perfil importado", resultado.resumo())
