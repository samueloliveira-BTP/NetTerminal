"""Edição dos modelos de comando de ONU por marca."""
import customtkinter as ctk

from netterminal.core import onu
from netterminal.core.models import MARCAS
from netterminal.ui.dialogs.admin import exigir_permissao
from netterminal.ui.utils import msgbox, nova_janela

_AJUDA = (
    "Sintaxe: [VARIAVEL] vira campo; [VARIAVEL|op1,op2] vira lista. Uma linha = um comando.\n"
    "Validação automática pelo nome: SERIAL/SN (8–20 letras/números) • VLAN (1–4094) • "
    "ONU, PORTA, GEMPORT, SERVICE_PORT, *_ID, LINE_PROFILE, SRV_PROFILE (números) • "
    "PON, FRAME/SLOT, PLACA (ex.: 1/1/1) • DESCRICAO/NOME (espaços viram _).\n"
    "Na busca, use [SERIAL] (por serial) e [DESCRICAO] (por descrição)."
)


def abrir(app):
    if not exigir_permissao(app, "modelos_onu"):
        return
    top = nova_janela(app, "Modelos de ONU", "860x680")
    modelos = app.db.listar_modelos_onu()
    marcas = sorted(set(MARCAS) | set(modelos))

    topo = ctk.CTkFrame(top, fg_color="transparent")
    topo.pack(fill="x", padx=12, pady=(12, 4))
    ctk.CTkLabel(topo, text="Marca:").pack(side="left")
    combo_marca = ctk.CTkComboBox(topo, values=marcas, width=180, state="readonly")
    combo_marca.pack(side="left", padx=8)
    ctk.CTkLabel(top, text=_AJUDA, text_color="gray", justify="left", wraplength=820).pack(anchor="w", padx=12)
    ctk.CTkLabel(top, text="⚠ Os modelos padrão são um ponto de partida: valide em laboratório antes de usar em clientes.",
                 text_color="#e0a030").pack(anchor="w", padx=12, pady=(2, 0))

    abas = ctk.CTkTabview(top)
    abas.pack(expand=True, fill="both", padx=12, pady=8)
    caixas = {}
    for tipo, rotulo in onu.TIPOS_MODELO.items():
        aba = abas.add(rotulo)
        caixa = ctk.CTkTextbox(aba, font=("Consolas", 12))
        caixa.pack(expand=True, fill="both")
        caixas[tipo] = caixa

    def carregar(marca=None):
        marca = marca or combo_marca.get()
        atuais = app.db.listar_modelos_onu().get(marca, {})
        for tipo, caixa in caixas.items():
            caixa.delete("1.0", "end")
            caixa.insert("1.0", atuais.get(tipo, ""))

    def salvar():
        marca = combo_marca.get()
        for tipo, caixa in caixas.items():
            texto = caixa.get("1.0", "end-1c")
            if tipo in onu.VAR_TERMO and texto.strip() and f"[{onu.VAR_TERMO[tipo]}]" not in texto:
                msgbox(app, "warning", "Modelo incompleto",
                       f"O modelo '{onu.TIPOS_MODELO[tipo]}' precisa conter [{onu.VAR_TERMO[tipo]}].", parent=top)
                return
        for tipo, caixa in caixas.items():
            app.db.salvar_modelo_onu(marca, tipo, caixa.get("1.0", "end-1c"))
        msgbox(app, "info", "Salvo", f"Modelos da marca {marca} salvos.", parent=top)

    def restaurar():
        marca = combo_marca.get()
        padrao = onu.MODELOS_PADRAO.get(marca)
        if not padrao:
            msgbox(app, "info", "Sem padrão", f"Não há modelo padrão para {marca}.", parent=top)
            return
        if msgbox(app, "askyesno", "Restaurar", f"Substituir o texto pelos modelos padrão de {marca}?\n"
                                                "(Só é gravado ao clicar em Salvar.)", parent=top):
            for tipo, caixa in caixas.items():
                caixa.delete("1.0", "end")
                caixa.insert("1.0", padrao.get(tipo, ""))

    rodape = ctk.CTkFrame(top, fg_color="transparent")
    rodape.pack(fill="x", padx=12, pady=(0, 12))
    ctk.CTkButton(rodape, text="💾 Salvar", width=120, fg_color=app.cores["btn_bg"],
                  hover_color=app.cores["btn_hover"], command=salvar).pack(side="left")
    ctk.CTkButton(rodape, text="↺ Restaurar padrão da marca", width=200, fg_color="#555555",
                  command=restaurar).pack(side="left", padx=8)

    combo_marca.configure(command=carregar)
    combo_marca.set("Datacom" if "Datacom" in marcas else marcas[0])
    carregar()
