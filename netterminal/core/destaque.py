"""Regras de realce de sintaxe definidas pelo usuário.

Cada regra pinta, no terminal, o texto que casar com o padrão:
    tipo "palavra" -> palavra inteira (ex.: "LOS" não pinta "CLOSE")
    tipo "texto"   -> qualquer ocorrência do texto (ex.: nome de cliente)
    tipo "regex"   -> expressão regular (para usuários avançados)
Sempre sem diferenciar maiúsculas/minúsculas.
"""
import re
import time
from dataclasses import dataclass

TIPOS = {"palavra": "Palavra inteira", "texto": "Contém o texto", "regex": "Expressão regular"}
_TAMANHO_MAXIMO = 200
_COR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class RegraDestaque:
    id: object
    nome: str
    padrao: str
    tipo: str = "palavra"
    cor: str = "#ffffff"
    negrito: bool = False
    ativo: bool = True
    ordem: int = 0

    @property
    def tag(self):
        return f"regra_{self.id}"


# Equivalentes às cores fixas da v2.0 — agora editáveis pelo usuário
REGRAS_PADRAO = [
    RegraDestaque(None, "Status up", "up", "palavra", "#50fa7b"),
    RegraDestaque(None, "Status down", r"\*?\bdown\b", "regex", "#ff5555"),
    RegraDestaque(None, "Não atribuído", "unassigned", "palavra", "#f1fa8c"),
    RegraDestaque(None, "Endereço IP", r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b", "regex", "#bd93f9"),
    RegraDestaque(None, "MAC (xxxx-xxxx-xxxx)", r"\b[0-9a-f]{4}[-.][0-9a-f]{4}[-.][0-9a-f]{4}\b", "regex", "#ffb86c"),
    RegraDestaque(None, "MAC (xx:xx:xx:xx:xx:xx)", r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", "regex", "#ffb86c"),
]


def compilar(padrao, tipo):
    """Converte a regra em regex compilada (sem diferenciar maiúsculas)."""
    if tipo == "palavra":
        fonte = rf"(?<![\w-]){re.escape(padrao)}(?![\w-])"
    elif tipo == "texto":
        fonte = re.escape(padrao)
    elif tipo == "regex":
        fonte = padrao
    else:
        raise ValueError(f"Tipo de regra desconhecido: {tipo}")
    return re.compile(fonte, re.IGNORECASE)


def validar(padrao, tipo, cor):
    """Levanta ValueError com mensagem amigável se a regra for inválida."""
    if not padrao or not padrao.strip():
        raise ValueError("Informe o texto/padrão a destacar.")
    if len(padrao) > _TAMANHO_MAXIMO:
        raise ValueError(f"Padrão muito longo (máximo {_TAMANHO_MAXIMO} caracteres).")
    if not _COR_RE.match(cor or ""):
        raise ValueError("Cor inválida: use o formato #RRGGBB (ou o botão Escolher).")
    try:
        regex = compilar(padrao, tipo)
    except re.error as e:
        raise ValueError(f"Expressão regular inválida: {e}") from None
    if regex.search(""):
        raise ValueError("O padrão casa com texto vazio — isso pintaria tudo.")
    if tipo == "regex":
        _recusar_regex_lenta(regex)
    return regex


def _recusar_regex_lenta(regex):
    """Proteção contra regex "catastrófica" (ex.: (a+)+$), que travaria a tela a
    cada saída do equipamento. Testa amostras PEQUENAS e crescentes: o tempo de
    uma regex exponencial explode já em ~20 caracteres, então ela é recusada
    antes de chegar num tamanho que trave (rodar direto numa amostra grande
    nunca terminaria)."""
    for caractere in ("a", "1", ".", "-", " ", ":", "/"):
        for tamanho in (8, 12, 16, 20):
            amostra = caractere * tamanho + "!\n"
            inicio = time.perf_counter()
            list(regex.finditer(amostra))
            if time.perf_counter() - inicio > 0.02:
                raise ValueError("Expressão regular lenta demais (risco de travar o terminal); simplifique o padrão.")
