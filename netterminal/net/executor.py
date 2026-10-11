"""Execução de comandos sem abrir aba (usada pela busca global de ONU).

Reaproveita as mesmas sessões SSH/Telnet da interface — portanto com a mesma
verificação de chave de host e o mesmo login seguro do Telnet — e responde
sozinho às paginações ("---- More ----") e às confirmações "{ <cr>|... }:"
da Huawei.
"""
import logging
import queue
import re
import time
from dataclasses import dataclass

from netterminal.core.saida import limpar, sem_ansi
from netterminal.net.sessao import SessaoSSH, SessaoTelnet
from netterminal.services import auditoria

log = logging.getLogger(__name__)

_PAGINACAO_RE = re.compile(r"(-+\s*more.*?-*\s*$|--more--\s*$|press any key to continue\s*$)", re.IGNORECASE)
_CONFIRMACAO_HUAWEI_RE = re.compile(r"\{\s*<cr>[^{}]*\}\s*:\s*$", re.IGNORECASE)


class Cancelado(Exception):
    pass


@dataclass
class ResultadoExecucao:
    equipamento: object
    ok: bool
    saida: str = ""
    erro: str = ""


def _ler_ate_ocioso(sessao, ocioso, limite, cancelado):
    """Acumula a saída até o equipamento ficar `ocioso` segundos sem enviar nada."""
    partes, inicio, ultimo = [], time.time(), time.time()
    while time.time() - inicio < limite:
        if cancelado is not None and cancelado.is_set():
            raise Cancelado()
        try:
            tipo, valor = sessao.eventos.get(timeout=0.2)
        except queue.Empty:
            if partes and time.time() - ultimo >= ocioso:
                break
            if not sessao.conectado:
                break
            continue
        if tipo == "dados":
            partes.append(valor)
            ultimo = time.time()
            cauda = sem_ansi("".join(partes)[-300:]).rstrip("\r\n")
            if _PAGINACAO_RE.search(cauda):
                sessao.enviar(" ")
            elif _CONFIRMACAO_HUAWEI_RE.search(cauda):
                sessao.enviar("\n")
        elif tipo in ("erro", "hostkey_mudou"):
            raise RuntimeError(valor if tipo == "erro" else "Chave SSH do equipamento mudou — conecte manualmente para revisar.")
        elif tipo == "encerrada":
            break
    return "".join(partes)


def executar(equipamento, comandos, usuario, senha, repositorio_hostkeys,
             ocioso=2.0, limite_por_comando=40, cancelado=None, origem="BUSCA"):
    """Conecta, executa os comandos em sequência e devolve ResultadoExecucao."""
    if equipamento.login_manual:
        return ResultadoExecucao(equipamento, False, erro="Login manual — não é possível executar automaticamente.")
    if equipamento.protocolo == "SSH":
        sessao = SessaoSSH(equipamento, usuario, senha, repositorio_hostkeys)
    else:
        sessao = SessaoTelnet(equipamento, usuario, senha)
    sessao.iniciar()
    saida = []
    try:
        # Espera conectar (ou falhar) e descarta o banner até o prompt
        fim = time.time() + 25
        while not sessao.conectado and time.time() < fim:
            if cancelado is not None and cancelado.is_set():
                raise Cancelado()
            try:
                tipo, valor = sessao.eventos.get(timeout=0.2)
            except queue.Empty:
                continue
            if tipo == "erro":
                return ResultadoExecucao(equipamento, False, erro=valor)
            if tipo == "hostkey_mudou":
                return ResultadoExecucao(equipamento, False, erro="Chave SSH do equipamento mudou — conecte manualmente para revisar.")
            if tipo == "ssh_legado_necessario":
                return ResultadoExecucao(equipamento, False, erro="SSH antigo — conecte uma vez pelo terminal e libere o 'SSH legado'.")
            if tipo == "dados":
                saida.append(valor)
        if not sessao.conectado:
            return ResultadoExecucao(equipamento, False, erro="Tempo esgotado ao conectar.")
        saida.append(_ler_ate_ocioso(sessao, ocioso, 15, cancelado))

        for comando in comandos:
            sessao.enviar(comando + "\n")
            auditoria.log_comando(equipamento.ip, equipamento.nome, equipamento.protocolo, comando, origem=origem)
            saida.append(_ler_ate_ocioso(sessao, ocioso, limite_por_comando, cancelado))
        return ResultadoExecucao(equipamento, True, saida=limpar("".join(saida)))
    except Cancelado:
        return ResultadoExecucao(equipamento, False, erro="Cancelado.")
    except Exception as e:
        log.warning(f"Execução automática em {equipamento.ip} falhou: {e}")
        return ResultadoExecucao(equipamento, False, saida=limpar("".join(saida)), erro=str(e))
    finally:
        sessao.fechar()
