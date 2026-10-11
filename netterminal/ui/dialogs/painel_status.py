"""Painel de status: quais equipamentos estão online/offline e desde quando."""
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from netterminal.ui.tema import COR_DESCONHECIDO, COR_OFFLINE, COR_ONLINE
from netterminal.ui.utils import nova_janela


def abrir(app):
    top = nova_janela(app, "Painel de Status", "960x560")

    cabecalho = ctk.CTkFrame(top, fg_color="transparent")
    cabecalho.pack(fill="x", padx=10, pady=(10, 5))
    lbl_resumo = ctk.CTkLabel(cabecalho, text="", font=ctk.CTkFont(size=14, weight="bold"))
    lbl_resumo.pack(side="left")

    filtro = tk.StringVar(value="offline")
    filtro_frame = ctk.CTkFrame(top, fg_color="transparent")
    filtro_frame.pack(fill="x", padx=10)

    colunas = (("nome", 190, "Nome"), ("ip", 130, "IP"), ("grupo", 110, "Grupo"),
               ("marca", 90, "Marca"), ("status", 150, "Status"), ("desde", 160, "Última verificação"))
    tabela = ttk.Treeview(top, columns=[c[0] for c in colunas], show="headings", height=18)
    for chave, largura, titulo in colunas:
        tabela.heading(chave, text=titulo)
        tabela.column(chave, width=largura, anchor="w")
    tabela.tag_configure("offline", foreground=COR_OFFLINE)
    tabela.tag_configure("online", foreground=COR_ONLINE)
    tabela.tag_configure("unknown", foreground=COR_DESCONHECIDO)
    tabela.tag_configure("mudou", background="#4a3b00")

    def carregar():
        if not top.winfo_exists():
            return
        tabela.delete(*tabela.get_children())
        status = app.monitor.status
        mudancas = app.monitor.mudancas_recentes
        n_on = n_off = n_desc = 0
        for eq in app.db.listar_equipamentos():
            info = status.get(eq.id)
            if info is None:
                texto, tag, online, ts = "Desconhecido", "unknown", None, "nunca verificado"
                n_desc += 1
            elif info["online"]:
                lat = info.get("latencia_ms")
                texto = f"Online ({lat:.0f} ms)" if lat is not None else "Online"
                tag, online, ts = "online", True, info.get("ts", "-")
                n_on += 1
            else:
                texto, tag, online, ts = "Offline", "offline", False, info.get("ts", "-")
                n_off += 1
            if filtro.get() == "offline" and online is not False:
                continue
            tags = [tag]
            if eq.id in mudancas:
                texto += "  🔄 mudou agora"
                tags.append("mudou")
            tabela.insert("", "end", values=(eq.nome, eq.ip, eq.grupo, eq.marca, texto, ts), tags=tuple(tags))
        lbl_resumo.configure(text=f"🟢 {n_on} online    🔴 {n_off} offline    ⚪ {n_desc} nunca verificado(s)")

    ctk.CTkRadioButton(filtro_frame, text="Só os fora do ar", variable=filtro, value="offline", command=carregar).pack(side="left", padx=(0, 15))
    ctk.CTkRadioButton(filtro_frame, text="Todos", variable=filtro, value="todas", command=carregar).pack(side="left")
    tabela.pack(expand=True, fill="both", padx=10, pady=10)

    rodape = ctk.CTkFrame(top, fg_color="transparent")
    rodape.pack(fill="x", padx=10, pady=(0, 10))

    def verificar_agora():
        app.monitor.forcar_agora()
        lbl_resumo.configure(text="Verificando agora, aguarde alguns segundos...")
        top.after(4000, carregar)

    ctk.CTkButton(rodape, text="🔄 Verificar agora", width=150, command=verificar_agora).pack(side="left")
    ctk.CTkButton(rodape, text="↻ Atualizar lista", width=130, command=carregar).pack(side="left", padx=10)
    carregar()
