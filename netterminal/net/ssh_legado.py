"""Compatibilidade com equipamentos de SSH antigo (ex.: ZTE com "ZTE_SSH.1.0").

Esses equipamentos só oferecem chave de host `ssh-rsa` assinada com SHA-1,
que o paramiko 4+ removeu dos padrões por ser fraca. Aqui criamos um
Transport PRÓPRIO que aceita `ssh-rsa`/SHA-1 — usado SOMENTE nas conexões com
equipamentos marcados como "SSH legado" (opção por equipamento). Todas as
outras conexões continuam com o paramiko padrão, sem nenhuma alteração global.

Mesmo legado, o SSH continua cifrado e com a verificação de chave de host
(known_hosts) — é muito melhor do que cair para Telnet.
"""
import paramiko
from cryptography.hazmat.primitives import hashes

TIPO_LEGADO = "ssh-rsa"


class RSAKeyLegado(paramiko.RSAKey):
    """RSAKey que também verifica (e, no servidor de testes, assina) ssh-rsa/SHA-1."""
    HASHES = dict(paramiko.RSAKey.HASHES, **{
        "ssh-rsa": hashes.SHA1,
        "ssh-rsa-cert-v01@openssh.com": hashes.SHA1,
    })


def _kex_legado():
    """Mesma lista do paramiko, mas com diffie-hellman-group14-sha256 ANTES do
    group16-sha512: firmwares antigos (ex.: ZTE_SSH.1.0) anunciam o group16 mas
    derrubam a conexão quando ele é escolhido (comportamento visto em campo)."""
    padrao = list(paramiko.Transport._preferred_kex)
    preferido = "diffie-hellman-group14-sha256"
    if preferido in padrao:
        padrao.remove(preferido)
        posicao = next((i for i, k in enumerate(padrao) if k.startswith("diffie-hellman")), len(padrao))
        padrao.insert(posicao, preferido)
    return tuple(padrao)


class TransportLegado(paramiko.Transport):
    """Transport que aceita ssh-rsa como ÚLTIMA opção (só é escolhido se o
    equipamento não oferecer nada mais moderno)."""
    _preferred_keys = tuple(paramiko.Transport._preferred_keys) + (TIPO_LEGADO,)
    _key_info = dict(paramiko.Transport._key_info, **{TIPO_LEGADO: RSAKeyLegado})
    _preferred_kex = _kex_legado()


def eh_erro_de_algoritmo_legado(erro):
    """True se a falha de conexão indica equipamento com SSH antigo."""
    texto = str(erro).lower()
    return isinstance(erro, paramiko.SSHException) and (
        "no acceptable host key" in texto or "incompatible ssh peer" in texto)
