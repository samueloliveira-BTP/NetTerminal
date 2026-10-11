"""CSV protegido contra "CSV/Formula Injection".

Uma célula que começa com = + - @ é interpretada como fórmula pelo Excel.
Na exportação, prefixamos essas células com apóstrofo; na importação, o
apóstrofo é removido de novo, para o ciclo exportar->importar ser fiel.
"""
import csv
import os

_INICIOS_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")
TAMANHO_MAXIMO_IMPORTACAO = 10 * 1024 * 1024  # 10 MB é muito mais do que qualquer cadastro real


def celula_segura(valor):
    texto = "" if valor is None else str(valor)
    if texto.startswith(_INICIOS_PERIGOSOS):
        return "'" + texto
    return texto


def desfazer_celula_segura(texto):
    texto = texto or ""
    if len(texto) > 1 and texto[0] == "'" and texto[1] in _INICIOS_PERIGOSOS:
        return texto[1:]
    return texto


def escrever_csv(caminho, cabecalho, linhas):
    """Grava CSV com ';' (padrão do Excel em pt-BR) e BOM UTF-8."""
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(cabecalho)
        for linha in linhas:
            writer.writerow([celula_segura(v) for v in linha])


def ler_csv(caminho):
    """Lê um CSV (';' ou ',' detectado automaticamente) e devolve lista de dicts
    com chaves em minúsculo e valores já sem o prefixo de proteção."""
    if os.path.getsize(caminho) > TAMANHO_MAXIMO_IMPORTACAO:
        raise ValueError("Arquivo grande demais para importação (limite de 10 MB).")
    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        amostra = f.read(4096)
        f.seek(0)
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        leitor = csv.DictReader(f, delimiter=delimitador)
        resultado = []
        for linha in leitor:
            resultado.append({
                (k or "").strip().lower(): desfazer_celula_segura((v or "").strip())
                for k, v in linha.items() if k is not None
            })
        return resultado
