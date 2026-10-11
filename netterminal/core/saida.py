"""Limpeza de saída de terminal (remove cores ANSI, backspaces e paginação),
usada quando o texto vai ser analisado em vez de exibido no terminal."""
import re

_ANSI_RE = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
_CURSOR_ESQUERDA_RE = re.compile(r"\x1b\[(\d*)D")
_PAGINACAO_RE = re.compile(r"-+\s*more.*?-+|--more--|press any key to continue", re.IGNORECASE)


def sem_ansi(texto):
    """Remove só códigos de cor/cursor — mantém o texto de paginação ("More"),
    necessário para detectar que o equipamento está esperando uma tecla."""
    return _ANSI_RE.sub("", _CURSOR_ESQUERDA_RE.sub("", texto))


def limpar(texto):
    texto = texto.replace("\r\n", "\n")
    texto = _CURSOR_ESQUERDA_RE.sub(lambda m: "\b" * (int(m.group(1)) if m.group(1) else 1), texto)
    texto = _ANSI_RE.sub("", texto)
    texto = _PAGINACAO_RE.sub("", texto)
    resultado = []
    for c in texto:
        if c in ("\b", "\x7f"):
            if resultado and resultado[-1] != "\n":
                resultado.pop()
        elif c == "\r":
            while resultado and resultado[-1] != "\n":
                resultado.pop()
        elif c in ("\x07", "\x00"):
            continue
        else:
            resultado.append(c)
    return "".join(resultado)


_FIM_DE_PROMPT = "#>$])"


def _eh_eco(linha, comando):
    """O eco de um comando aparece como "<prompt><comando>" (ex.: "OLT# show x").
    Só conta como eco se o que vem antes do comando parecer um prompt — senão
    uma linha de resultado como "state: enable" seria descartada por terminar
    com o comando "enable"."""
    if not linha.endswith(comando):
        return False
    antes = linha[:-len(comando)].rstrip()
    return antes == "" or antes[-1] in _FIM_DE_PROMPT


def linhas_com_termo(texto, termo, comandos_enviados=()):
    """Linhas que contêm o termo, ignorando o eco dos próprios comandos enviados."""
    termo = termo.lower()
    ecos = [c.strip().lower() for c in comandos_enviados if c.strip()]
    achadas = []
    for linha in limpar(texto).split("\n"):
        baixa = linha.lower().strip()
        if termo in baixa and not any(_eh_eco(baixa, eco) for eco in ecos):
            achadas.append(linha.strip())
    return achadas
