"""Barra de menu (Equipamentos / Ferramentas / Configurações / Ajuda).

Usa botões CustomTkinter em vez do menu nativo do Windows, porque o nativo
não segue o tema escuro. Para adicionar uma função nova, inclua um item na
lista da categoria certa em `BarraMenu._itens`.
"""
import tkinter as tk

import customtkinter as ctk

from netterminal.ui.dialogs import (acesso_rapido, admin, aparencia, busca_onu, credenciais, dashboard, destaque,
                                    equipamento, historico, macros, modelos_onu, painel_status, perfil_equipe)
from netterminal.ui.tema import paleta_atual


class BarraMenu:
    def __init__(self, app):
        self.app = app
        self.barra = ctk.CTkFrame(app, height=34, corner_radius=0)
        self.barra.pack(side="top", fill="x")
        self.barra.pack_propagate(False)
        self._botoes, self._menus = [], []
        for titulo, largura, itens in self._itens():
            self._criar(titulo, largura, itens)
        self.aplicar_paleta()

    def _itens(self):
        app = self.app
        return [
            ("Equipamentos", 130, [
                ("➕ Cadastrar Equipamento", lambda: equipamento.abrir(app)),
                ("⚡ Acesso Rápido", lambda: acesso_rapido.abrir(app)),
                None,
                ("⬇️ Exportar Cadastro (.csv)", app.exportar_cadastro),
                ("⬆️ Importar Cadastro (.csv)", app.importar_cadastro),
            ]),
            ("Ferramentas", 170, [
                ("🔎 Buscar ONU em todas as OLTs", lambda: busca_onu.abrir(app)),
                None,
                ("📡 Painel de Status", lambda: painel_status.abrir(app)),
                ("🔄 Verificar Status Agora", app.monitor.forcar_agora),
                None,
                ("📜 Histórico de Comandos", lambda: historico.abrir(app)),
                ("📊 Dashboard de Uso", lambda: dashboard.abrir(app)),
            ]),
            ("Configurações", 160, [
                ("🔑 Credenciais Globais", lambda: credenciais.abrir(app)),
                ("🎨 Aparência (tema, fonte, cores)", lambda: aparencia.abrir(app)),
                ("🖍️ Realce de Sintaxe", lambda: destaque.abrir(app)),
                ("🧩 Macros", lambda: macros.abrir(app)),
                ("📋 Modelos de ONU", lambda: modelos_onu.abrir(app)),
                None,
                ("📤 Exportar Perfil da Equipe", lambda: perfil_equipe.exportar(app)),
                ("📥 Importar Perfil da Equipe", lambda: perfil_equipe.importar(app)),
                None,
                ("🔒 Senha de Admin e Permissões", lambda: admin.abrir_painel_seguranca(app)),
            ]),
            ("Ajuda", 90, [
                ("🔄 Verificar atualizações agora", app.verificar_atualizacao_manual),
                ("⌨️ Atalhos de teclado", app.mostrar_atalhos),
                ("ℹ️ Sobre o NetTerminal", app.mostrar_sobre),
                ("📂 Abrir pasta de dados", app.abrir_pasta_dados),
            ]),
        ]

    def _criar(self, titulo, largura, itens):
        menu = tk.Menu(self.app, tearoff=0, borderwidth=0, relief="flat")
        for item in itens:
            if item is None:
                menu.add_separator()
            else:
                menu.add_command(label=item[0], command=item[1])
        btn = ctk.CTkButton(self.barra, text=titulo, width=largura, height=34, corner_radius=0,
                            fg_color="transparent", font=ctk.CTkFont(size=13))
        btn.configure(command=lambda: menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height()))
        btn.pack(side="left")
        self._botoes.append(btn)
        self._menus.append(menu)

    def aplicar_paleta(self):
        p = paleta_atual()
        self.barra.configure(fg_color=p["barra_menu"])
        for btn in self._botoes:
            btn.configure(hover_color=p["menu_hover"], text_color=p["menu_texto"])
        for menu in self._menus:
            menu.configure(bg=p["dropdown"], fg=p["menu_texto"], activebackground=self.app.cores["btn_bg"],
                           activeforeground="white")
