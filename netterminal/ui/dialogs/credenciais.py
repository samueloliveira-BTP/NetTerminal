"""Credenciais globais (usuário/senha padrão usados nas conexões)."""
import customtkinter as ctk

from netterminal.ui.dialogs.admin import exigir_permissao
from netterminal.ui.utils import msgbox, nova_janela


def abrir(app):
    if not exigir_permissao(app, "credenciais_globais"):
        return
    top = nova_janela(app, "Credenciais Globais", "480x540")

    card = ctk.CTkFrame(top, corner_radius=10)
    card.pack(fill="both", expand=True, padx=20, pady=20)
    ctk.CTkLabel(card, text="Credenciais de Acesso Global", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 15))

    ctk.CTkLabel(card, text="Usuário padrão:").pack(anchor="w", padx=30, pady=(5, 0))
    entry_user = ctk.CTkEntry(card, height=35)
    entry_user.insert(0, app.db.get_config("default_user", ""))
    entry_user.pack(fill="x", padx=30)

    tem_senha = bool(app.db.get_config("default_pass", ""))
    ctk.CTkLabel(card, text="Senha padrão:").pack(anchor="w", padx=30, pady=(15, 0))
    # A senha salva NÃO é carregada no campo (antes ela ficava decifrada na tela).
    entry_pass = ctk.CTkEntry(card, show="*", height=35,
                              placeholder_text="•••••• (salva — deixe em branco para manter)" if tem_senha else "")
    entry_pass.pack(fill="x", padx=30)
    ctk.CTkLabel(card, text="A senha é guardada cifrada (Fernet + chave protegida pelo Windows).",
                 text_color="gray", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=30, pady=(4, 0))

    def salvar():
        app.db.set_config("default_user", entry_user.get().strip())
        if entry_pass.get():
            app.db.set_config_secreto("default_pass", entry_pass.get())
        msgbox(app, "info", "Sucesso", "Credenciais salvas!", parent=top)
        top.destroy()

    ctk.CTkButton(card, text="Salvar Credenciais", height=40, font=ctk.CTkFont(weight="bold"),
                  fg_color=app.cores["btn_bg"], hover_color=app.cores["btn_hover"], command=salvar).pack(pady=25)

    card_import = ctk.CTkFrame(top, corner_radius=10)
    card_import.pack(fill="x", padx=20, pady=(0, 20))
    ctk.CTkLabel(card_import, text="Cadastro de Equipamentos", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 5))
    ctk.CTkLabel(card_import, text="Exporta/importa nome, IP, protocolo, porta, grupo e marca.\n"
                                   "Por segurança, usuário e senha NÃO entram no arquivo.",
                 text_color="gray", justify="center").pack(pady=(0, 10))
    linha = ctk.CTkFrame(card_import, fg_color="transparent")
    linha.pack(pady=(0, 15))
    ctk.CTkButton(linha, text="⬇️ Exportar (.csv)", width=160, command=app.exportar_cadastro).pack(side="left", padx=10)
    ctk.CTkButton(linha, text="⬆️ Importar (.csv)", width=160,
                  command=lambda: app.importar_cadastro(parent=top)).pack(side="left", padx=10)
