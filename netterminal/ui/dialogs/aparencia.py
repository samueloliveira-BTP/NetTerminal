"""Aparência: tema claro/escuro, tamanho da fonte do terminal e cores."""
from tkinter import colorchooser

import customtkinter as ctk

from netterminal.ui.tema import (CORES_PADRAO, CORES_SUGERIDAS, FONTE_MAX, FONTE_MIN, FONTE_PADRAO, TEMAS,
                                 cor_valida)
from netterminal.ui.utils import msgbox, nova_janela

_CAMPOS = [
    ("btn_bg", "color_btn_bg", "Botões (cor principal):"),
    ("btn_hover", "color_btn_hover", "Botões (ao passar o mouse):"),
    ("term_bg", "color_term_bg", "Terminal (fundo):"),
    ("term_fg", "color_term_fg", "Terminal (texto):"),
]
_TEMA_DO_ROTULO = {v: k for k, v in TEMAS.items()}


def abrir(app):
    top = nova_janela(app, "Aparência", "520x600")
    card = ctk.CTkFrame(top, corner_radius=10)
    card.pack(fill="both", expand=True, padx=20, pady=20)
    card.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(card, text="Aparência", font=ctk.CTkFont(size=16, weight="bold")).grid(
        row=0, column=0, columnspan=3, pady=(15, 10))

    ctk.CTkLabel(card, text="Tema:").grid(row=1, column=0, padx=15, pady=8, sticky="e")
    seletor_tema = ctk.CTkSegmentedButton(card, values=list(TEMAS.values()))
    seletor_tema.set(TEMAS[app.tema])
    seletor_tema.grid(row=1, column=1, columnspan=2, padx=15, pady=8, sticky="w")

    ctk.CTkLabel(card, text="Fonte do terminal:").grid(row=2, column=0, padx=15, pady=8, sticky="e")
    lbl_fonte = ctk.CTkLabel(card, text=str(app.fonte_terminal), width=30)
    lbl_fonte.grid(row=2, column=2, padx=(0, 15))
    slider = ctk.CTkSlider(card, from_=FONTE_MIN, to=FONTE_MAX, number_of_steps=FONTE_MAX - FONTE_MIN,
                           command=lambda v: lbl_fonte.configure(text=str(int(v))))
    slider.set(app.fonte_terminal)
    slider.grid(row=2, column=1, padx=15, pady=8, sticky="ew")
    ctk.CTkLabel(card, text="Dica: Ctrl + roda do mouse dentro do terminal também muda a fonte.",
                 text_color="gray").grid(row=3, column=0, columnspan=3, pady=(0, 10))

    combos = {}
    for i, (chave, _, rotulo) in enumerate(_CAMPOS, start=4):
        ctk.CTkLabel(card, text=rotulo).grid(row=i, column=0, padx=15, pady=6, sticky="e")
        combo = ctk.CTkComboBox(card, values=CORES_SUGERIDAS, width=150)
        combo.set(app.cores[chave])
        combo.grid(row=i, column=1, padx=15, pady=6, sticky="w")

        def escolher(c=combo):
            atual = c.get().strip()
            _, cor = colorchooser.askcolor(color=atual if cor_valida(top, atual) else "#ffffff", parent=top)
            if cor:
                c.set(cor)
        ctk.CTkButton(card, text="🎨", width=36, command=escolher).grid(row=i, column=2, padx=(0, 15))
        combos[chave] = combo

    def salvar():
        invalidas = [c.get() for c in combos.values() if not cor_valida(top, c.get().strip())]
        if invalidas:
            msgbox(app, "error", "Cor inválida", f"Cor não reconhecida: {', '.join(invalidas)}", parent=top)
            return
        pares = [(config_chave, combos[chave].get().strip()) for chave, config_chave, _ in _CAMPOS]
        pares += [("tema", _TEMA_DO_ROTULO[seletor_tema.get()]), ("fonte_terminal", str(int(slider.get())))]
        app.db.set_config_lote(pares)
        app.aplicar_aparencia()
        msgbox(app, "info", "Sucesso", "Aparência aplicada!", parent=top)

    def restaurar():
        for chave, combo in combos.items():
            combo.set(CORES_PADRAO[chave])
        slider.set(FONTE_PADRAO)
        lbl_fonte.configure(text=str(FONTE_PADRAO))
        seletor_tema.set(TEMAS["Dark"])

    linha = ctk.CTkFrame(card, fg_color="transparent")
    linha.grid(row=10, column=0, columnspan=3, pady=20)
    ctk.CTkButton(linha, text="Aplicar", height=38, font=ctk.CTkFont(weight="bold"), fg_color=app.cores["btn_bg"],
                  hover_color=app.cores["btn_hover"], command=salvar).pack(side="left", padx=6)
    ctk.CTkButton(linha, text="Restaurar padrão", height=38, fg_color="#555555", command=restaurar).pack(side="left", padx=6)
