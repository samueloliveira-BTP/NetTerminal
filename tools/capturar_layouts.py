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
class _Evento:  # simula o arraste do mouse numa divisória
    def __init__(self, x_root=0, y_root=0):
        self.x_root, self.y_root = x_root, y_root


def arrastar(fx=None, fy=None):
    c = app.tab_content_frame
    if fx is not None:
        app.layout_paineis._arrastar(_Evento(x_root=c.winfo_rootx() + int(c.winfo_width() * fx)), "x")
    if fy is not None:
        app.layout_paineis._arrastar(_Evento(y_root=c.winfo_rooty() + int(c.winfo_height() * fy)), "y")


def restaurar_exibicao():
    if app._foco is not None:
        app.alternar_modo_foco()
    app.definir_lista_visivel(True)
    app.definir_barras_visiveis(True)
    app.layout_paineis.resetar()


# (nome, layout, quantidade de abas, ajuste antes da foto)
cenarios = [
    ("01_um_terminal", "⊞ 4", 1, None),
    ("02_lado_a_lado", "⊞ 4", 2, None),
    ("03_tres", "⊞ 4", 3, None),
    ("04_quatro_um_desconectado", "⊞ 4", 4,
     lambda: list(app.abas.values())[-1]["frame"].encerrar(motivo="teste")),
    ("05_dois_empilhados", "⬒ 2", 2, None),
    ("06_sete_abas", "⊞ 4", 7, None),
    ("07_quatro_divisoes_arrastadas", "⊞ 4", 4, lambda: arrastar(fx=0.68, fy=0.36)),
    ("08_tres_divisao_arrastada", "⊞ 4", 3, lambda: arrastar(fx=0.3, fy=0.6)),
    ("09_quatro_um_expandido", "⊞ 4", 4, lambda: app.alternar_zoom(app.paineis[1])),
    ("10_quatro_barras_ocultas", "⊞ 4", 4, lambda: app.definir_barras_visiveis(False)),
    ("11_quatro_sem_lista", "⊞ 4", 4, lambda: app.definir_lista_visivel(False)),
    ("12_modo_foco", "⊞ 4", 4, app.alternar_modo_foco if False else lambda: app.alternar_modo_foco()),
    ("13_foco_e_expandido", "⊞ 4", 4, lambda: (app.alternar_modo_foco(), app.alternar_zoom(app.paineis[0]))),
]
estado = {"i": 0}


def preparar_proximo():
    if estado["i"] >= len(cenarios):
        restaurar_exibicao()
        app.after(300, app._ao_fechar)
        return
    nome, layout, n, _ = cenarios[estado["i"]]
    restaurar_exibicao()
    for aba in list(app.abas):
        app.fechar_aba(aba)
    app.definir_layout(layout)
    for k in range(n):
        app.abrir_aba(app._equipamentos[ids[k]], f"olt-dm-teste-{'abcdefg'[k]} (127.0.0.1)")
    app.after(3500, lambda: fotografar(nome))


def fotografar(nome):
    ajuste = cenarios[estado["i"]][3]
    if ajuste:
        ajuste()
    app.after(700, lambda: medir_e_capturar(nome))


def medir_e_capturar(nome):
    app.update()
    visiveis = [d["frame"] for d in app.abas.values() if d["frame"].winfo_ismapped()]
    area = app.tab_content_frame
    tamanhos = [f"{t.winfo_width()}x{t.winfo_height()}" for t in visiveis]
    print(f"{nome}: área {area.winfo_width()}x{area.winfo_height()} | terminais visíveis {tamanhos} | "
          f"lista={bool(app.sidebar.winfo_ismapped())} barras={app.barras_visiveis} "
          f"abas: rolagem={bool(app.tab_bar_frame._scrollbar.winfo_ismapped())} "
          f"lista_abas={bool(app.btn_lista_abas.winfo_ismapped())}")
    capturar_janela(int(app.wm_frame(), 16), os.path.join(saida, f"{nome}.png"))
    estado.update(i=estado["i"] + 1)
    preparar_proximo()


app.after(2500, preparar_proximo)
app.mainloop()
servidor.parar()
print("capturas em", saida)
print("PASTA_TEMP:", pasta)
