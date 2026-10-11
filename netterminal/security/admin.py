"""Senha de administrador e ações protegidas.

Ações marcadas como protegidas pedem a senha de admin antes de executar.
Enquanto não houver senha de admin definida, nada é bloqueado (mesmo
comportamento das versões anteriores).

Compatível com o hash criado pela versão de teste 1.4 (PBKDF2-SHA256 com
100 mil iterações): na primeira verificação correta, o hash é refeito com
o número de iterações atual (recomendação OWASP 2023+: 600 mil).

Limitação conhecida: o hash fica no banco local; quem tem acesso de escrita
à pasta de dados do usuário pode removê-lo. É uma barreira contra uso
indevido na estação, não um controle contra o próprio dono da conta.
"""
import hashlib
import hmac
import logging
import os
import time

log = logging.getLogger(__name__)

ACOES_PROTEGIVEIS = {
    "excluir_olt": "Excluir equipamento",
    "credenciais_globais": "Ver/editar credenciais globais",
    "macros": "Adicionar/editar/excluir macros",
    "importar_cadastro": "Importar cadastro (.csv) / perfil da equipe",
    "modelos_onu": "Editar modelos de ONU",
}

ITERACOES = 600_000
_ITERACOES_LEGADO = 100_000
DESBLOQUEIO_SEG = 600
MAX_TENTATIVAS = 5
BLOQUEIO_TENTATIVAS_SEG = 60
TAMANHO_MINIMO_SENHA = 8


def _hash(senha, salt, iteracoes):
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes).hex()


class ControleAdmin:
    def __init__(self, db):
        self._db = db
        self._desbloqueado_ate = 0.0
        self._falhas = 0
        self._bloqueado_ate = 0.0

    # --- senha -------------------------------------------------------------
    def configurado(self):
        return bool(self._db.get_config("admin_pass_hash", ""))

    def definir_senha(self, senha):
        if len(senha) < TAMANHO_MINIMO_SENHA:
            raise ValueError(f"A senha de admin precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")
        salt = os.urandom(16)
        self._db.set_config_lote([
            ("admin_pass_salt", salt.hex()),
            ("admin_pass_hash", _hash(senha, salt, ITERACOES)),
            ("admin_pass_iter", str(ITERACOES)),
        ])
        log.info("Senha de admin definida/alterada.")

    def segundos_bloqueado(self):
        return max(0, int(self._bloqueado_ate - time.time()))

    def verificar_senha(self, senha):
        """True se a senha confere. Após 5 erros seguidos, bloqueia por 60 s."""
        if self.segundos_bloqueado():
            return False
        salt_hex = self._db.get_config("admin_pass_salt", "")
        hash_salvo = self._db.get_config("admin_pass_hash", "")
        if not salt_hex or not hash_salvo:
            return False
        try:
            iteracoes = int(self._db.get_config("admin_pass_iter", str(_ITERACOES_LEGADO)))
        except ValueError:
            iteracoes = _ITERACOES_LEGADO
        calculado = _hash(senha, bytes.fromhex(salt_hex), iteracoes)
        if not hmac.compare_digest(calculado, hash_salvo):  # comparação em tempo constante
            self._falhas += 1
            log.warning(f"Senha de admin incorreta ({self._falhas}ª tentativa).")
            if self._falhas >= MAX_TENTATIVAS:
                self._bloqueado_ate = time.time() + BLOQUEIO_TENTATIVAS_SEG
                self._falhas = 0
                log.warning("Muitas tentativas de senha de admin; bloqueado temporariamente.")
            return False
        self._falhas = 0
        if iteracoes < ITERACOES:
            self.definir_senha_sem_validar(senha)
        return True

    def definir_senha_sem_validar(self, senha):
        """Usado só para atualizar o hash legado (a senha antiga pode ser curta)."""
        salt = os.urandom(16)
        self._db.set_config_lote([
            ("admin_pass_salt", salt.hex()),
            ("admin_pass_hash", _hash(senha, salt, ITERACOES)),
            ("admin_pass_iter", str(ITERACOES)),
        ])
        log.info("Hash da senha de admin atualizado para o padrão atual.")

    # --- desbloqueio temporário ---------------------------------------------
    def desbloquear(self):
        self._desbloqueado_ate = time.time() + DESBLOQUEIO_SEG

    def bloquear(self):
        self._desbloqueado_ate = 0.0

    def esta_desbloqueado(self):
        return time.time() < self._desbloqueado_ate

    # --- permissões ------------------------------------------------------------
    def acao_protegida(self, acao_id):
        return self.configurado() and self._db.get_config(f"perm_{acao_id}", "False") == "True"

    def definir_permissoes(self, protegidas):
        """protegidas: dict {acao_id: bool}"""
        self._db.set_config_lote([(f"perm_{a}", "True" if v else "False") for a, v in protegidas.items()])
