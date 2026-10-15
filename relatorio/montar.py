#!/usr/bin/env python3
"""Monta o relatório final do 1º turno 2026 a partir dos JSON do TSE em dados/ (baixar.py).
Saída: relatorio_final.html (template_relatorio.html + dados injetados) e relatorio.json.
Uso: python3 baixar.py && python3 montar.py"""
import json, math, collections
from datetime import datetime
from pathlib import Path
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pagina

H = Path(__file__).parent
D = H / "dados"
UFS = "ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to".split()
REGIAO = dict(ac="Norte", am="Norte", ap="Norte", pa="Norte", ro="Norte", rr="Norte", to="Norte",
              al="Nordeste", ba="Nordeste", ce="Nordeste", ma="Nordeste", pb="Nordeste", pe="Nordeste",
              pi="Nordeste", rn="Nordeste", se="Nordeste", df="Centro-Oeste", go="Centro-Oeste",
              mt="Centro-Oeste", ms="Centro-Oeste", es="Sudeste", mg="Sudeste", rj="Sudeste", sp="Sudeste",
              pr="Sul", rs="Sul", sc="Sul")
num = lambda x: float(str(x).replace(",", "."))
F, L = "FLAVIO BOLSONARO", "LULA"


def load(uf, c):
    d = json.load(open(D / f"{uf}-c{c:04d}.json"))
    k = d["carg"][0]
    cands = [dict(nmu=x["nmu"], n=x["n"], sg=p["sg"], agr=a["nm"], agr_com=a.get("com") or p["sg"],
                  vap=int(x["vap"]), pvapn=num(x["pvapn"]), dvt=x["dvt"], e=x["e"], st=x["st"])
             for a in k["agr"] for p in a["par"] for x in p["cand"]]
    return d, k, cands


PARTICULAS = {"de", "da", "do", "dos", "das", "e"}
SIGLAS = {"ACM", "JHC", "PM", "PRF", "II", "III"}


def nome(n):
    """Title case que respeita partículas (de, da...) e siglas (JHC, ACM)."""
    out = []
    for i, w in enumerate(n.split()):
        if w in SIGLAS or (not w.endswith(".") and len(w) <= 3 and not any(c in "AEIOUÁÉÍÓÚÂÊÔÃÕ" for c in w)): out.append(w)
        elif i and w.lower() in PARTICULAS: out.append(w.lower())
        else: out.append(w.capitalize() if "-" not in w else "-".join(x.capitalize() for x in w.split("-")))
    return " ".join(out)


def rnd(x, n=2):
    return round(x, n)


# ---------------- Presidente
br, _, brc = load("br", 1)
nac = dict(ht=br["ht"], dg=br["dg"], pst=num(br["s"]["pst"]),
           eleitores=int(br["e"]["te"]), comparecimento=int(br["e"]["c"]), pc=num(br["e"]["pc"]),
           abstencao=int(br["e"]["a"]), pa=num(br["e"]["pa"]),
           validos=int(br["v"]["vv"]), brancos=int(br["v"]["vb"]), pb=num(br["v"]["pvb"]),
           nulos=int(br["v"]["tvn"]), pn=num(br["v"]["ptvn"]),
           cand=[dict(nome=nome(c["nmu"]), sg=c["sg"], votos=c["vap"], p=rnd(100 * c["vap"] / int(br["v"]["vv"])))
                 for c in sorted(brc, key=lambda x: -x["vap"])])
coal_lula = next(a["com"] for a in br["carg"][0]["agr"] if any(c["nmu"] == L for p in a["par"] for c in p["cand"]))
nac["coalizao_lula"] = [s.strip() for s in coal_lula.split("/")]

pres_uf, regioes = [], collections.defaultdict(lambda: dict(f=0, l=0, vv=0))
for uf in UFS + ["zz"]:
    d, _, c = load(uf, 1)
    vv = int(d["v"]["vv"]); fv = next(x["vap"] for x in c if x["nmu"] == F); lv = next(x["vap"] for x in c if x["nmu"] == L)
    pres_uf.append(dict(uf=uf.upper(), pst=num(d["s"]["pst"]), eleitores=int(d["e"]["te"]), pc=num(d["e"]["pc"]),
                        f=rnd(100 * fv / vv), l=rnd(100 * lv / vv), fv=fv, lv=lv, saldo=fv - lv))
    r = REGIAO.get(uf, "Exterior"); regioes[r]["f"] += fv; regioes[r]["l"] += lv; regioes[r]["vv"] += vv
reg = [dict(regiao=k, f=rnd(100 * v["f"] / v["vv"]), l=rnd(100 * v["l"] / v["vv"]), saldo=v["f"] - v["l"], vv=v["vv"])
       for k, v in regioes.items()]

# ---------------- Governador
# Totalizado pelo TSE (tf == "s"): situação oficial (campo st), % sobre os válidos + votos sub judice, como o TSE.
# Antes disso: cálculo pela regra dos 50%, com e sem os votos sub judice ("indefinido" quando as contas divergem).
gov = []
for uf in UFS:
    d, _, c = load(uf, 3)
    vv = int(d["v"]["vv"]); sj = int(d["v"]["vansj"])
    val = sorted([x for x in c if x["dvt"] == "Válido"], key=lambda x: -x["vap"])
    a, b = val[0], val[1]
    p_sem, p_com = 100 * a["vap"] / vv, 100 * a["vap"] / (vv + sj)
    oficial = d.get("tf") == "s"
    if oficial:
        st = "eleito" if any(x["st"] == "Eleito" for x in c) else "2turno"
        den = vv + sj
    else:
        st = "eleito" if p_sem > 50 and p_com > 50 else "2turno" if p_sem <= 50 and p_com <= 50 else "indefinido"
        den = vv
    sjc = sorted([x for x in c if x["dvt"] != "Válido"], key=lambda x: -x["vap"])
    gov.append(dict(uf=uf.upper(), pst=num(d["s"]["pst"]), status=st, oficial=oficial,
                    a=dict(nome=nome(a["nmu"]), sg=a["sg"], p=rnd(100 * a["vap"] / den), p_sem_sj=rnd(p_sem), p_tse=rnd(p_com), votos=a["vap"]),
                    b=dict(nome=nome(b["nmu"]), sg=b["sg"], p=rnd(100 * b["vap"] / den), votos=b["vap"]),
                    falta_50=den // 2 + 1 - a["vap"],
                    subjudice=dict(nome=nome(sjc[0]["nmu"]), sg=sjc[0]["sg"], votos=sjc[0]["vap"],
                                   p=rnd(100 * sjc[0]["vap"] / (vv + sj))) if sjc and sjc[0]["vap"] > 10000 else None))

# ---------------- Senado
sen, sen_part = [], collections.Counter()
for uf in UFS:
    d, k, c = load(uf, 5)
    vv = int(d["v"]["vv"]) + int(d["v"]["vansj"]); n = int(k["nv"])  # % como o TSE: válidos + anulados sub judice
    val = sorted([x for x in c if x["dvt"] == "Válido"], key=lambda x: -x["vap"])
    if d.get("tf") == "s":  # eleitos oficiais primeiro, na ordem de votos
        el = [x for x in val if x["e"] == "s"]
        val = el + [x for x in val if x["e"] != "s"]
    for x in val[:n]: sen_part[x["sg"]] += 1
    sen.append(dict(uf=uf.upper(), pst=num(d["s"]["pst"]), vagas=n,
                    eleitos=[dict(nome=nome(x["nmu"]), sg=x["sg"], p=rnd(100 * x["vap"] / vv), votos=x["vap"]) for x in val[:n]],
                    proximo=dict(nome=nome(val[n]["nmu"]), sg=val[n]["sg"], p=rnd(100 * val[n]["vap"] / vv), votos=val[n]["vap"]),
                    dif_corte=val[n - 1]["vap"] - val[n]["vap"], oficial=d.get("tf") == "s"))


# ---------------- Deputados: vagas por agremiação publicadas pelo TSE ("vag"); partido dentro da federação = mais votados
def proporcional(cargos):
    por_agr, por_part, top, ufs = collections.Counter(), collections.Counter(), [], []
    for uf, c in cargos:
        d, k, cands = load(uf, c)
        vv = int(d["v"]["vv"])
        oficial = d.get("tf") == "s"
        linha = dict(uf=uf.upper(), vagas=int(k["nv"]), pst=num(d["s"]["pst"]), agr={}, oficial=oficial)
        if oficial:  # eleitos marcados pelo TSE (QP e média)
            for x in cands:
                if x["e"] == "s": por_part[x["sg"]] += 1
        for a in k["agr"]:
            vag = int(a.get("vag") or 0)
            if not vag: continue
            com = a.get("com") or a["par"][0]["sg"]
            por_agr[com] += vag; linha["agr"][com] = vag
            if oficial: continue
            el = sorted([x for x in cands if x["agr"] == a["nm"] and x["dvt"] == "Válido"], key=lambda x: -x["vap"])[:vag]
            for x in el: por_part[x["sg"]] += 1
        ufs.append(linha)
        top += [dict(nome=nome(x["nmu"]), sg=x["sg"], uf=uf.upper(), votos=x["vap"], p=rnd(100 * x["vap"] / vv))
                for x in cands if x["dvt"] == "Válido"]
    top.sort(key=lambda x: -x["votos"])
    return dict(total=sum(por_agr.values()), por_agr=por_agr.most_common(), por_partido=por_part.most_common(),
                ufs_oficiais=[l["uf"] for l in ufs if l["oficial"]], ufs_pendentes=[l["uf"] for l in ufs if not l["oficial"]],
                top=top[:15], ufs=ufs)


depfed = proporcional([(u, 6) for u in UFS])
depest = proporcional([(u, 7 if u != "df" else 8) for u in UFS])

# ---------------- Mapa: GeoJSON -> paths SVG (equiretangular corrigida pela latitude média, simplificada)
geo = json.load(open(D / "br-states.geojson"))
LON0, LAT0, LAT_C = -74.2, 5.5, math.cos(math.radians(-15))
S = 15.0  # px por grau
def proj(lo, la): return ((lo - LON0) * LAT_C * S, (LAT0 - la) * S)
def ring_path(ring):
    pts, last = [], None
    for lo, la in ring:
        x, y = proj(lo, la); p = (round(x, 1), round(y, 1))
        if last is None or abs(p[0] - last[0]) + abs(p[1] - last[1]) >= 1.4: pts.append(p); last = p
    if len(pts) < 4: return ""
    return "M" + "L".join(f"{x},{y}" for x, y in pts) + "Z"
mapa = {}
for ft in geo["features"]:
    g = ft["geometry"]; polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    path = "".join(ring_path(poly[0]) for poly in polys)
    xs = [proj(lo, la) for poly in polys for lo, la in poly[0]]
    cx = sum(p[0] for p in xs) / len(xs); cy = sum(p[1] for p in xs) / len(xs)
    mapa[ft["properties"]["sigla"]] = dict(d=path, cx=round(cx, 1), cy=round(cy, 1))

data = dict(gerado=datetime.now().strftime("%d/%m/%Y %H:%M"), nac=nac, pres_uf=pres_uf, regioes=reg, gov=gov, sen=sen,
            sen_part=sen_part.most_common(), depfed=depfed, depest=depest, mapa=mapa,
            hist=json.load(open(H.parent / "historico.json")))
# último ponto da trajetória = esta leitura, se for mais recente que o histórico
if nac["pst"] > data["hist"][-1]["pst"]:
    data["hist"].append(dict(ht=nac["ht"], pst=nac["pst"], f=nac["cand"][0]["p"] if nac["cand"][0]["nome"].startswith("Flavio") else nac["cand"][1]["p"],
                             l=next(c["p"] for c in nac["cand"] if c["nome"] == "Lula")))
(D / "mapa.json").write_text(json.dumps(mapa, ensure_ascii=False))  # contornos para a página ao vivo
ant = json.loads((H / "relatorio.json").read_text()) if (H / "relatorio.json").exists() else {}
sem = lambda d: json.dumps({k: v for k, v in d.items() if k not in ("mapa", "gerado")}, ensure_ascii=False, sort_keys=True)
if ant and sem(ant) == sem(data): data["gerado"] = ant["gerado"]  # dados iguais: mantém o carimbo da leitura
(H / "relatorio.json").write_text(json.dumps({k: v for k, v in data.items() if k != "mapa"}, ensure_ascii=False, indent=1))
tpl = (H / "template_relatorio.html").read_text() if (H / "template_relatorio.html").exists() else None
if tpl:  # siglas de 2022 (TSE) só no HTML, fora do relatorio.json
    (H / "relatorio_final.html").write_text(pagina.html_relatorio(tpl, data, pagina.siglas_2022()))
print("ok", nac["pst"], nac["ht"], "| gov:", collections.Counter(g["status"] for g in gov),
      "| dep fed", depfed["total"], "| dep est", depest["total"], "| mapa", len(mapa), "UFs",
      f"{len(json.dumps(mapa)) // 1024} KB")
