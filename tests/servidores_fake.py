"""Servidores SSH e Telnet falsos, só em 127.0.0.1, para testar as sessões
sem depender de equipamento real. Credenciais são fictícias de teste."""
import socket
import threading

import paramiko

USUARIO_TESTE = "tecnico.teste"
SENHA_TESTE = "senha-ficticia-123"


class _InterfaceSSH(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        if username == USUARIO_TESTE and password == SENHA_TESTE:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_pty_request(self, *args):
        return True

    def check_channel_shell_request(self, channel):
        return True


class ServidorSSHFake:
    """Aceita conexões e responde "eco:<linha>" para cada linha recebida."""

    def __init__(self, chave_host=None, classe_transporte=paramiko.Transport):
        self.chave_host = chave_host or paramiko.RSAKey.generate(2048)
        self.classe_transporte = classe_transporte
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.porta = self.sock.getsockname()[1]
        self._rodando = True
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while self._rodando:
            try:
                cliente, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(cliente,), daemon=True).start()

    def _atender(self, cliente):
        transporte = self.classe_transporte(cliente)
        transporte.add_server_key(self.chave_host)
        try:
            transporte.start_server(server=_InterfaceSSH())
            canal = transporte.accept(10)
            if canal is None:
                return
            canal.send(b"Bem-vindo ao equipamento de teste\r\nOLT# ")
            buffer = b""
            aguardando = None  # "espaco" (paginação) ou "enter" (confirmação estilo Huawei)
            while True:
                dados = canal.recv(1024)
                if not dados:
                    break
                buffer += dados
                if aguardando == "espaco" and b" " in buffer:
                    buffer = buffer.replace(b" ", b"", 1)
                    aguardando = None
                    canal.send(b"\r\nparte2 SERIALPAGINADO01\r\nOLT# ")
                while b"\n" in buffer:
                    linha, buffer = buffer.split(b"\n", 1)
                    linha = linha.strip()
                    if aguardando == "enter":
                        aguardando = None
                        canal.send(b"\r\nONT encontrada: CONFIRMADO01\r\nOLT# ")
                        continue
                    if linha == b"quit":
                        canal.close()
                        return
                    if linha == b"paginado":
                        canal.send(b"parte1\r\n  ---- More ( Press 'Q' to break ) ----")
                        aguardando = "espaco"
                        continue
                    if linha == b"confirmar":
                        canal.send(b"\r\n{ <cr>||<K> }:")
                        aguardando = "enter"
                        continue
                    canal.send(b"eco:" + linha + b"\r\nOLT# ")
        except Exception:
            pass
        finally:
            transporte.close()

    def parar(self):
        self._rodando = False
        self.sock.close()


def criar_servidor_ssh_antigo():
    """Servidor que imita a ZTE antiga real (banner ZTE_SSH.1.0): só oferece
    chave ssh-rsa/SHA-1, cifra aes128-cbc e MAC hmac-sha1."""
    from netterminal.net.ssh_legado import RSAKeyLegado, TransportLegado

    class TransportZTEAntiga(TransportLegado):
        _preferred_keys = ("ssh-rsa",)
        _preferred_ciphers = ("aes128-cbc",)
        _preferred_macs = ("hmac-sha1",)
        _preferred_kex = ("diffie-hellman-group14-sha256",)

    chave = RSAKeyLegado(key=paramiko.RSAKey.generate(2048).key)
    return ServidorSSHFake(chave_host=chave, classe_transporte=TransportZTEAntiga)


class ServidorTelnetFake:
    """Pede usuário/senha (com negociação IAC no meio) e depois ecoa linhas."""

    def __init__(self, pedir_senha=True):
        self.pedir_senha = pedir_senha
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.porta = self.sock.getsockname()[1]
        self.recebido = []
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _ler_linha(self, conn):
        dados = b""
        while not dados.endswith(b"\n"):
            parte = conn.recv(1)
            if not parte:
                raise EOFError
            dados += parte
        return dados.strip()

    def _aceitar(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        try:
            conn.sendall(bytes([255, 251, 1]) + b"Username: ")  # IAC WILL ECHO + prompt
            self.recebido.append(("usuario", self._ler_linha(conn)))
            if self.pedir_senha:
                conn.sendall(b"Password: ")
                self.recebido.append(("senha", self._ler_linha(conn)))
            else:
                conn.sendall(b"Banner sem pedir senha\r\n")
            conn.sendall(b"\r\nOLT> ")
            while True:
                linha = self._ler_linha(conn)
                self.recebido.append(("comando", linha))
                conn.sendall(b"eco:" + linha + b"\r\nOLT> ")
        except (EOFError, OSError):
            pass
        finally:
            conn.close()

    def parar(self):
        self.sock.close()
