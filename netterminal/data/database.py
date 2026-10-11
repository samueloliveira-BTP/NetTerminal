"""Acesso ao banco SQLite (~/.olt_manager/olts.db).

* Todas as consultas usam parâmetros (?) — nunca concatenação de texto —
  o que elimina SQL Injection.
* Uma única conexão é compartilhada entre a interface e as threads de
  background (monitor de status); um RLock serializa o acesso para evitar
  commits misturados entre threads.
* Senhas (credencial global) são gravadas cifradas pelo `Cifrador`.
"""
import logging
import sqlite3
import threading

from netterminal.core.destaque import REGRAS_PADRAO, RegraDestaque
from netterminal.core.models import GRUPO_PADRAO, Equipamento, Macro
from netterminal.core.onu import MODELOS_PADRAO
from netterminal.security.crypto import parece_token_fernet

log = logging.getLogger(__name__)

_COLUNAS_EQUIP = "id, nome, ip, protocolo, porta, grupo, manual_login, marca, nota"


def _linha_para_equipamento(r):
    return Equipamento(
        id=int(r[0]), nome=r[1], ip=r[2], protocolo=r[3], porta=int(r[4]),
        grupo=r[5] or GRUPO_PADRAO, login_manual=str(r[6]) in ("1", "True"),
        marca=r[7] or "Outra", nota=r[8] or "",
    )


class Database:
    def __init__(self, caminho_db, cifrador):
        self._cifrador = cifrador
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(caminho_db, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._criar_tabelas()
        self._migrar_senhas_texto_puro()
        self._semear_padroes()
        log.info(f"Banco de dados carregado: {caminho_db}")

    # ------------------------------------------------------------------ infra
    def _executar(self, sql, params=(), commit=False):
        with self._lock:
            cur = self.conn.execute(sql, params)
            linhas = cur.fetchall()
            if commit:
                self.conn.commit()
            return linhas

    def _executar_varios(self, sql, lista_params):
        with self._lock:
            self.conn.executemany(sql, lista_params)
            self.conn.commit()

    def fechar(self):
        with self._lock:
            self.conn.close()

    def _criar_tabelas(self):
        with self._lock:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS olts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL, ip TEXT NOT NULL,
                protocolo TEXT NOT NULL, usuario TEXT NOT NULL,
                senha TEXT NOT NULL, porta INTEGER NOT NULL,
                grupo TEXT DEFAULT 'Geral', manual_login INTEGER DEFAULT 0,
                marca TEXT DEFAULT 'Outra'
            )''')
            self.conn.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
            self.conn.execute('''CREATE TABLE IF NOT EXISTS macros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marca TEXT NOT NULL, nome TEXT NOT NULL, comando TEXT NOT NULL
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS status_olts (
                olt_id INTEGER PRIMARY KEY, status INTEGER, ultima_verificacao TEXT
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS destaque_regras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL, padrao TEXT NOT NULL, tipo TEXT NOT NULL, cor TEXT NOT NULL,
                negrito INTEGER DEFAULT 0, ativo INTEGER DEFAULT 1, ordem INTEGER DEFAULT 0
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS onu_modelos (
                marca TEXT NOT NULL, tipo TEXT NOT NULL, comando TEXT NOT NULL,
                PRIMARY KEY (marca, tipo)
            )''')
            # Colunas adicionadas ao longo das versões (bancos antigos não têm)
            for sql in (
                "ALTER TABLE olts ADD COLUMN grupo TEXT DEFAULT 'Geral'",
                "ALTER TABLE olts ADD COLUMN manual_login INTEGER DEFAULT 0",
                "ALTER TABLE olts ADD COLUMN marca TEXT DEFAULT 'Outra'",
                "ALTER TABLE olts ADD COLUMN nota TEXT DEFAULT ''",
                "ALTER TABLE status_olts ADD COLUMN latencia_ms REAL",
            ):
                try:
                    self.conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # coluna já existe
            self.conn.commit()

    def _migrar_senhas_texto_puro(self):
        """Cifra senhas que ainda estejam em texto puro (versões muito antigas).
        Antes elas ficavam assim para sempre, porque o app só "tolerava" o formato."""
        with self._lock:
            migradas = 0
            valor = self.get_config("default_pass", "")
            if valor and not parece_token_fernet(valor):
                self.set_config("default_pass", self._cifrador.cifrar(valor))
                migradas += 1
            for olt_id, senha in self.conn.execute("SELECT id, senha FROM olts WHERE senha <> ''").fetchall():
                if not parece_token_fernet(senha):
                    self.conn.execute("UPDATE olts SET senha=? WHERE id=?", (self._cifrador.cifrar(senha), olt_id))
                    migradas += 1
            self.conn.commit()
            if migradas:
                log.info(f"{migradas} senha(s) em texto puro migrada(s) para formato cifrado.")

    def _semear_padroes(self):
        """Grava regras de realce e modelos de ONU padrão UMA vez (controlado por
        flag), para que o usuário possa apagá-los sem que voltem sozinhos."""
        with self._lock:
            if self.get_config("seed_destaque_v1", "") != "1":
                for ordem, r in enumerate(REGRAS_PADRAO):
                    self.conn.execute(
                        "INSERT INTO destaque_regras (nome, padrao, tipo, cor, negrito, ativo, ordem) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (r.nome, r.padrao, r.tipo, r.cor, int(r.negrito), int(r.ativo), ordem))
                self.conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('seed_destaque_v1', '1')")
            if self.get_config("seed_onu_v1", "") != "1":
                for marca, modelos in MODELOS_PADRAO.items():
                    for tipo, comando in modelos.items():
                        self.conn.execute("INSERT OR IGNORE INTO onu_modelos (marca, tipo, comando) VALUES (?, ?, ?)",
                                          (marca, tipo, comando))
                self.conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('seed_onu_v1', '1')")
            self.conn.commit()

    # ----------------------------------------------------------- equipamentos
    def listar_equipamentos(self):
        linhas = self._executar(f"SELECT {_COLUNAS_EQUIP} FROM olts ORDER BY grupo, nome")
        return [_linha_para_equipamento(r) for r in linhas]

    def obter_equipamento(self, equip_id):
        linhas = self._executar(f"SELECT {_COLUNAS_EQUIP} FROM olts WHERE id=?", (equip_id,))
        return _linha_para_equipamento(linhas[0]) if linhas else None

    def adicionar_equipamento(self, eq):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO olts (nome, ip, protocolo, usuario, senha, porta, grupo, manual_login, marca, nota) "
                "VALUES (?, ?, ?, '', '', ?, ?, ?, ?, ?)",
                (eq.nome, eq.ip, eq.protocolo, int(eq.porta), eq.grupo or GRUPO_PADRAO,
                 1 if eq.login_manual else 0, eq.marca, eq.nota))
            self.conn.commit()
            return cur.lastrowid

    def atualizar_equipamento(self, eq):
        self._executar(
            "UPDATE olts SET nome=?, ip=?, protocolo=?, porta=?, grupo=?, manual_login=?, marca=?, nota=? WHERE id=?",
            (eq.nome, eq.ip, eq.protocolo, int(eq.porta), eq.grupo or GRUPO_PADRAO,
             1 if eq.login_manual else 0, eq.marca, eq.nota, eq.id), commit=True)

    def excluir_equipamentos(self, ids):
        with self._lock:
            for equip_id in ids:
                self.conn.execute("DELETE FROM olts WHERE id = ?", (equip_id,))
                self.conn.execute("DELETE FROM status_olts WHERE olt_id = ?", (equip_id,))
            self.conn.commit()

    def ips_cadastrados(self):
        return {r[0] for r in self._executar("SELECT ip FROM olts")}

    def grupos(self):
        grupos = [r[0] for r in self._executar("SELECT DISTINCT grupo FROM olts ORDER BY grupo") if r[0]]
        if GRUPO_PADRAO not in grupos:
            grupos.insert(0, GRUPO_PADRAO)
        return grupos

    # ----------------------------------------------------------------- status
    def carregar_status(self):
        linhas = self._executar("SELECT olt_id, status, ultima_verificacao, latencia_ms FROM status_olts")
        return {int(r[0]): {"online": bool(r[1]), "ts": r[2], "latencia_ms": r[3]} for r in linhas}

    def salvar_status_lote(self, resultados):
        """resultados: lista de (olt_id, online_bool, timestamp_str, latencia_ms_ou_None)"""
        self._executar_varios(
            "INSERT INTO status_olts (olt_id, status, ultima_verificacao, latencia_ms) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(olt_id) DO UPDATE SET status=excluded.status, "
            "ultima_verificacao=excluded.ultima_verificacao, latencia_ms=excluded.latencia_ms",
            [(oid, 1 if online else 0, ts, lat) for oid, online, ts, lat in resultados])

    # ----------------------------------------------------------------- config
    def get_config(self, chave, padrao=""):
        linhas = self._executar("SELECT valor FROM config WHERE chave = ?", (chave,))
        return linhas[0][0] if linhas else padrao

    def set_config(self, chave, valor):
        self._executar("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", (chave, valor), commit=True)

    def set_config_lote(self, pares):
        self._executar_varios("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", pares)

    def get_config_secreto(self, chave):
        return self._cifrador.decifrar(self.get_config(chave, ""))

    def set_config_secreto(self, chave, valor):
        self.set_config(chave, self._cifrador.cifrar(valor))

    def estados_pastas(self):
        """Estado (aberta/fechada) de todas as pastas da árvore, numa consulta só."""
        linhas = self._executar("SELECT chave, valor FROM config WHERE chave LIKE 'pasta\\_%' ESCAPE '\\'")
        return {chave[len("pasta_"):]: str(valor).lower() in ("true", "1") for chave, valor in linhas}

    # ----------------------------------------------------------------- macros
    def listar_macros(self):
        return [Macro(*r) for r in self._executar("SELECT id, marca, nome, comando FROM macros ORDER BY marca, nome")]

    def macros_existentes(self):
        return {(m.marca, m.nome) for m in self.listar_macros()}

    def adicionar_macro(self, marca, nome, comando):
        self._executar("INSERT INTO macros (marca, nome, comando) VALUES (?, ?, ?)", (marca, nome, comando), commit=True)

    def atualizar_macro(self, macro_id, marca, nome, comando):
        self._executar("UPDATE macros SET marca=?, nome=?, comando=? WHERE id=?",
                       (marca, nome, comando, macro_id), commit=True)

    def excluir_macro(self, macro_id):
        self._executar("DELETE FROM macros WHERE id = ?", (macro_id,), commit=True)

    # ------------------------------------------------------- realce (regras)
    def listar_regras_destaque(self):
        linhas = self._executar("SELECT id, nome, padrao, tipo, cor, negrito, ativo, ordem "
                                "FROM destaque_regras ORDER BY ordem, id")
        return [RegraDestaque(r[0], r[1], r[2], r[3], r[4], bool(r[5]), bool(r[6]), r[7]) for r in linhas]

    def salvar_regra_destaque(self, regra):
        """Insere (id None) ou atualiza. Devolve o id."""
        with self._lock:
            if regra.id is None:
                ordem = self.conn.execute("SELECT COALESCE(MAX(ordem), -1) + 1 FROM destaque_regras").fetchone()[0]
                cur = self.conn.execute(
                    "INSERT INTO destaque_regras (nome, padrao, tipo, cor, negrito, ativo, ordem) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (regra.nome, regra.padrao, regra.tipo, regra.cor, int(regra.negrito), int(regra.ativo), ordem))
                self.conn.commit()
                return cur.lastrowid
            self.conn.execute(
                "UPDATE destaque_regras SET nome=?, padrao=?, tipo=?, cor=?, negrito=?, ativo=? WHERE id=?",
                (regra.nome, regra.padrao, regra.tipo, regra.cor, int(regra.negrito), int(regra.ativo), regra.id))
            self.conn.commit()
            return regra.id

    def excluir_regra_destaque(self, regra_id):
        self._executar("DELETE FROM destaque_regras WHERE id=?", (regra_id,), commit=True)

    def reordenar_regras_destaque(self, ids_em_ordem):
        self._executar_varios("UPDATE destaque_regras SET ordem=? WHERE id=?",
                              [(i, rid) for i, rid in enumerate(ids_em_ordem)])

    # ---------------------------------------------------------- modelos de ONU
    def obter_modelo_onu(self, marca, tipo):
        linhas = self._executar("SELECT comando FROM onu_modelos WHERE marca=? AND tipo=?", (marca, tipo))
        return linhas[0][0] if linhas else ""

    def listar_modelos_onu(self):
        """{marca: {tipo: comando}}"""
        resultado = {}
        for marca, tipo, comando in self._executar("SELECT marca, tipo, comando FROM onu_modelos"):
            resultado.setdefault(marca, {})[tipo] = comando
        return resultado

    def salvar_modelo_onu(self, marca, tipo, comando):
        if comando.strip():
            self._executar("INSERT OR REPLACE INTO onu_modelos (marca, tipo, comando) VALUES (?, ?, ?)",
                           (marca, tipo, comando.strip()), commit=True)
        else:
            self._executar("DELETE FROM onu_modelos WHERE marca=? AND tipo=?", (marca, tipo), commit=True)
