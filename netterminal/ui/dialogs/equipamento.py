"""Formulário de cadastro/edição de equipamento."""
import tkinter as tk

import customtkinter as ctk

from netterminal.core.models import MARCAS, PROTOCOLOS, Equipamento
from netterminal.core.validators import ip_valido, porta_padrao, porta_valida, texto_limpo
from netterminal.ui.utils import msgbox, nova_janela


def abrir(app, equipamento=None):
    editando = equipamento is not None
    top = nova_janela(app, "Editar Equipamento" if editando else "Novo Equipamento", "360x620")

    def rotulo(texto):
        ctk.CTkLabel(top, text=texto).pack(anchor="w", padx=20, pady=(6, 0))

    rotulo("Grupo/Pasta:")
    combo_grupo = ctk.CTkComboBox(top, values=app.db.grupos())
    combo_grupo.pack(fill="x", padx=20)
    rotulo("Nome:")
    entry_nome = ctk.CTkEntry(top)
    entry_nome.pack(fill="x", padx=20)
    rotulo("IP:")
    entry_ip = ctk.CTkEntry(top, placeholder_text="Ex: 192.168.0.10")
    entry_ip.pack(fill="x", padx=20)
    rotulo("Marca:")
    combo_marca = ctk.CTkComboBox(top, values=MARCAS, state="readonly")
    combo_marca.pack(fill="x", padx=20)
    rotulo("Protocolo:")
    combo_proto = ctk.CTkComboBox(top, values=PROTOCOLOS, state="readonly")
    combo_proto.pack(fill="x", padx=20)
    rotulo("Porta:")
    entry_porta = ctk.CTkEntry(top)
    entry_porta.pack(fill="x", padx=20)

    def ao_trocar_proto(valor):
        if entry_porta.get().strip() in ("", "22", "23"):
            entry_porta.delete(0, "end")
            entry_porta.insert(0, str(porta_padrao(valor)))
    combo_proto.configure(command=ao_trocar_proto)

    chk_var = tk.IntVar()
    ctk.CTkCheckBox(top, text="Login Manual (não usar credencial global)", variable=chk_var).pack(anchor="w", padx=20, pady=15)
    rotulo("Nota (opcional):")
    entry_nota = ctk.CTkTextbox(top, height=70)
    entry_nota.pack(fill="x", padx=20, pady=(0, 10))

    if editando:
        combo_grupo.set(equipamento.grupo)
        entry_nome.insert(0, equipamento.nome)
        entry_ip.insert(0, equipamento.ip)
        combo_marca.set(equipamento.marca if equipamento.marca in MARCAS else "Outra")
        combo_proto.set(equipamento.protocolo)
        entry_porta.insert(0, str(equipamento.porta))
        chk_var.set(1 if equipamento.login_manual else 0)
        if equipamento.nota:
            entry_nota.insert("1.0", equipamento.nota)
    else:
        combo_grupo.set("Geral")
        combo_marca.set("Outra")
        combo_proto.set("SSH")
        entry_porta.insert(0, "22")

    def salvar():
        nome = texto_limpo(entry_nome.get())
        ip = entry_ip.get().strip()
        porta = porta_valida(entry_porta.get())
        if not nome or not ip:
            msgbox(app, "error", "Erro", "Nome e IP são obrigatórios!", parent=top)
            return
        if not ip_valido(ip):
            msgbox(app, "error", "Erro", f"'{ip}' não é um IP válido.\nExemplo válido: 192.168.0.10", parent=top)
            return
        if porta is None:
            msgbox(app, "error", "Erro", "A porta deve ser um número entre 1 e 65535.", parent=top)
            return
        if not editando and ip in app.db.ips_cadastrados():
            if not msgbox(app, "askyesno", "IP duplicado", f"Já existe um equipamento com o IP {ip}.\nCadastrar mesmo assim?", parent=top):
                return
        novo = Equipamento(
            id=equipamento.id if editando else None, nome=nome, ip=ip, protocolo=combo_proto.get(),
            porta=porta, grupo=texto_limpo(combo_grupo.get()) or "Geral", login_manual=bool(chk_var.get()),
            marca=combo_marca.get(), nota=entry_nota.get("1.0", "end-1c").strip()[:2000])
        if editando:
            app.db.atualizar_equipamento(novo)
        else:
            app.db.adicionar_equipamento(novo)
        app.carregar_lista()
        app.monitor.forcar_agora()
        top.destroy()

    ctk.CTkButton(top, text="Salvar", fg_color=app.cores["btn_bg"], hover_color=app.cores["btn_hover"],
                  command=salvar).pack(pady=10)
