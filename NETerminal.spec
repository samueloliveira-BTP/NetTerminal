# -*- mode: python ; coding: utf-8 -*-
# Build:  .venv\Scripts\pyinstaller.exe NETerminal.spec --noconfirm
# Saída:  dist\NETerminal.exe
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('assets/icone.ico', 'assets'),
    ('assets/logo_splash.jpg', 'assets'),
]
# Temas/fontes do customtkinter (antes era um caminho absoluto da máquina do dev)
datas += collect_data_files('customtkinter')

a = Analysis(
    ['NETerminal.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas', 'numpy', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NETerminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX desligado: executáveis comprimidos com UPX são frequentemente
    # marcados como suspeitos por antivírus.
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icone.ico'],
)
