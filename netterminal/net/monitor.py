"""Monitor de status: verifica periodicamente se cada equipamento responde
e mede a latência.

Método padrão: PING ICMP (net/icmp.py). O método antigo — abrir e fechar uma
conexão TCP na porta de login a cada ciclo — fazia equipamentos Huawei
bloquearem o IP do técnico por suspeita de força bruta, e enchia os logs das
OLTs de conexões sem login. TCP continua disponível como alternativa
(MONITOR_METHOD=tcp no .env) e é usado automaticamente para IPv6.

Os testes rodam em paralelo (pool de threads).
"""
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from netterminal.net import icmp

log = logging.getLogger(__name__)


def testar_porta(ip, porta, timeout):
    """Teste TCP. Devolve (online: bool, latencia_ms: float | None)."""
    inicio = time.perf_counter()
    try:
        with socket.create_connection((ip, int(porta)), timeout=timeout):
            return True, round((time.perf_counter() - inicio) * 1000, 1)
    except (OSError, ValueError):
        return False, None


def testar_equipamento(ip, porta, timeout, metodo="icmp"):
    """Ping ICMP quando possível; TCP se configurado ou se o ICMP não se aplica."""
    if metodo == "icmp" and icmp.disponivel_para(ip):
        try:
            return icmp.ping(ip, int(timeout * 1000))
        except OSError as e:
            log.debug(f"Ping ICMP indisponível para {ip} ({e}); usando TCP.")
    return testar_porta(ip, porta, timeout)


class MonitorStatus:
    def __init__(self, db, intervalo, workers, timeout, ao_atualizar=None, metodo="icmp"):
        """ao_atualizar é chamado na thread do monitor ao fim de cada ciclo —
        quem usa na interface deve repassar para a thread principal (after)."""
        self._db = db
        self._intervalo = intervalo
        self._workers = workers
        self._timeout = timeout
        self.metodo = metodo
        self._ao_atualizar = ao_atualizar
        self._evento_forcar = threading.Event()
        self._parar = threading.Event()
        # {olt_id(int): {"online": bool, "ts": str, "latencia_ms": float|None}}
        self.status = db.carregar_status()
        self.mudancas_recentes = set()

    def iniciar(self):
        threading.Thread(target=self._loop, daemon=True, name="monitor-status").start()

    def forcar_agora(self):
        self._evento_forcar.set()

    def parar(self):
        self._parar.set()
        self._evento_forcar.set()

    def executar_ciclo(self):
        equipamentos = self._db.listar_equipamentos()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            resultados = list(pool.map(
                lambda e: testar_equipamento(e.ip, e.porta, self._timeout, self.metodo), equipamentos))

        novo_status, mudou, para_salvar = {}, set(), []
        for eq, (online, latencia) in zip(equipamentos, resultados):
            anterior = self.status.get(eq.id)
            if anterior is not None and anterior["online"] != online:
                mudou.add(eq.id)
                log.info(f"Status mudou: {eq.nome} ({eq.ip}) agora está {'ONLINE' if online else 'OFFLINE'}")
            novo_status[eq.id] = {"online": online, "ts": timestamp, "latencia_ms": latencia}
            para_salvar.append((eq.id, online, timestamp, latencia))

        # Troca de referência é atômica: a interface nunca vê um dicionário pela metade
        self.status = novo_status
        self.mudancas_recentes = mudou
        self._db.salvar_status_lote(para_salvar)

    def _loop(self):
        while not self._parar.is_set():
            try:
                self.executar_ciclo()
                if self._ao_atualizar:
                    self._ao_atualizar()
            except Exception as e:
                log.warning(f"Erro no monitor de status: {e}")
            self._evento_forcar.wait(timeout=self._intervalo)
            self._evento_forcar.clear()
