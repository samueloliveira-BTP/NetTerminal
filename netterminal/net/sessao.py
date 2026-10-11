"""Sessões de terminal SSH/Telnet rodando em background.

A thread de rede NUNCA mexe na interface (o Tkinter não é thread-safe). Ela
só coloca eventos numa fila; a aba de terminal consome essa fila a partir
da thread principal. Tipos de evento:

    ("dados", texto)          saída do equipamento
    ("conectado", descricao)  conexão estabelecida
    ("aviso", texto)          mensagem informativa/de segurança para o técnico
    ("erro", texto)           falha ao conectar
    ("hostkey_mudou", info)   a chave SSH do equipamento mudou (possível MITM)
    ("encerrada", motivo)     conexão terminou
"""
import codecs
import logging
import queue
import socket
import threading

import paramiko

from netterminal.net.telnet import SimpleTelnet
from netterminal.security.hostkeys import fingerprint_sha256, nome_host

log = logging.getLogger(__name__)

_PROMPT_USUARIO = rb"(user\s*name|username|login|usu.{1,2}rio)\s*:\s*$"  # .{1,2}: "á" em UTF-8 ou Latin-1
_PROMPT_SENHA = rb"(password|senha)\s*:\s*$"


class Sessao:
    """Base comum de SSH e Telnet."""

    def __init__(self, equipamento, usuario="", senha=""):
        self.eq = equipamento
        self._usuario = usuario
        self._senha = senha
        self.eventos = queue.Queue()
        self.conectado = False
        self.falhou = False
        self._encerrando = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def iniciar(self):
        threading.Thread(target=self._executar, daemon=True, name=f"sessao-{self.eq.ip}").start()

    def _evento(self, tipo, valor=None):
        self.eventos.put((tipo, valor))

    def _emitir_dados(self, dados: bytes):
        texto = self._decoder.decode(dados)
        if texto:
            self._evento("dados", texto)

    def _executar(self):
        try:
            self._conectar()
            self._senha = ""  # não mantém a senha em memória além do necessário
            self._loop_leitura()
        except paramiko.BadHostKeyException as e:
            self.falhou = True
            log.error(f"Chave de host DIFERENTE da registrada para {self.eq.ip}:{self.eq.porta}")
            self._evento("hostkey_mudou", {
                "host": nome_host(self.eq.ip, self.eq.porta),
                "esperada": fingerprint_sha256(e.expected_key),
                "recebida": fingerprint_sha256(e.key),
            })
        except paramiko.AuthenticationException:
            self.falhou = True
            log.warning(f"Autenticação recusada por {self.eq.ip}:{self.eq.porta}")
            self._evento("erro", "Usuário ou senha recusados pelo equipamento.")
        except Exception as e:
            if self._encerrando:
                return
            self.falhou = True
            log.error(f"Falha na conexão {self.eq.protocolo} com {self.eq.ip}:{self.eq.porta}: {e}")
            self._evento("erro", _mensagem_amigavel(e))
        finally:
            self._senha = ""
            if self.conectado:
                self.conectado = False
                self._evento("encerrada", "Conexão encerrada.")
            self._liberar()

    # Implementados pelas subclasses
    def _conectar(self): raise NotImplementedError
    def _loop_leitura(self): raise NotImplementedError
    def enviar(self, dados): raise NotImplementedError
    def _liberar(self): raise NotImplementedError

    def fechar(self):
        self._encerrando = True
        self.conectado = False
        self._liberar()


class SessaoSSH(Sessao):
    def __init__(self, equipamento, usuario, senha, repositorio_hostkeys):
        super().__init__(equipamento, usuario, senha)
        self._repo = repositorio_hostkeys
        self._cliente = None
        self._canal = None

    def _conectar(self):
        self._cliente = paramiko.SSHClient()
        self._repo.preparar_cliente(
            self._cliente,
            ao_registrar=lambda host, tipo, fp: self._evento(
                "aviso", f"Primeira conexão com este equipamento: chave {tipo} registrada ({fp})."))
        self._cliente.connect(
            self.eq.ip, port=int(self.eq.porta), username=self._usuario, password=self._senha,
            timeout=8, banner_timeout=15, auth_timeout=15, allow_agent=False, look_for_keys=False)
        self._canal = self._cliente.invoke_shell(term="xterm", width=118, height=35)
        self._canal.settimeout(0.3)
        self.conectado = True
        log.info(f"Conectado via SSH a {self.eq.ip}:{self.eq.porta} ({self.eq.nome})")
        self._evento("conectado", f"Conectado a {self.eq.ip} (SSH)")

    def _loop_leitura(self):
        while self.conectado:
            try:
                dados = self._canal.recv(4096)
            except socket.timeout:
                continue
            if not dados:  # o equipamento fechou a sessão (ex.: "quit")
                break
            self._emitir_dados(dados)

    def enviar(self, dados):
        if isinstance(dados, str):
            dados = dados.encode("utf-8")
        if self._canal is not None and self.conectado:
            self._canal.sendall(dados)

    def _liberar(self):
        for recurso in (self._canal, self._cliente):
            try:
                if recurso is not None:
                    recurso.close()
            except Exception:
                pass


class SessaoTelnet(Sessao):
    def __init__(self, equipamento, usuario, senha, login_automatico=True):
        super().__init__(equipamento, usuario, senha)
        self._login_automatico = login_automatico
        self._conexao = None

    def _conectar(self):
        self._conexao = SimpleTelnet(self.eq.ip, port=int(self.eq.porta), timeout=8)
        self.conectado = True
        log.info(f"Conectado via Telnet a {self.eq.ip}:{self.eq.porta} ({self.eq.nome})")
        self._evento("conectado", f"Conectado a {self.eq.ip} (Telnet)")
        self._evento("aviso", "Telnet não é criptografado: usuário, senha e comandos trafegam em texto claro.")
        if self._login_automatico:
            self._login()

    def _login(self):
        """Só envia usuário/senha quando o equipamento realmente pedir.
        Antes, a senha era enviada às cegas depois de 2 s, mesmo sem prompt."""
        dados, casou = self._conexao.read_until_regex(_PROMPT_USUARIO, timeout=6)
        self._emitir_dados(dados)
        if not casou:
            self._evento("aviso", "Prompt de usuário não detectado — faça o login manualmente.")
            return
        self._conexao.write(self._usuario.encode("utf-8") + b"\n")
        dados, casou = self._conexao.read_until_regex(_PROMPT_SENHA, timeout=6)
        self._emitir_dados(dados)
        if not casou:
            self._evento("aviso", "Prompt de senha não detectado — a senha NÃO foi enviada.")
            return
        self._conexao.write(self._senha.encode("utf-8") + b"\n")

    def _loop_leitura(self):
        while self.conectado:
            try:
                dados = self._conexao.read_some()
            except EOFError:
                break
            if dados:
                self._emitir_dados(dados)

    def enviar(self, dados):
        if isinstance(dados, str):
            dados = dados.encode("utf-8")
        if self._conexao is not None and self.conectado:
            self._conexao.write(dados)

    def _liberar(self):
        if self._conexao is not None:
            self._conexao.close()


def _mensagem_amigavel(erro):
    """Mensagem curta para o técnico (o detalhe técnico vai só para o app.log)."""
    if isinstance(erro, (socket.timeout, TimeoutError)):
        return "Tempo esgotado: o equipamento não respondeu."
    if isinstance(erro, ConnectionRefusedError):
        return "Conexão recusada: a porta está fechada ou o serviço está desativado."
    if isinstance(erro, OSError) and getattr(erro, "winerror", None) in (10051, 10065):
        return "Rede/host inalcançável a partir desta máquina."
    if isinstance(erro, paramiko.SSHException):
        return f"Erro no protocolo SSH: {erro}"
    return f"Falha na conexão: {erro}"
