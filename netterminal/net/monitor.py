"""Monitor de status: testa periodicamente se a porta de cada equipamento
responde e mede a latência da conexão TCP.

Os testes rodam em paralelo (pool de threads). Antes eram sequenciais com
1,5 s de timeout cada: com 30 equipamentos fora do ar, um "ciclo de 15 s"
levava mais de 1 minuto.
"""
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)


def testar_porta(ip, porta, timeout):
    """Devolve (online: bool, latencia_ms: float | None)."""
    inicio = time.perf_counter()
    try:
        with socket.create_connection((ip, int(porta)), timeout=timeout):
            return True, round((time.perf_counter() - inicio) * 1000, 1)
    except (OSError, ValueError):
        return False, None


class MonitorStatus:
    def __init__(self, db, intervalo, workers, timeout, ao_atualizar=None):
        """ao_atualizar é chamado na thread do monitor ao fim de cada ciclo —
        quem usa na interface deve repassar para a thread principal (after)."""
        self._db = db
        self._intervalo = intervalo
        self._workers = workers
        self._timeout = timeout
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
            resultados = list(pool.map(lambda e: testar_porta(e.ip, e.porta, self._timeout), equipamentos))

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
