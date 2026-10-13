#!/usr/bin/env python3
"""Base de nomeados: servidores federais com função ou cargo comissionado (cadastro SIAPE do Portal da Transparência).
Lê o ZIP em streaming, sem extrair, e grava rastro/brutos/nomeados.json (fora do git) só com nome, trecho do meio do CPF
(6 dígitos, o que o Portal já publica mascarado), função e órgão. CPF inteiro nunca é gravado.
Uso: python3 rastro/nomeacoes.py"""
import csv
import io
import json
import logging
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from rastro import baixar
    from rastro.cnpj import _norm
    from rastro.contas import cpf_valido, digitos, gravar, limpar_texto
except ImportError:  # rodado como script: python3 rastro/nomeacoes.py
    import baixar
    from cnpj import _norm
    from contas import cpf_valido, digitos, gravar, limpar_texto

log = logging.getLogger("rastro.nomeacoes")
AQUI = Path(__file__).resolve().parent
CONFIG = AQUI / "config.json"
NOMEADOS = baixar.OUT / "nomeados.json"
RE_MASCARA = re.compile(r"\*{3}\.?(\d{3})\.?(\d{3})-?\*{2}")  # '***.123.456-**' (Portal) ou '***123456**' (Receita)
COLUNAS_SIAPE = {"nome": "NOME", "cpf": "CPF", "funcao": "SIGLA_FUNCAO", "orgao": "ORG_LOTACAO"}
SEM_FUNCAO = {"", "-1", "-2", "-3"}


def cpf_meio(campo, avisos):
    """Os 6 dígitos visíveis de um CPF mascarado, ou None. CPF inteiro ou vazio é descartado e contado em avisos."""
    campo = (campo or "").strip()
    m = RE_MASCARA.fullmatch(campo)
    if m:
        return m.group(1) + m.group(2)
    if not campo:
        avisos["vazio"] += 1
    elif cpf_valido(digitos(campo)):
        avisos["inteiro"] += 1
    else:
        avisos["formato"] += 1
    return None


def _comissionada(sigla, funcoes):
    sigla = (sigla or "").strip().upper()
    return sigla not in SEM_FUNCAO and any(sigla.startswith(p.upper()) for p in funcoes)


def _linhas(zip_path, sufixo):
    with zipfile.ZipFile(zip_path) as z:
        membros = [n for n in z.namelist() if n.lower().endswith(sufixo)]
        if len(membros) != 1:
            raise FileNotFoundError(f"{zip_path}: esperava 1 membro *{sufixo}, achei {z.namelist()}")
        with z.open(membros[0]) as bruto:
            yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")


def _ler(linhas, colunas, funcoes, base):
    avisos = {"vazio": 0, "inteiro": 0, "formato": 0}
    out = {}
    conferido = False
    for l in linhas:
        if not conferido:  # cabeçalho renomeado pelo Portal não pode virar base vazia em silêncio
            faltam = [c for k, c in colunas.items() if c and k != "orgao" and c not in l]
            if faltam:
                raise ValueError(f"{base}: colunas ausentes no cabeçalho: {faltam}")
            conferido = True
        sigla = (l.get(colunas["funcao"]) or "").strip() if colunas.get("funcao") else ""
        if funcoes is not None and not _comissionada(sigla, funcoes):
            continue
        meio = cpf_meio(l.get(colunas["cpf"]), avisos)
        nome = limpar_texto(l.get(colunas["nome"]))
        if not meio or not nome:
            continue
        orgao = limpar_texto(l.get(colunas["orgao"])) if colunas.get("orgao") else ""
        out[(_norm(nome), meio)] = {"funcao": sigla or None, "orgao": orgao or None, "base": base}
    if avisos["inteiro"]:
        log.warning("%s: %d linha(s) com CPF inteiro descartada(s)", base, avisos["inteiro"])
    if avisos["formato"]:
        log.warning("%s: %d linha(s) com CPF em formato inesperado descartada(s)", base, avisos["formato"])
    if avisos["vazio"]:
        log.info("%s: %d linha(s) comissionada(s) sem CPF descartada(s)", base, avisos["vazio"])
    return out


def ler_siape(zip_path, funcoes):
    """{(nome normalizado, cpf_meio): {funcao, orgao, base}} só de quem tem função comissionada pelos prefixos."""
    return _ler(_linhas(zip_path, "cadastro.csv"), COLUNAS_SIAPE, funcoes, "siape")


def ler_externa(zip_path, colunas, base, sufixo=".csv"):
    """Câmara/Senado: colunas = {nome, cpf, orgao, funcao?}. Sem coluna de CPF mascarado a base inteira é ignorada."""
    if not colunas.get("cpf"):
        log.warning("%s: base sem CPF mascarado ignorada (casar só pelo nome gera homônimo demais)", base)
        return {}
    it = _linhas(zip_path, sufixo)
    primeira = next(it, None)
    if primeira is None:
        return {}
    if colunas["cpf"] not in primeira:
        log.warning("%s: base sem coluna %r ignorada (casar só pelo nome gera homônimo demais)", base, colunas["cpf"])
        return {}
    def todas():
        yield primeira
        yield from it
    return _ler(todas(), colunas, None, base)


def url_fonte(cfg, base="siape"):
    modelo = (cfg.get("nomeacoes_fontes") or {}).get(base)
    return modelo.format(mes=cfg["nomeacoes_mes"].replace("-", "")) if modelo else None


def gerar(zip_siape, cfg, saida, extras=()):
    """Grava saida com os nomeados do SIAPE (e das bases extras já lidas). Devolve a quantidade."""
    achados = ler_siape(zip_siape, cfg["nomeacoes_funcoes"])
    for extra in extras:
        achados.update(extra)
    mes = cfg["nomeacoes_mes"]
    nomeados = [{"nome": nome, "cpf_meio": meio, **d} for (nome, meio), d in sorted(achados.items())]
    gravar(saida, {"fonte": [url_fonte(cfg)], "data_base": f"{mes}-01",
                   "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nomeados": nomeados})
    return len(nomeados)


def main(opener=urllib.request.urlopen, hoje=None, cfg=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = cfg or json.loads(CONFIG.read_text(encoding="utf-8"))
    mes = cfg["nomeacoes_mes"].replace("-", "")
    if not url_fonte(cfg):
        raise SystemExit("config.json sem nomeacoes_fontes.siape: nada a baixar")
    dest = baixar.OUT / "nomeacoes" / f"{mes}_Servidores.zip"
    print(f"{dest.name}: {baixar.baixar(url_fonte(cfg), dest, opener=opener, hoje=hoje)}")
    n = gerar(dest, cfg, baixar.OUT / "nomeados.json")
    print(f"{n} nomeados -> {baixar.OUT / 'nomeados.json'}")


if __name__ == "__main__":
    main()
