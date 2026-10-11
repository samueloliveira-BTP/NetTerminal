"""Caminhos do aplicativo e parâmetros configuráveis.

Os parâmetros vêm do arquivo `.env` que fica ao lado do executável (ou da
raiz do projeto, em desenvolvimento). Veja `.env.example` para a lista
completa. Nenhum segredo deve ser colocado aqui nem no .env — senhas ficam
somente no banco, criptografadas.
"""
import os
import sys


def pasta_app():
    """Pasta onde o executável (ou a raiz do projeto, em dev) está.
    Usada para achar o .env, que precisa ficar editável fora do pacote."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relativo):
    """Caminho absoluto de um recurso empacotado (ícone, imagens).
    Funciona tanto em dev quanto dentro do executável do PyInstaller."""
    base = getattr(sys, "_MEIPASS", pasta_app())
    return os.path.join(base, relativo)


def carregar_env(nome_arquivo=".env"):
    """Lê um .env simples (CHAVE=valor por linha; # é comentário),
    sem depender de biblioteca externa."""
    valores = {}
    caminho = os.path.join(pasta_app(), nome_arquivo)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass  # segue com os valores padrão
    return valores


_ENV = carregar_env()


def env_str(chave, padrao=""):
    # Variável de ambiente do sistema tem prioridade sobre o .env
    return os.environ.get(chave, _ENV.get(chave, padrao))


def env_bool(chave, padrao=False):
    valor = env_str(chave, "")
    if valor == "":
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


def env_int(chave, padrao):
    try:
        return int(env_str(chave, str(padrao)))
    except ValueError:
        return padrao


def get_data_dir():
    """Pasta de dados do usuário (banco, chave, logs). Cria se não existir.
    NETTERMINAL_DATA_DIR permite apontar para outra pasta (usado nos testes)."""
    pasta = os.environ.get("NETTERMINAL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".olt_manager")
    os.makedirs(pasta, exist_ok=True)
    return pasta


# ---------------------------------------------------------------------------
# Parâmetros ajustáveis via .env
# ---------------------------------------------------------------------------

# Atualização automática
UPDATE_CHECK_URL = env_str("UPDATE_CHECK_URL")
UPDATE_ALLOWED_HOSTS = [h.strip().lower() for h in env_str("UPDATE_ALLOWED_HOSTS").split(",") if h.strip()]
UPDATE_REQUIRE_SIGNATURE = env_bool("UPDATE_REQUIRE_SIGNATURE", False)
UPDATE_SIGNER_SUBJECT = env_str("UPDATE_SIGNER_SUBJECT")

# Sessões de terminal
SESSAO_INATIVIDADE_SEG = max(1, env_int("SESSION_IDLE_TIMEOUT_MIN", 10)) * 60
CONFIRMAR_COLAGEM_MULTILINHA = env_bool("CONFIRM_MULTILINE_PASTE", True)
SCROLLBACK_LINHAS = max(1000, env_int("TERMINAL_SCROLLBACK_LINES", 20000))

# Monitor de status
MONITOR_INTERVALO_SEG = max(5, env_int("MONITOR_INTERVAL_SEC", 15))
MONITOR_WORKERS = max(1, env_int("MONITOR_WORKERS", 32))
MONITOR_TIMEOUT_SEG = 1.5
# "icmp" (padrão, ping — não aciona bloqueio anti-força-bruta dos equipamentos)
# ou "tcp" (abre conexão na porta de login, como nas versões antigas)
MONITOR_METODO = "tcp" if env_str("MONITOR_METHOD", "icmp").strip().lower() == "tcp" else "icmp"

# Logs e auditoria
LOG_LIMITE_BYTES = 5 * 1024 * 1024
LOG_RETENCAO_DIAS = max(0, env_int("LOG_RETENTION_DAYS", 0))  # 0 = nunca apaga
SYSLOG_HOST = env_str("AUDIT_SYSLOG_HOST")
SYSLOG_PORTA = env_int("AUDIT_SYSLOG_PORT", 514)
