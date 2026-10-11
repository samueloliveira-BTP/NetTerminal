"""Testes das regras puras: validação, mascaramento de segredos e CSV."""
import os
import tempfile
import unittest

from netterminal.core import csv_seguro
from netterminal.core.redaction import eh_prompt_de_senha, mascarar_segredos
from netterminal.core.validators import ip_valido, normalizar_protocolo, porta_valida, texto_limpo


class TestValidadores(unittest.TestCase):
    def test_ip(self):
        self.assertTrue(ip_valido(" 192.168.0.10 "))
        self.assertTrue(ip_valido("2001:db8::1"))
        for invalido in ("", "300.1.1.1", "192.168.0", "abc", None, "10.0.0.1; rm"):
            self.assertFalse(ip_valido(invalido), invalido)

    def test_porta(self):
        self.assertEqual(porta_valida("22"), 22)
        self.assertEqual(porta_valida(65535), 65535)
        for invalida in ("0", "65536", "-1", "abc", "", None, "22.5"):
            self.assertIsNone(porta_valida(invalida), invalida)

    def test_protocolo(self):
        self.assertEqual(normalizar_protocolo("ssh"), "SSH")
        self.assertEqual(normalizar_protocolo("TELNET"), "Telnet")
        self.assertIsNone(normalizar_protocolo("ftp"))

    def test_texto_limpo_remove_quebras(self):
        self.assertEqual(texto_limpo("OLT\nX\t1  "), "OLTX1")
        self.assertEqual(len(texto_limpo("a" * 500)), 200)


class TestMascaramento(unittest.TestCase):
    def test_mascara_senhas_em_comandos(self):
        casos = {
            "local-user admin password irreversible-cipher Abc@123": "local-user admin password ******",
            "aaa user tec password Segredo1": "aaa user tec password ******",
            "snmp-server community publica RO": "snmp-server community ******",
            "enable secret 5 $1$abc": "enable secret ******",
            "set password=xyz": "set password=******",
        }
        for entrada, esperado in casos.items():
            self.assertEqual(mascarar_segredos(entrada), esperado, entrada)

    def test_nao_mascara_comandos_comuns(self):
        for comando in ("display ont info 0 1 2", "show interface gpon 1/1/1",
                        "display current-configuration | include password", "show password-policy"):
            self.assertEqual(mascarar_segredos(comando), comando)

    def test_multilinha(self):
        texto = "interface x\nsnmp community abc\nquit"
        self.assertEqual(mascarar_segredos(texto), "interface x\nsnmp community ******\nquit")

    def test_prompt_de_senha(self):
        for prompt in ("Password:", "password: ", "Senha:", "User password:"):
            self.assertTrue(eh_prompt_de_senha(prompt), prompt)
        for nao in ("OLT#", "Username:", "display password-policy"):
            self.assertFalse(eh_prompt_de_senha(nao), nao)


class TestCSVSeguro(unittest.TestCase):
    def test_formula_injection_e_ida_e_volta(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "x.csv")
            perigosos = ["=CMD()", "+1", "-2", "@SUM(A1)", "normal"]
            csv_seguro.escrever_csv(caminho, ["campo"], [[v] for v in perigosos])
            with open(caminho, encoding="utf-8-sig") as f:
                bruto = f.read()
            self.assertIn("'=CMD()", bruto)
            self.assertNotIn("\n=CMD()", bruto)
            lidos = [l["campo"] for l in csv_seguro.ler_csv(caminho)]
            self.assertEqual(lidos, perigosos)

    def test_detecta_virgula(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "y.csv")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write("Nome,IP\nolt-a,10.0.0.1\n")
            self.assertEqual(csv_seguro.ler_csv(caminho), [{"nome": "olt-a", "ip": "10.0.0.1"}])


if __name__ == "__main__":
    unittest.main()
