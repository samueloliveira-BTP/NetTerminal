"""Inicialização do aplicativo: logs -> chave mestra -> banco -> janela."""
import logging
import os
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from netterminal import config
from netterminal.data.database import Database
from netterminal.log_config import setup_logging
from netterminal.security.crypto import (ChaveIndisponivelError, Cifrador, carregar_ou_criar_chave,
                                         descartar_chave_inacessivel)
from netterminal.security.hostkeys import RepositorioHostKeys

log = logging.getLogger(__name__)


def _perguntar(titulo, mensagem, tipo="askyesno"):
    """Messagebox antes da janela principal existir."""
    raiz = tk.Tk()
    raiz.withdraw()
    try:
        return getattr(messagebox, tipo)(titulo, mensagem, parent=raiz)
    finally:
        raiz.destroy()


def _obter_chave(pasta):
    try:
        return carregar_ou_criar_chave(pasta)
    except ChaveIndisponivelError as e:
        log.critical(f"Chave mestra indisponível: {e}")
        gerar_nova = _perguntar(
            "Chave de criptografia",
            "A chave que protege as senhas salvas não pode ser aberta por este usuário do Windows "
            "(isso acontece se o perfil foi recriado ou a pasta veio de outra máquina).\n\n"
            "Gerar uma nova chave? A senha global precisará ser cadastrada de novo.\n"
            "(A chave antiga será preservada, não apagada.)")
        if not gerar_nova:
            return None
        descartar_chave_inacessivel(pasta)
        return carregar_ou_criar_chave(pasta)


def main():
    setup_logging()
    ctk.deactivate_automatic_dpi_awareness()
    try:
        pasta = config.get_data_dir()
        chave = _obter_chave(pasta)
        if chave is None:
            return
        db = Database(os.path.join(pasta, "olts.db"), Cifrador(chave))
        hostkeys = RepositorioHostKeys(os.path.join(pasta, "known_hosts"))

        from netterminal.ui.app import OLTManagerApp  # importa a UI só depois da chave pronta
        app = OLTManagerApp(db, hostkeys)
        app.mainloop()
    except Exception:
        log.critical("Falha ao iniciar o aplicativo:", exc_info=True)
        _perguntar("Erro", "O NetTerminal não conseguiu iniciar.\nOs detalhes foram registrados no app.log.",
                   tipo="showerror")
        raise
