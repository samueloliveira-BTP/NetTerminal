"""Importação e exportação de cadastro, macros e histórico em CSV.

Por segurança, usuário e senha NUNCA entram nos arquivos exportados.
"""
import logging
from dataclasses import dataclass, field

from netterminal.core.csv_seguro import escrever_csv, ler_csv
from netterminal.core.models import GRUPO_PADRAO, MARCAS, Equipamento
from netterminal.core.validators import (ip_valido, normalizar_protocolo, porta_padrao,
                                         porta_valida, texto_limpo)

log = logging.getLogger(__name__)


@dataclass
class ResultadoImportacao:
    inseridas: int = 0
    duplicadas: int = 0
    invalidas: list = field(default_factory=list)  # mensagens "linha N: motivo"

    def resumo(self, rotulo_duplicada):
        texto = f"Inseridas: {self.inseridas}\nIgnoradas ({rotulo_duplicada}): {self.duplicadas}"
        if self.invalidas:
            texto += f"\nInválidas: {len(self.invalidas)}\n\n" + "\n".join(self.invalidas[:10])
            if len(self.invalidas) > 10:
                texto += f"\n... e mais {len(self.invalidas) - 10} (detalhes no app.log)"
        return texto


def exportar_equipamentos(caminho, equipamentos):
    escrever_csv(caminho, ["nome", "ip", "protocolo", "porta", "grupo", "marca", "nota"],
                 [[e.nome, e.ip, e.protocolo, e.porta, e.grupo, e.marca, e.nota] for e in equipamentos])
    log.info(f"Cadastro exportado para {caminho} ({len(equipamentos)} equipamento(s)).")
    return len(equipamentos)


def importar_equipamentos(caminho, db):
    res = ResultadoImportacao()
    existentes = db.ips_cadastrados()
    for n, linha in enumerate(ler_csv(caminho), start=2):  # linha 1 = cabeçalho
        nome = texto_limpo(linha.get("nome"))
        ip = (linha.get("ip") or "").strip()
        if not nome or not ip:
            res.invalidas.append(f"linha {n}: nome e IP são obrigatórios")
            continue
        if not ip_valido(ip):
            res.invalidas.append(f"linha {n}: IP inválido ({ip[:40]})")
            continue
        protocolo = normalizar_protocolo(linha.get("protocolo") or "SSH")
        if protocolo is None:
            res.invalidas.append(f"linha {n}: protocolo deve ser SSH ou Telnet")
            continue
        porta = porta_valida(linha.get("porta") or porta_padrao(protocolo))
        if porta is None:
            res.invalidas.append(f"linha {n}: porta inválida")
            continue
        if ip in existentes:
            res.duplicadas += 1
            continue
        marca = texto_limpo(linha.get("marca")) or "Outra"
        if marca not in MARCAS:
            marca = "Outra"
        db.adicionar_equipamento(Equipamento(
            id=None, nome=nome, ip=ip, protocolo=protocolo, porta=porta,
            grupo=texto_limpo(linha.get("grupo")) or GRUPO_PADRAO, marca=marca,
            nota=(linha.get("nota") or "")[:2000]))
        existentes.add(ip)
        res.inseridas += 1
    for msg in res.invalidas:
        log.warning(f"Importação de {caminho}: {msg}")
    log.info(f"Cadastro importado de {caminho}: {res.inseridas} inserida(s), "
             f"{res.duplicadas} duplicada(s), {len(res.invalidas)} inválida(s).")
    return res


def exportar_macros(caminho, macros):
    escrever_csv(caminho, ["marca", "nome", "comando"], [[m.marca, m.nome, m.comando] for m in macros])
    log.info(f"Macros exportadas para {caminho} ({len(macros)}).")
    return len(macros)


def importar_macros(caminho, db):
    res = ResultadoImportacao()
    existentes = db.macros_existentes()
    for n, linha in enumerate(ler_csv(caminho), start=2):
        marca = texto_limpo(linha.get("marca"), 60)
        nome = texto_limpo(linha.get("nome") or linha.get("rotulo"), 60)
        comando = (linha.get("comando") or "").strip()
        if not marca or not nome or not comando:
            res.invalidas.append(f"linha {n}: marca, nome e comando são obrigatórios")
            continue
        if (marca, nome) in existentes:
            res.duplicadas += 1
            continue
        db.adicionar_macro(marca, nome, comando)
        existentes.add((marca, nome))
        res.inseridas += 1
    log.info(f"Macros importadas de {caminho}: {res.inseridas} inserida(s), {res.duplicadas} duplicada(s).")
    return res


def exportar_historico(caminho, linhas):
    escrever_csv(caminho, ["data_hora", "usuario", "olt", "protocolo", "comando"], linhas)
    log.info(f"Histórico exportado para {caminho} ({len(linhas)} linha(s)).")
    return len(linhas)
