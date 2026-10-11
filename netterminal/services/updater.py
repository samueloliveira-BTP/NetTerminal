"""Atualização automática segura.

Fluxo: o app consulta UPDATE_CHECK_URL (JSON) e, se houver versão mais nova,
baixa o instalador e só o executa depois de TODAS as verificações:

  1. HTTPS obrigatório na consulta, no download e em qualquer redirecionamento.
  2. O host do download precisa ser o mesmo da consulta (ou estar em
     UPDATE_ALLOWED_HOSTS).
  3. SHA-256 obrigatório no JSON e conferido no arquivo baixado.
  4. Somente .exe ou .msi.
  5. (Opcional, recomendado) Assinatura Authenticode válida, conferida pelo
     Windows, com UPDATE_REQUIRE_SIGNATURE=true e UPDATE_SIGNER_SUBJECT.

Formato esperado do JSON:
    {"versao": "2.1.0", "url_download": "https://.../NetTerminal-2.1.0.exe",
     "sha256": "<64 hex>", "obrigatoria": false, "notas": "texto opcional"}
"""
import hashlib
import json
import logging
import os
import re
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass

from netterminal import APP_VERSION, config

log = logging.getLogger(__name__)

_TAMANHO_MAXIMO_JSON = 64 * 1024
_TAMANHO_MAXIMO_INSTALADOR = 500 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EXTENSOES_PERMITIDAS = (".exe", ".msi")


class AtualizacaoRecusada(Exception):
    """Alguma verificação de segurança falhou."""


@dataclass
class InfoAtualizacao:
    versao: str
    url_download: str
    sha256: str
    obrigatoria: bool = False
    notas: str = ""


def comparar_versoes(v1, v2):
    """True se v1 > v2, comparando numericamente (1.10.0 > 1.9.0)."""
    try:
        return [int(p) for p in v1.strip().split(".")] > [int(p) for p in v2.strip().split(".")]
    except (ValueError, AttributeError):
        return False


class _SomenteHttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme.lower() != "https":
            raise AtualizacaoRecusada(f"Redirecionamento para URL não-HTTPS recusado: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _contexto_tls():
    """TLS com validação COMPLETA (cadeia de certificados + nome do host), usando
    o repositório de certificados do Windows. Só desliga o modo VERIFY_X509_STRICT
    (padrão do Python 3.13+), que recusa cadeias válidas e aceitas por navegadores
    — inclusive a do GitHub ("Missing Authority Key Identifier")."""
    contexto = ssl.create_default_context()
    contexto.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return contexto


_opener = urllib.request.build_opener(_SomenteHttpsRedirect(), urllib.request.HTTPSHandler(context=_contexto_tls()))


def _exigir_https(url):
    partes = urllib.parse.urlparse(url or "")
    if partes.scheme.lower() != "https" or not partes.hostname:
        raise AtualizacaoRecusada(f"URL precisa ser HTTPS: {url!r}")
    return partes


def _host_permitido(url_download, url_consulta):
    host = _exigir_https(url_download).hostname.lower()
    permitidos = set(config.UPDATE_ALLOWED_HOSTS) | {_exigir_https(url_consulta).hostname.lower()}
    if host not in permitidos:
        raise AtualizacaoRecusada(f"Host de download não permitido: {host}")


def interpretar_resposta(dados, url_consulta):
    """Valida o JSON do servidor. Devolve InfoAtualizacao ou levanta AtualizacaoRecusada."""
    if not isinstance(dados, dict):
        raise AtualizacaoRecusada("Resposta do servidor de atualização não é um objeto JSON.")
    info = InfoAtualizacao(
        versao=str(dados.get("versao", "")).strip(),
        url_download=str(dados.get("url_download", "")).strip(),
        sha256=str(dados.get("sha256", "")).strip().lower(),
        obrigatoria=bool(dados.get("obrigatoria", False)),
        notas=str(dados.get("notas", ""))[:1000],
    )
    _host_permitido(info.url_download, url_consulta)
    if not _SHA256_RE.match(info.sha256):
        raise AtualizacaoRecusada("Atualização sem SHA-256 válido — recusada.")
    nome = os.path.basename(urllib.parse.urlparse(info.url_download).path).lower()
    if not nome.endswith(_EXTENSOES_PERMITIDAS):
        raise AtualizacaoRecusada(f"Tipo de instalador não permitido: {nome!r}")
    return info


def verificar_atualizacao():
    """Devolve InfoAtualizacao se houver versão mais nova; None caso contrário
    (sem URL configurada, sem novidade, servidor fora ou resposta recusada)."""
    url = config.UPDATE_CHECK_URL
    if not url:
        return None
    try:
        _exigir_https(url)
        with _opener.open(url, timeout=8) as resp:
            dados = json.loads(resp.read(_TAMANHO_MAXIMO_JSON).decode("utf-8"))
        info = interpretar_resposta(dados, url)
        if comparar_versoes(info.versao, APP_VERSION):
            return info
    except AtualizacaoRecusada as e:
        log.error(f"Atualização recusada: {e}")
    except Exception as e:
        log.info(f"Verificação de atualização indisponível: {e}")
    return None


def _sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def verificar_assinatura(caminho):
    """Confere a assinatura Authenticode pelo próprio Windows.
    O caminho vai por variável de ambiente (nunca concatenado no comando)."""
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:NT_ARQUIVO; "
              "Write-Output $s.Status; Write-Output $s.SignerCertificate.Subject")
    ambiente = dict(os.environ, NT_ARQUIVO=caminho)
    saida = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=60, env=ambiente,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.splitlines()
    status = saida[0].strip() if saida else ""
    assunto = saida[1].strip() if len(saida) > 1 else ""
    if status != "Valid":
        raise AtualizacaoRecusada(f"Assinatura digital inválida ou ausente (status: {status or 'desconhecido'}).")
    if config.UPDATE_SIGNER_SUBJECT and config.UPDATE_SIGNER_SUBJECT.lower() not in assunto.lower():
        raise AtualizacaoRecusada("Instalador assinado por um certificado diferente do esperado.")


def baixar_e_verificar(info):
    """Baixa o instalador para uma pasta temporária exclusiva e verifica tudo.
    Devolve o caminho do arquivo ou levanta AtualizacaoRecusada."""
    _exigir_https(info.url_download)
    nome = os.path.basename(urllib.parse.urlparse(info.url_download).path)
    destino = os.path.join(tempfile.mkdtemp(prefix="netterminal_update_"), nome)
    baixados = 0
    with _opener.open(info.url_download, timeout=30) as resp, open(destino, "wb") as f:
        while True:
            bloco = resp.read(65536)
            if not bloco:
                break
            baixados += len(bloco)
            if baixados > _TAMANHO_MAXIMO_INSTALADOR:
                raise AtualizacaoRecusada("Instalador maior que o limite permitido.")
            f.write(bloco)

    if _sha256_arquivo(destino) != info.sha256:
        os.remove(destino)
        raise AtualizacaoRecusada("O SHA-256 do instalador baixado não confere.")
    if config.UPDATE_REQUIRE_SIGNATURE:
        try:
            verificar_assinatura(destino)
        except AtualizacaoRecusada:
            os.remove(destino)
            raise
    log.info(f"Instalador da versão {info.versao} baixado e verificado: {destino}")
    return destino


def comando_instalacao(caminho, executavel_para_reabrir=None):
    """Monta a linha de comando da instalação.

    .msi -> instalação silenciosa (/passive: só barra de progresso, sem
    perguntas), log em %USERPROFILE%\\.olt_manager\\update_msi.log e, ao
    terminar com sucesso, o app é aberto de novo automaticamente.
    """
    if not caminho.lower().endswith(".msi"):
        return [caminho]
    log_msi = os.path.join(config.get_data_dir(), "update_msi.log")
    comando = ["cmd.exe", "/c", "msiexec.exe", "/i", caminho, "/passive", "/norestart", "/l*v", log_msi]
    if executavel_para_reabrir:
        comando += ["&&", "start", "", executavel_para_reabrir]
    return comando


def executar_instalador(caminho, executavel_para_reabrir=None):
    subprocess.Popen(comando_instalacao(caminho, executavel_para_reabrir), close_fds=True,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log.info(f"Instalador de atualização iniciado: {caminho}")
