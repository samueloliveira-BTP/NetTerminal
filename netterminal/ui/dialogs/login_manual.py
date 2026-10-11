"""Pede usuário e senha para equipamentos SSH com "Login Manual".

Na v1, o SSH com login manual tentava conectar sem credencial nenhuma (o que
o paramiko recusa). Agora as credenciais são pedidas aqui, usadas uma única
vez e descartadas — não são salvas nem registradas em log.
"""
import customtkinter as ctk

from netterminal.ui.utils import nova_janela


def pedir_credenciais(app, equipamento):
    """Devolve (usuario, senha) ou None se o técnico cancelar."""
    resultado = {}
    top = nova_janela(app, f"Login — {equipamento.rotulo}", "360x260", modal=True)

    ctk.CTkLabel(top, text=f"Login manual em {equipamento.rotulo}",
                 font=ctk.CTkFont(weight="bold")).pack(pady=(18, 10), padx=20)
    ctk.CTkLabel(top, text="Usuário:").pack(anchor="w", padx=30)
    e_usuario = ctk.CTkEntry(top, width=280)
    e_usuario.pack(padx=30, pady=(0, 8))
    ctk.CTkLabel(top, text="Senha:").pack(anchor="w", padx=30)
    e_senha = ctk.CTkEntry(top, width=280, show="*")
    e_senha.pack(padx=30)

    def confirmar(event=None):
        if e_usuario.get().strip():
            resultado["cred"] = (e_usuario.get().strip(), e_senha.get())
            top.destroy()

    linha = ctk.CTkFrame(top, fg_color="transparent")
    linha.pack(pady=18)
    ctk.CTkButton(linha, text="Conectar", width=120, command=confirmar).pack(side="left", padx=6)
    ctk.CTkButton(linha, text="Cancelar", width=120, fg_color="#555555", command=top.destroy).pack(side="left", padx=6)
    e_senha.bind("<Return>", confirmar)
    e_usuario.bind("<Return>", lambda e: e_senha.focus_set())
    top.after(150, e_usuario.focus_set)

    app.wait_window(top)
    return resultado.get("cred")
