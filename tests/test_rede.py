"""Testes de rede usando servidores falsos em 127.0.0.1."""
import os
import socket
import tempfile
import time
import unittest

import paramiko
from cryptography.fernet import Fernet

from netterminal.core.models import Equipamento
from netterminal.data.database import Database
from netterminal.net.monitor import MonitorStatus, testar_porta
from netterminal.net.sessao import SessaoSSH, SessaoTelnet
from netterminal.net.telnet import FiltroIAC
from netterminal.security.crypto import Cifrador
from netterminal.security.hostkeys import RepositorioHostKeys, nome_host
from tests.servidores_fake import SENHA_TESTE, USUARIO_TESTE, ServidorSSHFake, ServidorTelnetFake


def coletar(sessao, ate_tipo=None, contendo=None, timeout=10):
    """Lê eventos da sessão até achar o tipo/texto esperado."""
    eventos, fim = [], time.time() + timeout
    while time.time() < fim:
        try:
            tipo, valor = sessao.eventos.get(timeout=0.2)
        except Exception:
            continue
        eventos.append((tipo, valor))
        if ate_tipo and tipo == ate_tipo:
            break
        if contendo and contendo in "".join(v for t, v in eventos if t == "dados"):
            break
    return eventos


class TestFiltroIAC(unittest.TestCase):
    def test_remove_negociacao_mesmo_dividida(self):
        f = FiltroIAC()
        self.assertEqual(f.filtrar(b"ab\xff"), b"ab")
        self.assertEqual(f.filtrar(b"\xfb\x01cd"), b"cd")
        self.assertEqual(f.filtrar(b"\xff\xff"), b"\xff")
        self.assertEqual(f.filtrar(b"x\xff\xfa\x18\x01\xff\xf0y"), b"xy")


class TestSessaoSSH(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ServidorSSHFake()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.parar()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = RepositorioHostKeys(os.path.join(self._tmp.name, "known_hosts"))
        self.eq = Equipamento(1, "OLT-teste", "127.0.0.1", "SSH", self.servidor.porta)

    def tearDown(self):
        self._tmp.cleanup()

    def test_conecta_registra_chave_e_troca_comandos(self):
        s = SessaoSSH(self.eq, USUARIO_TESTE, SENHA_TESTE, self.repo)
        s.iniciar()
        eventos = coletar(s, contendo="OLT#")
        tipos = [t for t, _ in eventos]
        self.assertIn("conectado", tipos)
        self.assertTrue(any(t == "aviso" and "registrada" in v for t, v in eventos))
        self.assertIsNotNone(self.repo.fingerprint_registrado(nome_host("127.0.0.1", self.servidor.porta)))
        s.enviar("display version\n")
        eventos = coletar(s, contendo="eco:display version")
        self.assertIn("eco:display version", "".join(v for t, v in eventos if t == "dados"))
        s.enviar("quit\n")
        self.assertIn("encerrada", [t for t, _ in coletar(s, ate_tipo="encerrada")])
        self.assertFalse(s.conectado)

    def test_senha_errada(self):
        s = SessaoSSH(self.eq, USUARIO_TESTE, "senha-errada", self.repo)
        s.iniciar()
        eventos = coletar(s, ate_tipo="erro")
        self.assertEqual(eventos[-1][0], "erro")
        self.assertTrue(s.falhou)

    def test_chave_alterada_bloqueia_conexao(self):
        host = nome_host("127.0.0.1", self.servidor.porta)
        self.repo.adicionar(host, paramiko.RSAKey.generate(2048))  # chave "antiga" diferente
        s = SessaoSSH(self.eq, USUARIO_TESTE, SENHA_TESTE, self.repo)
        s.iniciar()
        eventos = coletar(s, ate_tipo="hostkey_mudou")
        self.assertEqual(eventos[-1][0], "hostkey_mudou")
        self.assertNotIn("conectado", [t for t, _ in eventos])
        info = eventos[-1][1]
        self.assertNotEqual(info["esperada"], info["recebida"])
        # Técnico aceita a troca -> conecta normalmente
        self.repo.remover(host)
        s2 = SessaoSSH(self.eq, USUARIO_TESTE, SENHA_TESTE, self.repo)
        s2.iniciar()
        self.assertIn("conectado", [t for t, _ in coletar(s2, ate_tipo="conectado")])
        s2.fechar()


class TestSessaoTelnet(unittest.TestCase):
    def test_login_automatico_so_com_prompt(self):
        servidor = ServidorTelnetFake()
        eq = Equipamento(2, "SW-teste", "127.0.0.1", "Telnet", servidor.porta)
        s = SessaoTelnet(eq, USUARIO_TESTE, SENHA_TESTE)
        s.iniciar()
        eventos = coletar(s, contendo="OLT>")
        self.assertTrue(any(t == "aviso" and "texto claro" in v for t, v in eventos))
        s.enviar("show vlan\n")
        coletar(s, contendo="eco:show vlan")
        s.fechar()
        servidor.parar()
        self.assertEqual(servidor.recebido[0], ("usuario", USUARIO_TESTE.encode()))
        self.assertEqual(servidor.recebido[1], ("senha", SENHA_TESTE.encode()))
        self.assertIn(("comando", b"show vlan"), servidor.recebido)

    def test_nao_envia_senha_sem_prompt(self):
        servidor = ServidorTelnetFake(pedir_senha=False)
        eq = Equipamento(3, "SW-teste", "127.0.0.1", "Telnet", servidor.porta)
        s = SessaoTelnet(eq, USUARIO_TESTE, SENHA_TESTE)
        s.iniciar()
        eventos = coletar(s, timeout=9, ate_tipo=None, contendo="OLT>")
        eventos += coletar(s, timeout=8)
        s.fechar()
        servidor.parar()
        self.assertTrue(any(t == "aviso" and "NÃO foi enviada" in v for t, v in eventos))
        self.assertNotIn(SENHA_TESTE.encode(), b" ".join(v for _, v in servidor.recebido))


class TestMonitor(unittest.TestCase):
    def test_ciclo_paralelo_detecta_online_offline(self):
        ouvinte = socket.socket()
        ouvinte.bind(("127.0.0.1", 0))
        ouvinte.listen(50)
        porta_aberta = ouvinte.getsockname()[1]
        livre = socket.socket(); livre.bind(("127.0.0.1", 0)); porta_fechada = livre.getsockname()[1]; livre.close()

        with tempfile.TemporaryDirectory() as pasta:
            db = Database(os.path.join(pasta, "olts.db"), Cifrador(Fernet.generate_key()))
            id_on = db.adicionar_equipamento(Equipamento(None, "on", "127.0.0.1", "SSH", porta_aberta))
            id_off = db.adicionar_equipamento(Equipamento(None, "off", "127.0.0.1", "SSH", porta_fechada))
            monitor = MonitorStatus(db, 15, 8, 1.0, metodo="tcp")  # este teste é do modo TCP
            monitor.executar_ciclo()
            self.assertTrue(monitor.status[id_on]["online"])
            self.assertIsNotNone(monitor.status[id_on]["latencia_ms"])
            self.assertFalse(monitor.status[id_off]["online"])
            self.assertTrue(db.carregar_status()[id_on]["online"])
            db.fechar()
        ouvinte.close()
        self.assertEqual(testar_porta("127.0.0.1", "porta-invalida", 0.5), (False, None))


if __name__ == "__main__":
    unittest.main()
