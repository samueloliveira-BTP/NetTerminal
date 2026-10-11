"""Assistente de provisionamento de ONU.

Fluxo seguro: preencher campos -> "Gerar prévia" (valida tudo) -> revisar os
comandos -> marcar "Revisei" -> enviar. Qualquer alteração num campo invalida
a prévia. Os comandos vão para a aba de terminal aberta, linha a linha, então
o técnico acompanha a resposta da OLT ao vivo. Tudo fica no histórico [ONU].
"""
import json
import logging

import customtkinter as ctk

from netterminal.core import onu
from netterminal.ui.utils import msgbox, nova_janela

log = logging.getLogger(__name__)

# Campos que mudam a cada cliente não são lembrados entre usos
_NAO_LEMBRAR = {"SERIAL", "SN", "DESCRICAO", "NOME", "NAME", "DESC", "ONU", "SERVICE_PORT"}


def _chave_memoria(marca):
    return f"onu_ultimos_{marca}"


def abrir(app, term):
    marca = term.eq.marca
    modelo = app.db.obter_modelo_onu(marca, "provisionar")
    if not modelo:
        msgbox(app, "info", "Modelo não configurado",
               f"Não há modelo de provisionamento para a marca '{marca}'.\n\n"
               "Cadastre em Configurações > Modelos de ONU.")
        return
    if not term.conectado:
        msgbox(app, "warning", "Desconectado", "Conecte-se à OLT antes de usar o assistente.")
        return

    try:
        memoria = json.loads(app.db.get_config(_chave_memoria(marca), "{}") or "{}")
    except ValueError:
        memoria = {}

    top = nova_janela(app, f"Provisionar ONU — {term.eq.rotulo}", "900x620")
    estado = {"linhas": None, "valores": None}

    ctk.CTkLabel(top, text=f"🧙 Provisionar ONU em {term.eq.rotulo}  ({marca})",
                 font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=15, pady=(12, 2))
    ctk.CTkLabel(top, text="Preencha os campos, gere a prévia e revise antes de enviar. "
                           "O modelo pode ser ajustado em Configurações > Modelos de ONU.",
                 text_color="gray").pack(anchor="w", padx=15)

    corpo = ctk.CTkFrame(top, fg_color="transparent")
    corpo.pack(expand=True, fill="both", padx=10, pady=10)
    form = ctk.CTkScrollableFrame(corpo, width=330, label_text="Dados da ONU")
    form.pack(side="left", fill="y", padx=(0, 10))
    direita = ctk.CTkFrame(corpo, fg_color="transparent")
    direita.pack(side="left", expand=True, fill="both")
    ctk.CTkLabel(direita, text="Prévia dos comandos", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
    previa = ctk.CTkTextbox(direita, font=("Consolas", 12))
    previa.pack(expand=True, fill="both", pady=(4, 6))
    previa.insert("1.0", "Clique em \"Gerar prévia\".")
    previa.configure(state="disabled")

    var_revisei = ctk.BooleanVar(value=False)
    campos = {}

    def invalidar(*_):
        estado["linhas"] = None
        var_revisei.set(False)
        btn_enviar.configure(state="disabled")

    for chave, rotulo, opcoes in onu.variaveis(modelo):
        ctk.CTkLabel(form, text=f"{rotulo}:").pack(anchor="w", padx=6, pady=(6, 0))
        if opcoes:
            widget = ctk.CTkComboBox(form, values=opcoes, width=280, command=invalidar)
            widget.set(memoria.get(rotulo, opcoes[0]))
        else:
            widget = ctk.CTkEntry(form, width=280)
            if rotulo.upper() not in _NAO_LEMBRAR and memoria.get(rotulo):
                widget.insert(0, memoria[rotulo])
            widget.bind("<KeyRelease>", invalidar)
        widget.pack(anchor="w", padx=6)
        campos[chave] = (rotulo, widget)

    def gerar_previa():
        valores, erros = {}, []
        for chave, (rotulo, widget) in campos.items():
            try:
                valores[chave] = onu.validar_valor(rotulo, widget.get())
            except ValueError as e:
                erros.append(str(e))
        if erros:
            msgbox(app, "warning", "Campos inválidos", "\n".join(erros), parent=top)
            return
        estado["linhas"] = onu.montar(modelo, valores)
        estado["valores"] = {rotulo: valores[chave] for chave, (rotulo, _) in campos.items()}
        previa.configure(state="normal")
        previa.delete("1.0", "end")
        previa.insert("1.0", "\n".join(estado["linhas"]))
        previa.configure(state="disabled")
        var_revisei.set(False)
        btn_enviar.configure(state="disabled")

    def ao_marcar_revisei():
        btn_enviar.configure(state="normal" if var_revisei.get() and estado["linhas"] else "disabled")

    def enviar():
        if not estado["linhas"] or not var_revisei.get():
            return
        if not term.conectado:
            msgbox(app, "error", "Desconectado", "A sessão com a OLT caiu. Reconecte e tente de novo.", parent=top)
            return
        if not msgbox(app, "askyesno", "Confirmar provisionamento",
                      f"Enviar {len(estado['linhas'])} comandos para {term.eq.rotulo}?", parent=top):
            return
        lembrar = {r: v for r, v in estado["valores"].items() if r.upper() not in _NAO_LEMBRAR}
        app.db.set_config(_chave_memoria(marca), json.dumps(lembrar))
        log.info(f"Provisionamento de ONU enviado para {term.eq.rotulo}: "
                 f"serial={estado['valores'].get('SERIAL', '-')}")
        term.enviar_linhas(estado["linhas"], origem="ONU")
        top.destroy()
        term.terminal_text.focus_set()

    def listar_pendentes():
        comando = app.db.obter_modelo_onu(marca, "pendentes")
        if not comando:
            msgbox(app, "info", "Sem modelo", "Não há comando de 'ONUs pendentes' para esta marca.", parent=top)
            return
        term.enviar_linhas(onu.montar(comando, {}), origem="ONU")
        msgbox(app, "info", "Comando enviado", "A lista aparece no terminal.\n"
                                               "Selecione o serial com o mouse (copia automaticamente) e cole aqui.",
               parent=top)

    acoes = ctk.CTkFrame(direita, fg_color="transparent")
    acoes.pack(fill="x")
    ctk.CTkButton(acoes, text="📋 Listar ONUs pendentes", width=180, fg_color="transparent", border_width=1,
                  border_color="#555555", command=listar_pendentes).pack(side="left")
    ctk.CTkButton(acoes, text="👁 Gerar prévia", width=130, command=gerar_previa).pack(side="left", padx=8)
    ctk.CTkCheckBox(acoes, text="Revisei os comandos", variable=var_revisei, command=ao_marcar_revisei).pack(side="left", padx=8)
    btn_enviar = ctk.CTkButton(acoes, text="🚀 Enviar para a OLT", width=160, fg_color="#006400",
                               hover_color="green", state="disabled", command=enviar)
    btn_enviar.pack(side="right")
