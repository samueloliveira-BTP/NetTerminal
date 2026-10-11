"""Tela de abertura.

Na v1 ela simulava ~5,5 s de carregamento com textos fictícios
("Estabelecendo parâmetros de segurança..."). Agora ela aparece só pelo
tempo de uma breve animação, porque quando ela é exibida o app já está pronto.
"""
import logging

import customtkinter as ctk
from PIL import Image

from netterminal import APP_VERSION
from netterminal.config import resource_path

LARGURA, ALTURA = 650, 400
DURACAO_MS = 900


def mostrar_splash(app):
    try:
        imagem = Image.open(resource_path("assets/logo_splash.jpg"))
    except OSError as e:
        logging.warning(f"Imagem da splash indisponível: {e}")
        app.deiconify()
        return

    splash = ctk.CTkToplevel(app)
    splash.withdraw()
    splash.overrideredirect(True)
    x = (app.winfo_screenwidth() - LARGURA) // 2
    y = (app.winfo_screenheight() - ALTURA) // 2
    splash.geometry(f"{LARGURA}x{ALTURA}+{x}+{y}")
    splash.configure(fg_color="#0d3a54")

    img = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(LARGURA, ALTURA - 65))
    ctk.CTkLabel(splash, image=img, text="").pack(side="top", fill="both", expand=True)

    rodape = ctk.CTkFrame(splash, fg_color="transparent")
    rodape.pack(side="bottom", fill="x", padx=20, pady=(5, 15))
    ctk.CTkLabel(rodape, text="Carregando...", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                 text_color="#00e5ff").pack(side="top", anchor="w", pady=(0, 5))
    ctk.CTkLabel(rodape, text=f"v{APP_VERSION}", font=ctk.CTkFont(family="Segoe UI", size=11),
                 text_color="#5a8fa8").place(relx=1.0, rely=0.0, anchor="ne")
    barra = ctk.CTkProgressBar(rodape, height=6, progress_color="#00e5ff", fg_color="#082336", border_width=0)
    barra.pack(side="bottom", fill="x")
    barra.set(0)

    splash.update_idletasks()
    splash.deiconify()

    passos = 30

    def avancar(i=0):
        if i <= passos:
            barra.set(i / passos)
            splash.after(DURACAO_MS // passos, avancar, i + 1)
        else:
            splash.destroy()
            app.deiconify()

    avancar()
