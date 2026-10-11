"""Acesso Rápido: conecta direto a um IP sem cadastrar o equipamento.
Usa a credencial global (ou login manual, se marcado)."""
import customtkinter as ctk

from netterminal.core.models import PROTOCOLOS, Equipamento
from netterminal.core.validators import ip_valido, porta_padrao, porta_valida
from netterminal.ui.utils import msgbox, nova_janela


def abrir(app):
    top = nova_janela(app, "Acesso Rápido", "320x330")
    ctk.CTkLabel(top, text="Acesso Rápido", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(15, 0))

    ctk.CTkLabel(top, text="Protocolo:").pack(anchor="w", padx=20, pady=(10, 0))
    combo_proto = ctk.CTkComboBox(top, values=PROTOCOLOS, state="readonly")
    combo_proto.set("SSH")
    combo_proto.pack(fill="x", padx=20, pady=(0, 10))

    ctk.CTkLabel(top, text="IP do equipamento:").pack(anchor="w", padx=20)
    entry_ip = ctk.CTkEntry(top, placeholder_text="Ex: 192.168.0.1")
    entry_ip.pack(fill="x", padx=20, pady=(0, 10))

    ctk.CTkLabel(top, text="Porta:").pack(anchor="w", padx=20)
    entry_porta = ctk.CTkEntry(top)
    entry_porta.insert(0, "22")
    entry_porta.pack(fill="x", padx=20, pady=(0, 10))

    var_manual = ctk.IntVar(value=0)
    ctk.CTkCheckBox(top, text="Login manual", variable=var_manual).pack(anchor="w", padx=20, pady=(0, 12))

    def ao_trocar_proto(valor):
        if entry_porta.get().strip() in ("", "22", "23"):
            entry_porta.delete(0, "end")
            entry_porta.insert(0, str(porta_padrao(valor)))
    combo_proto.configure(command=ao_trocar_proto)

    def conectar(event=None):
        ip = entry_ip.get().strip()
        proto = combo_proto.get()
        porta = porta_valida(entry_porta.get() or porta_padrao(proto))
        if not ip_valido(ip):
            msgbox(app, "error", "Erro", f"'{ip}' não é um IP válido.\nExemplo válido: 192.168.0.1", parent=top)
            return
        if porta is None:
            msgbox(app, "error", "Erro", "A porta deve ser um número entre 1 e 65535.", parent=top)
            return
        top.destroy()
        eq = Equipamento.acesso_rapido(ip, proto, porta)
        eq.login_manual = bool(var_manual.get())
        app.abrir_aba(eq, f"{ip} (Acesso Rápido)")

    entry_ip.bind("<Return>", conectar)
    ctk.CTkButton(top, text="Conectar", fg_color=app.cores["btn_bg"], hover_color=app.cores["btn_hover"],
                  command=conectar).pack(padx=20, fill="x")
    top.after(150, entry_ip.focus_set)
