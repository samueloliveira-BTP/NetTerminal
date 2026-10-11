"""Cliente Telnet mínimo baseado em socket.

O módulo `telnetlib` foi removido do Python 3.13, por isso este cliente
próprio. Ele descarta as negociações Telnet (IAC), como o telnetlib fazia
por padrão.

ATENÇÃO: Telnet trafega tudo em texto claro, inclusive a senha. Prefira SSH
sempre que o equipamento suportar.
"""
import re
import socket
import time

IAC, DONT, DO, WONT, WILL, SB, SE = 0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA, 0xF0


class FiltroIAC:
    """Remove sequências IAC do fluxo, mesmo quando a sequência chega
    dividida entre dois pacotes (o restante fica guardado para o próximo)."""

    def __init__(self):
        self._pendente = b""

    def filtrar(self, dados: bytes) -> bytes:
        dados = self._pendente + dados
        self._pendente = b""
        resultado = bytearray()
        i, n = 0, len(dados)
        while i < n:
            b = dados[i]
            if b != IAC:
                resultado.append(b)
                i += 1
                continue
            if i + 1 >= n:
                self._pendente = dados[i:]
                break
            cmd = dados[i + 1]
            if cmd == IAC:
                resultado.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= n:
                    self._pendente = dados[i:]
                    break
                i += 3
            elif cmd == SB:
                fim = dados.find(bytes([IAC, SE]), i)
                if fim == -1:
                    self._pendente = dados[i:]
                    break
                i = fim + 2
            else:
                i += 2
        return bytes(resultado)


class SimpleTelnet:
    def __init__(self, host, port=23, timeout=5):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(0.3)
        self._filtro = FiltroIAC()

    def write(self, dados: bytes):
        # 0xFF nos dados precisa ser enviado duplicado (IAC IAC), pelo protocolo
        self.sock.sendall(dados.replace(bytes([IAC]), bytes([IAC, IAC])))

    def read_some(self):
        """Lê o que estiver disponível. Devolve b"" se nada chegou no intervalo
        e levanta EOFError se o equipamento fechou a conexão."""
        try:
            bruto = self.sock.recv(4096)
        except socket.timeout:
            return b""
        if not bruto:
            raise EOFError("Conexão encerrada pelo equipamento.")
        return self._filtro.filtrar(bruto)

    def read_until_regex(self, padrao: bytes, timeout=5):
        """Lê até a regex casar com o final do que foi recebido ou o tempo acabar.
        Devolve (dados_recebidos, casou)."""
        regex = re.compile(padrao, re.IGNORECASE)
        fim = time.time() + timeout
        dados = b""
        while time.time() < fim:
            dados += self.read_some()
            if regex.search(dados[-300:]):
                return dados, True
        return dados, False

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
