"""Testes de auditoria, importação/exportação e atualização automática."""
import importlib
import os
import tempfile
import unittest
from unittest import mock

from cryptography.fernet import Fernet

from netterminal import config
from netterminal.data.database import Database
from netterminal.security.crypto import Cifrador
from netterminal.services import transferencia, updater


class _ComPastaTemporaria(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"NETTERMINAL_DATA_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class TestAuditoria(_ComPastaTemporaria):
    def test_registra_usuario_real_e_mascara_segredos(self):
        from netterminal.services import auditoria
        auditoria.log_comando("10.0.0.1", "OLT-A", "SSH", "local-user x password Segredo1")
        auditoria.log_comando("10.0.0.1", "OLT-A", "SSH", "linha1\nlinha2", origem="COLADO")
        auditoria.log_comando("10.0.0.1", "OLT-A", "SSH", "   ")
        linhas = auditoria.ler_historico()
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0][1], auditoria.usuario_atual())
        self.assertNotEqual(linhas[0][1], "local")
        self.assertIn("@", linhas[0][1])
        self.assertTrue(linhas[0][4].endswith("password ******"))
        self.assertEqual(linhas[1][4], "[COLADO] linha1 ↵ linha2")
        with open(auditoria.caminho_historico(), encoding="utf-8") as f:
            self.assertNotIn("Segredo1", f.read())
        self.assertEqual(auditoria.ler_historico(termo="outra"), [])
        self.assertEqual(len(auditoria.ler_historico(data_ini="2000-01-01", data_fim="2999-12-31")), 2)

        auditoria.registrar_sessao("10.0.0.1", "OLT-A", "SSH", 125)
        auditoria.registrar_sessao("10.0.0.1", "OLT-A", "SSH", 0)
        self.assertEqual(auditoria.ler_total_sessoes(), (125, 1))


class TestTransferencia(_ComPastaTemporaria):
    def test_importacao_valida_linhas(self):
        db = Database(os.path.join(self._tmp.name, "olts.db"), Cifrador(Fernet.generate_key()))
        csv_entrada = os.path.join(self._tmp.name, "in.csv")
        with open(csv_entrada, "w", encoding="utf-8") as f:
            f.write("nome;ip;protocolo;porta;grupo;marca;nota\n"
                    "OLT-1;10.0.0.1;ssh;22;Norte;Huawei;\n"
                    "OLT-2;10.0.0.2;TELNET;;Norte;MarcaX;\n"
                    "OLT-dup;10.0.0.1;SSH;22;;;\n"
                    "OLT-ip;999.0.0.1;SSH;22;;;\n"
                    "OLT-porta;10.0.0.3;SSH;99999;;;\n"
                    "OLT-proto;10.0.0.4;FTP;21;;;\n"
                    ";10.0.0.5;SSH;22;;;\n")
        res = transferencia.importar_equipamentos(csv_entrada, db)
        self.assertEqual((res.inseridas, res.duplicadas, len(res.invalidas)), (2, 1, 4))
        por_ip = {e.ip: e for e in db.listar_equipamentos()}
        self.assertEqual(por_ip["10.0.0.2"].protocolo, "Telnet")
        self.assertEqual(por_ip["10.0.0.2"].porta, 23)
        self.assertEqual(por_ip["10.0.0.2"].marca, "Outra")

        saida = os.path.join(self._tmp.name, "out.csv")
        transferencia.exportar_equipamentos(saida, db.listar_equipamentos())
        with open(saida, encoding="utf-8-sig") as f:
            conteudo = f.read()
        self.assertNotIn("senha", conteudo.lower())
        db.fechar()


class TestUpdater(unittest.TestCase):
    URL = "https://updates.exemplo.com.br/netterminal.json"
    HASH = "a" * 64

    def _info(self, **mudancas):
        dados = {"versao": "9.0.0", "url_download": "https://updates.exemplo.com.br/NetTerminal.exe",
                 "sha256": self.HASH}
        dados.update(mudancas)
        return updater.interpretar_resposta(dados, self.URL)

    def test_aceita_resposta_valida(self):
        self.assertEqual(self._info().versao, "9.0.0")

    def test_recusa_respostas_inseguras(self):
        casos = [
            {"url_download": "http://updates.exemplo.com.br/NetTerminal.exe"},  # sem HTTPS
            {"url_download": "https://atacante.exemplo.net/NetTerminal.exe"},   # outro host
            {"url_download": "file:///C:/Windows/System32/calc.exe"},
            {"sha256": ""},                                                      # sem hash
            {"sha256": "123"},
            {"url_download": "https://updates.exemplo.com.br/script.bat"},      # extensão
        ]
        for mudanca in casos:
            with self.assertRaises(updater.AtualizacaoRecusada, msg=str(mudanca)):
                self._info(**mudanca)

    def test_host_extra_permitido(self):
        with mock.patch.object(config, "UPDATE_ALLOWED_HOSTS", ["cdn.exemplo.com.br"]):
            self._info(url_download="https://cdn.exemplo.com.br/NetTerminal.msi")

    def test_comparar_versoes(self):
        self.assertTrue(updater.comparar_versoes("1.10.0", "1.9.0"))
        self.assertFalse(updater.comparar_versoes("2.0.0", "2.0.0"))
        self.assertFalse(updater.comparar_versoes("abc", "1.0"))

    def test_sem_url_nao_consulta(self):
        with mock.patch.object(config, "UPDATE_CHECK_URL", ""):
            self.assertIsNone(updater.verificar_atualizacao())
        with mock.patch.object(config, "UPDATE_CHECK_URL", "http://inseguro.exemplo.com.br/x.json"):
            self.assertIsNone(updater.verificar_atualizacao())

    def test_hash_divergente_e_recusado(self):
        conteudo = b"instalador-falso"

        class _Resp:
            def __init__(self): self._dados = [conteudo, b""]
            def read(self, n=-1): return self._dados.pop(0)
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with mock.patch.object(updater._opener, "open", return_value=_Resp()):
            with self.assertRaises(updater.AtualizacaoRecusada):
                updater.baixar_e_verificar(self._info())


if __name__ == "__main__":
    unittest.main()
