#!/usr/bin/env python3
"""Estatísticas do horário dos votos (2º turno, 25/10/2026) a partir de horarios/brutos/2t_UF.jsonl.gz (ler_logs.py)
e do resultado por seção do TSE (municipios/brutos_secao/votacao_secao_2026_BR.zip, baixar_secao.py).
Saída: horarios/dados/estatisticas.json (agregados; nada por eleitor). Exterior (ZZ) fica fora das curvas em hora
de Brasília (cada país tem o seu fuso).

Fuso: o relógio da urna está na hora local. A votação abre às 8h de Brasília em todo o país, então o fuso de cada
município sai da mediana do 1º voto das suas seções: deslocamento = 8h − mediana, arredondado para a hora cheia.

Uso: python3 horarios/estatisticas.py [--secao CAMINHO_DO_ZIP]"""
import argparse, glob, gzip, io, json, statistics, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path

H = Path(__file__).resolve().parent
R = H.parent
BRUTOS = H / "brutos"
SAIDA = H / "dados" / "estatisticas.json"
SECAO = R / "municipios" / "brutos_secao" / "votacao_secao_2026_BR.zip"
REGIOES = {"Norte": "AC AM AP PA RO RR TO", "Nordeste": "AL BA CE MA PB PE PI RN SE", "Centro-Oeste": "DF GO MS MT",
           "Sudeste": "ES MG RJ SP", "Sul": "PR RS SC"}
REG = {u: r for r, us in REGIOES.items() for u in us.split()}
ABRE, FECHA, MEIO_DIA = 8 * 3600, 17 * 3600, 12 * 3600


def fuso(primeiros):
    """Deslocamento (horas a somar à hora local para virar Brasília) pela mediana do 1º voto das seções."""
    return round((ABRE - statistics.median(primeiros)) / 3600)


def inclinacao(pts):
    """Inclinação ponderada de y em x; pts = [(x, y, peso)]."""
    W = sum(p[2] for p in pts)
    if not W:
        return 0.0
    mx = sum(x * w for x, _, w in pts) / W
    my = sum(y * w for _, y, w in pts) / W
    sxx = sum(w * (x - mx) ** 2 for x, _, w in pts)
    return sum(w * (x - mx) * (y - my) for x, y, w in pts) / sxx if sxx else 0.0


def dentro(grupos):
    """Inclinação dentro dos grupos (efeito fixo): tira a média ponderada de cada grupo antes de juntar."""
    pts = []
    for g in grupos.values():
        W = sum(p[2] for p in g)
        if not W:
            continue
        mx = sum(p[0] * p[2] for p in g) / W
        my = sum(p[1] * p[2] for p in g) / W
        pts += [(x - mx, y - my, w) for x, y, w in g]
    return inclinacao(pts)


def pct(a, b): return round(100 * a / b, 2) if b else 0.0


def quantis(c, qs=(0.25, 0.5, 0.75, 0.9)):
    """Quantis de um Counter {valor: n}."""
    tot, acc, out, it = sum(c.values()), 0, {}, iter(qs)
    q = next(it, None)
    for v in sorted(c):
        acc += c[v]
        while q is not None and acc >= q * tot:
            out[f"p{round(q * 100)}"] = v
            q = next(it, None)
    return out


def ler_resultado(caminho):
    """{(uf, mun, zona, secao): [lula, flavio, branco, nulo]} do presidente no 2º turno (chaves int)."""
    res = defaultdict(lambda: [0, 0, 0, 0])
    col = {"13": 0, "22": 1, "95": 2, "96": 3}
    with zipfile.ZipFile(caminho) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        f = io.TextIOWrapper(z.open(nome), encoding="latin1")
        f.readline()
        for ln in f:
            r = ln.rstrip("\n").split(";")
            if r[5] != "2" or r[19] not in col:
                continue
            res[(r[10].strip('"'), int(r[13]), int(r[15]), int(r[16]))][col[r[19]]] += int(r[21])
    return res


def ler_brutos(pasta=BRUTOS):
    for arq in sorted(glob.glob(str(pasta / "2t_*.jsonl.gz"))):
        uf = Path(arq).name[3:5]
        with gzip.open(arq, "rt", encoding="utf-8") as f:
            for ln in f:
                yield uf, json.loads(ln)


def calcular(secoes, resultado):
    secoes = [(uf, s) for uf, s in secoes if s["t"]]
    # fuso por município
    prim = defaultdict(list)
    for uf, s in secoes:
        prim[(uf, s["mun"])].append(min(s["t"]))
    desl = {k: fuso(v) for k, v in prim.items()}

    por10, por_uf_h, uf_tot = Counter(), defaultdict(Counter), Counter()
    cab, mesa, cab_h, hab, hab_uf = Counter(), Counter(), defaultdict(list), Counter(), defaultdict(Counter)
    fila_uf, ate12_uf, ultimo = Counter(), Counter(), Counter()
    cobertura, pts, n_cruzadas = defaultdict(lambda: [0, 0]), [], 0
    for uf, s in secoes:
        d = desl[(uf, s["mun"])] * 3600
        br = [t + d for t in s["t"]]
        n = len(br)
        hab_uf[uf].update(s["hab"])
        if uf != "ZZ":  # no exterior a habilitação segue outro fluxo (maioria sem registro do tipo)
            hab.update(s["hab"])
        for c in s["cab"]:
            if 0 <= c <= 1800: cab[c] += 1
        for m in s["mesa"]:
            if 0 <= m <= 1800: mesa[m] += 1
        if uf != "ZZ":
            uf_tot[uf] += n
            for t, c in zip(br, s["cab"]):
                por10[t // 600 * 600] += 1
                por_uf_h[uf][t // 3600] += 1
                if 0 <= c <= 1800 and len(cab_h[t // 3600]) < 200000: cab_h[t // 3600].append(c)
            fila_uf[uf] += sum(t >= FECHA for t in br)
            ate12_uf[uf] += sum(t < MEIO_DIA for t in br)
            ultimo[max(br) // 600 * 600] += 1
        r = resultado.get((uf, int(s["mun"]), int(s["zona"]), int(s["secao"])))
        cobertura[uf][0] += n
        if r:
            n_cruzadas += 1
            cobertura[uf][1] += sum(r)
            if uf != "ZZ" and r[0] + r[1] >= 30:
                cedo = pct(sum(t < MEIO_DIA for t in br), n)
                pts.append((uf, s["mun"], cedo, 100 * r[0] / (r[0] + r[1]), r[0] + r[1]))

    hhmm = lambda s: f"{s // 3600:02d}:{s % 3600 // 60:02d}"
    tot = sum(uf_tot.values())
    curva, acc = [], 0
    for t in sorted(por10):
        acc += por10[t]
        curva.append(dict(hora=hhmm(t), votos=por10[t], pct=pct(por10[t], tot), acumulado=pct(acc, tot)))

    # Simpson: % de votos da seção até 12h × % de Lula (válidos dos dois). Brasil junto × dentro de UF e de município
    xy = lambda ps: [(p[2], p[3], p[4]) for p in ps]
    g_uf, g_mun, g_reg = defaultdict(list), defaultdict(list), defaultdict(list)
    for p in pts:
        g_uf[p[0]].append(p[2:]); g_mun[(p[0], p[1])].append(p[2:]); g_reg[REG.get(p[0], "?")].append(p[2:])
    por_uf_incl = {u: round(inclinacao(g), 3) for u, g in sorted(g_uf.items())}
    # faixas de "quão cedo a seção votou" (quintis de eleitores), para ver o padrão sem regressão
    ordem = sorted(pts, key=lambda p: p[2])
    W = sum(p[4] for p in ordem)
    faixas, grupo, acc = [], [], 0
    for p in ordem:
        grupo.append(p); acc += p[4]
        if acc >= W * (len(faixas) + 1) / 5 or p is ordem[-1]:
            w = sum(q[4] for q in grupo)
            faixas.append(dict(secoes=len(grupo), cedo_de=round(grupo[0][2], 1), cedo_ate=round(grupo[-1][2], 1),
                               lula=round(sum(q[3] * q[4] for q in grupo) / w, 2)))
            grupo = []

    return dict(
        fonte="logs de urna do TSE (bu_imgbu_logjez_rdv_vscmr_2026_2t_UF.zip) + votacao_secao_2026_BR.zip",
        secoes=len(secoes), votos=sum(len(s["t"]) for _, s in secoes), secoes_cruzadas=n_cruzadas,
        cobertura={u: dict(log=a, oficial=b, pct=pct(a, b)) for u, (a, b) in sorted(cobertura.items())},
        fusos=dict(Counter(f"{v:+d}h" for v in desl.values())),
        fusos_fora_de_brasilia=sorted(f"{u}-{m}:{v:+d}" for (u, m), v in desl.items() if v and u != "ZZ"),
        curva_10min=curva,
        ate_meio_dia=pct(sum(ate12_uf.values()), tot), depois_das_17h=sum(fila_uf.values()),
        ufs=[dict(uf=u, votos=uf_tot[u], ate_meio_dia=pct(ate12_uf[u], uf_tot[u]), depois_das_17h=fila_uf[u],
                  pico=hhmm(max(por_uf_h[u], key=por_uf_h[u].get) * 3600),
                  biometria=pct(hab_uf[u]["b"], sum(hab_uf[u].values()))) for u in sorted(uf_tot)],
        ultimo_voto_por_secao=[dict(hora=hhmm(t), secoes=n) for t, n in sorted(ultimo.items()) if t >= 16 * 3600],
        cabine=dict(segundos=quantis(cab), por_hora={hhmm(h * 3600): statistics.median(v) for h, v in sorted(cab_h.items()) if len(v) > 1000}),
        mesa=dict(segundos=quantis(mesa)),
        habilitacao=dict(biometria=pct(hab["b"], sum(hab.values())), manual=pct(hab["m"], sum(hab.values())),
                         sem_registro=pct(hab["?"], sum(hab.values()))),
        simpson=dict(
            explica="inclinação = pontos de % de Lula a mais por +1 ponto de % dos votos da seção até 12h; peso = válidos",
            brasil=round(inclinacao(xy(pts)), 3), dentro_regiao=round(dentro(g_reg), 3),
            dentro_uf=round(dentro(g_uf), 3), dentro_municipio=round(dentro(g_mun), 3),
            ufs=por_uf_incl, ufs_sinal_contrario_ao_brasil=sorted(
                u for u, v in por_uf_incl.items() if v * inclinacao(xy(pts)) < 0),
            faixas=faixas),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secao", default=str(SECAO))
    a = ap.parse_args()
    est = calcular(list(ler_brutos()), ler_resultado(a.secao))
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ok → {SAIDA} | {est['secoes']} seções, {est['votos']} votos")


if __name__ == "__main__":
    main()
