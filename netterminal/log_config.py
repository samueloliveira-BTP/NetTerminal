"""Configuração do log da aplicação (app.log), rotação e retenção."""
import glob
import logging
import os
import sys
import time

from netterminal import APP_VERSION
from netterminal import config


def rotacionar_se_necessario(caminho, limite_bytes=config.LOG_LIMITE_BYTES):
    """Se o arquivo passou do limite, renomeia com data/hora e começa um novo."""
    try:
        if os.path.exists(caminho) and os.path.getsize(caminho) >= limite_bytes:
            pasta, nome = os.path.split(caminho)
            base, ext = os.path.splitext(nome)
            carimbo = time.strftime("%Y%m%d_%H%M%S")
            os.rename(caminho, os.path.join(pasta, f"{base}_{carimbo}{ext}"))
    except Exception:
        pass  # rotação nunca pode travar o log em si


def aplicar_retencao(pasta, dias=config.LOG_RETENCAO_DIAS):
    """Apaga arquivos de log JÁ ROTACIONADOS mais antigos que `dias`.
    Desligado por padrão (dias=0). Defina LOG_RETENTION_DAYS no .env conforme
    a política de retenção aprovada pelo responsável de LGPD."""
    if dias <= 0:
        return 0
    limite = time.time() - dias * 86400
    removidos = 0
    for padrao in ("app_*.log", "historico_comandos_*.log", "sessoes_*.log"):
        for caminho in glob.glob(os.path.join(pasta, padrao)):
            try:
                if os.path.getmtime(caminho) < limite:
                    os.remove(caminho)
                    removidos += 1
            except OSError:
                pass
    return removidos


def setup_logging():
    """Configura ~/.olt_manager/app.log e captura exceções não tratadas."""
    pasta = config.get_data_dir()
    caminho_log = os.path.join(pasta, "app.log")
    rotacionar_se_necessario(caminho_log)
    logging.basicConfig(
        filename=caminho_log,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    # O paramiko é muito verboso em INFO; só interessa aviso/erro.
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    def log_excecao_nao_tratada(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Erro não tratado:", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_excecao_nao_tratada
    removidos = aplicar_retencao(pasta)
    if removidos:
        logging.info(f"Retenção de logs: {removidos} arquivo(s) antigo(s) removido(s).")
    logging.info(f"=== NetTerminal v{APP_VERSION} iniciado ===")
