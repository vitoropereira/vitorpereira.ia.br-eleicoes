#!/usr/bin/env python3
"""Lê o ZIP do extrato bancário das campanhas 2026 (rastro/brutos/, em streaming, sem extrair) e grava
rastro/brutos/extrato_saques.json (fora do git): {cnpj_prestador: [{data, ds, tp, valor}]}, só com os lançamentos
de saque ou pagamento em espécie. A contraparte (CPF/CNPJ e nome) nunca é guardada. Uso: python3 rastro/extrato.py"""
import csv
import io
import json
import logging
import zipfile
from collections import Counter
from pathlib import Path

try:
    from rastro.baixar import OUT as BRUTOS, URL_EXTRATO
    from rastro.cnpj import _norm
    from rastro.contas import data_iso, digitos, gravar, limpar_texto, num, parse_valor
except ImportError:  # rodado como script: python3 rastro/extrato.py
    from baixar import OUT as BRUTOS, URL_EXTRATO
    from cnpj import _norm
    from contas import data_iso, digitos, gravar, limpar_texto, num, parse_valor

log = logging.getLogger("rastro.extrato")
AQUI = Path(__file__).resolve().parent
CONFIG = AQUI / "config.json"
ZIP_EXTRATO = BRUTOS / URL_EXTRATO.rsplit("/", 1)[-1]
SAIDA_SAQUES = BRUTOS / "extrato_saques.json"
ARQ = "extrato_bancario"


def membro_csv(nomes):
    """O *_BRASIL.csv do ZIP, ou o único CSV se não houver esse sufixo."""
    csvs = [n for n in nomes if n.lower().endswith(".csv")]
    brasil = [n for n in csvs if n.rsplit("/", 1)[-1].upper().endswith("_BRASIL.CSV")]
    escolhidos = brasil or csvs
    if len(escolhidos) != 1:
        raise FileNotFoundError(f"esperava 1 CSV (*_BRASIL.csv) no extrato, achei {escolhidos}")
    return escolhidos[0]


def ler_extrato(zip_path, termos, invalidas=None):
    """{cnpj_prestador: [{data, ds, tp, valor}]} dos lançamentos cuja descrição contém algum dos termos
    (comparação sem acento e sem caixa). Valor ausente ou inválido não vira 0: conta em invalidas e entra no log."""
    invalidas = invalidas if invalidas is not None else Counter()
    termos = [_norm(t) for t in termos]
    out = {}
    with zipfile.ZipFile(zip_path) as z:
        with z.open(membro_csv(z.namelist())) as bruto:
            leitor = csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")
            for l in leitor:
                ds = l.get("DS_LANCAMENTO") or ""
                if not any(t in _norm(ds) for t in termos):
                    continue
                cnpj = digitos(l.get("NR_CNPJ_PRESTADOR_CONTA"))
                if len(cnpj) != 14:
                    invalidas[f"{ARQ} (sem cnpj)"] += 1
                    continue
                try:
                    v = parse_valor(l.get("VR_LANCAMENTO"))
                except ValueError:
                    v = None
                if v is None:  # vazio, #NULO ou lixo: nunca vira 0
                    invalidas[ARQ] += 1
                    log.warning("%s: VR_LANCAMENTO ausente ou inválido num saque (campanha ...%s)", ARQ, cnpj[-6:])
                    continue
                try:
                    data = data_iso((l.get("DT_LANCAMENTO") or "").strip()[:10])
                except ValueError:
                    data = None
                out.setdefault(cnpj, []).append({"data": data, "ds": limpar_texto(ds), "tp": (l.get("TP_LANCAMENTO") or "").strip(),
                                                 "valor": num(v)})
    return out


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalidas = Counter()
    saques = ler_extrato(ZIP_EXTRATO, cfg["saque_termos"], invalidas)
    gravar(SAIDA_SAQUES, saques)
    print(f"{sum(len(v) for v in saques.values())} saques de {len(saques)} campanhas em {SAIDA_SAQUES}")
    print(f"linhas inválidas: {dict(invalidas)}")


if __name__ == "__main__":
    main()
