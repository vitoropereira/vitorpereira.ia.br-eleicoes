#!/usr/bin/env python3
"""Base CNPJ da Receita, só dos fornecedores PJ dos eleitos: lê os ZIPs (rastro/brutos/cnpj/<AAAA-MM>/, em streaming,
sem extrair) e grava rastro/dados/fornecedores.json. Sócio só com o CPF mascarado que a Receita já publica.
Uso: python3 rastro/cnpj.py [--mes AAAA-MM]"""
import argparse
import csv
import io
import json
import logging
import re
import unicodedata
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from rastro import baixar
    from rastro.contas import SAIDA_CONTAS, cpf_valido, digitos, gravar, limpar_texto
except ImportError:  # rodado como script: python3 rastro/cnpj.py
    import baixar
    from contas import SAIDA_CONTAS, cpf_valido, digitos, gravar, limpar_texto

log = logging.getLogger("rastro.cnpj")
AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "dados" / "fornecedores.json"
# compartilhamento Nextcloud do SERPRO; a listagem não foi verificada por script (ver rastro/README.md)
BASE_CNPJ = "https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9/download"
MES_PADRAO = "2026-09"
PARTES = 10  # Empresas0..9, Estabelecimentos0..9, Socios0..9
SITUACAO = {"01": "NULA", "02": "ATIVA", "03": "SUSPENSA", "04": "INAPTA", "08": "BAIXADA"}
RE_MASCARA = re.compile(r"\*{3}\d{6}\*{2}")


def nomes_zip():
    return ([f"{g}{i}.zip" for g in ("Empresas", "Estabelecimentos", "Socios") for i in range(PARTES)]
            + ["Simples.zip"])


def url_zip(mes, nome):
    return f"{BASE_CNPJ}?path=/{mes}&files={nome}"


def cnpjs_alvo(dir_contas):
    """Conjunto de CNPJs (14 dígitos) de fornecedores_pj em dir_contas/<sq>.json."""
    alvo = set()
    for arq in sorted(Path(dir_contas).glob("*.json")):
        desp = json.loads(arq.read_text(encoding="utf-8")).get("despesas") or {}
        for f in desp.get("fornecedores_pj", []):
            doc = digitos(f.get("cnpj"))
            if len(doc) == 14:
                alvo.add(doc)
            else:
                log.warning("%s: documento de fornecedor PJ com tamanho errado ignorado", arq.name)
    return alvo


def situacao(cod):
    cod = (cod or "").strip()
    if cod not in SITUACAO:
        log.warning("situação cadastral desconhecida: %r", cod)
        return cod or None
    return SITUACAO[cod]


def data_iso(txt):
    txt = (txt or "").strip()
    if not txt or txt == "00000000":
        return None
    try:
        return datetime.strptime(txt, "%Y%m%d").date().isoformat()
    except ValueError:
        log.warning("data inválida: %r", txt)
        return None


def _norm(txt):
    sem = unicodedata.normalize("NFD", txt or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem.upper()).strip()


def endereco_chave(tipo, logradouro, numero, cep):
    """'RUA DAS FLORES|123|01234567'; sem logradouro ou sem CEP de 8 dígitos não há chave."""
    rua = _norm(f"{tipo or ''} {logradouro or ''}") if (logradouro or "").strip() else ""
    cep = digitos(cep)
    if not rua or len(cep) != 8:
        return None
    num = _norm(numero)
    if num in ("", "S/N", "SN"):
        num = "SN"
    return f"{rua}|{num}|{cep}"


def cpf_mascarado(identificador, campo):
    """Só PF, e só o que já vem mascarado. CPF inteiro ou lixo nunca é gravado."""
    if (identificador or "").strip() != "2":
        return None
    campo = (campo or "").strip()
    if RE_MASCARA.fullmatch(campo):
        return campo
    if cpf_valido(digitos(campo)):
        log.warning("sócio PF com CPF sem máscara descartado")
    else:
        log.warning("sócio PF com CPF em formato inesperado descartado: %r", re.sub(r"\d", "9", campo))
    return None


def ler_zip(caminho):
    """Linhas (listas) do único membro do ZIP: ';', latin-1, sem cabeçalho. Nada vai a disco."""
    with zipfile.ZipFile(caminho) as z:
        membros = z.namelist()
        if len(membros) != 1:
            raise FileNotFoundError(f"{caminho}: esperava 1 membro, achei {membros}")
        with z.open(membros[0]) as bruto:
            yield from csv.reader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")


def _zips(dir_zips, prefixo):
    achados = sorted(Path(dir_zips).glob(f"{prefixo}*.zip"))
    if not achados:
        log.warning("nenhum %s*.zip em %s", prefixo, dir_zips)
    return achados


def _col(linha, i):
    return linha[i] if len(linha) > i else ""


def gerar(dir_zips, dir_contas, saida, mes=MES_PADRAO):
    """Filtra a base pelos CNPJs-alvo e grava saida. Devolve (alvos, encontrados)."""
    alvo = cnpjs_alvo(dir_contas)
    forn = {}
    for z in _zips(dir_zips, "Estabelecimentos"):
        for l in ler_zip(z):
            cnpj = _col(l, 0) + _col(l, 1) + _col(l, 2)
            if cnpj in alvo:
                forn[cnpj] = {"razao": None, "abertura": data_iso(_col(l, 10)), "situacao": situacao(_col(l, 5)),
                              "cnae": _col(l, 11).strip() or None, "mei": False, "simples": False,
                              "endereco_chave": endereco_chave(_col(l, 13), _col(l, 14), _col(l, 15), _col(l, 18)),
                              "socios": []}
    achados = set(forn)
    basicos = {c[:8] for c in achados}
    for z in _zips(dir_zips, "Empresas"):
        for l in ler_zip(z):
            if _col(l, 0) in basicos:
                for c in achados:
                    if c[:8] == l[0]:
                        forn[c]["razao"] = limpar_texto(_col(l, 1)) or None
    for z in _zips(dir_zips, "Socios"):
        for l in ler_zip(z):
            if _col(l, 0) in basicos:
                socio = {"nome": limpar_texto(_col(l, 2)) or None, "cpf_mascarado": cpf_mascarado(_col(l, 1), _col(l, 3))}
                for c in sorted(achados):
                    if c[:8] == l[0]:
                        forn[c]["socios"].append(socio)
    for z in _zips(dir_zips, "Simples"):
        for l in ler_zip(z):
            if _col(l, 0) in basicos:
                optante = _col(l, 1).strip() == "S" and not data_iso(_col(l, 3))
                mei = _col(l, 4).strip() == "S" and not data_iso(_col(l, 6))
                for c in achados:
                    if c[:8] == l[0]:
                        forn[c]["simples"], forn[c]["mei"] = optante or mei, mei
    for cnpj in sorted(alvo - achados):
        log.warning("CNPJ %s não está na base da Receita", cnpj)
        forn[cnpj] = {"razao": None, "abertura": None, "situacao": None, "cnae": None, "mei": False,
                      "simples": False, "endereco_chave": None, "socios": []}
    obj = {"fonte": [url_zip(mes, n) for n in nomes_zip()], "data_base": f"{mes}-01",
           "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "fornecedores": dict(sorted(forn.items()))}
    gravar(saida, obj)
    return len(alvo), len(achados)


def main(argv=None, opener=urllib.request.urlopen, hoje=None):
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mes", default=MES_PADRAO, help="mês de referência da Receita, AAAA-MM")
    mes = ap.parse_args(argv).mes
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        raise SystemExit(f"--mes inválido: {mes!r} (use AAAA-MM)")
    pasta = baixar.OUT / "cnpj" / mes
    for nome in nomes_zip():
        print(f"{nome}: {baixar.baixar(url_zip(mes, nome), pasta / nome, opener=opener, hoje=hoje)}")
    alvos, achados = gerar(pasta, SAIDA_CONTAS, SAIDA, mes)
    print(f"{achados} de {alvos} CNPJs-alvo encontrados; saída em {SAIDA}")


if __name__ == "__main__":
    main()
