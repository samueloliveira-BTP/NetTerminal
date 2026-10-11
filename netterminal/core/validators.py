"""Validação e normalização das entradas do usuário (formulários e CSV)."""
import ipaddress

from netterminal.core.models import PROTOCOLOS


def ip_valido(ip):
    """Valida IPv4/IPv6. Aceita espaços nas pontas (comuns em copy/paste)."""
    try:
        ipaddress.ip_address((ip or "").strip())
        return True
    except ValueError:
        return False


def porta_valida(valor):
    """Devolve a porta como int (1–65535) ou None se for inválida."""
    try:
        porta = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return porta if 1 <= porta <= 65535 else None


def normalizar_protocolo(texto):
    """'ssh' -> 'SSH', 'TELNET' -> 'Telnet'; None se não reconhecido."""
    t = (texto or "").strip().lower()
    for p in PROTOCOLOS:
        if p.lower() == t:
            return p
    return None


def porta_padrao(protocolo):
    return 22 if protocolo == "SSH" else 23


def texto_limpo(valor, limite=200):
    """Remove quebras de linha/controles e limita o tamanho de campos curtos
    (nome, grupo, marca), evitando quebrar a árvore e os arquivos de log."""
    texto = "".join(c for c in str(valor or "") if c.isprintable())
    return texto.strip()[:limite]
