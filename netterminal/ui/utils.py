"""Funções auxiliares de janela usadas por todas as telas."""
from tkinter import messagebox

import customtkinter as ctk


def centralizar_e_topo(master, janela):
    """Centraliza a janela filha sobre a principal (mesmo monitor) e traz para frente."""
    master.update_idletasks()
    janela.update_idletasks()
    largura, altura = janela.winfo_width(), janela.winfo_height()
    x = master.winfo_x() + max(0, (master.winfo_width() - largura) // 2)
    y = master.winfo_y() + max(0, (master.winfo_height() - altura) // 2)
    janela.geometry(f"+{x}+{y}")
    janela.attributes("-topmost", True)
    janela.lift()
    janela.focus_force()
    # Libera o "sempre visível" depois de focar: é janela de trabalho, não aviso
    janela.after(400, lambda: janela.winfo_exists() and janela.attributes("-topmost", False))


def nova_janela(master, titulo, geometria, modal=False):
    janela = ctk.CTkToplevel(master)
    janela.title(titulo)
    janela.geometry(geometria)
    centralizar_e_topo(master, janela)
    if modal:
        janela.transient(master)
        janela.after(100, lambda: janela.winfo_exists() and janela.grab_set())
    return janela


def msgbox(master, tipo, titulo, mensagem, parent=None, **kwargs):
    """Messagebox garantidamente na frente de tudo (inclusive de janelas 'topmost')."""
    alvo = parent or master
    try:
        alvo.lift()
        alvo.attributes("-topmost", True)
    except Exception:
        pass
    funcao = {"info": messagebox.showinfo, "error": messagebox.showerror,
              "warning": messagebox.showwarning, "askyesno": messagebox.askyesno}[tipo]
    try:
        return funcao(titulo, mensagem, parent=alvo, **kwargs)
    finally:
        try:
            alvo.attributes("-topmost", False)
        except Exception:
            pass
