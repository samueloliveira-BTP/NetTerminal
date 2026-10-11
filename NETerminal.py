"""Ponto de entrada do NetTerminal.

Todo o código fica no pacote `netterminal/` (veja o mapa em
netterminal/__init__.py). Este arquivo existe para manter o mesmo comando
de sempre (`python NETerminal.py`) e o mesmo alvo do PyInstaller.
"""
from netterminal.main import main

if __name__ == "__main__":
    main()
