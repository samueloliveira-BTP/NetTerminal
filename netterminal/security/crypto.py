"""Chave mestra do app e criptografia (Fernet) das senhas salvas no banco.

Arquivos na pasta de dados:
    security.key.dpapi  -> chave Fernet protegida pelo DPAPI (formato atual)
    security.key        -> chave em texto puro (formato antigo, v1.x)

Na primeira execução da v2, a chave antiga é migrada automaticamente para o
formato DPAPI e o arquivo em texto puro é removido (somente depois de
confirmar que a versão protegida abre corretamente).
"""
import logging
import os
import time

from cryptography.fernet import Fernet, InvalidToken

from netterminal.security import dpapi

ARQ_CHAVE_LEGADA = "security.key"
ARQ_CHAVE_DPAPI = "security.key.dpapi"
_PREFIXO_FERNET = "gAAAAA"  # todo token Fernet começa assim (versão 0x80 + timestamp)

log = logging.getLogger(__name__)


class ChaveIndisponivelError(Exception):
    """A chave existe mas não pôde ser aberta (ex.: perfil do Windows recriado)."""


def parece_token_fernet(valor):
    return bool(valor) and str(valor).startswith(_PREFIXO_FERNET)


def _gravar_atomico(caminho, dados):
    temporario = caminho + ".tmp"
    with open(temporario, "wb") as f:
        f.write(dados)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporario, caminho)


def carregar_ou_criar_chave(pasta):
    """Devolve a chave Fernet (bytes), migrando/criando quando necessário."""
    caminho_dpapi = os.path.join(pasta, ARQ_CHAVE_DPAPI)
    caminho_legado = os.path.join(pasta, ARQ_CHAVE_LEGADA)

    if os.path.exists(caminho_dpapi):
        try:
            with open(caminho_dpapi, "rb") as f:
                return dpapi.desproteger(f.read())
        except OSError as e:
            raise ChaveIndisponivelError(
                "A chave de criptografia existe, mas não pode ser aberta por este usuário do Windows."
            ) from e

    if os.path.exists(caminho_legado):
        with open(caminho_legado, "rb") as f:
            chave = f.read().strip()
        Fernet(chave)  # valida o formato antes de migrar
        if dpapi.disponivel():
            _gravar_atomico(caminho_dpapi, dpapi.proteger(chave))
            with open(caminho_dpapi, "rb") as f:
                if dpapi.desproteger(f.read()) != chave:
                    raise ChaveIndisponivelError("Falha ao verificar a chave migrada para DPAPI.")
            os.remove(caminho_legado)
            log.info("Chave mestra migrada para DPAPI; arquivo em texto puro removido.")
        return chave

    chave = Fernet.generate_key()
    if dpapi.disponivel():
        _gravar_atomico(caminho_dpapi, dpapi.proteger(chave))
    else:
        _gravar_atomico(caminho_legado, chave)
        os.chmod(caminho_legado, 0o600)
    log.info("Nova chave mestra gerada (primeira execução).")
    return chave


def descartar_chave_inacessivel(pasta):
    """Renomeia (não apaga) a chave que não abre mais, para gerar uma nova.
    As senhas cifradas com ela precisarão ser cadastradas de novo."""
    caminho = os.path.join(pasta, ARQ_CHAVE_DPAPI)
    destino = f"{caminho}.inacessivel_{time.strftime('%Y%m%d_%H%M%S')}"
    os.replace(caminho, destino)
    log.warning(f"Chave inacessível preservada em {destino}; uma nova chave será gerada.")


class Cifrador:
    """Cifra/decifra textos curtos (senhas) com Fernet (AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, chave):
        self._fernet = Fernet(chave)

    def cifrar(self, texto):
        if not texto:
            return ""
        return self._fernet.encrypt(texto.encode("utf-8")).decode("ascii")

    def decifrar(self, valor):
        """Devolve o texto puro.

        - Valor vazio -> "".
        - Token Fernet válido -> texto decifrado.
        - Token Fernet que NÃO abre com esta chave -> "" (e loga erro). Antes, o
          app devolvia o próprio token e o enviava como senha ao equipamento.
        - Texto que não é token (senha salva em versões muito antigas) -> devolvido
          como está; o Database migra esses valores para cifrado na inicialização.
        """
        if not valor:
            return ""
        try:
            return self._fernet.decrypt(valor.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError):
            if parece_token_fernet(valor):
                log.error("Senha salva não pôde ser decifrada com a chave atual (chave trocada?).")
                return ""
            return valor
