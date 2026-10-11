"""Wrapper mínimo do DPAPI do Windows (CryptProtectData/CryptUnprotectData).

O DPAPI cifra dados com uma chave derivada da conta do Windows do usuário:
só o mesmo usuário, na mesma conta, consegue decifrar. Assim a chave mestra
do app deixa de ser um arquivo que qualquer um copia e usa em outra máquina.

Implementado com ctypes para não adicionar dependência (pywin32).
"""
import ctypes
import sys

# Entropia extra: amarra o segredo a este aplicativo (outro programa rodando
# como o mesmo usuário precisaria conhecer este valor para chamar o DPAPI).
_ENTROPIA = b"NetTerminal/master-key/v2"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def disponivel():
    return sys.platform == "win32"


if disponivel():
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    def _blob(dados):
        buffer = ctypes.create_string_buffer(dados, len(dados))
        blob = _DATA_BLOB(len(dados), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        return blob, buffer  # o buffer precisa continuar vivo enquanto o blob for usado

    def _extrair(blob):
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))

    def proteger(dados: bytes) -> bytes:
        entrada, _b1 = _blob(dados)
        entropia, _b2 = _blob(_ENTROPIA)
        saida = _DATA_BLOB()
        if not _crypt32.CryptProtectData(ctypes.byref(entrada), "NetTerminal", ctypes.byref(entropia),
                                         None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida)):
            raise ctypes.WinError(ctypes.get_last_error())
        return _extrair(saida)

    def desproteger(dados: bytes) -> bytes:
        entrada, _b1 = _blob(dados)
        entropia, _b2 = _blob(_ENTROPIA)
        saida = _DATA_BLOB()
        if not _crypt32.CryptUnprotectData(ctypes.byref(entrada), None, ctypes.byref(entropia),
                                           None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida)):
            raise ctypes.WinError(ctypes.get_last_error())
        return _extrair(saida)

else:  # pragma: no cover - só roda fora do Windows (desenvolvimento)
    def proteger(dados: bytes) -> bytes:
        raise OSError("DPAPI disponível apenas no Windows")

    def desproteger(dados: bytes) -> bytes:
        raise OSError("DPAPI disponível apenas no Windows")
