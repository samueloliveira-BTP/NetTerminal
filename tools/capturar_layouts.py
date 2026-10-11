"""Teste visual da tela dividida (Windows).

Abre o app com OLTs FALSAS (servidor SSH local, pasta de dados temporária) e
captura SÓ a janela do app (PrintWindow) em cada formato: 1, 2 lado a lado,
3, 4, 2 empilhados e 7 abas. Nada da área de trabalho é capturado.

Uso (na raiz do projeto), gravando as imagens FORA do repositório:
    .venv\\Scripts\\python.exe tools\\capturar_layouts.py . %TEMP%\\netterminal_capturas
"""
import ctypes
import os
import sys
import tempfile
from ctypes import wintypes

repo, saida = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
os.chdir(repo)
os.makedirs(saida, exist_ok=True)
pasta = tempfile.mkdtemp(prefix="nt_visual_")
os.environ["NETTERMINAL_DATA_DIR"] = pasta

from PIL import Image  # noqa: E402

from netterminal.log_config import setup_logging  # noqa: E402
setup_logging()
from netterminal.security.crypto import Cifrador, carregar_ou_criar_chave  # noqa: E402
from netterminal.data.database import Database  # noqa: E402
from netterminal.security.hostkeys import RepositorioHostKeys  # noqa: E402
from netterminal.core.models import Equipamento  # noqa: E402
from tests.servidores_fake import ServidorSSHFake, USUARIO_TESTE, SENHA_TESTE  # noqa: E402
import customtkinter as ctk  # noqa: E402

# ---------------------------------------------------------------- captura
user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
for f, args, res in [
    (user32.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    (user32.GetWindowDC, [wintypes.HWND], ctypes.c_void_p),
    (user32.ReleaseDC, [wintypes.HWND, ctypes.c_void_p], ctypes.c_int),
    (user32.PrintWindow, [wintypes.HWND, ctypes.c_void_p, wintypes.UINT], wintypes.BOOL),
    (gdi32.CreateCompatibleDC, [ctypes.c_void_p], ctypes.c_void_p),
    (gdi32.CreateCompatibleBitmap, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
    (gdi32.SelectObject, [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p),
    (gdi32.GetDIBits, [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
    (gdi32.DeleteObject, [ctypes.c_void_p], wintypes.BOOL),
    (gdi32.DeleteDC, [ctypes.c_void_p], wintypes.BOOL),
]:
    f.argtypes, f.restype = args, res


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def capturar_janela(hwnd, caminho):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc_janela = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_janela)
    bmp = gdi32.CreateCompatibleBitmap(hdc_janela, w, h)
    gdi32.SelectObject(hdc_mem, bmp)
    user32.PrintWindow(hwnd, hdc_mem, 2)  # PW_RENDERFULLCONTENT: só esta janela
    info = BITMAPINFOHEADER(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, bmp, 0, h, buffer, ctypes.byref(info), 0)
    Image.frombuffer("RGB", (w, h), buffer, "raw", "BGRX", 0, 1).save(caminho)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_janela)


# ------------------------------------------------------------------ cenário
ctk.deactivate_automatic_dpi_awareness()
servidor = ServidorSSHFake()
db = Database(os.path.join(pasta, "olts.db"), Cifrador(carregar_ou_criar_chave(pasta)))
db.set_config("default_user", USUARIO_TESTE)
db.set_config_secreto("default_pass", SENHA_TESTE)
for nome, cmd in [("Atualizar ONU", "x [PON]"), ("Reiniciar ONU", "x"), ("Temperatura gbic", "x"),
                  ("Ver porta ethernet", "x"), ("Ver service-port", "x"), ("Verificação Total (MAC)", "x")]:
    db.adicionar_macro("Datacom", nome, cmd)
ids = [db.adicionar_equipamento(Equipamento(None, f"olt-dm-teste-{c}", "127.0.0.1", "SSH", servidor.porta,
                                            "TESTE", marca="Datacom")) for c in "abcdefg"]

from netterminal.ui.app import OLTManagerApp  # noqa: E402
app = OLTManagerApp(db, RepositorioHostKeys(os.path.join(pasta, "known_hosts")))
app.after(1200, lambda: app.state("zoomed"))  # maximizada, igual ao uso real
cenarios = [("1_um_terminal", "⊞ 4", 1), ("2_lado_a_lado", "⊞ 4", 2), ("3_tres", "⊞ 4", 3),
            ("4_quatro", "⊞ 4", 4), ("5_dois_empilhados", "⬒ 2", 2), ("6_sete_abas", "⊞ 4", 7)]
estado = {"i": 0}


def preparar_proximo():
    if estado["i"] >= len(cenarios):
        app.after(300, app._ao_fechar)
        return
    nome, layout, n = cenarios[estado["i"]]
    for aba in list(app.abas):
        app.fechar_aba(aba)
    app.definir_layout(layout)
    for k in range(n):
        app.abrir_aba(app._equipamentos[ids[k]], f"olt-dm-teste-{'abcdefg'[k]} (127.0.0.1)")
    app.after(3500, lambda: fotografar(nome))


def fotografar(nome):
    # Um terminal desconectado (mostra o botão Reconectar) para ver o cabeçalho cheio
    if estado["i"] == 3:
        list(app.abas.values())[-1]["frame"].encerrar(motivo="teste")
    app.update()
    barra = app.tab_bar_frame._scrollbar
    print(f"{nome}: barra de rolagem das abas visível = {bool(barra.winfo_ismapped())} | "
          f"botão lista de abas = {bool(app.btn_lista_abas.winfo_ismapped())} | "
          f"terminais compactos = {[t._compacto for t in (d['frame'] for d in app.abas.values()) if t.winfo_ismapped()]}")
    app.after(400, lambda: (capturar_janela(int(app.wm_frame(), 16), os.path.join(saida, f"{nome}.png")),
                            estado.update(i=estado["i"] + 1), preparar_proximo()))


app.after(2500, preparar_proximo)
app.mainloop()
servidor.parar()
print("capturas em", saida)
print("PASTA_TEMP:", pasta)
