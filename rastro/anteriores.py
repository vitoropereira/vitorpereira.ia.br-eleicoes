#!/usr/bin/env python3
"""Cruza os fornecedores PJ de 2026 com as despesas contratadas das campanhas de 2022 e 2024 (anos em rastro/config.json,
`anteriores_anos`). Lê os ZIPs de prestação de contas do TSE em streaming (rastro/brutos/, nunca commitado) e grava
rastro/dados/anteriores.json: por CNPJ e ano, quantas campanhas contrataram e quanto. Só CNPJ de 14 dígitos que também está
em agregados.json (2026) entra; fornecedor pessoa física é descartado e nenhum nome é gravado, só números.
Uso: python3 -m rastro.anteriores [--baixar]   (--baixar: GBs; nunca em 25/10; baixa um ano, processa e apaga o ZIP)"""
import argparse
import json
import logging
import shutil
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from rastro import baixar as bx
from rastro.contas import BRUTOS, SAIDA_AGREGADOS, AQUI, data_iso, digitos, gravar, ler_csv, num, texto, valor_linha

log = logging.getLogger("rastro.anteriores")
CONFIG = AQUI / "config.json"
SAIDA = AQUI / "dados" / "anteriores.json"
ARQUIVO = "despesas_contratadas_candidatos"
# nomes das colunas do CSV; se o TSE mudar algum entre anos, só esta constante muda
COL = {"cnpj": "NR_CPF_CNPJ_FORNECEDOR", "despesa": "SQ_DESPESA", "valor": "VR_DESPESA_CONTRATADA",
       "cand": "SQ_CANDIDATO", "data": "DT_GERACAO"}


def agregar(zip_path, cnpjs_alvo, invalidas=None, datas=None):
    """{cnpj: {n_campanhas, total_contratado}} das despesas contratadas do ZIP, só para CNPJs de 14 dígitos em cnpjs_alvo.
    SQ_DESPESA repetido na mesma campanha conta uma vez; valor vazio, #NULO ou lixo não vira 0: entra em `invalidas` e no log.
    `datas` (set, opcional) recebe os DT_GERACAO lidos."""
    invalidas = Counter() if invalidas is None else invalidas
    alvo = set(cnpjs_alvo)
    vistos, soma, campanhas = set(), {}, {}
    for l in ler_csv(zip_path, ARQUIVO):
        if datas is not None and l.get(COL["data"]):
            datas.add(l[COL["data"]])
        doc = digitos(l.get(COL["cnpj"]))
        if len(doc) != 14 or doc not in alvo:  # PF (CPF) e quem não é fornecedor de 2026 saem aqui
            continue
        cand, sqd = l.get(COL["cand"]), texto(l, COL["despesa"])
        antes = invalidas[ARQUIVO]
        v = valor_linha({**l, "VR_DESPESA_CONTRATADA": l.get(COL["valor"])}, "VR_DESPESA_CONTRATADA", ARQUIVO, invalidas)
        if v is None:
            if invalidas[ARQUIVO] == antes:  # vazio/#NULO: valor_linha não conta
                invalidas[ARQUIVO] += 1
                log.warning("%s: %s ausente (SQ_CANDIDATO=%s)", ARQUIVO, COL["valor"], cand)
            continue
        if sqd and (cand, sqd) in vistos:
            continue
        vistos.add((cand, sqd))
        soma[doc] = soma.get(doc, Decimal(0)) + v
        campanhas.setdefault(doc, set()).add(cand)
    return {c: {"n_campanhas": len(campanhas[c]), "total_contratado": num(soma[c])} for c in sorted(soma)}


def gerar(anos, zips, agregados_path, saida):
    """Lê agregados.json (2026) para saber os CNPJs-alvo e grava `saida`. zips: {ano: caminho}; ZIP ausente vira aviso e
    o ano fica fora de `anos`, sem derrubar os outros. Devolve o contador de linhas inválidas por ano."""
    alvo = json.loads(Path(agregados_path).read_text(encoding="utf-8"))["por_cnpj"].keys()
    por_cnpj, feitos, datas, invalidas = {}, [], set(), Counter()
    for ano in anos:
        z = zips.get(ano)
        if not z or not Path(z).exists():
            log.warning("sem o ZIP de %s: ano fora de anteriores.json", ano)
            continue
        feitos.append(ano)
        inv = Counter()
        for cnpj, a in agregar(z, alvo, inv, datas).items():
            por_cnpj.setdefault(cnpj, {})[str(ano)] = a
        invalidas[ano] = inv[ARQUIVO]
    gravar(saida, {"fonte": [bx.url_contas(a) for a in feitos],
                   "data_base": data_iso(max(datas, key=data_iso)) if datas else None,
                   "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "anos": feitos, "por_cnpj": dict(sorted(por_cnpj.items()))})
    return invalidas


def checar_disco(url, pasta, opener=urllib.request.urlopen, disk_usage=shutil.disk_usage):
    """HEAD no pacote; exige 2x o Content-Length livre (como rastro/cnpj.py)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": bx.UA})
    with opener(req, timeout=60) as r:
        tam = int(r.headers.get("Content-Length") or 0)
    Path(pasta).mkdir(parents=True, exist_ok=True)
    livre = disk_usage(pasta).free
    if livre < 2 * tam:
        raise SystemExit(f"pouco espaço em {pasta}: livre {livre / 1e9:.1f} GB, necessário {2 * tam / 1e9:.1f} GB (2x o pacote)")


def main(argv=None, opener=urllib.request.urlopen, hoje=None):
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baixar", action="store_true", help="baixa cada ZIP (GBs), processa o ano e apaga o ZIP")
    args = ap.parse_args(argv)
    anos = json.loads(CONFIG.read_text(encoding="utf-8"))["anteriores_anos"]
    zips = {a: BRUTOS / bx.url_contas(a).rsplit("/", 1)[-1] for a in anos}
    if args.baixar:
        if (hoje or date.today()) == bx.DIA_APURACAO:  # o HEAD do checar_disco também bate no TSE
            raise SystemExit("25/10: não baixar nada do TSE no dia da apuração (mesmo IP de saída do agregador)")
        for a in anos:  # um ano por vez: o disco só precisa de um pacote
            try:
                checar_disco(bx.url_contas(a), BRUTOS, opener)
                print(f"{zips[a].name}: {bx.baixar(bx.url_contas(a), zips[a], opener, hoje)}")
            except Exception as e:  # 404 etc. (inclusive no HEAD): o ano fica fora, os outros seguem
                log.warning("%s: não baixado (%s)", a, e)
    try:
        inv = gerar(anos, zips, SAIDA_AGREGADOS, SAIDA)
    finally:
        if args.baixar:
            for z in zips.values():
                z.unlink(missing_ok=True)
                z.with_name(z.name + ".lastmod").unlink(missing_ok=True)
    print(f"gravado em {SAIDA}")
    for a in anos:
        print(f"linhas inválidas em {a}: {inv[a]}")


if __name__ == "__main__":
    main()
