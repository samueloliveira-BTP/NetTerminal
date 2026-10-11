"""Mascaramento de segredos antes de qualquer gravação em log.

O histórico de comandos é uma trilha de auditoria — ele precisa mostrar O QUE
foi feito, mas nunca pode guardar senhas, communities SNMP ou chaves.
"""
import re

MASCARA = "******"

# Palavra-chave sensível seguida de espaço/=/: -> tudo que vem depois na linha
# é mascarado (ex.: "local-user x password irreversible-cipher ABC" vira
# "local-user x password ******"). É proposital mascarar "demais": num log de
# auditoria, perder um detalhe é melhor do que vazar um segredo.
_PALAVRAS_SENSIVEIS = (
    r"password|passwd|senha|secret|cipher|community|pre-shared-key|psk|"
    r"key-string|auth-key|authentication-key|md5|shared-secret|private-key"
)
_SEGREDO_RE = re.compile(rf"\b({_PALAVRAS_SENSIVEIS})\b([\s=:]+)(\S.*)$", re.IGNORECASE)

# Última linha recebida do equipamento que indica que ele está pedindo senha.
PROMPT_SENHA_RE = re.compile(r"(password|passwd|senha|passcode|pin)\s*:?\s*$", re.IGNORECASE)


def mascarar_segredos(texto):
    """Mascara segredos linha a linha. Seguro para chamar com qualquer texto."""
    if not texto:
        return texto
    linhas = []
    for linha in str(texto).splitlines() or [""]:
        linhas.append(_SEGREDO_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", linha))
    return "\n".join(linhas)


def eh_prompt_de_senha(ultima_linha):
    return bool(PROMPT_SENHA_RE.search((ultima_linha or "").rstrip()))
