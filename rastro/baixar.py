#!/usr/bin/env python3
"""Baixa do CDN do TSE os ZIPs de prestação de contas 2026 para rastro/brutos/ (nunca commitado).
Cache por Last-Modified: só baixa de novo se o TSE publicou versão mais nova. Nunca roda em 25/10.
Uso: python3 rastro/baixar.py"""
import contextlib
import shutil
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent / "brutos"
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_CONTAS = f"{BASE}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip"
URL_DESPESA_DOC = f"{BASE}/prestacao_contas/despesa_documento_2026.zip"
# extrato bancário: URL no CDN ainda não achada (extrato_bancario_2026.zip dá 404); entra quando a Issue que o usa a confirmar
URL_CAND = f"{BASE}/consulta_cand/consulta_cand_2026.zip"
ARQUIVOS = [URL_CONTAS, URL_DESPESA_DOC, URL_CAND]
UA = "eleicoes-2026-painel/1.0 (dados abertos; github.com/vitoropereira/vitorpereira.ia.br-eleicoes)"
DIA_APURACAO = date(2026, 10, 25)


def baixar(url, dest, opener=urllib.request.urlopen, hoje=None):
    """Baixa url em dest se o servidor tiver versão mais nova que a de dest.lastmod. Devolve 'baixado' ou 'em cache'."""
    hoje = hoje or date.today()
    if hoje == DIA_APURACAO:
        raise SystemExit("25/10: não baixar nada do TSE no dia da apuração (mesmo IP de saída do agregador)")
    dest = Path(dest)
    marca = dest.with_name(dest.name + ".lastmod")
    cab = {"User-Agent": UA}
    tmp = dest.with_name(dest.name + ".tmp")
    if dest.exists() and marca.exists():
        cab["If-Modified-Since"] = marca.read_text(encoding="utf-8").strip()
    try:
        with contextlib.closing(opener(urllib.request.Request(url, headers=cab), timeout=120)) as r:
            novo = r.headers.get("Last-Modified")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return "em cache"
        raise
    except BaseException:
        tmp.unlink(missing_ok=True)  # download interrompido não deixa .tmp parcial para trás
        raise
    tmp.replace(dest)
    if novo:
        marca.write_text(novo + "\n", encoding="utf-8")
    else:
        marca.unlink(missing_ok=True)  # sem Last-Modified, marca antiga ficaria velha e daria 304 sobre arquivo trocado
    return "baixado"


def main():
    for url in ARQUIVOS:
        dest = OUT / url.rsplit("/", 1)[-1]
        print(f"{dest.name}: {baixar(url, dest)}")


if __name__ == "__main__":
    main()
