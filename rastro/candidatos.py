#!/usr/bin/env python3
"""Lê consulta_cand_2026.zip (rastro/brutos/, em streaming) e grava rastro/brutos/candidatos.json (fora do git):
{sq: {nome, uf, cargo, cpf_meio|None}}, com titulares e suplentes. Só os 6 dígitos do meio do CPF são guardados,
nunca o CPF inteiro. Uso: python3 rastro/candidatos.py"""
import logging

try:
    from rastro.baixar import OUT as BRUTOS, URL_CAND
    from rastro.contas import cpf_valido, digitos, gravar, ler_csv, limpar_texto, texto
except ImportError:  # rodado como script: python3 rastro/candidatos.py
    from baixar import OUT as BRUTOS, URL_CAND
    from contas import cpf_valido, digitos, gravar, ler_csv, limpar_texto, texto

log = logging.getLogger("rastro.candidatos")
ZIP_CAND = BRUTOS / URL_CAND.rsplit("/", 1)[-1]
SAIDA = BRUTOS / "candidatos.json"


def candidatos(zip_path):
    out = {}
    for l in ler_csv(zip_path, "consulta_cand"):
        sq, nome = texto(l, "SQ_CANDIDATO"), limpar_texto(l.get("NM_CANDIDATO"))
        if not sq or not nome:
            continue
        cpf = digitos(l.get("NR_CPF_CANDIDATO"))
        out[sq] = {"nome": nome, "uf": texto(l, "SG_UF"), "cargo": texto(l, "DS_CARGO"),
                   "cpf_meio": cpf[3:9] if cpf_valido(cpf) else None}
    return out


def gerar(zip_path, saida):
    res = candidatos(zip_path)
    if res and not any(c["cpf_meio"] for c in res.values()):
        log.warning("nenhum candidato com CPF válido em %s: o ramo candidato do socio_ligado não vai casar", zip_path)
    gravar(saida, res)
    return res


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    res = gerar(ZIP_CAND, SAIDA)
    log.info("%d candidatos e suplentes -> %s", len(res), SAIDA)


if __name__ == "__main__":
    main()
