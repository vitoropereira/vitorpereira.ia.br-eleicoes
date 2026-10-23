"""Posições do modo "Pessoas" do HUD (#152): um círculo por município, com área ∝ eleitorado (aptos do 1º turno).

Cartograma de Dorling: cada círculo parte do centroide do município e os que se sobrepõem são afastados até não
sobrar nenhuma sobreposição. Os aptos são os mesmos nos dois turnos, então uma posição só serve aos dois; o que muda
é a cor (calculada no front). Saída: municipios/geo/pessoas.json, na projeção do HUD (hud/topo.js: x = lon·cos(−14°),
y = −lat). Só biblioteca padrão.

    python3 municipios/pessoas.py        # gera/atualiza municipios/geo/pessoas.json
"""
import hashlib
import json
import math
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parent.parent
GEO = R / "municipios" / "geo"
TOPO = GEO / "municipios.topo.json"
PRESIDENTE = GEO / "t1" / "presidente.json"
SAIDA = GEO / "pessoas.json"

VERSAO = 1
FRACAO = 0.35  # os círculos somam 35% da área do mapa
FOLGA = 0.004  # vão entre círculos, em unidades do mapa (graus)
ITERS = 200
SOBRE = 1.8  # sobre-relaxamento da separação
K = math.cos(math.radians(-14))


def _aneis(topo):
    """{cod: [anel externo, ...]} em (x, y) já na projeção do HUD; só os anéis externos (o 1º de cada polígono)"""
    t = topo.get("transform")
    arcos = []
    for a in topo["arcs"]:
        x = y = 0
        pts = []
        for p in a:
            if t:
                x, y = x + p[0], y + p[1]
                lon, lat = x * t["scale"][0] + t["translate"][0], y * t["scale"][1] + t["translate"][1]
            else:
                lon, lat = p
            pts.append((lon * K, -lat))
        arcos.append(pts)

    def anel(idx):
        pts = []
        for i in idx:
            a = arcos[i] if i >= 0 else arcos[~i][::-1]  # índice negativo = ~i invertido
            pts += a[1:] if pts else a
        return pts

    out = {}
    for g in topo["objects"]["BRMU"]["geometries"]:
        polis = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"] if g["type"] == "MultiPolygon" else []
        out[str(g["properties"]["codarea"])] = [anel(p[0]) for p in polis if p]
    return out


def centroides(topo):
    """{cod: (x, y, área)}: centroide ponderado pela área dos anéis externos, na projeção do HUD"""
    out = {}
    for cod, aneis in _aneis(topo).items():
        A = sx = sy = 0.0
        for r in aneis:
            a = cx = cy = 0.0
            for (xj, yj), (xi, yi) in zip(r[-1:] + r[:-1], r):
                f = xj * yi - xi * yj
                a += f; cx += (xj + xi) * f; cy += (yj + yi) * f
            if not a:
                continue
            cx, cy, a = cx / (3 * a), cy / (3 * a), abs(a) / 2  # = (cx/6A, cy/6A) com A = a/2
            A += a; sx += cx * a; sy += cy * a
        if A:
            out[cod] = (sx / A, sy / A, A)
    return out


def escala(te, area_total, fracao=FRACAO):
    """k tal que raio = k·√te e Σ π·raio² = fracao·area_total"""
    return math.sqrt(fracao * area_total / (math.pi * sum(te)))


def sobreposicao_maxima(pos, raios):
    """maior (ri + rj − distância) entre dois círculos, 0 se não há sobreposição (varredura em x)"""
    ordem = sorted(range(len(pos)), key=lambda i: pos[i][0] - raios[i])
    pior, ativos = 0.0, []
    for i in ordem:
        xi, yi = pos[i]
        ativos = [j for j in ativos if pos[j][0] + raios[j] > xi - raios[i]]
        for j in ativos:
            o = raios[i] + raios[j] - math.hypot(xi - pos[j][0], yi - pos[j][1])
            if o > pior:
                pior = o
        ativos.append(i)
    return pior


def _pares(pos, raios, folga, celula, pad):
    """pares (i<j) de círculos que dividem alguma célula da grade; cada círculo entra em todas as que cobre"""
    grade = {}
    for i, ((x, y), r) in enumerate(zip(pos, raios)):
        al = r + folga + pad
        for gx in range(math.floor((x - al) / celula), math.floor((x + al) / celula) + 1):
            for gy in range(math.floor((y - al) / celula), math.floor((y + al) / celula) + 1):
                grade.setdefault((gx, gy), []).append(i)
    pares = set()
    for L in grade.values():
        for a in range(len(L)):
            for b in range(a + 1, len(L)):
                pares.add((L[a], L[b]))
    return [(i, j) for i, j in pares if math.dist(pos[i], pos[j]) < raios[i] + raios[j] + folga + 2 * pad]


def dorling(casa, raios, folga=FOLGA, iters=ITERS, sobre=SOBRE):
    """posições sem sobreposição, perto de `casa`. Cada sobreposição é desfeita com mais peso no menor círculo
    (wi = rj²/(ri²+rj²)); a atração para casa só vale nos primeiros 60% das iterações, o resto só separa."""
    n = len(casa)
    pos = [list(p) for p in casa]
    if n < 2:
        return [tuple(p) for p in pos]
    media = sum(raios) / n
    celula, pad = 4 * media, media
    fim_atracao = int(iters * 0.6)
    tol = 1e-3 * folga
    pares, it, ultimo = [], 0, -10**9
    limite = iters * 6  # a fase final continua até limpar tudo, com teto
    while it < limite:
        if it - ultimo >= 5:
            pares, ultimo = _pares(pos, raios, folga, celula, pad), it
        pior = 0.0
        for i, j in pares:
            pi, pj = pos[i], pos[j]
            dx, dy = pj[0] - pi[0], pj[1] - pi[1]
            d = math.hypot(dx, dy)
            o = raios[i] + raios[j] + folga - d
            if o <= 0:
                continue
            if o > pior:
                pior = o
            o *= sobre
            if d < 1e-12:  # mesmo ponto: separa numa direção determinística
                ang = (i * 2.399963 + j * 0.7548777) % (2 * math.pi)
                dx, dy, d = math.cos(ang), math.sin(ang), 1.0
            ri2, rj2 = raios[i] ** 2, raios[j] ** 2
            wi, wj = rj2 / (ri2 + rj2), ri2 / (ri2 + rj2)
            ux, uy = dx / d, dy / d
            pi[0] -= ux * o * wi; pi[1] -= uy * o * wi
            pj[0] += ux * o * wj; pj[1] += uy * o * wj
        if it < fim_atracao:
            a = 0.05 * (1 - it / fim_atracao)
            for p, c in zip(pos, casa):
                p[0] += a * (c[0] - p[0]); p[1] += a * (c[1] - p[1])
        elif pior < tol:
            # a lista de pares pode estar velha: confirma com uma lista nova antes de parar
            pares, ultimo = _pares(pos, raios, folga, celula, pad), it
            if all(raios[i] + raios[j] + folga - math.dist(pos[i], pos[j]) < tol for i, j in pares):
                break
        it += 1
    return [tuple(p) for p in pos]


def assinatura(topo, pres):
    """sha1 de versão, parâmetros e das entradas (malha e aptos): muda quando o arquivo precisa ser refeito"""
    h = hashlib.sha1(f"v{VERSAO}|{FRACAO}|{FOLGA}".encode())
    h.update(json.dumps(topo, sort_keys=True, separators=(",", ":")).encode())
    h.update(json.dumps({c: l[0] for c, l in sorted(pres["mu"].items())}, separators=(",", ":")).encode())
    return h.hexdigest()


def calcular(topo, pres):
    """{"k", "mu": {cod: [x, y, te]}}: só municípios com polígono e eleitorado > 0"""
    cen = centroides(topo)
    cods = sorted(c for c in pres["mu"] if c in cen and pres["mu"][c][0] > 0)
    te = [pres["mu"][c][0] for c in cods]
    k = escala(te, sum(cen[c][2] for c in cen))
    raios = [k * math.sqrt(t) for t in te]
    pos = dorling([cen[c][:2] for c in cods], raios)
    return {"k": k, "mu": {c: [round(p[0], 4), round(p[1], 4), t] for c, p, t in zip(cods, pos, te)}}


def gerar(topo_p=TOPO, pres_p=PRESIDENTE, saida=SAIDA):
    topo, pres = json.loads(Path(topo_p).read_text()), json.loads(Path(pres_p).read_text())
    r = calcular(topo, pres)
    doc = {"v": VERSAO, "fonte": assinatura(topo, pres), "campo": "te", "k": r["k"], "mu": r["mu"]}
    Path(saida).write_text(json.dumps(doc, separators=(",", ":")))
    return Path(saida)


def garantir(topo_p=TOPO, pres_p=PRESIDENTE, saida=SAIDA):
    """regera só se o arquivo faltar ou a fonte mudar; sem as entradas (malha ou presidente.json), devolve None"""
    topo_p, pres_p, saida = Path(topo_p), Path(pres_p), Path(saida)
    if not (topo_p.is_file() and pres_p.is_file()):
        return None
    topo, pres = json.loads(topo_p.read_text()), json.loads(pres_p.read_text())
    if saida.is_file():
        try:
            if json.loads(saida.read_text()).get("fonte") == assinatura(topo, pres):
                return saida
        except ValueError:
            pass
    return gerar(topo_p, pres_p, saida)


if __name__ == "__main__":
    t0 = time.time()
    s = gerar()
    print(f"{s} · {s.stat().st_size / 1024:.0f} KB · {time.time() - t0:.1f} s")
    sys.exit(0)
