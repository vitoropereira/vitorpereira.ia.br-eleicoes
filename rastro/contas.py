#!/usr/bin/env python3
"""Lê o ZIP de prestação de contas 2026 (rastro/brutos/, em streaming, sem extrair) e grava:
rastro/dados/contas/<sq>.json (um por eleito), rastro/dados/base/agregados.json (todos os candidatos) e
rastro/brutos/doadores_hash.json (fora do git). Só os arquivos *_BRASIL.csv são lidos. Uso: python3 rastro/contas.py"""
import csv
import hashlib
import io
import json
import logging
import os
import re
import secrets
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

try:
    from rastro.baixar import OUT as BRUTOS, URL_CONTAS
    from rastro.eleitos import CARGOS, DADOS, UFS, codigos
except ImportError:  # rodado como script: python3 rastro/contas.py
    from baixar import OUT as BRUTOS, URL_CONTAS
    from eleitos import CARGOS, DADOS, UFS, codigos

log = logging.getLogger("rastro.contas")
AQUI = Path(__file__).resolve().parent
ZIP_CONTAS = BRUTOS / URL_CONTAS.rsplit("/", 1)[-1]
ELEITOS = AQUI / "dados" / "eleitos.json"
SAIDA_CONTAS = AQUI / "dados" / "contas"
SAIDA_AGREGADOS = AQUI / "dados" / "base" / "agregados.json"
SAIDA_HASH = BRUTOS / "doadores_hash.json"
SAIDA_PF = BRUTOS / "pf_por_campanha.json"
SAL = AQUI / ".sal"

CARGO_DS = {"governador": "governador", "senador": "senador", "deputado federal": "depfed",
            "deputado estadual": "depest", "deputado distrital": "distrital"}
RE_VALOR = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?")
RE_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
NULOS = {"", "#NULO", "#NE", "#NULO#"}
CODIGOS_NULOS = {"-1", "-3", "-4"}  # o TSE usa códigos negativos como "não informado" em campos de texto


def parse_valor(txt):
    """'1.234,56' -> Decimal('1234.56'); vazio e '#NULO' -> None (nunca 0); lixo -> ValueError."""
    txt = (txt or "").strip()
    if txt.upper() in NULOS:
        return None
    if not RE_VALOR.fullmatch(txt):
        raise ValueError(txt)
    return Decimal(txt.replace(".", "").replace(",", "."))


def valor_linha(linha, campo, arquivo, invalidas):
    """parse_valor de uma linha; valor inválido vira None, entra em invalidas[arquivo] e no log."""
    try:
        return parse_valor(linha.get(campo))
    except ValueError:
        invalidas[arquivo] += 1
        log.warning("%s: %s inválido %r (SQ_CANDIDATO=%s)", arquivo, campo, linha.get(campo), linha.get("SQ_CANDIDATO"))
        return None


def ler_csv(zip_path, prefixo):
    """Gerador de dicts do membro <prefixo>_<ano>_BRASIL.csv, lido direto do ZIP (nada vai a disco)."""
    padrao = re.compile(rf"{re.escape(prefixo)}_\d{{4}}_BRASIL\.csv")
    with zipfile.ZipFile(zip_path) as z:
        membros = [n for n in z.namelist() if padrao.fullmatch(n.rsplit("/", 1)[-1])]
        if len(membros) != 1:
            raise FileNotFoundError(f"{zip_path}: esperava 1 membro {prefixo}_*_BRASIL.csv, achei {membros}")
        with z.open(membros[0]) as bruto:
            yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")


def cpf_valido(d):
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def limpar_texto(txt):
    """Remove sequências de CPF válido (inclusive o sufixo de nome de MEI) e normaliza espaços."""
    sem = RE_CPF.sub(lambda m: "" if cpf_valido(re.sub(r"\D", "", m.group())) else m.group(), txt or "")
    return re.sub(r"\s+", " ", sem).strip()


def texto(linha, campo):
    v = (linha.get(campo) or "").strip()
    return None if v.upper() in NULOS or v in CODIGOS_NULOS else v


def digitos(s):
    return re.sub(r"\D", "", s or "")


def num(x):
    return float(round(x, 2))


def qtd(por_doc):
    """Pessoas distintas; documento ausente não conta como uma pessoa."""
    return sum(1 for doc in por_doc if doc)


def data_iso(dt):
    return datetime.strptime(dt, "%d/%m/%Y").date().isoformat()


def novo_cand(linha):
    return {"uf": linha.get("SG_UF"), "ds_cargo": linha.get("DS_CARGO"),
            "rec": False, "rec_total": Decimal(0), "por_origem": defaultdict(Decimal),
            "por_fonte": defaultdict(Decimal), "doa_pj": {}, "doa_pf": defaultdict(Decimal),
            "desp": False, "contratado": Decimal(0), "pago": Decimal(0), "ids": set(), "ids_pago": set(),
            "forn_pj": {}, "forn_pf": defaultdict(Decimal), "pf_tipo": defaultdict(Decimal),
            "tipo_total": defaultdict(Decimal), "cnpj_prestador": None,
            "pago_dia": defaultdict(Decimal), "com_data": False}


def acumular(zip_path, invalidas):
    """Uma passada pelos 3 CSVs _BRASIL. Devolve (candidatos por sq, pessoas por cpf, maior DT_GERACAO em ISO)."""
    cands, pessoas, datas, prestador = {}, {}, set(), {}

    def cand(l):
        dt = l.get("DT_GERACAO")
        if dt:
            datas.add(dt)
        prestador[l["SQ_PRESTADOR_CONTAS"]] = l["SQ_CANDIDATO"]
        c = cands.setdefault(l["SQ_CANDIDATO"], novo_cand(l))
        cnpj = digitos(l.get("NR_CNPJ_PRESTADOR_CONTA"))  # CNPJ da campanha: dado público
        if len(cnpj) == 14:
            c["cnpj_prestador"] = cnpj
        return c

    def pessoa(cpf, nome, sq, v, papel):
        p = pessoas.setdefault(cpf, {"nome": nome, "campanhas": set(), "total": Decimal(0), "papeis": set()})
        p["campanhas"].add(sq)
        p["total"] += v
        p["papeis"].add(papel)

    arq = "receitas_candidatos"
    for l in ler_csv(zip_path, arq):
        c = cand(l)
        c["rec"] = True
        v = valor_linha(l, "VR_RECEITA", arq, invalidas)
        if v is None:
            continue
        c["rec_total"] += v
        c["por_origem"][texto(l, "DS_ORIGEM_RECEITA") or "Não informada"] += v
        c["por_fonte"][texto(l, "DS_FONTE_RECEITA") or "Não informada"] += v
        doc, nome = digitos(l.get("NR_CPF_CNPJ_DOADOR")), limpar_texto(l.get("NM_DOADOR"))
        if len(doc) == 14:
            d = c["doa_pj"].setdefault(doc, [nome, Decimal(0)])
            d[1] += v
        else:
            c["doa_pf"][doc] += v
            if len(doc) == 11:
                pessoa(doc, nome, l["SQ_CANDIDATO"], v, "doador")

    arq = "despesas_contratadas_candidatos"
    for l in ler_csv(zip_path, arq):
        c = cand(l)
        c["desp"] = True
        v = valor_linha(l, "VR_DESPESA_CONTRATADA", arq, invalidas)
        sqd = texto(l, "SQ_DESPESA")
        if v is None or (sqd and sqd in c["ids"]):  # a linha repete por parcela: conta a despesa uma vez
            continue
        c["ids"].add(sqd)
        c["contratado"] += v
        tipo = texto(l, "DS_ORIGEM_DESPESA") or "Não informada"
        c["tipo_total"][tipo] += v
        doc, nome = digitos(l.get("NR_CPF_CNPJ_FORNECEDOR")), limpar_texto(l.get("NM_FORNECEDOR"))
        if len(doc) == 14:
            f = c["forn_pj"].setdefault(doc, {"nome": nome, "cnae": texto(l, "CD_CNAE_FORNECEDOR"),
                                              "n": 0, "tipos": set(), "total": Decimal(0)})
            f["n"] += 1
            f["tipos"].add(tipo)
            f["total"] += v
        else:
            c["forn_pf"][doc] += v
            c["pf_tipo"][tipo] += v
            if len(doc) == 11:
                pessoa(doc, nome, l["SQ_CANDIDATO"], v, "fornecedor")

    arq = "despesas_pagas_candidatos"
    for l in ler_csv(zip_path, arq):  # este arquivo não traz o candidato: liga pelo prestador de contas
        c = cands.get(prestador.get(l["SQ_PRESTADOR_CONTAS"]))
        if c is None:
            invalidas[f"{arq} (sem candidato)"] += 1
            continue
        c["desp"] = True
        v = valor_linha(l, "VR_PAGTO_DESPESA", arq, invalidas)
        chave = (texto(l, "SQ_DESPESA"), texto(l, "SQ_PARCELAMENTO_DESPESA"))
        if v is None or (chave[0] and chave in c["ids_pago"]):
            continue
        c["ids_pago"].add(chave)
        c["pago"] += v
        if "DT_PAGTO_DESPESA" in l:
            c["com_data"] = True
            try:
                c["pago_dia"][data_iso(texto(l, "DT_PAGTO_DESPESA") or "")] += v
            except ValueError:
                invalidas[f"{arq} (data)"] += 1
    return cands, pessoas, (data_iso(max(datas, key=data_iso)) if datas else None)


def contas_json(e, c, meta):
    rec = desp = None
    if c and c["rec"]:
        rec = {"total": num(c["rec_total"]),
               "por_origem": {k: num(v) for k, v in sorted(c["por_origem"].items())},
               "por_fonte": {k: num(v) for k, v in sorted(c["por_fonte"].items())},
               "doadores_pj": [{"cnpj": k, "nome": n, "total": num(t)}
                               for k, (n, t) in sorted(c["doa_pj"].items(), key=lambda kv: (-kv[1][1], kv[0]))],
               "doadores_pf": {"qtd": qtd(c["doa_pf"]), "total": num(sum(c["doa_pf"].values(), Decimal(0)))}}
    if c and c["desp"]:
        desp = {"total_contratado": num(c["contratado"]), "total_pago": num(c["pago"]),
                "fornecedores_pj": [{"cnpj": k, "nome": f["nome"], "cnae": f["cnae"], "n_despesas": f["n"],
                                     "tipos": sorted(f["tipos"]), "total": num(f["total"])}
                                    for k, f in sorted(c["forn_pj"].items(), key=lambda kv: (-kv[1]["total"], kv[0]))],
                "fornecedores_pf": {"qtd": qtd(c["forn_pf"]), "total": num(sum(c["forn_pf"].values(), Decimal(0))),
                                    "por_tipo": {k: num(v) for k, v in sorted(c["pf_tipo"].items())},
                                    "valores": sorted(num(v) for doc, v in c["forn_pf"].items() if doc)}}
        desp["pago_por_dia"] = ({k: num(v) for k, v in sorted(c["pago_dia"].items())} if c["com_data"] else None)
    return {"sq": e["sq"], "nome_urna": e["nome_urna"], "cargo": e["cargo"], "uf": e["uf"], "partido": e["partido"],
            "cnpj_prestador": c["cnpj_prestador"] if c else None,
            "prestacao_parcial": rec is not None or desp is not None,
            "receitas": rec, "despesas": desp, **meta}


def ler_votos(dados_dir, ufs):
    """({sq: (cargo, UF, votos)} de todos os candidatos, {UF: eleitorado}) a partir de relatorio/dados/."""
    dados_dir = Path(dados_dir)
    votos, eleitorado = {}, {}
    for uf in ufs:
        pres = dados_dir / f"{uf}-c0001.json"
        if pres.exists():
            eleitorado[uf.upper()] = int(json.loads(pres.read_text(encoding="utf-8"))["e"]["te"])
        for cd in codigos(uf):
            arq = dados_dir / f"{uf}-c{cd:04d}.json"
            if not arq.exists():
                log.warning("sem %s: custo por voto de %s/%s fica de fora", arq.name, CARGOS[cd], uf.upper())
                continue
            d = json.loads(arq.read_text(encoding="utf-8"))
            for agr in d["carg"][0].get("agr", []):
                for par in agr.get("par", []):
                    for cand in par.get("cand", []):
                        votos[str(cand["sqcand"])] = (CARGOS[cd], uf.upper(), int(cand.get("vap") or 0))
    return votos, eleitorado


def agregados_json(cands, votos, eleitorado, meta):
    por_cnpj, por_tipo, custo = {}, defaultdict(list), defaultdict(list)
    for sq, c in cands.items():
        for cnpj, f in c["forn_pj"].items():
            a = por_cnpj.setdefault(cnpj, {"total_recebido": Decimal(0), "campanhas": []})
            a["total_recebido"] += f["total"]
            a["campanhas"].append(sq)
        cargo = CARGO_DS.get((c["ds_cargo"] or "").lower(), (c["ds_cargo"] or "").lower())
        for tipo, t in c["tipo_total"].items():
            por_tipo[f"{tipo}|{cargo}|{c['uf']}"].append(num(t))
        cargo_v, uf_v, n_votos = votos.get(sq, (None, None, 0))
        if cargo_v and n_votos > 0 and c["ids"]:
            custo[f"{cargo_v}|{uf_v}"].append(round(float(c["contratado"]) / n_votos, 2))
    return {
        "por_cnpj": {k: {"total_recebido": num(a["total_recebido"]), "n_campanhas": len(a["campanhas"]),
                         "campanhas": sorted(a["campanhas"])} for k, a in sorted(por_cnpj.items())},
        "por_tipo_cargo_uf": {k: sorted(v) for k, v in sorted(por_tipo.items())},
        "custo_por_voto": {k: sorted(v) for k, v in sorted(custo.items())},
        "eleitorado": dict(sorted(eleitorado.items())),
        **meta,
    }


def carregar_sal(caminho=SAL):
    caminho = Path(caminho)
    if caminho.exists():
        return caminho.read_text(encoding="utf-8").strip()
    sal = secrets.token_hex(16)
    with os.fdopen(os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as f:
        f.write(sal + "\n")
    return sal


def hash_json(pessoas, sal):
    """sha256(sal+cpf) -> dados mínimos para cruzar sócio/doador depois. Nunca guarda o CPF inteiro."""
    out = {}
    for cpf, p in sorted(pessoas.items()):
        papel = next(iter(p["papeis"])) if len(p["papeis"]) == 1 else "ambos"
        out[hashlib.sha256((sal + cpf).encode()).hexdigest()] = {
            "nome": p["nome"], "cpf_meio": cpf[3:9], "campanhas": sorted(p["campanhas"]),
            "total": num(p["total"]), "papel": papel}
    return out


def pf_por_campanha(cands, sal):
    """{sq: [sha256(sal+cpf)]} dos fornecedores PF de cada campanha. Hash de CPF não se publica: fica em brutos/."""
    return {sq: sorted(hashlib.sha256((sal + doc).encode()).hexdigest() for doc in c["forn_pf"] if len(doc) == 11)
            for sq, c in sorted(cands.items())}


def gravar(caminho, obj):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def gerar(zip_path, eleitos_path, dados_dir, ufs, sal, saida_contas, saida_agregados, saida_hash, saida_pf=None):
    """Roda tudo e grava as saídas (a de hashes de PF só se saida_pf vier). Devolve o contador de linhas inválidas por arquivo."""
    invalidas = Counter()
    cands, pessoas, data_base = acumular(zip_path, invalidas)
    meta = {"fonte": [URL_CONTAS], "data_base": data_base,
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    eleitos = json.loads(Path(eleitos_path).read_text(encoding="utf-8"))["eleitos"]
    for e in eleitos:
        gravar(Path(saida_contas) / f"{e['sq']}.json", contas_json(e, cands.get(e["sq"]), meta))
    votos, eleitorado = ler_votos(dados_dir, ufs)
    gravar(saida_agregados, agregados_json(cands, votos, eleitorado, meta))
    gravar(saida_hash, hash_json(pessoas, sal))
    if saida_pf is not None:
        gravar(saida_pf, pf_por_campanha(cands, sal))
    return invalidas


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    invalidas = gerar(ZIP_CONTAS, ELEITOS, DADOS, UFS, carregar_sal(), SAIDA_CONTAS, SAIDA_AGREGADOS, SAIDA_HASH, SAIDA_PF)
    n = len(list(SAIDA_CONTAS.glob("*.json")))
    print(f"{n} contas em {SAIDA_CONTAS}; agregados em {SAIDA_AGREGADOS}")
    for arq in ("receitas_candidatos", "despesas_contratadas_candidatos", "despesas_pagas_candidatos",
                "despesas_pagas_candidatos (sem candidato)", "despesas_pagas_candidatos (data)"):
        print(f"linhas inválidas em {arq}: {invalidas[arq]}")


if __name__ == "__main__":
    main()
