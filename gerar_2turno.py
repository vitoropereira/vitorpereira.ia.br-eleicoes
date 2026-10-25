#!/usr/bin/env python3
"""Gera painel_2turno.html com apuração ao vivo do TSE (presidente, 2º turno 2026, 25/10) + projeções.
Mesmo método do gerar.py (1º turno), com duas diferenças: UF ainda sem seção apurada entra pela base do 1º turno
ajustada pelas pesquisas da véspera, e UF com pouca apuração mistura o % atual com essa base.
Uso: python3 gerar_2turno.py [--snapshot]   (sem a flag só atualiza painel_2turno.html e o histórico;
com ela grava a leitura em snapshots/2-turno/, que vira página em /apuracao/2-turno/. watch_2turno.sh roda nos marcos)"""
import sys, json, time, random, urllib.request, concurrent.futures as cf
from datetime import datetime
from pathlib import Path
import brand

ELE, ELE_1T = "6258", "6257"
B = "https://resultados.tse.jus.br/oficial/ele2026/{e}/dados/{u}/{u}-c0001-e00{e}-u.json"
UFS = "ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to zz".split()
F, L = "FLAVIO BOLSONARO", "LULA"
num = lambda x: float(x.replace(",", "."))
R = Path(__file__).parent

# Véspera — fonte: Poder360, "Saiba como estão Lula e Flávio nas últimas 18 pesquisas divulgadas" (25/10/2026),
# já em votos válidos (Palver recalculada pelo Poder360). Só as 10 com percentual no texto. (instituto, campo, lula, flavio)
POLLS = [
    ("PoderData/Aya", "23–24/out", 49, 51), ("BTG/Nexus", "23–24/out", 49.5, 50.5),
    ("AtlasIntel", "18–23/out", 49.2, 50.8), ("Datafolha", "23–24/out", 49, 51),
    ("CNT/MDA", "21–23/out", 49.3, 50.7), ("Palver", "16–20/out", 49, 51),
    ("Gerp", "22–24/out", 48, 52), ("Futura", "23–24/out", 49.9, 50.1),
    ("Quaest", "23–24/out", 49, 51), ("Vox Brasil", "20–22/out", 50.6, 49.4),
]
# UF com pouca apuração: peso do % atual = pst / MISTURA (até 1). As primeiras seções não são amostra aleatória.
MISTURA = 30.0


def get(u, ele=ELE):
    d = json.load(urllib.request.urlopen(B.format(e=ele, u=u) + f"?t={int(time.time())}", timeout=25))
    c = {k["nmu"]: int(k["vap"]) for a in d["carg"][0]["agr"] for p in a["par"] for k in p["cand"]}
    sg = {k["nmu"]: p["sg"] for a in d["carg"][0]["agr"] for p in a["par"] for k in p["cand"]}
    return dict(uf=u.upper(), ht=d["ht"], pst=num(d["s"]["pst"]), ts=int(d["s"]["ts"]), st=int(d["s"]["st"]), te=int(d["e"]["te"]),
                vv=int(d["v"]["vv"]), cand=c, sg=sg)


def projetar(ufs, u1, polls=POLLS, mistura=MISTURA):
    """ufs = leituras do 2º turno; u1 = leituras do 1º turno por UF. Devolve (base, desloc, f1n, pol_f)."""
    # base do 1º turno: fatia de Flávio entre os dois em cada UF, deslocada pela diferença nacional entre a média das
    # pesquisas do 2º turno e o resultado de 04/10 (só Flávio × Lula)
    dois = lambda s: s["cand"].get(F, 0) + s["cand"].get(L, 0)
    f1 = {u: s["cand"].get(F, 0) / max(dois(s), 1) for u, s in u1.items()}
    f1n = sum(s["cand"].get(F, 0) for s in u1.values()) / sum(dois(s) for s in u1.values())
    pol_f = sum(p[3] for p in polls) / len(polls) / 100
    desloc = pol_f - f1n
    base = []
    for s in ufs:
        u = s["uf"]
        prior = min(max(f1[u] + desloc, 0), 1)
        if s["vv"] and s["pst"]:
            tot = s["vv"] / (s["pst"] / 100)
            fa = s["cand"].get(F, 0) / s["vv"]
            w = min(s["pst"] / mistura, 1)
            fr, fv, lv = w * fa + (1 - w) * prior, fa, s["cand"].get(L, 0) / s["vv"]
        else:
            tot, fr, fv, lv = float(dois(u1[u])), prior, 0.0, 0.0
        base.append(dict(s, tot=tot, rem=tot - s["vv"], fr=fr, f=fv, l=lv, prior=prior))
    return base, desloc, f1n, pol_f


def proj(base, shift=0.0, noise=None):
    """% final de Flávio e Lula nos válidos; shift/noise = pontos (fração) a mais para Lula no voto restante"""
    Fv = Lv = V = 0
    for i, s in enumerate(base):
        sh = shift + (noise[i] if noise else 0)
        fr = min(max(s["fr"] - sh, 0), 1)
        Fv += s["cand"].get(F, 0) + s["rem"] * fr
        Lv += s["cand"].get(L, 0) + s["rem"] * (1 - fr)
        V += s["tot"]
    return 100 * Fv / V, 100 * Lv / V


def total_agora(ufs, br, agora):
    """O "agora" do país: soma das UFs ou, quando tem mais seções, o arquivo Brasil do TSE (o número do site do TSE;
    mesma regra do agregador). Devolve (nat, fonte). A projeção continua UF a UF."""
    st = sum(s["st"] for s in ufs); ts = sum(s["ts"] for s in ufs)
    if br and br["ts"] and st < br["st"] <= br["ts"]:
        return dict(ht=br["ht"] or agora, pst=round(100 * br["st"] / br["ts"], 2), vv=br["vv"],
                    cand={F: br["cand"].get(F, 0), L: br["cand"].get(L, 0)}), "tse"
    nat = dict(ht=max((s["ht"] for s in ufs if s["uf"] != "ZZ" and s["ht"] and s["ht"] <= agora), default=agora),
               pst=round(100 * st / ts, 2), vv=sum(s["vv"] for s in ufs), cand={F: 0, L: 0})
    for s in ufs:
        for k, v in s["cand"].items():
            nat["cand"][k] = nat["cand"].get(k, 0) + v
    return nat, "uf"


def main():
    with cf.ThreadPoolExecutor(10) as ex:
        ufs = list(ex.map(get, UFS))
        u1 = {s["uf"]: s for s in ex.map(lambda u: get(u, ELE_1T), UFS)}
    try:
        br = get("br")
    except Exception as e:  # sem o arquivo Brasil, o "agora" fica na soma das UFs
        print(f"aviso: arquivo Brasil indisponível ({e})")
        br = None
    nat, fonte = total_agora(ufs, br, datetime.now().strftime("%H:%M:%S"))

    base, desloc, f1n, pol_f = projetar(ufs, u1)
    shifts = [x / 2 for x in range(-10, 11)]          # -5 a +5 pts para Lula
    scen = [dict(shift=sh, f=round(proj(base, sh / 100)[0], 2), l=round(proj(base, sh / 100)[1], 2)) for sh in shifts]
    s0 = next(s for s in scen if s["shift"] == 0)

    # Monte Carlo — PREMISSA (igual ao 1º turno): viés nacional do voto restante ~ N(+1pt Lula, 3pt) + ruído por UF N(0, 2pt)
    random.seed(42)
    N = 20000; lead = 0; fs = []; ff = []; ll = []
    for _ in range(N):
        g = random.gauss(0.01, 0.03)
        fv, lv = proj(base, g, [random.gauss(0, 0.02) for _ in base])
        fs.append(fv - lv); ff.append(fv); ll.append(lv); lead += fv > lv
    fs.sort(); ff.sort(); ll.sort()
    q = lambda xs, p: xs[int(p * (len(xs) - 1))]
    mc = dict(p_flavio=round(100 * lead / N, 1), p_lula=round(100 * (N - lead) / N, 1),
              p10=round(fs[N // 10], 1), p50=round(fs[N // 2], 1), p90=round(fs[9 * N // 10], 1))

    states = [dict(uf=s["uf"], pst=s["pst"], te=s["te"], f=round(100 * s["f"], 1), l=round(100 * s["l"], 1),
                   marg=round((s["cand"].get(F, 0) - s["cand"].get(L, 0)) / 1e3),
                   rem_net=round(s["rem"] * (2 * s["fr"] - 1) / 1e3), rem=round(s["rem"] / 1e3), ht=s["ht"],
                   base=round(100 * s["prior"], 1))
              for s in base]
    nv = nat["vv"] or 1
    fnow, lnow = 100 * nat["cand"][F] / nv, 100 * nat["cand"][L] / nv

    hp = R / "historico_2turno.json"
    hist = json.loads(hp.read_text()) if hp.exists() else []
    if nat["vv"] and (not hist or hist[-1]["pst"] != nat["pst"]):
        hist.append(dict(ht=nat["ht"], pst=nat["pst"], f=round(fnow, 2), l=round(lnow, 2)))
        hp.write_text(json.dumps(hist, ensure_ascii=False, indent=1))

    Vnow = nat["vv"]; Vtot = sum(s["tot"] for s in base); Vrem = Vtot - Vnow
    def path(sf, sl):
        pts = []
        for i in range(21):
            t = i / 20
            w = max(Vnow + t * Vrem, 1)
            pts.append(dict(x=round(nat["pst"] + t * (100 - nat["pst"]), 2),
                            f=round((Vnow * fnow + t * (sf * Vtot - Vnow * fnow)) / w, 2),
                            l=round((Vnow * lnow + t * (sl * Vtot - Vnow * lnow)) / w, 2)))
        return pts
    traj = dict(base=path(s0["f"], s0["l"]), mc50=path(q(ff, .5), q(ll, .5)),
                lo=path(q(ff, .1), q(ll, .1)), hi=path(q(ff, .9), q(ll, .9)))
    sgs = {k: v for s in ufs for k, v in s["sg"].items()}
    data = dict(
        turno=2, total=fonte, gerado=datetime.now().strftime("%d/%m/%Y %H:%M"), ht=nat["ht"], pst=nat["pst"],
        f=round(fnow, 2), l=round(lnow, 2), fv=nat["cand"][F], lv=nat["cand"][L], outros=[],
        sg={"f": sgs.get(F, ""), "l": sgs.get(L, "")}, sgn={},
        scen=scen, base0=s0, mc=mc, states=states, hist=hist, traj=traj,
        premissa=dict(f1n=round(100 * f1n, 2), pol_f=round(100 * pol_f, 2), desloc=round(100 * desloc, 2), mistura=MISTURA),
        polls=[dict(n=n, d=d, l=l, f=f) for n, d, l, f in POLLS],
    )
    tpl = (R / "template_2turno.html").read_text()
    html = brand.aplicar(tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False)))
    (R / "painel_2turno.html").write_text(html)
    # resumo para a linha "Projeção…" da home (/vivo/projecao.json, enviado pelo watch_2turno.sh a cada ciclo)
    nomes = {F: "Flávio Bolsonaro", L: "Lula"}
    (R / "projecao_vivo.json").write_text(json.dumps(dict(
        t=datetime.now().strftime("%H:%M"), pst=nat["pst"], f=s0["f"], l=s0["l"], pf=mc["p_flavio"], pl=mc["p_lula"],
        nf=nomes[F], nl=nomes[L], sf=data["sg"]["f"], sl=data["sg"]["l"]), ensure_ascii=False, separators=(",", ":")))
    if "--snapshot" not in sys.argv:
        print(f"ok → painel_2turno.html  | apurado {nat['pst']}%  Flávio {data['f']}  Lula {data['l']}  | base {s0}  | MC {mc}")
        return
    snap = R / "snapshots" / "2-turno" / f"{datetime.now():%Y-%m-%d}_{nat['ht'][:5].replace(':', '')}_{nat['pst']:.1f}pct"
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "painel.html").write_text(html)
    (snap / "dados.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"ok → {snap}  | apurado {nat['pst']}%  Flávio {data['f']}  Lula {data['l']}  | base {s0}  | MC {mc}")


if __name__ == "__main__":
    main()
