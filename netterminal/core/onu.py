"""Modelos de comando de ONU por marca (busca, pendentes e provisionamento).

Os modelos usam a mesma sintaxe das macros: [VARIAVEL] vira um campo e
[VARIAVEL|op1,op2] vira uma lista de opções. Os padrões abaixo seguem a
sintaxe das macros já usadas pela equipe, mas cada rede tem perfis, VLANs
e firmwares próprios: REVISE em Configurações > Modelos de ONU e valide em
laboratório antes de provisionar clientes reais.

Todo valor digitado passa por `validar_valor`, que impede quebras de linha
(injeção de comandos extras) e confere o formato de seriais, VLANs e IDs.
"""
import re

TIPOS_MODELO = {
    "buscar_serial": "Buscar ONU por serial",
    "buscar_descricao": "Buscar ONU por descrição/nome",
    "pendentes": "Listar ONUs não provisionadas",
    "provisionar": "Provisionar ONU",
}

# Variável usada pela busca global para inserir o termo pesquisado
VAR_TERMO = {"buscar_serial": "SERIAL", "buscar_descricao": "DESCRICAO"}

MODELOS_PADRAO = {
    "Datacom": {
        "buscar_serial": "show running-config interface gpon | context-match [SERIAL]",
        "buscar_descricao": "show running-config interface gpon | context-match [DESCRICAO]",
        "pendentes": "show interface gpon discovered-onus",
        "provisionar": (
            "config\n"
            "interface gpon [PON]\n"
            "onu [ONU]\n"
            "name [DESCRICAO]\n"
            "serial-number [SERIAL]\n"
            "line-profile [LINE_PROFILE]\n"
            "ethernet 1\n"
            "negotiation\n"
            "no shutdown\n"
            "native vlan vlan-id [VLAN]\n"
            "top\n"
            "service-port [SERVICE_PORT] gpon [PON] onu [ONU] gem 1 match vlan vlan-id [VLAN] action vlan replace vlan-id [VLAN]\n"
            "commit\n"
            "end"
        ),
    },
    "Huawei": {
        "buscar_serial": "enable\nundo smart\ndisplay ont info by-sn [SERIAL]",
        "buscar_descricao": "enable\nundo smart\ndisplay ont info by-desc [DESCRICAO]",
        "pendentes": "enable\nundo smart\ndisplay ont autofind all",
        "provisionar": (
            "enable\n"
            "config\n"
            "interface gpon [FRAME/SLOT]\n"
            "ont add [PORTA] [ONU] sn-auth [SERIAL] omci ont-lineprofile-id [LINE_PROFILE] "
            "ont-srvprofile-id [SRV_PROFILE] desc \"[DESCRICAO]\"\n"
            "ont port native-vlan [PORTA] [ONU] eth 1 vlan [VLAN]\n"
            "quit\n"
            "service-port vlan [VLAN] gpon [FRAME/SLOT]/[PORTA] ont [ONU] gemport [GEMPORT] "
            "multi-service user-vlan [VLAN] tag-transform translate\n"
            "quit"
        ),
    },
    "ZTE": {
        "buscar_serial": "show gpon onu by sn [SERIAL]",
        "buscar_descricao": "show running-config | include [DESCRICAO]",
        "pendentes": "show pon onu uncfg",
        "provisionar": (
            "conf t\n"
            "interface gpon_olt-[PON]\n"
            "onu [ONU] type [TIPO_ONU] sn [SERIAL]\n"
            "exit\n"
            "interface gpon_onu-[PON]:[ONU]\n"
            "name [DESCRICAO]\n"
            "tcont 1 profile [TCONT_PROFILE]\n"
            "gemport 1 tcont 1\n"
            "exit\n"
            "interface vport-[PON].[ONU]:1\n"
            "service-port 1 user-vlan [VLAN] vlan [VLAN]\n"
            "exit\n"
            "pon-onu-mng gpon_onu-[PON]:[ONU]\n"
            "service 1 gemport 1 vlan [VLAN]\n"
            "exit\n"
            "end"
        ),
    },
}

_VARIAVEL_RE = re.compile(r"\[(.*?)\]")
_NUMERICAS = {"ONU", "PORTA", "GEMPORT", "SERVICE_PORT", "VPORT", "LINE_PROFILE", "SRV_PROFILE"}
_POSICOES = {"PON", "FRAME/SLOT", "PLACA", "SLOT", "PLACA/SLOT"}
_DESCRICOES = {"DESCRICAO", "NOME", "NAME", "DESC"}
_SERIAL_RE = re.compile(r"^[A-Za-z0-9-]{8,20}$")
_POSICAO_RE = re.compile(r"^\d{1,3}(/\d{1,3}){0,2}$")


def variaveis(modelo):
    """Lista as variáveis do modelo na ordem, sem repetir: [(chave, rotulo, opcoes)]."""
    vistas, resultado = set(), []
    for bruto in _VARIAVEL_RE.findall(modelo or ""):
        if bruto in vistas:
            continue
        vistas.add(bruto)
        if "|" in bruto:
            rotulo, opcoes = bruto.split("|", 1)
            resultado.append((bruto, rotulo.strip(), [o.strip() for o in opcoes.split(",") if o.strip()]))
        else:
            resultado.append((bruto, bruto.strip(), None))
    return resultado


def _nome_base(rotulo):
    return rotulo.strip().upper()


def validar_valor(rotulo, valor):
    """Normaliza e valida o valor de um campo. Levanta ValueError se inválido."""
    nome = _nome_base(rotulo)
    valor = (valor or "").strip()
    if any(c in valor for c in "\r\n\x00") or any(not c.isprintable() for c in valor):
        raise ValueError(f"{rotulo}: não pode conter quebra de linha ou caracteres de controle.")
    if not valor:
        raise ValueError(f"{rotulo}: campo obrigatório.")
    if nome in ("SERIAL", "SN") or nome.endswith("_SN"):
        if not _SERIAL_RE.match(valor):
            raise ValueError(f"{rotulo}: serial inválido (8 a 20 letras/números).")
        return valor.upper()
    if "VLAN" in nome:
        if not valor.isdigit() or not 1 <= int(valor) <= 4094:
            raise ValueError(f"{rotulo}: VLAN deve ser um número entre 1 e 4094.")
        return str(int(valor))
    if nome in _NUMERICAS or nome.endswith("_ID"):
        if not valor.isdigit() or int(valor) > 65535:
            raise ValueError(f"{rotulo}: deve ser um número.")
        return str(int(valor))
    if nome in _POSICOES:
        if not _POSICAO_RE.match(valor):
            raise ValueError(f"{rotulo}: formato inválido (ex.: 1/1/1 ou 0/1).")
        return valor
    if nome in _DESCRICOES:
        # Espaços viram "_" e só ficam caracteres seguros: a descrição vai
        # dentro de comandos de configuração, onde aspas/espaços mudam o sentido.
        limpo = re.sub(r"[^A-Za-z0-9_.@:/-]", "", valor.replace(" ", "_"))
        if not limpo:
            raise ValueError(f"{rotulo}: use letras, números, _ . - @")
        return limpo[:64]
    if len(valor) > 100:
        raise ValueError(f"{rotulo}: valor longo demais.")
    if any(c in valor for c in ";|`"):
        raise ValueError(f"{rotulo}: caracteres ; | ` não são permitidos.")
    return valor


def montar(modelo, valores):
    """Substitui as variáveis pelos valores (já validados). Devolve a lista de linhas."""
    texto = modelo
    for chave, valor in valores.items():
        texto = texto.replace(f"[{chave}]", valor)
    return [l.rstrip() for l in texto.replace("\r\n", "\n").split("\n") if l.strip()]


def preencher_termo(modelo, tipo, termo):
    """Monta os comandos de busca preenchendo a variável de termo (e só ela)."""
    nome_var = VAR_TERMO[tipo]
    return montar(modelo, {nome_var: validar_valor(nome_var, termo)})
