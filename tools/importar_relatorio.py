"""Importa equipamentos de um relatório CSV externo (colunas `hostname` e `ip`).

Substitui o antigo importador.py, que gravava num olts.db da pasta atual (e
não no banco real do app) e dependia do pandas.

Uso:
    python -m tools.importar_relatorio caminho\\relatorio.csv [--grupo Geral] [--marca Datacom]

O nome curto é a primeira parte do hostname antes de "|"
(ex.: "olt-xyz | descrição" -> "olt-xyz"). IPs já cadastrados são ignorados.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netterminal import config  # noqa: E402
from netterminal.core.csv_seguro import ler_csv  # noqa: E402
from netterminal.core.models import MARCAS, Equipamento  # noqa: E402
from netterminal.core.validators import ip_valido, texto_limpo  # noqa: E402
from netterminal.data.database import Database  # noqa: E402
from netterminal.security.crypto import Cifrador, carregar_ou_criar_chave  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Importa equipamentos de um relatório CSV (hostname, ip).")
    parser.add_argument("arquivo")
    parser.add_argument("--grupo", default="Geral")
    parser.add_argument("--marca", default="Outra", choices=MARCAS)
    args = parser.parse_args()

    pasta = config.get_data_dir()
    db = Database(os.path.join(pasta, "olts.db"), Cifrador(carregar_ou_criar_chave(pasta)))
    existentes = db.ips_cadastrados()
    inseridas = ignoradas = invalidas = 0

    for linha in ler_csv(args.arquivo):
        ip = (linha.get("ip") or "").strip()
        nome = texto_limpo((linha.get("hostname") or "").split("|")[0])
        if not nome or not ip_valido(ip):
            invalidas += 1
            continue
        if ip in existentes:
            ignoradas += 1
            continue
        db.adicionar_equipamento(Equipamento(id=None, nome=nome, ip=ip, protocolo="SSH", porta=22,
                                             grupo=args.grupo, marca=args.marca))
        existentes.add(ip)
        inseridas += 1

    print(f"Inseridas: {inseridas} | Já existiam: {ignoradas} | Inválidas: {invalidas}")


if __name__ == "__main__":
    main()
