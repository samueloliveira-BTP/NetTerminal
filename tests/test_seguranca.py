"""Testes de chave mestra (DPAPI), criptografia, banco e senha de admin."""
import hashlib
import os
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet

from netterminal.core.models import Equipamento
from netterminal.data.database import Database
from netterminal.security import dpapi
from netterminal.security.admin import ControleAdmin
from netterminal.security.crypto import (ARQ_CHAVE_DPAPI, ARQ_CHAVE_LEGADA, ChaveIndisponivelError,
                                         Cifrador, carregar_ou_criar_chave, descartar_chave_inacessivel)


class TestChaveMestra(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    @unittest.skipUnless(dpapi.disponivel(), "DPAPI só existe no Windows")
    def test_dpapi_ida_e_volta(self):
        self.assertEqual(dpapi.desproteger(dpapi.proteger(b"segredo")), b"segredo")
        self.assertNotIn(b"segredo", dpapi.proteger(b"segredo"))

    def test_cria_chave_nova_e_reabre(self):
        chave = carregar_ou_criar_chave(self.pasta)
        self.assertEqual(carregar_ou_criar_chave(self.pasta), chave)
        if dpapi.disponivel():
            self.assertTrue(os.path.exists(os.path.join(self.pasta, ARQ_CHAVE_DPAPI)))
            self.assertFalse(os.path.exists(os.path.join(self.pasta, ARQ_CHAVE_LEGADA)))

    @unittest.skipUnless(dpapi.disponivel(), "DPAPI só existe no Windows")
    def test_migra_chave_legada_mantendo_senhas(self):
        chave_antiga = Fernet.generate_key()
        with open(os.path.join(self.pasta, ARQ_CHAVE_LEGADA), "wb") as f:
            f.write(chave_antiga)
        token = Fernet(chave_antiga).encrypt(b"senha-ficticia").decode()

        chave = carregar_ou_criar_chave(self.pasta)
        self.assertEqual(chave, chave_antiga)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, ARQ_CHAVE_LEGADA)))
        self.assertEqual(Cifrador(carregar_ou_criar_chave(self.pasta)).decifrar(token), "senha-ficticia")

    @unittest.skipUnless(dpapi.disponivel(), "DPAPI só existe no Windows")
    def test_chave_corrompida_gera_erro_claro_e_e_preservada(self):
        with open(os.path.join(self.pasta, ARQ_CHAVE_DPAPI), "wb") as f:
            f.write(b"lixo-que-nao-e-dpapi")
        with self.assertRaises(ChaveIndisponivelError):
            carregar_ou_criar_chave(self.pasta)
        descartar_chave_inacessivel(self.pasta)
        self.assertTrue(any(n.startswith(ARQ_CHAVE_DPAPI + ".inacessivel_") for n in os.listdir(self.pasta)))
        carregar_ou_criar_chave(self.pasta)  # gera uma nova sem erro

    def test_cifrador(self):
        c = Cifrador(Fernet.generate_key())
        token = c.cifrar("abc")
        self.assertNotEqual(token, "abc")
        self.assertEqual(c.decifrar(token), "abc")
        self.assertEqual(c.decifrar(""), "")
        self.assertEqual(c.decifrar("texto-puro-legado"), "texto-puro-legado")
        # Token de OUTRA chave: nunca devolve o token como se fosse a senha
        outro = Cifrador(Fernet.generate_key()).cifrar("x")
        self.assertEqual(c.decifrar(outro), "")


class TestBanco(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.caminho = os.path.join(self._tmp.name, "olts.db")
        self.cifrador = Cifrador(Fernet.generate_key())

    def tearDown(self):
        self._tmp.cleanup()

    def _criar_banco_v1(self):
        """Banco no formato das versões antigas, com senhas em texto puro."""
        conn = sqlite3.connect(self.caminho)
        conn.execute("CREATE TABLE olts (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, ip TEXT NOT NULL, "
                     "protocolo TEXT NOT NULL, usuario TEXT NOT NULL, senha TEXT NOT NULL, porta INTEGER NOT NULL)")
        conn.execute("CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT)")
        conn.execute("INSERT INTO olts (nome, ip, protocolo, usuario, senha, porta) VALUES ('OLT-A','10.0.0.1','SSH','u','puro',22)")
        conn.execute("INSERT INTO config VALUES ('default_pass', 'senha-global-pura')")
        conn.execute("INSERT INTO config VALUES ('pasta_Geral', 'True')")
        conn.commit()
        conn.close()

    def test_migra_esquema_e_cifra_senhas_texto_puro(self):
        self._criar_banco_v1()
        db = Database(self.caminho, self.cifrador)
        bruto = db.conn.execute("SELECT valor FROM config WHERE chave='default_pass'").fetchone()[0]
        self.assertTrue(bruto.startswith("gAAAAA"))
        self.assertEqual(db.get_config_secreto("default_pass"), "senha-global-pura")
        senha_olt = db.conn.execute("SELECT senha FROM olts").fetchone()[0]
        self.assertTrue(senha_olt.startswith("gAAAAA"))
        eq = db.listar_equipamentos()[0]
        self.assertEqual((eq.nome, eq.grupo, eq.marca, eq.login_manual), ("OLT-A", "Geral", "Outra", False))
        self.assertFalse(hasattr(eq, "senha"))  # a senha não circula pela interface
        self.assertEqual(db.estados_pastas(), {"Geral": True})
        db.fechar()

    def test_crud_equipamentos_e_macros(self):
        db = Database(self.caminho, self.cifrador)
        novo_id = db.adicionar_equipamento(Equipamento(None, "SW-1", "10.1.1.1", "Telnet", 23, "Core", True, "Huawei", "n"))
        eq = db.obter_equipamento(novo_id)
        self.assertEqual((eq.protocolo, eq.porta, eq.login_manual), ("Telnet", 23, True))
        eq.nome = "SW-1b"
        db.atualizar_equipamento(eq)
        self.assertEqual(db.obter_equipamento(novo_id).nome, "SW-1b")
        db.salvar_status_lote([(novo_id, True, "2026-01-01 00:00:00", 3.2)])
        self.assertTrue(db.carregar_status()[novo_id]["online"])
        db.excluir_equipamentos([novo_id])
        self.assertIsNone(db.obter_equipamento(novo_id))
        self.assertEqual(db.carregar_status(), {})

        db.adicionar_macro("Huawei", "ont", "display ont info [F/S/P]")
        m = db.listar_macros()[0]
        db.atualizar_macro(m.id, "Huawei", "ont2", "x")
        self.assertEqual(db.listar_macros()[0].nome, "ont2")
        db.excluir_macro(m.id)
        self.assertEqual(db.listar_macros(), [])
        db.fechar()

    def test_entrada_maliciosa_nao_vira_sql(self):
        db = Database(self.caminho, self.cifrador)
        db.adicionar_equipamento(Equipamento(None, "x'); DROP TABLE olts;--", "10.0.0.9", "SSH", 22))
        self.assertEqual(len(db.listar_equipamentos()), 1)
        db.fechar()


class TestAdmin(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._tmp.name, "olts.db"), Cifrador(Fernet.generate_key()))
        self.admin = ControleAdmin(self.db)

    def tearDown(self):
        self.db.fechar()
        self._tmp.cleanup()

    def test_sem_senha_nada_e_protegido(self):
        self.db.set_config("perm_excluir_olt", "True")
        self.assertFalse(self.admin.configurado())
        self.assertFalse(self.admin.acao_protegida("excluir_olt"))

    def test_senha_e_permissoes(self):
        with self.assertRaises(ValueError):
            self.admin.definir_senha("curta")
        self.admin.definir_senha("senha-admin-teste")
        self.assertTrue(self.admin.verificar_senha("senha-admin-teste"))
        self.assertFalse(self.admin.verificar_senha("errada"))
        self.admin.definir_permissoes({"excluir_olt": True, "macros": False})
        self.assertTrue(self.admin.acao_protegida("excluir_olt"))
        self.assertFalse(self.admin.acao_protegida("macros"))

    def test_hash_legado_v14_e_atualizado(self):
        salt = os.urandom(16)
        legado = hashlib.pbkdf2_hmac("sha256", b"antiga", salt, 100_000).hex()
        self.db.set_config_lote([("admin_pass_salt", salt.hex()), ("admin_pass_hash", legado)])
        self.assertTrue(self.admin.verificar_senha("antiga"))
        self.assertEqual(self.db.get_config("admin_pass_iter"), "600000")
        self.assertNotEqual(self.db.get_config("admin_pass_hash"), legado)
        self.assertTrue(self.admin.verificar_senha("antiga"))

    def test_bloqueio_apos_tentativas(self):
        self.admin.definir_senha("senha-admin-teste")
        for _ in range(5):
            self.admin.verificar_senha("errada")
        self.assertGreater(self.admin.segundos_bloqueado(), 0)
        self.assertFalse(self.admin.verificar_senha("senha-admin-teste"))


if __name__ == "__main__":
    unittest.main()
