"""Perfil da equipe: exporta/importa as configurações do app num arquivo JSON,
para padronizar todas as estações.

Seções: aparência (tema, cores, fonte), regras de realce, macros, modelos de
ONU e equipamentos/grupos. Por segurança, o arquivo NUNCA contém usuário,
senha, senha de admin, permissões nem chaves SSH — e esses campos são
ignorados na importação mesmo que alguém os adicione manualmente.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field

from netterminal import APP_VERSION
from netterminal.core import destaque as destaque_core
from netterminal.core.models import GRUPO_PADRAO, MARCAS, Equipamento
from netterminal.core.onu import TIPOS_MODELO
from netterminal.core.validators import ip_valido, normalizar_protocolo, porta_valida, texto_limpo
from netterminal.services import auditoria

log = logging.getLogger(__name__)

FORMATO = "netterminal-perfil"
VERSAO_FORMATO = 1
TAMANHO_MAXIMO = 20 * 1024 * 1024

SECOES = {
    "aparencia": "Aparência (tema, cores, fonte)",
    "destaque": "Regras de realce de sintaxe",
    "macros": "Macros",
    "modelos_onu": "Modelos de ONU",
    "equipamentos": "Equipamentos e grupos",
}

# Chaves de configuração que fazem parte da "aparência"
CHAVES_APARENCIA = ("tema", "fonte_terminal", "color_btn_bg", "color_btn_hover",
                    "color_term_bg", "color_term_fg", "syntax_highlighting", "layout_modo")


@dataclass
class ResultadoPerfil:
    contagens: dict = field(default_factory=dict)  # secao -> "x inseridos, y ignorados"
    avisos: list = field(default_factory=list)

    def resumo(self):
        linhas = [f"• {SECOES[s]}: {t}" for s, t in self.contagens.items()]
        if self.avisos:
            linhas.append(f"\n{len(self.avisos)} aviso(s):")
            linhas += [f"  - {a}" for a in self.avisos[:10]]
        return "\n".join(linhas) or "Nada importado."


def exportar(caminho, db, secoes):
    dados = {"formato": FORMATO, "versao_formato": VERSAO_FORMATO, "app_versao": APP_VERSION,
             "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"), "gerado_por": auditoria.usuario_atual()}
    if "aparencia" in secoes:
        dados["aparencia"] = {k: db.get_config(k) for k in CHAVES_APARENCIA if db.get_config(k) != ""}
    if "destaque" in secoes:
        dados["destaque"] = [{"nome": r.nome, "padrao": r.padrao, "tipo": r.tipo, "cor": r.cor,
                              "negrito": r.negrito, "ativo": r.ativo} for r in db.listar_regras_destaque()]
    if "macros" in secoes:
        dados["macros"] = [{"marca": m.marca, "nome": m.nome, "comando": m.comando} for m in db.listar_macros()]
    if "modelos_onu" in secoes:
        dados["modelos_onu"] = [{"marca": marca, "tipo": tipo, "comando": cmd}
                                for marca, tipos in db.listar_modelos_onu().items() for tipo, cmd in tipos.items()]
    if "equipamentos" in secoes:
        dados["equipamentos"] = [{"nome": e.nome, "ip": e.ip, "protocolo": e.protocolo, "porta": e.porta,
                                  "grupo": e.grupo, "marca": e.marca, "nota": e.nota, "login_manual": e.login_manual,
                                  "ssh_legado": e.ssh_legado}
                                 for e in db.listar_equipamentos()]
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    log.info(f"Perfil exportado para {caminho} (seções: {', '.join(secoes)}).")


def ler(caminho):
    """Lê e valida o cabeçalho do arquivo. Devolve o dict (ou levanta ValueError)."""
    if os.path.getsize(caminho) > TAMANHO_MAXIMO:
        raise ValueError("Arquivo grande demais (limite de 20 MB).")
    with open(caminho, "r", encoding="utf-8") as f:
        try:
            dados = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Arquivo não é um JSON válido: {e}") from None
    if not isinstance(dados, dict) or dados.get("formato") != FORMATO:
        raise ValueError("Este arquivo não é um perfil do NetTerminal.")
    if dados.get("versao_formato", 0) > VERSAO_FORMATO:
        raise ValueError("Perfil gerado por uma versão mais nova do NetTerminal; atualize o app.")
    return dados


def secoes_disponiveis(dados):
    return [s for s in SECOES if isinstance(dados.get(s), (list, dict)) and dados.get(s)]


def _lista_de_dicts(dados, secao):
    valor = dados.get(secao) or []
    return [item for item in valor if isinstance(item, dict)] if isinstance(valor, list) else []


def importar(dados, db, secoes, substituir_destaque=False):
    res = ResultadoPerfil()

    if "aparencia" in secoes and isinstance(dados.get("aparencia"), dict):
        pares = [(k, str(v)[:50]) for k, v in dados["aparencia"].items() if k in CHAVES_APARENCIA]
        db.set_config_lote(pares)
        res.contagens["aparencia"] = f"{len(pares)} configuração(ões) aplicada(s)"

    if "destaque" in secoes:
        existentes = {(r.padrao, r.tipo) for r in db.listar_regras_destaque()}
        if substituir_destaque:
            for r in db.listar_regras_destaque():
                db.excluir_regra_destaque(r.id)
            existentes = set()
        ins = ign = 0
        for item in _lista_de_dicts(dados, "destaque"):
            padrao, tipo, cor = str(item.get("padrao", "")), str(item.get("tipo", "")), str(item.get("cor", ""))
            try:
                destaque_core.validar(padrao, tipo, cor)
            except ValueError as e:
                res.avisos.append(f"Regra '{padrao[:30]}' ignorada: {e}")
                continue
            if (padrao, tipo) in existentes:
                ign += 1
                continue
            db.salvar_regra_destaque(destaque_core.RegraDestaque(
                None, texto_limpo(item.get("nome") or padrao, 60), padrao, tipo, cor,
                bool(item.get("negrito")), bool(item.get("ativo", True))))
            existentes.add((padrao, tipo))
            ins += 1
        res.contagens["destaque"] = f"{ins} inserida(s), {ign} já existiam"

    if "macros" in secoes:
        existentes = db.macros_existentes()
        ins = ign = 0
        for item in _lista_de_dicts(dados, "macros"):
            marca, nome = texto_limpo(item.get("marca"), 60), texto_limpo(item.get("nome"), 60)
            comando = str(item.get("comando") or "").strip()
            if not marca or not nome or not comando:
                continue
            if (marca, nome) in existentes:
                ign += 1
                continue
            db.adicionar_macro(marca, nome, comando)
            existentes.add((marca, nome))
            ins += 1
        res.contagens["macros"] = f"{ins} inserida(s), {ign} já existiam"

    if "modelos_onu" in secoes:
        n = 0
        for item in _lista_de_dicts(dados, "modelos_onu"):
            marca, tipo = texto_limpo(item.get("marca"), 60), str(item.get("tipo", ""))
            comando = str(item.get("comando") or "")
            if marca and tipo in TIPOS_MODELO and comando.strip() and len(comando) < 10000:
                db.salvar_modelo_onu(marca, tipo, comando)
                n += 1
        res.contagens["modelos_onu"] = f"{n} modelo(s) aplicado(s)"

    if "equipamentos" in secoes:
        existentes = db.ips_cadastrados()
        ins = ign = 0
        for item in _lista_de_dicts(dados, "equipamentos"):
            nome, ip = texto_limpo(item.get("nome")), str(item.get("ip") or "").strip()
            protocolo = normalizar_protocolo(str(item.get("protocolo") or "SSH"))
            porta = porta_valida(item.get("porta"))
            if not nome or not ip_valido(ip) or protocolo is None or porta is None:
                res.avisos.append(f"Equipamento '{nome or ip}' ignorado: dados inválidos")
                continue
            if ip in existentes:
                ign += 1
                continue
            marca = texto_limpo(item.get("marca")) or "Outra"
            db.adicionar_equipamento(Equipamento(
                None, nome, ip, protocolo, porta, texto_limpo(item.get("grupo")) or GRUPO_PADRAO,
                bool(item.get("login_manual")), marca if marca in MARCAS else "Outra",
                str(item.get("nota") or "")[:2000], bool(item.get("ssh_legado"))))
            existentes.add(ip)
            ins += 1
        res.contagens["equipamentos"] = f"{ins} inserido(s), {ign} IP(s) já existiam"

    log.info(f"Perfil importado por {auditoria.usuario_atual()}: {res.contagens}")
    return res
