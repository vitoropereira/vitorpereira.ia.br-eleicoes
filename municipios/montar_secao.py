#!/usr/bin/env python3
"""Cruza a votação por seção do TSE (presidente) com os locais de votação geolocalizados.
Fonte: municipios/brutos_secao/ (baixar_secao.py), lida direto dos ZIPs, em streaming.
Saída: municipios/geo/locais/<ibge>.json (ou <UF>.json com --por-uf), copiado pelo build_site.py para site/geo/locais/.
Formato por município: {"cand": {turno: [[nr, nome], ...]}, "t": {turno: [local, ...]}}, com
local = [lat, lon, nome, bairro, cep5, aptos, comp, [votos]|null, bn|null, [[zona, secao, aptos, comp, [votos]|null, bn|null], ...]].
Votos seguem a ordem de cand[turno]; bn = brancos + nulos. Abaixo do PISO de comparecimento só ficam aptos e comparecimento.
O 2º turno entra sozinho quando o TSE publicar as linhas com NR_TURNO=2.
Uso: python3 municipios/montar_secao.py [--por-uf]"""
import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent))
from municipios.baixar_t2022 import CONFIG_MUN  # noqa: E402
from municipios.montar import nome  # noqa: E402

BR = H / "brutos_secao"
OUT = H / "geo"
ZIP_SECAO = "votacao_secao_2026_BR.zip"
ZIP_LOCAIS = "eleitorado_local_votacao_2026.zip"
CFG = CONFIG_MUN.rsplit("/", 1)[-1]
PISO = 30  # comparecimento mínimo para mostrar voto por candidato (seção ou local)
BN = {"95", "96", "97"}  # branco, nulo, anulado
LIMITE_BYTES = 15 * 1024 * 1024
LIMITE_ARQ = 6000
csv.field_size_limit(1 << 24)


def linhas_zip(caminho):
    """Linhas (dict) de todos os CSVs do ZIP, sem extrair; pula o _BRASIL.csv (duplicata das UFs)."""
    with zipfile.ZipFile(caminho) as zf:
        for m in sorted(zf.namelist()):
            if not m.lower().endswith(".csv") or m.lower().endswith("_brasil.csv"):
                continue
            with zf.open(m) as b, io.TextIOWrapper(b, encoding="latin-1", newline="") as f:
                yield from csv.DictReader(f, delimiter=";")


def mapa_ibge(cfg):
    """(UF, código TSE do município) -> código IBGE (cdi), como em montar_t2022.py."""
    return {(ab["cd"].upper(), m["cd"]): m["cdi"] for ab in cfg["abr"] for m in ab["mu"] if m.get("cdi")}


def _num(s):
    return int(s) if s and s.strip().lstrip("-").isdigit() else 0


def _coord(s):
    s = (s or "").strip().replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return None if v == -1 else v


def _cep5(s):
    s = (s or "").strip()
    return s.zfill(8)[:5] if s.isdigit() and int(s) > 0 else None


def _txt(s):
    s = (s or "").strip()
    return None if s in ("", "#NULO", "#NE", "-1") else s


def _apara(v):
    while v and v[-1] == 0:
        v.pop()
    return v


def juntar(secao_zip, locais_zip, cfg):
    """Junta seção e local por (UF, município TSE, zona, seção). Devolve (dados, órfãs, sem_cdi):
    dados = {ibge: registro}; órfãs = seções sem local [(turno, uf, mun, zona, secao)]; sem_cdi = [(uf, mun)]."""
    ibge = mapa_ibge(cfg)

    # locais: uma linha por seção e turno; seção agregada soma os aptos na principal
    loc, apt = {}, {}  # (turno, uf, mun, zona, secao) -> nr_local; idem -> aptos
    info = {}  # (uf, mun, zona, nr_local) -> [lat, lon, nome, bairro, cep5]
    for r in linhas_zip(locais_zip):
        t, uf, mun, zona = r.get("NR_TURNO") or "1", r["SG_UF"], r["CD_MUNICIPIO"].zfill(5), int(r["NR_ZONA"])
        sec, princ = int(r["NR_SECAO"]), _num(r.get("NR_SECAO_PRINCIPAL"))
        alvo = princ if princ > 0 else sec
        k = (t, uf, mun, zona, alvo)
        apt[k] = apt.get(k, 0) + _num(r.get("QT_ELEITOR_SECAO"))
        if alvo != sec:
            continue
        nl = int(r["NR_LOCAL_VOTACAO"])
        loc[k] = nl
        info.setdefault((uf, mun, zona, nl), [_coord(r.get("NR_LATITUDE")), _coord(r.get("NR_LONGITUDE")),
                                              _txt(r.get("NM_LOCAL_VOTACAO")), _txt(r.get("NM_BAIRRO")), _cep5(r.get("NR_CEP"))])

    # votos de presidente por seção
    votos, cinfo, tot = {}, {}, {}  # (t, uf, mun, zona, secao) -> {nr: votos}; t -> nr -> nome; t -> nr -> total
    for r in linhas_zip(secao_zip):
        if r["CD_CARGO"] != "1":
            continue
        t, nr, q = r["NR_TURNO"], r["NR_VOTAVEL"], int(r["QT_VOTOS"])
        k = (t, r["SG_UF"], r["CD_MUNICIPIO"].zfill(5), int(r["NR_ZONA"]), int(r["NR_SECAO"]))
        d = votos.setdefault(k, {})
        d[nr] = d.get(nr, 0) + q
        if nr not in BN:
            cinfo.setdefault(t, {})[nr] = nome(r["NM_VOTAVEL"])
            tt = tot.setdefault(t, {})
            tt[nr] = tt.get(nr, 0) + q

    ordem = {t: sorted(c, key=lambda nr: (-tot[t][nr], int(nr))) for t, c in cinfo.items()}
    idx = {t: {nr: i for i, nr in enumerate(o)} for t, o in ordem.items()}
    cand = {t: [[int(nr), cinfo[t][nr]] for nr in o] for t, o in sorted(ordem.items())}

    orfas, sem_cdi, grupos = [], set(), {}  # (cdi, t, uf, mun, zona, nr_local) -> [secoes]
    fora = {}  # (cdi, t) -> comparecimento das seções órfãs (entra no total do município, não sai em local nenhum)
    for k in sorted(votos):
        t, uf, mun, zona, sec = k
        if uf == "ZZ":
            continue  # exterior: sem município IBGE nem coordenada
        if (uf, mun) not in ibge:
            sem_cdi.add((uf, mun))
            continue
        nl = loc.get(k, loc.get(("1",) + k[1:]))  # 2º turno sem linha própria nos locais: usa a do 1º
        if nl is None:
            orfas.append(k)
            kf = (ibge[(uf, mun)], t)
            fora[kf] = fora.get(kf, 0) + sum(votos[k].values())
            continue
        d = votos[k]
        v = [0] * len(idx[t])
        for nr, q in d.items():
            if nr not in BN:
                v[idx[t][nr]] = q
        comp, bn = sum(d.values()), sum(q for nr, q in d.items() if nr in BN)
        aptos = apt.get(k, apt.get(("1",) + k[1:], 0))
        grupos.setdefault((ibge[(uf, mun)], t, uf, mun, zona, nl), []).append([zona, sec, aptos, comp, v, bn])

    dados = {}
    for (cdi, t, uf, mun, zona, nl), secs in sorted(grupos.items()):
        aptos, comp = sum(s[2] for s in secs), sum(s[3] for s in secs)
        v = [sum(x) for x in zip(*(s[4] for s in secs))]
        bn = sum(s[5] for s in secs)
        # total do local menos as seções visíveis não pode revelar uma seção abaixo do piso
        ocultas = _ocultar(secs, 3)
        for i, s in enumerate(secs):
            if i in ocultas:
                s[4] = s[5] = None
            else:
                s[4] = _apara(s[4])
        local = info[(uf, mun, zona, nl)] + [aptos, comp, _apara(v), bn, secs]
        reg = dados.setdefault(cdi, {"uf": uf, "cand": {}, "t": {}})
        reg["cand"][t] = cand[t]
        reg["t"].setdefault(t, []).append(local)
    # mesmo raciocínio um nível acima: o total do município (publicado em geo/t1) menos os locais visíveis não pode
    # revelar um local abaixo do piso; local oculto leva junto o voto de todas as suas seções
    for cdi, reg in dados.items():
        for t, locais in reg["t"].items():
            for i in _ocultar(locais, 6, fora.get((cdi, t), 0)):
                locais[i][7] = locais[i][8] = None
                for s in locais[i][9]:
                    s[4] = s[5] = None
    return dados, orfas, sorted(sem_cdi)


def _ocultar(itens, col, fora=0):
    """Índices sem voto: comparecimento (itens[i][col]) abaixo do PISO e, por supressão complementar, os menores
    visíveis até as ocultas somarem PISO (o total do nível de cima menos as visíveis não pode revelar uma oculta).
    fora = comparecimento que entra no total de cima mas não sai em item nenhum (seções órfãs): se for de 1 a PISO-1,
    a diferença revelaria essas seções, então também se oculta até fora + ocultas somarem PISO."""
    ocultas = {i for i, x in enumerate(itens) if x[col] < PISO}
    visiveis = sorted((x[col], i) for i, x in enumerate(itens) if i not in ocultas)
    soma = sum(itens[i][col] for i in ocultas)
    while visiveis and ((ocultas and soma < PISO) or 0 < fora and fora + soma < PISO):
        c, i = visiveis.pop(0)
        ocultas.add(i)
        soma += c
    return ocultas


def serializar(dados, por_uf=False):
    """{nome do arquivo sem .json: bytes UTF-8}: <ibge> -> registro, ou <UF> -> {ibge: registro}."""
    arqs = {}
    for cdi, reg in dados.items():
        r = {"cand": reg["cand"], "t": reg["t"]}
        if por_uf:
            arqs.setdefault(reg["uf"], {})[cdi] = r
        else:
            arqs[cdi] = r
    return {nm: json.dumps(o, separators=(",", ":"), ensure_ascii=False).encode("utf-8") for nm, o in arqs.items()}


def gravar(arqs, out):
    """Troca o conteúdo de out/locais/ pelos arquivos já serializados. Devolve (n_arquivos, bytes)."""
    pasta = Path(out) / "locais"
    pasta.mkdir(parents=True, exist_ok=True)
    for p in pasta.glob("*.json"):
        p.unlink()
    for nm, b in arqs.items():
        (pasta / f"{nm}.json").write_bytes(b)
    return len(arqs), sum(map(len, arqs.values()))


def montar(brutos=BR, out=OUT, por_uf=False, limite_bytes=LIMITE_BYTES, limite_arq=LIMITE_ARQ):
    """Lê os ZIPs de brutos/, grava em out/locais/ e devolve (n_arquivos, bytes).
    Acima do limite (arquivos ou bytes), grava por UF mesmo sem por_uf."""
    brutos = Path(brutos)
    for n in (ZIP_SECAO, ZIP_LOCAIS, CFG):
        if not (brutos / n).exists():
            sys.exit(f"falta {brutos / n}: rode municipios/baixar_secao.py antes")
    cfg = json.loads((brutos / CFG).read_text(encoding="utf-8"))
    dados, orfas, sem_cdi = juntar(brutos / ZIP_SECAO, brutos / ZIP_LOCAIS, cfg)
    if orfas:
        print(f"seções sem local de votação: {len(orfas)} (ex.: {orfas[:5]})")
    if sem_cdi:
        print(f"municípios sem código IBGE no mun-config: {len(sem_cdi)} {sem_cdi[:10]}")
    arqs = serializar(dados, por_uf)
    if not por_uf and (len(arqs) > limite_arq or sum(map(len, arqs.values())) > limite_bytes):
        print(f"acima de {limite_arq} arquivos ou {limite_bytes / 2**20:.0f} MB: gravando por UF")
        arqs = serializar(dados, True)
    return gravar(arqs, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--por-uf", action="store_true", help="um arquivo por UF em vez de um por município")
    args = ap.parse_args(argv)
    n, b = montar(por_uf=args.por_uf)
    print(f"locais: {n} arquivos, {b / 2**20:.1f} MB em {OUT / 'locais'}")
    if b > LIMITE_BYTES:
        print(f"aviso: passou de {LIMITE_BYTES / 2**20:.0f} MB")


if __name__ == "__main__":
    main()
