#!/usr/bin/env python3
"""Baixa do CDN do TSE os ZIPs de prestação de contas 2026 para rastro/brutos/ (nunca commitado).
Cache por Last-Modified: só baixa de novo se o TSE publicou versão mais nova. Nunca roda em 25/10.
Uso: python3 rastro/baixar.py"""
import contextlib
import logging
import shutil
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

log = logging.getLogger("rastro.baixar")
OUT = Path(__file__).resolve().parent / "brutos"
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_CONTAS = f"{BASE}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip"
URL_DESPESA_DOC = f"{BASE}/prestacao_contas/despesa_documento_2026.zip"
# extrato bancário: o nome extrato_bancario_2026.zip deu 404; este é o do plano e pode ainda não existir no CDN (404 = aviso)
URL_EXTRATO = f"{BASE}/prestacao_contas/extrato_bancario_candidato_2026.zip"
ARQUIVOS = [URL_CONTAS, URL_DESPESA_DOC, URL_EXTRATO]
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


def baixar_todos(urls=ARQUIVOS, out=OUT, opener=urllib.request.urlopen, hoje=None):
    """Baixa cada url em out/. 404 vira aviso ('não encontrado') e não derruba os outros; {nome: situação}."""
    res = {}
    for url in urls:
        dest = Path(out) / url.rsplit("/", 1)[-1]
        try:
            res[dest.name] = baixar(url, dest, opener, hoje)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            log.warning("%s: 404 no CDN do TSE (arquivo ainda não publicado ou nome errado); seguindo", url)
            res[dest.name] = "não encontrado"
    return res


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for nome, situacao in baixar_todos().items():
        print(f"{nome}: {situacao}")


if __name__ == "__main__":
    main()
