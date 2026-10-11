"""Trilha de auditoria: histórico de comandos e duração das sessões.

Arquivos (na pasta de dados):
    historico_comandos.log   data | usuário | ip (nome) | protocolo | comando
    sessoes.log              data | ip (nome) | protocolo | duração_em_segundos

Melhorias em relação à v1:
  * O usuário é o login real do Windows (usuario@maquina), não "local".
  * Senhas e outros segredos são mascarados antes de gravar.
  * Comandos de várias linhas são gravados numa linha só (separador ↵),
    para não quebrar o formato do arquivo.
  * Opcionalmente, cada registro também é enviado a um servidor syslog
    central (AUDIT_SYSLOG_HOST no .env), onde o técnico não consegue apagar.
"""
import getpass
import logging
import logging.handlers
import os
import socket
import threading
import time

from netterminal import config
from netterminal.core.redaction import mascarar_segredos
from netterminal.log_config import rotacionar_se_necessario

log = logging.getLogger(__name__)

ARQ_HISTORICO = "historico_comandos.log"
ARQ_SESSOES = "sessoes.log"
_lock_arquivos = threading.Lock()


def _descobrir_usuario():
    try:
        usuario = getpass.getuser()
    except Exception:
        usuario = "desconhecido"
    return f"{usuario}@{socket.gethostname()}"


_usuario_atual = _descobrir_usuario()

_log_syslog = logging.getLogger("netterminal.auditoria.syslog")
_log_syslog.propagate = False  # não duplica no app.log
_log_syslog.setLevel(logging.INFO)
if config.SYSLOG_HOST:
    try:
        _handler = logging.handlers.SysLogHandler(address=(config.SYSLOG_HOST, config.SYSLOG_PORTA))
        _handler.setFormatter(logging.Formatter("netterminal: %(message)s"))
        _log_syslog.addHandler(_handler)
    except OSError as e:
        log.warning(f"Syslog de auditoria indisponível: {e}")
else:
    _log_syslog.addHandler(logging.NullHandler())


def usuario_atual():
    return _usuario_atual


def caminho_historico():
    return os.path.join(config.get_data_dir(), ARQ_HISTORICO)


def caminho_sessoes():
    return os.path.join(config.get_data_dir(), ARQ_SESSOES)


def _uma_linha(texto):
    return str(texto).replace("\r\n", "\n").replace("\r", "\n").strip().replace("\n", " ↵ ")


def log_comando(ip, nome, protocolo, comando, origem=""):
    """Grava um comando no histórico. `origem`: "", "MACRO" ou "COLADO"."""
    if not comando or not str(comando).strip():
        return
    texto = _uma_linha(mascarar_segredos(comando))
    if origem:
        texto = f"[{origem}] {texto}"
    linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {_usuario_atual} | {ip} ({_uma_linha(nome)}) | {protocolo} | {texto}"
    try:
        # Várias threads (busca em paralelo) gravam ao mesmo tempo; no Windows o
        # modo "append" não é atômico entre handles, então serializamos a escrita.
        with _lock_arquivos:
            caminho = caminho_historico()
            rotacionar_se_necessario(caminho)
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
    except OSError as e:
        log.warning(f"Falha ao gravar histórico de comandos: {e}")
    _log_syslog.info(linha)


def registrar_sessao(ip, nome, protocolo, duracao_segundos):
    """Grava a duração de uma sessão encerrada (usado pelo dashboard)."""
    if duracao_segundos < 1:
        return
    try:
        with _lock_arquivos:
            caminho = caminho_sessoes()
            rotacionar_se_necessario(caminho)
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {ip} ({_uma_linha(nome)}) | {protocolo} | {int(duracao_segundos)}\n")
    except OSError as e:
        log.warning(f"Falha ao gravar duração de sessão: {e}")


def ler_historico(termo="", data_ini="", data_fim=""):
    """Devolve lista de (ts, usuario, alvo, protocolo, comando), já filtrada."""
    try:
        with open(caminho_historico(), "r", encoding="utf-8") as f:
            linhas = f.readlines()
    except FileNotFoundError:
        return []
    termo = termo.strip().lower()
    resultado = []
    for linha in linhas:
        partes = linha.rstrip("\n").split(" | ", 4)
        if len(partes) < 5:
            continue
        ts, usuario, alvo, protocolo, comando = partes
        data = ts[:10]
        if termo and termo not in alvo.lower():
            continue
        if data_ini and data < data_ini:
            continue
        if data_fim and data > data_fim:
            continue
        resultado.append((ts, usuario, alvo, protocolo, comando))
    return resultado


def ler_total_sessoes():
    """Devolve (segundos_totais, numero_de_sessoes)."""
    total, n = 0, 0
    try:
        with open(caminho_sessoes(), "r", encoding="utf-8") as f:
            for linha in f:
                partes = linha.rstrip("\n").split(" | ", 3)
                if len(partes) == 4 and partes[3].strip().isdigit():
                    total += int(partes[3])
                    n += 1
    except FileNotFoundError:
        pass
    return total, n
