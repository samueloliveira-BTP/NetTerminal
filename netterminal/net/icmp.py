"""Ping ICMP pela API nativa do Windows (IcmpSendEcho), SEM precisar de administrador.

Usado pelo monitor de status. Antes, o monitor abria uma conexão TCP na porta
de login (22/23) de cada equipamento a cada 15 s e fechava sem logar — o
Huawei VRP (e outros) interpreta isso como ataque de força bruta e BLOQUEIA o
IP de origem ("The IP has been blocked and you cannot log on it"). O ping não
toca no serviço de login.

IPv6 e sistemas não-Windows: `disponivel_para(ip)` devolve False e o monitor
usa o teste TCP como alternativa.
"""
import ctypes
import ipaddress
import socket
import struct
import sys

_IP_SUCCESS = 0


def _carregar_api():
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    class _IP_OPTION_INFORMATION(ctypes.Structure):
        _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                    ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]

    class _ICMP_ECHO_REPLY(ctypes.Structure):
        _fields_ = [("Address", wintypes.ULONG), ("Status", wintypes.ULONG), ("RoundTripTime", wintypes.ULONG),
                    ("DataSize", wintypes.USHORT), ("Reserved", wintypes.USHORT), ("Data", ctypes.c_void_p),
                    ("Options", _IP_OPTION_INFORMATION)]

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
    iphlpapi.IcmpCreateFile.argtypes = []
    iphlpapi.IcmpCloseHandle.restype = wintypes.BOOL
    iphlpapi.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
    iphlpapi.IcmpSendEcho.restype = wintypes.DWORD
    iphlpapi.IcmpSendEcho.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.WORD,
                                      ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    return iphlpapi, _ICMP_ECHO_REPLY


_API = _carregar_api()
_INVALIDO = ctypes.c_void_p(-1).value


def disponivel_para(ip):
    """True se dá para pingar este IP pela API nativa (Windows + IPv4)."""
    if _API is None:
        return False
    try:
        return ipaddress.ip_address(ip).version == 4
    except ValueError:
        return False


def ping(ip, timeout_ms=1500):
    """Envia 1 eco ICMP. Devolve (respondeu: bool, latencia_ms: float | None)."""
    iphlpapi, Resposta = _API
    destino = struct.unpack("<I", socket.inet_aton(ip))[0]  # IPAddr em ordem de rede
    dados = b"NetTerminal"
    tamanho_buffer = ctypes.sizeof(Resposta) + len(dados) + 8 + 32
    buffer = ctypes.create_string_buffer(tamanho_buffer)
    handle = iphlpapi.IcmpCreateFile()
    if not handle or handle == _INVALIDO:
        raise OSError("IcmpCreateFile falhou")
    try:
        respostas = iphlpapi.IcmpSendEcho(handle, destino, dados, len(dados), None, buffer,
                                          tamanho_buffer, int(timeout_ms))
        if respostas == 0:
            return False, None
        resposta = Resposta.from_buffer(buffer)
        if resposta.Status != _IP_SUCCESS:
            return False, None
        return True, float(resposta.RoundTripTime)
    finally:
        iphlpapi.IcmpCloseHandle(handle)
