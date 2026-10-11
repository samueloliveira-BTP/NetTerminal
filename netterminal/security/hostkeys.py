"""Verificação de chave de host SSH (proteção contra man-in-the-middle).

Política "TOFU" (Trust On First Use), a mesma do OpenSSH/PuTTY:
  * Primeira conexão a um equipamento: a chave é registrada em known_hosts.
  * Conexões seguintes: a chave PRECISA ser a mesma. Se mudou, o paramiko
    levanta BadHostKeyException e a interface pergunta ao técnico se a troca
    é legítima (ex.: equipamento substituído) antes de seguir.

Antes, o app usava AutoAddPolicy sem guardar nada: aceitava qualquer chave,
sempre — inclusive a de um atacante interceptando a conexão.
"""
import base64
import hashlib
import logging
import os
import threading

import paramiko

log = logging.getLogger(__name__)


def fingerprint_sha256(chave):
    """Formato igual ao do OpenSSH: SHA256:base64-sem-padding."""
    digest = hashlib.sha256(chave.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def nome_host(ip, porta):
    """Mesmo formato que o paramiko usa para procurar no known_hosts."""
    porta = int(porta)
    return ip if porta == 22 else f"[{ip}]:{porta}"


class RepositorioHostKeys:
    """Arquivo known_hosts do app, seguro para várias abas conectando ao mesmo tempo."""

    def __init__(self, caminho):
        self.caminho = caminho
        self._lock = threading.Lock()

    def _ler(self):
        chaves = paramiko.HostKeys()
        if os.path.exists(self.caminho):
            chaves.load(self.caminho)
        return chaves

    def preparar_cliente(self, cliente, ao_registrar=None):
        """Carrega as chaves conhecidas no cliente e instala a política TOFU."""
        with self._lock:
            if os.path.exists(self.caminho):
                cliente.load_system_host_keys(self.caminho)
        cliente.set_missing_host_key_policy(_PoliticaTOFU(self, ao_registrar))

    def adicionar(self, hostname, chave):
        with self._lock:
            chaves = self._ler()
            chaves.add(hostname, chave.get_name(), chave)
            chaves.save(self.caminho)

    def remover(self, hostname):
        with self._lock:
            chaves = self._ler()
            if hostname in chaves:
                del chaves[hostname]
                chaves.save(self.caminho)

    def fingerprint_registrado(self, hostname):
        with self._lock:
            entrada = self._ler().lookup(hostname)
        if not entrada:
            return None
        return ", ".join(fingerprint_sha256(k) for k in entrada.values())


class _PoliticaTOFU(paramiko.MissingHostKeyPolicy):
    def __init__(self, repositorio, ao_registrar=None):
        self._repo = repositorio
        self._ao_registrar = ao_registrar

    def missing_host_key(self, client, hostname, key):
        self._repo.adicionar(hostname, key)
        client.get_host_keys().add(hostname, key.get_name(), key)
        fp = fingerprint_sha256(key)
        log.info(f"Nova chave de host registrada para {hostname}: {key.get_name()} {fp}")
        if self._ao_registrar:
            self._ao_registrar(hostname, key.get_name(), fp)
