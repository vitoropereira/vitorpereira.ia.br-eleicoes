#!/usr/bin/env python3
"""Gera painel.html com apuração ao vivo do TSE (presidente, 1º turno 2026) + projeções.
Uso: python3 gerar.py   (rode de novo para atualizar)"""
import json, time, random, statistics, urllib.request, concurrent.futures as cf
from datetime import datetime
from pathlib import Path
import brand

ELE = "6257"
B = "https://resultados.tse.jus.br/oficial/ele2026/{e}/dados/{u}/{u}-c0001-e00{e}-u.json"
UFS = "ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to zz".split()
F, L = "FLAVIO BOLSONARO", "LULA"
num = lambda x: float(x.replace(",", "."))

# Véspera — fonte: Wikipedia "Opinion polling for the 2026 Brazilian presidential election" (não conferido 1 a 1)
# (instituto, data, lula, flavio, branco/indeciso)  → convertido para votos válidos
POLLS = [
    ("Datafolha", "3/out", 42, 40, 7), ("Quaest", "2–3/out", 40, 38, 13),
    ("Futura", "2–3/out", 40.5, 42.5, 2.6), ("Palver", "30/set–3/out", 43, 47, 0),
    ("PoderData", "30/set–2/out", 42, 41, 6), ("MDA", "29/set–2/out", 43.1, 38, 9.7),
    ("AtlasIntel", "27/set–2/out", 46.7, 43.8, 0.6), ("Vox Brasil", "29/set–1/out", 40.4, 41.2, 10.2),
]


def get(u):
    d = json.load(urllib.request.urlopen(B.format(e=ELE, u=u) + f"?t={int(time.time())}", timeout=25))
    c = {k["nmu"]: int(k["vap"]) for a in d["carg"][0]["agr"] for p in a["par"] for k in p["cand"]}
    sg = {k["nmu"]: p["sg"] for a in d["carg"][0]["agr"] for p in a["par"] for k in p["cand"]}
    return dict(uf=u.upper(), ht=d["ht"], pst=num(d["s"]["pst"]), ts=int(d["s"]["ts"]), st=int(d["s"]["st"]), te=int(d["e"]["te"]),
                vv=int(d["v"]["vv"]), cand=c, sg=sg)


def main():
    ufs = list(cf.ThreadPoolExecutor(10).map(get, UFS))
    # nacional = soma das UFs. O arquivo "br" do TSE congelou às 19:14 em 04/10 enquanto as UFs seguiam atualizando.
    # hora = UF mais recente que não esteja no futuro (o arquivo de PE vem ~50 min adiantado)
    agora = datetime.now().strftime("%H:%M:%S")
    nat = dict(ht=max((s["ht"] for s in ufs if s["uf"] != "ZZ" and s["ht"] <= agora), default=agora),
               pst=round(100 * sum(s["st"] for s in ufs) / sum(s["ts"] for s in ufs), 2),
               vv=sum(s["vv"] for s in ufs), cand={})
    for s in ufs:
        for k, v in s["cand"].items():
            nat["cand"][k] = nat["cand"].get(k, 0) + v

    # projeção: restante de cada UF segue o % atual daquela UF (+ shift p/ Lula), com a taxa de válidos/eleitor da UF
    base = []
    for s in ufs:
        if not s["vv"] or not s["pst"]:
            continue
        tot = s["vv"] / (s["pst"] / 100)              # válidos projetados da UF
        rem = tot - s["vv"]
        base.append(dict(s, tot=tot, rem=rem, f=s["cand"].get(F, 0) / s["vv"], l=s["cand"].get(L, 0) / s["vv"]))

    def proj(shift=0.0, noise=None):
        Fv = Lv = V = 0
        for i, s in enumerate(base):
            sh = shift + (noise[i] if noise else 0)
            Fv += s["cand"].get(F, 0) + s["rem"] * max(s["f"] - sh, 0)
            Lv += s["cand"].get(L, 0) + s["rem"] * min(s["l"] + sh, 1)
            V += s["tot"]
        return 100 * Fv / V, 100 * Lv / V

    shifts = [x / 2 for x in range(0, 21)]           # 0 a 10 pts
    scen = [dict(shift=sh, f=round(proj(sh / 100)[0], 2), l=round(proj(sh / 100)[1], 2)) for sh in shifts]

    # Monte Carlo — PREMISSA: viés nacional do voto restante ~ N(+1pt Lula, 3pt) + ruído por UF N(0, 2pt)
    random.seed(42)
    N = 20000; win1 = lead = 0; fs = []; ff = []; ll = []
    for _ in range(N):
        g = random.gauss(0.01, 0.03)
        fv, lv = proj(g, [random.gauss(0, 0.02) for _ in base])
        fs.append(fv - lv); ff.append(fv); ll.append(lv); win1 += fv > 50; lead += fv > lv
    fs.sort(); ff.sort(); ll.sort()
    q = lambda xs, p: xs[int(p * (len(xs) - 1))]
    mc = dict(p_win1=round(100 * win1 / N, 1), p_lead=round(100 * lead / N, 1),
              p_lula=round(100 * (N - lead) / N, 1),
              p10=round(fs[N // 10], 1), p50=round(fs[N // 2], 1), p90=round(fs[9 * N // 10], 1))

    states = [dict(uf=s["uf"], pst=s["pst"], te=s["te"], f=round(100 * s["f"], 1), l=round(100 * s["l"], 1),
                   marg=round((s["cand"].get(F, 0) - s["cand"].get(L, 0)) / 1e3),
                   rem_net=round(s["rem"] * (s["f"] - s["l"]) / 1e3), rem=round(s["rem"] / 1e3), ht=s["ht"])
              for s in base]
    nv = nat["vv"] or 1
    fnow, lnow = 100 * nat["cand"][F] / nv, 100 * nat["cand"][L] / nv

    # histórico: um ponto por execução (ignora repetido)
    hp = Path(__file__).parent / "historico.json"
    hist = json.loads(hp.read_text()) if hp.exists() else []
    if not hist or hist[-1]["pst"] != nat["pst"]:
        hist.append(dict(ht=nat["ht"], pst=nat["pst"], f=round(fnow, 2), l=round(lnow, 2)))
        hp.write_text(json.dumps(hist, ensure_ascii=False, indent=1))

    # trajetória até 100%: o restante entra proporcionalmente; share acumulado = mistura ponderada por votos
    Vnow = sum(s["vv"] for s in base); Vtot = sum(s["tot"] for s in base); Vrem = Vtot - Vnow
    def path(sf, sl):  # sf/sl = % final projetado
        pts = []
        for i in range(21):
            t = i / 20
            w = Vnow + t * Vrem
            pts.append(dict(x=round(nat["pst"] + t * (100 - nat["pst"]), 2),
                            f=round((Vnow * fnow + t * (sf * Vtot - Vnow * fnow)) / w, 2),
                            l=round((Vnow * lnow + t * (sl * Vtot - Vnow * lnow)) / w, 2)))
        return pts
    traj = dict(base=path(scen[0]["f"], scen[0]["l"]),
                mc50=path(q(ff, .5), q(ll, .5)),
                lo=path(q(ff, .1), q(ll, .1)), hi=path(q(ff, .9), q(ll, .9)))
    sgs = {k: v for s in ufs for k, v in s["sg"].items()}
    others = sorted(((k, v) for k, v in nat["cand"].items() if k not in (F, L)), key=lambda x: -x[1])
    data = dict(
        gerado=datetime.now().strftime("%d/%m/%Y %H:%M"), ht=nat["ht"], pst=nat["pst"],
        f=round(100 * nat["cand"][F] / nv, 2), l=round(100 * nat["cand"][L] / nv, 2),
        fv=nat["cand"][F], lv=nat["cand"][L],
        outros=[dict(n=k.title(), p=round(100 * v / nv, 2)) for k, v in others[:4]],
        # siglas do TSE para o template.html (D.sg, D.sgn): partido junto do nome
        sg={"f": sgs.get(F, ""), "l": sgs.get(L, "")}, sgn={k.title(): sgs[k] for k, _ in others[:4] if k in sgs},
        scen=scen, mc=mc, states=states, hist=hist, traj=traj,
        polls=[dict(n=n, d=d, l=round(100 * l / (100 - b), 1), f=round(100 * f / (100 - b), 1))
               for n, d, l, f, b in POLLS],
    )
    tpl = (Path(__file__).parent / "template.html").read_text()
    out = Path(__file__).parent / "painel.html"
    html = brand.aplicar(tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False)))
    out.write_text(html)
    # snapshot imutável desta rodada: snapshots/AAAA-MM-DD_HHMM_<pct>pct/
    snap = Path(__file__).parent / "snapshots" / f"{datetime.now():%Y-%m-%d}_{nat['ht'][:5].replace(':', '')}_{nat['pst']:.1f}pct"
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "painel.html").write_text(html)
    (snap / "dados.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"ok → {out}  | apurado {nat['pst']}%  Flávio {data['f']}  Lula {data['l']}  | MC {mc}")


if __name__ == "__main__":
    main()
