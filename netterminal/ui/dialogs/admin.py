"""Senha de admin: pedir senha, definir/trocar senha e escolher ações protegidas."""
import customtkinter as ctk

from netterminal.security.admin import ACOES_PROTEGIVEIS, TAMANHO_MINIMO_SENHA
from netterminal.ui.utils import msgbox, nova_janela


def pedir_senha_admin(app, titulo="Autenticação necessária"):
    """Janela modal que pede a senha de admin. Devolve True se conferiu."""
    admin = app.admin
    espera = admin.segundos_bloqueado()
    if espera:
        msgbox(app, "warning", "Bloqueado", f"Muitas tentativas erradas. Tente de novo em {espera} s.")
        return False

    resultado = {"ok": False}
    top = nova_janela(app, titulo, "380x210", modal=True)
    ctk.CTkLabel(top, text="🔒 Esta ação requer a senha de admin",
                 font=ctk.CTkFont(weight="bold")).pack(pady=(25, 15))
    entrada = ctk.CTkEntry(top, show="*", width=250)
    entrada.pack()

    def confirmar(event=None):
        if admin.verificar_senha(entrada.get()):
            admin.desbloquear()
            resultado["ok"] = True
            top.destroy()
            return
        entrada.delete(0, "end")
        restante = admin.segundos_bloqueado()
        texto = (f"Muitas tentativas. Aguarde {restante} s." if restante else "Senha incorreta.")
        msgbox(app, "error", "Erro", texto, parent=top)
        if restante:
            top.destroy()

    entrada.bind("<Return>", confirmar)
    ctk.CTkButton(top, text="Confirmar", command=confirmar).pack(pady=20)
    top.after(150, entrada.focus_set)
    app.wait_window(top)
    return resultado["ok"]


def exigir_permissao(app, acao_id):
    """Chame no início de qualquer ação sensível. True = pode prosseguir."""
    admin = app.admin
    if not admin.acao_protegida(acao_id) or admin.esta_desbloqueado():
        return True
    return pedir_senha_admin(app, f"Autorização: {ACOES_PROTEGIVEIS.get(acao_id, acao_id)}")


def abrir_painel_seguranca(app):
    """Configurações > Senha de Admin e Permissões."""
    if not app.admin.configurado():
        _definir_senha(app, primeira_vez=True)
        return
    if not (app.admin.esta_desbloqueado() or pedir_senha_admin(app, "Senha de admin")):
        return
    _painel_permissoes(app)


def _definir_senha(app, primeira_vez=False):
    top = nova_janela(app, "Definir Senha de Admin", "400x320", modal=True)
    if primeira_vez:
        ctk.CTkLabel(top, text="Nenhuma senha de admin definida ainda.", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 2))
        ctk.CTkLabel(top, text="Crie uma para poder proteger ações sensíveis.", text_color="gray").pack(pady=(0, 15))
    else:
        ctk.CTkLabel(top, text="Trocar senha de admin", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 15))
    ctk.CTkLabel(top, text=f"Nova senha (mínimo {TAMANHO_MINIMO_SENHA} caracteres):").pack(anchor="w", padx=40)
    e1 = ctk.CTkEntry(top, show="*", width=300)
    e1.pack(padx=40, pady=(0, 10))
    ctk.CTkLabel(top, text="Confirmar senha:").pack(anchor="w", padx=40)
    e2 = ctk.CTkEntry(top, show="*", width=300)
    e2.pack(padx=40)

    def salvar():
        if e1.get() != e2.get():
            msgbox(app, "error", "Erro", "As senhas não coincidem.", parent=top)
            return
        try:
            app.admin.definir_senha(e1.get())
        except ValueError as e:
            msgbox(app, "error", "Erro", str(e), parent=top)
            return
        app.admin.desbloquear()
        top.destroy()
        _painel_permissoes(app)

    ctk.CTkButton(top, text="Salvar Senha", height=38, fg_color=app.cores["btn_bg"],
                  hover_color=app.cores["btn_hover"], command=salvar).pack(pady=20)


def _painel_permissoes(app):
    top = nova_janela(app, "Senha de Admin e Permissões", "460x470")
    ctk.CTkLabel(top, text="🔒 Ações que exigem senha de admin",
                 font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(20, 5))
    ctk.CTkLabel(top, text="Marcadas = pedem a senha antes de executar.\n"
                           "Desmarcadas = livres para qualquer usuário.", text_color="gray").pack(pady=(0, 15))

    variaveis = {}
    for acao_id, rotulo in ACOES_PROTEGIVEIS.items():
        var = ctk.StringVar(value="True" if app.admin.acao_protegida(acao_id) else "False")
        ctk.CTkCheckBox(top, text=rotulo, variable=var, onvalue="True", offvalue="False").pack(anchor="w", padx=40, pady=6)
        variaveis[acao_id] = var

    def salvar():
        app.admin.definir_permissoes({a: v.get() == "True" for a, v in variaveis.items()})
        msgbox(app, "info", "Salvo", "Permissões atualizadas!", parent=top)

    ctk.CTkButton(top, text="Salvar", height=38, fg_color=app.cores["btn_bg"],
                  hover_color=app.cores["btn_hover"], command=salvar).pack(pady=(15, 8))
    ctk.CTkButton(top, text="🔑 Trocar Senha de Admin", fg_color="transparent", border_width=1,
                  border_color="#555555", command=lambda: (top.destroy(), _definir_senha(app))).pack(pady=4)
    ctk.CTkButton(top, text="🔐 Bloquear agora", fg_color="transparent", border_width=1, border_color="#555555",
                  command=lambda: (app.admin.bloquear(), top.destroy())).pack(pady=4)
    ctk.CTkLabel(top, text="Após digitar a senha, ela vale por 10 minutos.", text_color="gray").pack(pady=(10, 0))
