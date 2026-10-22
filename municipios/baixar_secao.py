#!/usr/bin/env python3
"""Baixa do CDN do TSE a votação por seção 2026 (BR) e os locais de votação para municipios/brutos_secao/
(~340 MB; nunca commitado). Reusa rastro/baixar.py: cache por Last-Modified, .tmp, UA e a trava de 25/10.
Download sequencial e sem extrair: montar_secao.py lê os ZIPs direto.
Uso: python3 municipios/baixar_secao.py"""
import sys
import urllib.request
from datetime import date
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent))
from rastro.baixar import BASE, DIA_APURACAO, baixar_todos  # noqa: E402
from municipios.baixar_t2022 import CONFIG_MUN  # noqa: E402

OUT = H / "brutos_secao"
URL_SECAO = f"{BASE}/votacao_secao/votacao_secao_2026_BR.zip"
URL_LOCAIS = f"{BASE}/eleitorado_locais/eleitorado_local_votacao_2026.zip"
ARQUIVOS = [URL_SECAO, URL_LOCAIS, CONFIG_MUN]


def baixar(out=OUT, opener=urllib.request.urlopen, hoje=None):
    """Baixa os dois ZIPs e o mun-config do TSE em out/. Em 25/10 sai antes de qualquer requisição."""
    if (hoje or date.today()) == DIA_APURACAO:
        raise SystemExit("25/10: não baixar nada do TSE no dia da apuração (mesmo IP de saída do agregador)")
    return baixar_todos(ARQUIVOS, out, opener, hoje)


def main():
    for nome, situacao in baixar().items():
        print(f"{nome}: {situacao}")


if __name__ == "__main__":
    main()
