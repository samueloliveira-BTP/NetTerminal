"""Testes das funcionalidades da v2.1: realce personalizado, modelos de ONU,
execução automática (busca global), perfil da equipe e instalação MSI."""
import json
import os
import re
import tempfile
import unittest
import unittest.mock

import paramiko
from cryptography.fernet import Fernet

from netterminal.core import destaque, onu, saida
from netterminal.core.models import Equipamento
from netterminal.data.database import Database
from netterminal.net import executor
from netterminal.security.crypto import Cifrador
from netterminal.security.hostkeys import RepositorioHostKeys, nome_host
from netterminal.services import perfil, updater
from tests.servidores_fake import SENHA_TESTE, USUARIO_TESTE, ServidorSSHFake


def _novo_db(pasta, nome="olts.db"):
    return Database(os.path.join(pasta, nome), Cifrador(Fernet.generate_key()))


class TestDestaque(unittest.TestCase):
    def test_palavra_inteira_x_texto(self):
        palavra = destaque.compilar("LOS", "palavra")
        self.assertTrue(palavra.search("status: LOS"))
        self.assertTrue(palavra.search("los"))
        self.assertFalse(palavra.search("CLOSE"))
        self.assertFalse(palavra.search("LOS-ALARM") and palavra.search("LOS-ALARM").group() != "LOS")
        self.assertTrue(destaque.compilar("cliente x", "texto").search("ONU do Cliente X ativa"))
        self.assertTrue(destaque.compilar("dying-gasp", "palavra").search("ultimo: dying-gasp"))
        self.assertTrue(destaque.compilar("a+b", "texto").search("a+b"))  # caracteres especiais escapados

    def test_validacao(self):
        destaque.validar("LOS", "palavra", "#ff0000")
        for padrao, tipo, cor in (("", "palavra", "#ff0000"), ("LOS", "palavra", "vermelho"),
                                  ("(", "regex", "#ff0000"), (".*", "regex", "#ff0000"),
                                  ("x" * 300, "texto", "#ff0000"), ("LOS", "outro", "#ff0000")):
            with self.assertRaises(ValueError, msg=(padrao[:10], tipo, cor)):
                destaque.validar(padrao, tipo, cor)

    def test_regex_catastrofica_recusada(self):
        with self.assertRaises(ValueError):
            destaque.validar(r"(a+)+$", "regex", "#ff0000")

    def test_padroes_sao_validos(self):
        for r in destaque.REGRAS_PADRAO:
            destaque.validar(r.padrao, r.tipo, r.cor)

    def test_banco_semeia_uma_vez_e_respeita_exclusao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "olts.db")
            chave = Fernet.generate_key()
            db = Database(caminho, Cifrador(chave))
            regras = db.listar_regras_destaque()
            self.assertEqual(len(regras), len(destaque.REGRAS_PADRAO))
            for r in regras:
                db.excluir_regra_destaque(r.id)
            novo = db.salvar_regra_destaque(destaque.RegraDestaque(None, "LOS", "LOS", "palavra", "#ff0000", True))
            db.fechar()
            db = Database(caminho, Cifrador(chave))  # reabrir não recria os padrões apagados
            regras = db.listar_regras_destaque()
            self.assertEqual([(r.id, r.padrao, r.negrito) for r in regras], [(novo, "LOS", True)])
            db.fechar()

    def test_reordenar(self):
        with tempfile.TemporaryDirectory() as pasta:
            db = _novo_db(pasta)
            ids = [r.id for r in db.listar_regras_destaque()]
            db.reordenar_regras_destaque(list(reversed(ids)))
            self.assertEqual([r.id for r in db.listar_regras_destaque()], list(reversed(ids)))
            db.fechar()


class TestModelosOnu(unittest.TestCase):
    def test_variaveis(self):
        v = onu.variaveis("interface gpon [PON]\nonu [ONU] [MODO|bridge,router] [PON]")
        self.assertEqual(v, [("PON", "PON", None), ("ONU", "ONU", None),
                             ("MODO|bridge,router", "MODO", ["bridge", "router"])])

    def test_validacao_de_campos(self):
        self.assertEqual(onu.validar_valor("SERIAL", " dacm1234abcd "), "DACM1234ABCD")
        self.assertEqual(onu.validar_valor("VLAN", "0100"), "100")
        self.assertEqual(onu.validar_valor("PON", "1/1/16"), "1/1/16")
        self.assertEqual(onu.validar_valor("DESCRICAO", "Cliente José 123"), "Cliente_Jos_123")
        self.assertEqual(onu.validar_valor("LINE_PROFILE", "10"), "10")
        invalidos = [("SERIAL", "abc"), ("SERIAL", "ABCD1234; reboot"), ("VLAN", "5000"), ("VLAN", "x"),
                     ("ONU", "1 2"), ("PON", "1/1/1; x"), ("TIPO_ONU", "F601\nreboot"), ("TIPO_ONU", "a|b"),
                     ("DESCRICAO", "!!!"), ("ONU", "")]
        for rotulo, valor in invalidos:
            with self.assertRaises(ValueError, msg=(rotulo, valor)):
                onu.validar_valor(rotulo, valor)

    def test_montar_e_preencher_termo(self):
        linhas = onu.montar("config\n\ninterface gpon [PON]\n onu [ONU]  \n", {"PON": "1/1/1", "ONU": "5"})
        self.assertEqual(linhas, ["config", "interface gpon 1/1/1", " onu 5"])
        self.assertEqual(onu.preencher_termo("show x | include [SERIAL]", "buscar_serial", "dacm00000001"),
                         ["show x | include DACM00000001"])
        with self.assertRaises(ValueError):
            onu.preencher_termo("show [SERIAL]", "buscar_serial", "x\nreboot")

    def test_modelos_padrao_sao_preenchiveis(self):
        exemplo = {"SERIAL": "DACM00000001", "VLAN": "100", "ONU": "5", "PON": "1/1/1", "FRAME/SLOT": "0/1",
                   "PORTA": "0", "DESCRICAO": "cliente teste", "LINE_PROFILE": "10", "SRV_PROFILE": "10",
                   "GEMPORT": "1", "SERVICE_PORT": "100", "TIPO_ONU": "ZTE-F601", "TCONT_PROFILE": "1G"}
        for marca, modelos in onu.MODELOS_PADRAO.items():
            for tipo, texto in modelos.items():
                valores = {}
                for chave, rotulo, _ in onu.variaveis(texto):
                    self.assertIn(rotulo, exemplo, f"{marca}/{tipo}: variável sem exemplo {rotulo}")
                    valores[chave] = onu.validar_valor(rotulo, exemplo[rotulo])
                linhas = onu.montar(texto, valores)
                self.assertTrue(linhas)
                self.assertFalse(any("[" in l and "]" in l and re.search(r"\[[A-Z_/]+\]", l) for l in linhas))
            for tipo, var in onu.VAR_TERMO.items():
                self.assertIn(f"[{var}]", modelos[tipo])

    def test_banco_modelos(self):
        with tempfile.TemporaryDirectory() as pasta:
            db = _novo_db(pasta)
            self.assertIn("display ont info by-sn", db.obter_modelo_onu("Huawei", "buscar_serial"))
            db.salvar_modelo_onu("Fiberhome", "pendentes", "show onu unauth")
            self.assertEqual(db.listar_modelos_onu()["Fiberhome"]["pendentes"], "show onu unauth")
            db.salvar_modelo_onu("Fiberhome", "pendentes", "   ")  # vazio = remove
            self.assertNotIn("Fiberhome", db.listar_modelos_onu())
            db.fechar()


class TestSaida(unittest.TestCase):
    def test_limpar(self):
        self.assertEqual(saida.limpar("abc\x08d\x1b[32mverde\x1b[0m\r\nlinha\rnova"), "abdverde\nnova")
        self.assertNotIn("More", saida.limpar("a\n---- More ( Press 'Q' to break ) ----b"))

    def test_linhas_com_termo_ignora_eco(self):
        texto = "OLT# show onu | include DACM01\r\n1  DACM01  up  cliente\r\nOLT# "
        self.assertEqual(saida.linhas_com_termo(texto, "dacm01", ["show onu | include DACM01"]),
                         ["1  DACM01  up  cliente"])
        self.assertEqual(saida.linhas_com_termo("OLT# show onu | include X\r\n", "x", ["show onu | include X"]), [])

    def test_comando_curto_nao_esconde_resultado(self):
        texto = "MA5800>enable\r\nMA5800#display ont info by-sn HWTC01\r\n  SN: HWTC01  state: enable\r\n"
        self.assertEqual(saida.linhas_com_termo(texto, "hwtc01", ["enable", "display ont info by-sn HWTC01"]),
                         ["SN: HWTC01  state: enable"])


class TestAuditoriaConcorrente(unittest.TestCase):
    def test_nenhuma_linha_perdida_com_threads(self):
        import threading
        from unittest import mock
        from netterminal.services import auditoria
        with tempfile.TemporaryDirectory() as pasta, mock.patch.dict(os.environ, {"NETTERMINAL_DATA_DIR": pasta}):
            def gravar(n):
                for i in range(50):
                    auditoria.log_comando("10.0.0.1", f"OLT-{n}", "SSH", f"cmd {n}-{i}", origem="BUSCA")
            threads = [threading.Thread(target=gravar, args=(n,)) for n in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(len(auditoria.ler_historico()), 1000)


class TestExecutor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ServidorSSHFake()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.parar()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = unittest.mock.patch.dict(os.environ, {"NETTERMINAL_DATA_DIR": self._tmp.name})
        self._env.start()
        self.repo = RepositorioHostKeys(os.path.join(self._tmp.name, "known_hosts"))
        self.eq = Equipamento(1, "OLT-teste", "127.0.0.1", "SSH", self.servidor.porta, marca="Huawei")

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_executa_responde_paginacao_e_confirmacao(self):
        res = executor.executar(self.eq, ["display version", "paginado", "confirmar"], USUARIO_TESTE, SENHA_TESTE,
                                self.repo, ocioso=0.8)
        self.assertTrue(res.ok, res.erro)
        self.assertIn("eco:display version", res.saida)
        self.assertIn("SERIALPAGINADO01", res.saida)   # respondeu ao "---- More ----"
        self.assertIn("CONFIRMADO01", res.saida)       # respondeu ao "{ <cr>||<K> }:"
        self.assertNotIn("More", res.saida)
        from netterminal.services import auditoria
        self.assertTrue(any(r[4] == "[BUSCA] paginado" for r in auditoria.ler_historico()))

    def test_erros_controlados(self):
        manual = Equipamento(2, "x", "127.0.0.1", "SSH", self.servidor.porta, login_manual=True)
        self.assertFalse(executor.executar(manual, ["x"], USUARIO_TESTE, SENHA_TESTE, self.repo).ok)
        self.assertIn("recusados", executor.executar(self.eq, ["x"], USUARIO_TESTE, "errada", self.repo).erro)
        self.repo.adicionar(nome_host("127.0.0.1", self.servidor.porta), paramiko.RSAKey.generate(2048))
        res = executor.executar(self.eq, ["x"], USUARIO_TESTE, SENHA_TESTE, self.repo)
        self.assertFalse(res.ok)
        self.assertIn("Chave SSH", res.erro)


class TestPerfil(unittest.TestCase):
    def test_exportar_importar_sem_segredos(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = _novo_db(pasta, "a.db")
            origem.set_config_lote([("tema", "Light"), ("fonte_terminal", "18"), ("color_term_fg", "#ffffff")])
            origem.set_config("default_user", "usuario-ficticio")
            origem.set_config_secreto("default_pass", "senha-ficticia")
            origem.adicionar_macro("Huawei", "ver ont", "display ont info [PON] [ONU]")
            origem.salvar_regra_destaque(destaque.RegraDestaque(None, "LOS", "LOS", "palavra", "#ff0000"))
            origem.salvar_modelo_onu("Fiberhome", "pendentes", "show onu unauth")
            origem.adicionar_equipamento(Equipamento(None, "OLT-1", "10.0.0.1", "SSH", 22, "Norte", marca="ZTE"))
            arquivo = os.path.join(pasta, "perfil.json")
            perfil.exportar(arquivo, origem, list(perfil.SECOES))

            with open(arquivo, encoding="utf-8") as f:
                bruto = f.read()
            for proibido in ("usuario-ficticio", "senha-ficticia", "default_pass", "admin_pass", "gAAAAA"):
                self.assertNotIn(proibido, bruto)

            # Alguém tenta "contrabandear" segredos/config arbitrária no arquivo
            dados = json.loads(bruto)
            dados["aparencia"]["default_user"] = "invasor"
            dados["aparencia"]["admin_pass_hash"] = "x"
            dados["destaque"].append({"nome": "ruim", "padrao": "(a+)+$", "tipo": "regex", "cor": "#ff0000"})
            dados["equipamentos"].append({"nome": "x", "ip": "999.1.1.1", "protocolo": "SSH", "porta": 22})
            with open(arquivo, "w", encoding="utf-8") as f:
                json.dump(dados, f)

            destino = _novo_db(pasta, "b.db")
            lido = perfil.ler(arquivo)
            self.assertEqual(set(perfil.secoes_disponiveis(lido)), set(perfil.SECOES))
            res = perfil.importar(lido, destino, list(perfil.SECOES))
            self.assertEqual(destino.get_config("tema"), "Light")
            self.assertEqual(destino.get_config("fonte_terminal"), "18")
            self.assertEqual(destino.get_config("default_user"), "")
            self.assertEqual(destino.get_config("admin_pass_hash"), "")
            self.assertIn(("Huawei", "ver ont"), destino.macros_existentes())
            self.assertIn("LOS", [r.padrao for r in destino.listar_regras_destaque()])
            self.assertNotIn("(a+)+$", [r.padrao for r in destino.listar_regras_destaque()])
            self.assertEqual(destino.obter_modelo_onu("Fiberhome", "pendentes"), "show onu unauth")
            self.assertEqual([e.ip for e in destino.listar_equipamentos()], ["10.0.0.1"])
            self.assertEqual(len(res.avisos), 2)

            # Importar de novo não duplica nada
            perfil.importar(lido, destino, list(perfil.SECOES))
            self.assertEqual(len(destino.listar_equipamentos()), 1)
            self.assertEqual(len(destino.listar_macros()), 1)
            origem.fechar()
            destino.fechar()

    def test_arquivo_invalido(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "x.json")
            for conteudo in ("não é json", json.dumps({"formato": "outro"}), json.dumps([1, 2])):
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                with self.assertRaises(ValueError):
                    perfil.ler(caminho)


class TestTLSAtualizacao(unittest.TestCase):
    def test_validacao_completa_sem_modo_estrito(self):
        import ssl
        ctx = updater._contexto_tls()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)      # cadeia é validada
        self.assertTrue(ctx.check_hostname)                         # nome do host é validado
        self.assertFalse(ctx.verify_flags & ssl.VERIFY_X509_STRICT)  # sem o modo que recusa o GitHub


class TestTelaDividida(unittest.TestCase):
    def test_grade_adaptativa(self):
        from netterminal.ui.app import posicoes_paineis
        self.assertEqual(posicoes_paineis(0, "lado"), ([], (1, 1)))
        self.assertEqual(posicoes_paineis(1, "lado"), ([(0, 0, 1, 1)], (1, 1)))          # 1 ocupa tudo
        self.assertEqual(posicoes_paineis(2, "lado")[1], (1, 2))                         # lado a lado
        self.assertEqual(posicoes_paineis(2, "empilhado")[1], (2, 1))                    # empilhados
        pos3, grade3 = posicoes_paineis(3, "lado")
        self.assertEqual(grade3, (2, 2))
        self.assertEqual(pos3[2], (1, 0, 1, 2))                                          # 3º ocupa a largura toda
        self.assertEqual(len(set(p[:2] for p in posicoes_paineis(4, "lado")[0])), 4)    # 4 posições distintas


class TestConsultaManual(unittest.TestCase):
    URL = "https://github.com/dono/NetTerminal-releases/releases/latest/download/versao.json"

    def _resposta(self, versao):
        corpo = json.dumps({"versao": versao, "sha256": "b" * 64,
                            "url_download": f"https://github.com/dono/NetTerminal-releases/releases/download/v{versao}/NetTerminal-{versao}.msi"}).encode()

        class _Resp:
            def read(self, n=-1): return corpo
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _Resp()

    def _consultar(self, **patch_open):
        from unittest import mock
        from netterminal import config
        with mock.patch.object(config, "UPDATE_CHECK_URL", self.URL), \
                mock.patch.object(updater._opener, "open", **patch_open):
            return updater.consultar_atualizacao()

    def test_status(self):
        from unittest import mock
        from netterminal import APP_VERSION, config
        self.assertEqual(self._consultar(return_value=self._resposta("99.0.0")).status, "nova")
        self.assertEqual(self._consultar(return_value=self._resposta(APP_VERSION)).status, "atualizado")
        self.assertEqual(self._consultar(side_effect=OSError("404")).status, "indisponivel")
        self.assertEqual(self._consultar(return_value=self._resposta("99.0.0.x")).status, "atualizado")
        with mock.patch.object(config, "UPDATE_CHECK_URL", ""):
            self.assertEqual(updater.consultar_atualizacao().status, "sem_url")
        # Repositório de releases público: download no mesmo host (github.com) é aceito
        info = self._consultar(return_value=self._resposta("99.0.0")).info
        self.assertTrue(info.url_download.endswith("NetTerminal-99.0.0.msi"))


class TestInstalacaoSilenciosa(unittest.TestCase):
    def test_comando_msi(self):
        cmd = updater.comando_instalacao(r"C:\temp\NetTerminal-2.1.0.msi", r"C:\Apps\NetTerminal\NETerminal.exe")
        self.assertEqual(cmd[:5], ["cmd.exe", "/c", "msiexec.exe", "/i", r"C:\temp\NetTerminal-2.1.0.msi"])
        self.assertIn("/passive", cmd)
        self.assertEqual(cmd[-4:], ["&&", "start", "", r"C:\Apps\NetTerminal\NETerminal.exe"])
        self.assertEqual(updater.comando_instalacao(r"C:\temp\setup.exe"), [r"C:\temp\setup.exe"])


if __name__ == "__main__":
    unittest.main()
