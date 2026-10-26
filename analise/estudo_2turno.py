"""Estudo do 2º turno (presidente, 25/10/2026): de onde vieram os votos da virada de Lula.

Entradas: municipios/geo/t1/presidente.json (1º turno, final) e analise/estudo2t/agora-2turno.json (cópia do
/vivo/agora.json do 2º turno; regravar com --baixar quando o TSE fechar). Saída: analise/estudo2t/estudo.json,
lido pelo build_site.py para montar /estudo-2-turno/.

Fatos (contagens do TSE) e estimativas (inferência ecológica, analise/inferencia.py) ficam separados no JSON.
Uso: python3 analise/estudo_2turno.py [--baixar] [--boot N]"""
import json, sys, urllib.request
from collections import defaultdict
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "analise"))
import inferencia as INF

PASTA = R / "analise" / "estudo2t"
ARQ_2T = PASTA / "agora-2turno.json"
SAIDA = PASTA / "estudo.json"
VIVO = "https://eleicoes2026.vitorpereira.ia.br/vivo/agora.json"

# Abstenção (% do eleitorado) e brancos/nulos (% do comparecimento), presidente, Brasil.
# 2002–2018: tabelas de resultados da Wikipédia em português, que citam o TSE (conferidas pela aritmética: base do
# percentual = eleitorado ou comparecimento). 2022: dados abertos do TSE (municipios/geo/t2022). 2026: este estudo.
W = "Wikipédia (resultados, cita o TSE)"
SERIE_FONTES = [  # (ano, turno, eleitorado, comparecimento, brancos, nulos, fonte)
    (2002, 1, 115253816, 94805583, 2873753, 6976685, W), (2002, 2, 115253816, 91664259, 1727760, 3772138, W),
    (2006, 1, 125913134, 104820459, 2866205, 5931752, W), (2006, 2, 125912935, 101998221, 1351448, 4808553, W),
    (2010, 1, 135804433, 111193747, 3479340, 6124254, W), (2010, 2, 135804433, 106606214, 2452597, 4689428, W),
    (2014, 1, 142822046, 115122611, 4420488, 6678580, W), (2014, 2, 142822046, 112683879, 1921819, 5219787, W),
    (2018, 1, 147306295, 117364654, 3106937, 7206222, W), (2018, 2, 147306294, 115933451, 2486593, 8608105, W),
]
LINHAS = ["Flávio", "Lula", "Outros candidatos", "Branco ou nulo", "Não votou"]
COLUNAS = ["Flávio", "Lula", "Branco ou nulo", "Não votou"]


def partes1(l, iF, iL):
    te, comp, vv, vb, vn, votos = l[0], l[1], l[2], l[3], l[4], l[5]
    F, L = votos[iF], votos[iL]
    return dict(te=te, comp=comp, F=F, L=L, O=vv - F - L, BN=vb + vn, A=te - comp)


def partes2(l, iF, iL):
    te, comp, vb, vn, votos = l[0], l[1], l[3], l[4], l[5]
    return dict(te=te, comp=comp, F=votos[iF], L=votos[iL], BN=vb + vn, A=te - comp)


def unidade(p1, p2):
    """(n, linhas do 1º turno, colunas do 2º) com o 2º escalado para o eleitorado do 1º (variação < 0,1%)."""
    a = [p1["F"], p1["L"], p1["O"], p1["BN"], p1["A"]]
    n = sum(a)
    b0 = [p2["F"], p2["L"], p2["BN"], p2["A"]]
    s = n / (sum(b0) or 1)
    return (n, a, [v * s for v in b0])


def faixas_bn(pares, n=10):
    """Municípios em n faixas de % de brancos e nulos no 1º turno (cada faixa com ~1/n do eleitorado). Por faixa:
    quanto Lula e Flávio cresceram por 100 eleitores e quanto o comparecimento mudou. É o padrão observado (contagens
    somadas), sem inferência; mostra onde cada um cresceu, não quem votou em quem."""
    ordem = sorted(pares, key=lambda p: p[0]["BN"] / p[0]["comp"])
    total = sum(p1["te"] for p1, _ in ordem)
    out, acc, grupo = [], 0, []
    for p1, p2 in ordem:
        grupo.append((p1, p2)); acc += p1["te"]
        if acc >= total * (len(out) + 1) / n or (p1, p2) is ordem[-1]:
            s = lambda k, i: sum(g[i][k] for g in grupo)
            te = s("te", 0)
            out.append(dict(municipios=len(grupo), eleitores=te,
                            bn_de=round(100 * grupo[0][0]["BN"] / grupo[0][0]["comp"], 1),
                            bn_ate=round(100 * grupo[-1][0]["BN"] / grupo[-1][0]["comp"], 1),
                            bn=round(100 * s("BN", 0) / s("comp", 0), 2),
                            lula=round(100 * (s("L", 1) - s("L", 0)) / te, 2),
                            flavio=round(100 * (s("F", 1) - s("F", 0)) / te, 2),
                            comparecimento=round(100 * (s("comp", 1) - s("comp", 0)) / te, 2),
                            bn_queda=round(100 * (s("BN", 0) - s("BN", 1)) / te, 2)))
            grupo = []
    return out


def serie(t2022, b1, b2, pst2):
    linhas = list(SERIE_FONTES)
    for t, b in (("1t", t2022[0]), ("2t", t2022[1])):
        linhas.append((2022, int(t[0]), b[0], b[1], b[3], b[4], "TSE, dados abertos"))
    linhas.append((2026, 1, b1[0], b1[1], b1[3], b1[4], "TSE (1º turno, final)"))
    linhas.append((2026, 2, b2[0], b2[1], b2[3], b2[4], f"TSE ({pst2:.2f}% das seções)".replace(".", ",")))
    return [dict(ano=a, turno=t, eleitorado=te, comparecimento=c, brancos=vb, nulos=vn, fonte=f,
                 abstencao=round(100 * (te - c) / te, 2), bn=round(100 * (vb + vn) / c, 2),
                 brancos_pct=round(100 * vb / c, 2), nulos_pct=round(100 * vn / c, 2))
            for a, t, te, c, vb, vn, f in linhas]


def calcular(t1, meta, t2, t2022, n_boot=40):
    c1 = [c["n"] for c in meta["cand"]["presidente"]]
    c2 = [c["n"] for c in t2["cand"]]
    i1 = (c1.index("22"), c1.index("13"))
    i2 = (c2.index("22"), c2.index("13"))
    uf_mun = {k: v[1] for k, v in meta["mun"].items()}

    b1, b2 = partes1(t1["br"], *i1), partes2(t2["br"], *i2)
    v1 = b1["F"] + b1["L"] + b1["O"]
    v2 = b2["F"] + b2["L"]
    novos = (b2["F"] + b2["L"]) - (b1["F"] + b1["L"])
    fatos = dict(
        t1=b1, t2=b2, validos1=v1, validos2=v2,
        pct=dict(F1=100 * b1["F"] / v1, L1=100 * b1["L"] / v1, O1=100 * b1["O"] / v1,
                 F2=100 * b2["F"] / v2, L2=100 * b2["L"] / v2,
                 comp1=100 * b1["comp"] / b1["te"], comp2=100 * b2["comp"] / b2["te"]),
        saldo1=b1["L"] - b1["F"], saldo2=b2["L"] - b2["F"], virada=(b2["L"] - b2["F"]) - (b1["L"] - b1["F"]),
        ganho=dict(L=b2["L"] - b1["L"], F=b2["F"] - b1["F"]),
        # os votos que Lula e Flávio somaram a mais vêm, por contagem, de três lugares
        bolo=dict(total=novos, outros=b1["O"], bn=b1["BN"] - b2["BN"], comparecimento=b2["comp"] - b1["comp"]),
    )

    por_uf = defaultdict(lambda: [defaultdict(int), defaultdict(int)])
    mun, un_uf, pares = [], defaultdict(list), []
    for cd, l1 in t1["mu"].items():
        l2 = t2["mu"].get(cd)
        if not l2:
            continue
        p1, p2 = partes1(l1, *i1), partes2(l2, *i2)
        if p1["te"] <= 0 or p2["te"] <= 0:
            continue
        u = uf_mun.get(cd, "?")
        for k, v in p1.items(): por_uf[u][0][k] += v
        for k, v in p2.items(): por_uf[u][1][k] += v
        un = unidade(p1, p2)
        mun.append(un)
        pares.append((p1, p2))
        un_uf[u].append(un)
    ufs = []
    for u, (a, b) in por_uf.items():
        va, vb = a["F"] + a["L"] + a["O"], b["F"] + b["L"]
        ufs.append(dict(uf=u, saldo1=a["L"] - a["F"], saldo2=b["L"] - b["F"], virada=(b["L"] - b["F"]) - (a["L"] - a["F"]),
                        l1=round(100 * a["L"] / va, 2) if va else 0, l2=round(100 * b["L"] / vb, 2) if vb else 0,
                        comp1=round(100 * a["comp"] / a["te"], 2), comp2=round(100 * b["comp"] / b["te"], 2),
                        dcomp=b["comp"] - a["comp"], outros=a["O"]))
    ufs.sort(key=lambda x: -x["virada"])

    faixas = faixas_bn(pares)

    # inferência: B nacional como âncora, uma estimativa por UF (como na Análise do 1º turno); bootstrap por UF
    B0, _ = INF.estima(mun)
    ponto = [[0.0] * len(COLUNAS) for _ in LINHAS]
    boots = [[[0.0] * len(COLUNAS) for _ in LINHAS] for _ in range(n_boot)]
    for u, un in sorted(un_uf.items()):
        lam = INF.lam_para(len(un))
        _, T = INF.estima(un, B0, lam)
        for r in range(len(LINHAS)):
            for c in range(len(COLUNAS)): ponto[r][c] += T[r][c]
        for k, Tb in enumerate(INF.bootstrap(un, B0, lam, n_boot, f"estudo2t-{u}")):
            for r in range(len(LINHAS)):
                for c in range(len(COLUNAS)): boots[k][r][c] += Tb[r][c]
    transf = []
    for r, nome in enumerate(LINHAS):
        tot = sum(ponto[r]) or 1
        cel = []
        for c, col in enumerate(COLUNAS):
            vals = [b[r][c] for b in boots]
            lo, hi = INF.duncan_davis(mun, r, c)
            cel.append(dict(para=col, votos=round(ponto[r][c]), pct=round(100 * ponto[r][c] / tot, 1),
                            ic90=[round(INF.percentil(vals, 0.05)), round(INF.percentil(vals, 0.95))],
                            limites=[round(lo), round(hi)]))
        transf.append(dict(de=nome, total=round(tot), para=cel))

    return dict(
        gerado_com=dict(pst2=t2.get("pst"), hora2=t2.get("t"), total2=t2.get("total"), municipios=len(mun), n_boot=n_boot),
        fatos=fatos, ufs=ufs, faixas_bn=faixas, transferencia=transf,
        serie=serie(t2022, t1["br"], t2["br"], t2.get("pst") or 0),
    )


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    if "--baixar" in sys.argv:
        ARQ_2T.write_bytes(urllib.request.urlopen(VIVO).read())
    n_boot = int(sys.argv[sys.argv.index("--boot") + 1]) if "--boot" in sys.argv else 40
    geo = R / "municipios" / "geo"
    t1 = json.loads((geo / "t1" / "presidente.json").read_text())
    meta = json.loads((geo / "t1" / "meta.json").read_text())
    t2022 = [json.loads((geo / "t2022" / f"presidente-{t}.json").read_text())["br"] for t in ("1t", "2t")]
    t2 = json.loads(ARQ_2T.read_text())
    est = calcular(t1, meta, t2, t2022, n_boot)
    SAIDA.write_text(json.dumps(est, ensure_ascii=False, indent=1))
    f = est["fatos"]
    print(f"ok → {SAIDA} | {est['gerado_com']} | virada {f['virada']:,} | bolo {f['bolo']}")


if __name__ == "__main__":
    main()
