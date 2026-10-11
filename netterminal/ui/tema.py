"""Tema (claro/escuro), cores, fonte do terminal e estilos visuais."""
from tkinter import ttk

import customtkinter as ctk

CORES_PADRAO = {
    "btn_bg": "#1f538d",
    "btn_hover": "#14375e",
    "term_bg": "#0d1117",
    "term_fg": "#00FF00",
}

CORES_SUGERIDAS = ["#1f538d", "#14375e", "#0d1117", "#00FF00", "black", "white", "gray", "red",
                   "green", "blue", "yellow", "cyan", "magenta", "orange", "purple", "brown"]

# Cores fixas de status (árvore, painel e bolinha das abas)
COR_ONLINE = "#3ddc84"
COR_OFFLINE = "#ff5c5c"
COR_DESCONHECIDO = "#9a9a9a"
COR_SISTEMA = "#8be9fd"  # mensagens do próprio NetTerminal no terminal

TEMAS = {"Dark": "Escuro", "Light": "Claro", "System": "Igual ao Windows"}

# Cores da "moldura" do app, que o CustomTkinter não troca sozinho
PALETAS = {
    "Dark": {
        "arvore_bg": "#212121", "arvore_fg": "white", "cabecalho_bg": "#2b2b2b", "cabecalho_fg": "white",
        "barra_menu": "#1c1c1c", "menu_texto": "#d8d8d8", "menu_hover": "#333333", "dropdown": "#262626",
        "aba": "#333333", "aba_visivel": "#4a4a4a", "painel": "#2b2b2b", "divisoria": "#1a1a1a",
        "busca_bg": "#f1fa8c", "busca_atual_bg": "#ff9f43",
    },
    "Light": {
        "arvore_bg": "#ffffff", "arvore_fg": "#1a1a1a", "cabecalho_bg": "#e3e3e3", "cabecalho_fg": "#1a1a1a",
        "barra_menu": "#e6e6e6", "menu_texto": "#1a1a1a", "menu_hover": "#cfcfcf", "dropdown": "#f4f4f4",
        "aba": "#d4d4d4", "aba_visivel": "#bdbdbd", "painel": "#dedede", "divisoria": "#c8c8c8",
        "busca_bg": "#ffe066", "busca_atual_bg": "#ff9f43",
    },
}

FONTE_MIN, FONTE_MAX, FONTE_PADRAO = 8, 32, 14


def carregar_cores(db):
    return {
        "btn_bg": db.get_config("color_btn_bg", CORES_PADRAO["btn_bg"]),
        "btn_hover": db.get_config("color_btn_hover", CORES_PADRAO["btn_hover"]),
        "term_bg": db.get_config("color_term_bg", CORES_PADRAO["term_bg"]),
        "term_fg": db.get_config("color_term_fg", CORES_PADRAO["term_fg"]),
    }


def carregar_tema(db):
    tema = db.get_config("tema", "Dark")
    return tema if tema in TEMAS else "Dark"


def carregar_fonte(db):
    try:
        return max(FONTE_MIN, min(FONTE_MAX, int(db.get_config("fonte_terminal", str(FONTE_PADRAO)))))
    except ValueError:
        return FONTE_PADRAO


def paleta_atual():
    """Paleta do modo efetivo (resolve "System" para claro/escuro)."""
    return PALETAS["Light" if ctk.get_appearance_mode() == "Light" else "Dark"]


def cor_valida(widget, cor):
    """True se o Tk reconhece a cor (nome ou #hex). Evita travar a tela com cor inválida."""
    try:
        widget.winfo_rgb(cor)
        return True
    except Exception:
        return False


def aplicar_estilo_ttk(cores, paleta=None):
    paleta = paleta or paleta_atual()
    style = ttk.Style()
    style.theme_use("default")
    style.configure("Treeview", background=paleta["arvore_bg"], foreground=paleta["arvore_fg"], rowheight=25,
                    fieldbackground=paleta["arvore_bg"], borderwidth=0, font=("Segoe UI", 10))
    style.map("Treeview", background=[("selected", cores["btn_bg"])], foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background=paleta["cabecalho_bg"], foreground=paleta["cabecalho_fg"],
                    font=("Segoe UI", 10, "bold"))
    style.configure("Macros.Treeview", rowheight=28, font=("Segoe UI", 10))
