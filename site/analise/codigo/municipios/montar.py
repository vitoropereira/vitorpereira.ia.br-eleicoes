#!/usr/bin/env python3
"""Monta os dados publicados do painel (1º turno por município) em municipios/geo/.
Lê municipios/brutos/ (baixar.py), relatorio/dados/ (arquivos por UF), historico.json,
snapshots/*/dados.json, marcos/*/dados.json e relatorio/relatorio.json.
Saída: geo/municipios.topo.json e geo/t1/{meta,presidente,governador,senador,depfed,depest,serie,feed}.json
Uso: python3 municipios/montar.py"""
import json, shutil, sys
from pathlib import Path

H = Path(__file__).resolve().parent
R = H.parent
BR = H / "brutos"
UFD = R / "relatorio" / "dados"
GEO = H / "geo"
T1 = GEO / "t1"
UFS = "ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to".split()
NOME_UF = dict(AC="Acre", AL="Alagoas", AP="Amapá", AM="Amazonas", BA="Bahia", CE="Ceará", DF="Distrito Federal",
               ES="Espírito Santo", GO="Goiás", MA="Maranhão", MT="Mato Grosso", MS="Mato Grosso do Sul",
               MG="Minas Gerais", PA="Pará", PB="Paraíba", PR="Paraná", PE="Pernambuco", PI="Piauí",
               RJ="Rio de Janeiro", RN="Rio Grande do Norte", RS="Rio Grande do Sul", RO="Rondônia",
               RR="Roraima", SC="Santa Catarina", SP="São Paulo", SE="Sergipe", TO="Tocantins")
NOME_EXIBICAO = {"Flavio Bolsonaro": "Flávio Bolsonaro"}  # o TSE publica sem acento (mesmo critério do build_site.py)
PARTICULAS = {"de", "da", "do", "dos", "das", "e"}
SIGLAS = {"ACM", "JHC", "PM", "PRF", "II", "III"}


def cap(w):
    """Capitaliza respeitando hífen e apóstrofo (d'Oeste)."""
    for sep in ("-", "'"):
        if sep in w: return sep.join(cap(x) if x else x for x in w.split(sep))
    return w.capitalize()


def nome(n):
    """Nome de urna em caixa de título (mesma regra de relatorio/montar.py)."""
    out = []
    for i, w in enumerate(n.split()):
        if w in SIGLAS or (not w.endswith(".") and len(w) <= 3 and not any(c in "AEIOUÁÉÍÓÚÂÊÔÃÕ" for c in w)): out.append(w)
        elif i and w.lower() in PARTICULAS: out.append(w.lower())
        else: out.append(cap(w))
    r = " ".join(out)
    return NOME_EXIBICAO.get(r, r)


def nome_mun(n):
    out = []
    for i, w in enumerate(n.split()):
        lw = w.lower()
        if i and lw in PARTICULAS: out.append(lw)
        elif lw.startswith("d'") : out.append("d'" + cap(lw[2:]))
        else: out.append(cap(lw) if w not in ("I", "II", "III") else w)
    return " ".join(out)


def js(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def ld(p):
    with open(p) as f: return json.load(f)


def cands(d):
    """[(chave, nmu, sg, vap, dvt)] de um arquivo de cargo majoritário/proporcional."""
    return [(x["sqcand"], x["nmu"], p["sg"], int(x["vap"]), x.get("dvt", ""))
            for a in d["carg"][0]["agr"] for p in a["par"] for x in p.get("cand", [])]


def totais(d):
    e, v = d["e"], d["v"]
    return [int(e["te"]), int(e["c"]), int(v["vv"]), int(v["vb"]), int(v["tvn"])]


def linha_maj(d, ordem):
    votos = {k: vap for k, _, _, vap, _ in cands(d)}
    return totais(d) + [[votos.get(k, 0) for k in ordem], int(d["v"].get("vansj") or 0)]


def lista_meta(d):
    """Candidatos de um arquivo, por votos desc: (chaves ordenadas, [{n,nome,sg}])."""
    cs = sorted(cands(d), key=lambda c: (-c[3], c[1]))
    num = {x["sqcand"]: x["n"] for a in d["carg"][0]["agr"] for p in a["par"] for x in p.get("cand", [])}
    # sj: "Anulado sub judice" (votos fora de v.vv; somados em v.vansj)
    return [c[0] for c in cs], [dict(n=num[c[0]], nome=nome(c[1]), sg=c[2], **({"sj": True} if "sub judice" in c[4] else {})) for c in cs]


def linha_prop(d):
    cs = [c for c in cands(d) if c[4] == "Válido"]
    part = {}
    for _, _, sg, vap, _ in cs: part[sg] = part.get(sg, 0) + vap
    top = sorted(cs, key=lambda c: (-c[3], c[1]))[:3]
    sg, vp = max(part.items(), key=lambda kv: (kv[1], kv[0])) if part else ("", 0)
    return [int(d["v"]["vv"]), sg, vp, [[nome(c[1]), c[2], c[3]] for c in top]]


def main():
    if not (BR / "mun-config.json").exists(): sys.exit("rode municipios/baixar.py antes")
    cfg = ld(BR / "mun-config.json")
    rel = ld(R / "relatorio" / "relatorio.json")
    br = ld(UFD / "br-c0001.json")

    # ---- malha: como vem do IBGE
    GEO.mkdir(exist_ok=True)
    shutil.copyfile(BR / "malha-ibge.json", GEO / "municipios.topo.json")

    # ---- candidatos (ordem fixa por cargo)
    ordem_pres, cand_pres = lista_meta(br)
    meta = dict(dg=br["dg"], ht=br["ht"], mun={}, exterior=[], cand=dict(presidente=cand_pres, governador={}, senador={}))
    ordem = dict(governador={}, senador={})
    for uf in UFS:
        for cargo, c in (("governador", 3), ("senador", 5)):
            o, m = lista_meta(ld(UFD / f"{uf}-c{c:04d}.json"))
            ordem[cargo][uf] = o; meta["cand"][cargo][uf.upper()] = m

    # ---- presidente
    pres = dict(br=linha_maj(br, ordem_pres), uf={}, mu={}, ex={})
    for uf in UFS + ["zz"]:
        pres["uf"][uf.upper()] = linha_maj(ld(UFD / f"{uf}-c0001.json"), ordem_pres)
    gov, sen = dict(uf={}, mu={}), dict(uf={}, mu={})
    dfed, dest = dict(mu={}, uf={}), dict(mu={}, uf={})
    for uf in UFS:
        U = uf.upper()
        gov["uf"][U] = linha_maj(ld(UFD / f"{uf}-c0003.json"), ordem["governador"][uf])
        sen["uf"][U] = linha_maj(ld(UFD / f"{uf}-c0005.json"), ordem["senador"][uf])
        dfed["uf"][U] = linha_prop(ld(UFD / f"{uf}-c0006.json"))
        dest["uf"][U] = linha_prop(ld(UFD / f"{uf}-c{8 if uf == 'df' else 7:04d}.json"))

    faltam = []
    for ab in cfg["abr"]:
        uf = ab["cd"]; U = uf.upper()
        for m in ab["mu"]:
            cd = m["cd"]
            def abre(c):
                p = BR / f"{uf}{cd}-c{c:04d}.json"
                if not p.exists(): faltam.append(p.name); return None
                return ld(p)
            d = abre(1)
            if uf == "zz":
                meta["exterior"].append([m["nm"], cd])
                if d: pres["ex"][cd] = linha_maj(d, ordem_pres)
                continue
            key = m["cdi"]
            meta["mun"][key] = [nome_mun(m["nm"]), U]
            if d: pres["mu"][key] = linha_maj(d, ordem_pres)
            d = abre(3)
            if d: gov["mu"][key] = linha_maj(d, ordem["governador"][uf])
            d = abre(5)
            if d: sen["mu"][key] = linha_maj(d, ordem["senador"][uf])
            d = abre(6)
            if d: dfed["mu"][key] = linha_prop(d)
            d = abre(8 if uf == "df" else 7)
            if d: dest["mu"][key] = linha_prop(d)

    # ---- série da noite: histórico (sem uf) + snapshots/marcos (com uf) + leitura final
    pts = {}
    DNOITE = "04/10"
    for p in ld(R / "historico.json"):
        pts[p["ht"]] = dict(ht=p["ht"][:5], d=DNOITE, pst=p["pst"], f=p["f"], l=p["l"], uf=None)
    for g in sorted((R / "snapshots").glob("*/dados.json")) + sorted((R / "marcos").glob("*/dados.json")):
        d = ld(g)
        uf = {s["uf"]: [s["pst"], s["f"], s["l"]] for s in d["states"] if s["uf"] != "ZZ"}
        pts[d["ht"]] = dict(ht=d["ht"][:5], d=d["gerado"][:5], pst=d["pst"], f=d["f"], l=d["l"], uf=uf)
    cf_ = next(c for c in rel["nac"]["cand"] if c["nome"].startswith("Flavio"))
    cl_ = next(c for c in rel["nac"]["cand"] if c["nome"] == "Lula")
    fin_uf = {u["uf"]: [u["pst"], u["f"], u["l"]] for u in rel["pres_uf"] if u["uf"] != "ZZ"}
    pts[rel["nac"]["ht"]] = dict(ht=rel["nac"]["ht"][:5], d=rel["nac"]["dg"][:5], pst=rel["nac"]["pst"], f=cf_["p"], l=cl_["p"], uf=fin_uf)
    serie = sorted(pts.values(), key=lambda p: p["pst"])  # por avanço da apuração (a leitura final é do dia seguinte)

    # ---- feed
    pt = lambda x: f"{x:.1f}".replace(".", ",")
    fim = serie[-1]
    final = dict(h=fim["ht"], d=fim["d"], t="apuracao",
                 txt=f"100% das seções · Flávio {pt(fim['f'])}% × Lula {pt(fim['l'])}%")
    bloco = []  # sem hora real por UF: h nulo, dia da leitura final
    for g in rel["gov"]:
        n = NOME_UF[g["uf"]]
        if g["status"] == "eleito":
            bloco.append(dict(h=None, d=fim["d"], t="eleito", uf=g["uf"], txt=f"{n}: {g['a']['nome']} ({g['a']['sg']}) é eleito governador"))
        elif g["status"] == "2turno":
            bloco.append(dict(h=None, d=fim["d"], t="2turno", uf=g["uf"], txt=f"{n}: {g['a']['nome']} ({g['a']['sg']}) × {g['b']['nome']} ({g['b']['sg']}) vão ao 2º turno"))
    for sn in rel["sen"]:
        if sn.get("oficial"):
            bloco.append(dict(h=None, d=fim["d"], t="eleito", uf=sn["uf"], txt=f"{NOME_UF[sn['uf']]}: " + " e ".join(f"{e['nome']} ({e['sg']})" for e in sn["eleitos"]) + " eleitos senadores"))
    noite = [dict(h=p["ht"], d=p["d"], t="apuracao", txt=f"{pt(p['pst'])}% das seções · Flávio {pt(p['f'])}% × Lula {pt(p['l'])}%")
             for p in reversed(serie[:-1])]
    feed = [final] + bloco[:max(0, 60 - 1 - len(noite))] + noite  # nunca corta leituras da apuração

    if faltam:
        sys.exit(f"{len(faltam)} arquivos ausentes em brutos/ (rode baixar.py): {faltam[:10]}")
    meta["mun"] = dict(sorted(meta["mun"].items()))
    for nm, o in (("meta", meta), ("presidente", pres), ("governador", gov), ("senador", sen),
                  ("depfed", dfed), ("depest", dest), ("serie", serie), ("feed", feed)):
        js(T1 / f"{nm}.json", o)
    print("ok | municípios", len(meta["mun"]), "| exterior", len(meta["exterior"]), "| arquivos ausentes", len(faltam), faltam[:10])
    for p in sorted(GEO.rglob("*.json")): print(f"{p.relative_to(GEO)}: {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
