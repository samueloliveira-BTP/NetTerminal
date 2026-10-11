"""Testes de compatibilidade: SSH legado (equipamentos antigos) e monitor por ping ICMP."""
import os
import socket
import sqlite3
import sys
import tempfile
import time
import unittest

import paramiko
from cryptography.fernet import Fernet

from netterminal.core.models import Equipamento
from netterminal.data.database import Database
from netterminal.net import executor, icmp
from netterminal.net.monitor import MonitorStatus, testar_equipamento
from netterminal.net.sessao import SessaoSSH
from netterminal.security.crypto import Cifrador
from netterminal.security.hostkeys import RepositorioHostKeys, nome_host
from tests.servidores_fake import SENHA_TESTE, USUARIO_TESTE, criar_servidor_ssh_antigo
from tests.test_rede import coletar


class TestSSHLegado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = criar_servidor_ssh_antigo()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.parar()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = RepositorioHostKeys(os.path.join(self._tmp.name, "known_hosts"))

    def tearDown(self):
        self._tmp.cleanup()

    def _eq(self, legado):
        return Equipamento(1, "olt-zte-antiga", "127.0.0.1", "SSH", self.servidor.porta, marca="ZTE", ssh_legado=legado)

    def test_sem_legado_pede_liberacao(self):
        s = SessaoSSH(self._eq(False), USUARIO_TESTE, SENHA_TESTE, self.repo)
        s.iniciar()
        eventos = coletar(s, ate_tipo="ssh_legado_necessario")
        self.assertEqual(eventos[-1][0], "ssh_legado_necessario")
        self.assertNotIn("conectado", [t for t, _ in eventos])

    def test_com_legado_conecta_e_verifica_chave(self):
        for tentativa in range(2):  # 2ª vez: confere a chave já registrada no known_hosts
            s = SessaoSSH(self._eq(True), USUARIO_TESTE, SENHA_TESTE, self.repo)
            s.iniciar()
            eventos = coletar(s, contendo="OLT#")
            self.assertIn("conectado", [t for t, _ in eventos], f"tentativa {tentativa + 1}: {eventos}")
            s.enviar("display version\n")
            self.assertIn("eco:display version", "".join(v for t, v in coletar(s, contendo="eco:display") if t == "dados"))
            s.fechar()
        self.assertIsNotNone(self.repo.fingerprint_registrado(nome_host("127.0.0.1", self.servidor.porta)))

    def test_legado_continua_bloqueando_chave_trocada(self):
        self.repo.adicionar(nome_host("127.0.0.1", self.servidor.porta), paramiko.RSAKey.generate(2048))
        s = SessaoSSH(self._eq(True), USUARIO_TESTE, SENHA_TESTE, self.repo)
        s.iniciar()
        self.assertEqual(coletar(s, ate_tipo="hostkey_mudou")[-1][0], "hostkey_mudou")

    def test_kex_legado_prefere_group14(self):
        # ZTE_SSH.1.0 real anuncia group16-sha512 mas derruba a conexão se ele for escolhido
        from netterminal.net.ssh_legado import TransportLegado
        kex = list(TransportLegado._preferred_kex)
        self.assertLess(kex.index("diffie-hellman-group14-sha256"), kex.index("diffie-hellman-group16-sha512"))
        self.assertEqual(set(kex), set(paramiko.Transport._preferred_kex))  # só reordena, não adiciona nada fraco

    def test_padrao_global_nao_foi_alterado(self):
        self.assertNotIn("ssh-rsa", paramiko.Transport._preferred_keys)
        self.assertNotIn("ssh-rsa", paramiko.Transport._key_info)
        self.assertNotIn("ssh-rsa", paramiko.RSAKey.HASHES)

    def test_busca_global_informa_ssh_antigo(self):
        res = executor.executar(self._eq(False), ["x"], USUARIO_TESTE, SENHA_TESTE, self.repo)
        self.assertFalse(res.ok)
        self.assertIn("SSH antigo", res.erro)


class TestBancoSSHLegado(unittest.TestCase):
    def test_coluna_migrada_e_persistida(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "olts.db")
            conn = sqlite3.connect(caminho)  # banco no formato antigo, sem a coluna
            conn.execute("CREATE TABLE olts (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, ip TEXT NOT NULL, "
                         "protocolo TEXT NOT NULL, usuario TEXT NOT NULL, senha TEXT NOT NULL, porta INTEGER NOT NULL)")
            conn.execute("INSERT INTO olts (nome, ip, protocolo, usuario, senha, porta) VALUES ('Z','10.0.0.9','SSH','','',22)")
            conn.commit()
            conn.close()
            db = Database(caminho, Cifrador(Fernet.generate_key()))
            eq = db.listar_equipamentos()[0]
            self.assertFalse(eq.ssh_legado)
            db.definir_ssh_legado(eq.id, True)
            self.assertTrue(db.obter_equipamento(eq.id).ssh_legado)
            eq = db.obter_equipamento(eq.id)
            eq.nome = "Z2"
            db.atualizar_equipamento(eq)
            self.assertTrue(db.obter_equipamento(eq.id).ssh_legado)
            db.fechar()


@unittest.skipUnless(sys.platform == "win32", "ping nativo só no Windows")
class TestMonitorICMP(unittest.TestCase):
    def test_ping(self):
        self.assertTrue(icmp.disponivel_para("127.0.0.1"))
        self.assertFalse(icmp.disponivel_para("::1"))  # IPv6 usa TCP
        ok, latencia = icmp.ping("127.0.0.1")
        self.assertTrue(ok)
        self.assertIsNotNone(latencia)
        self.assertEqual(icmp.ping("192.0.2.1", 300), (False, None))  # faixa de documentação: nunca responde

    def test_monitor_icmp_nao_abre_conexao_na_porta_de_login(self):
        ouvinte = socket.socket()
        ouvinte.bind(("127.0.0.1", 0))
        ouvinte.listen(5)
        ouvinte.settimeout(0.5)
        porta = ouvinte.getsockname()[1]
        with tempfile.TemporaryDirectory() as pasta:
            db = Database(os.path.join(pasta, "olts.db"), Cifrador(Fernet.generate_key()))
            eid = db.adicionar_equipamento(Equipamento(None, "x", "127.0.0.1", "Telnet", porta))
            monitor = MonitorStatus(db, 15, 4, 1.0, metodo="icmp")
            monitor.executar_ciclo()
            self.assertTrue(monitor.status[eid]["online"])
            with self.assertRaises(socket.timeout):
                ouvinte.accept()  # ninguém conectou na "porta de login"
            # Modo tcp (antigo) continua disponível e conecta na porta
            MonitorStatus(db, 15, 4, 1.0, metodo="tcp").executar_ciclo()
            conexao, _ = ouvinte.accept()
            conexao.close()
            db.fechar()
        ouvinte.close()

    def test_ipv6_usa_tcp(self):
        inicio = time.time()
        self.assertEqual(testar_equipamento("::1", 1, 0.5, "icmp")[0], False)
        self.assertLess(time.time() - inicio, 3)


if __name__ == "__main__":
    unittest.main()
