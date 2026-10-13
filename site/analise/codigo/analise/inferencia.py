"""Inferência ecológica do voto dividido (só biblioteca padrão).

Problema: em cada município conhecemos as margens de uma tabela que não é publicada (o voto é secreto):
  linhas  = voto para presidente  (r = Lula, Flávio, Outros = demais candidatos + brancos + nulos)
  colunas = lado do voto no cargo C (c = L, F, C = centro/sem lado, BN = brancos/nulos)
Queremos B[r][c] = fração dos eleitores da linha r que votaram na coluna c.

Método (por UF):
 1. Goodman com restrições: minimiza  sum_i w_i ||y_i - x_i B||^2 + lam ||B - B0||^2  com cada linha de B no
    simplex (entradas em [0,1], soma 1). x_i, y_i = proporções do município i; w_i = comparecimento / total.
    B0 = mesmo ajuste com todos os municípios do Brasil (lam pequeno: só segura UFs com poucos municípios, ex. DF).
    Resolvido por gradiente projetado acelerado (FISTA) com projeção exata no simplex.
 2. Reconciliação: em cada município, a semente x_ir * B[r][c] é ajustada por IPF às margens observadas
    (linhas = votos para presidente, colunas = votos no cargo). Somar municípios dá contagens que batem com os
    totais oficiais e ficam, por construção, dentro dos limites de Duncan-Davis.
 3. Intervalo de 90%: bootstrap de municípios (reamostra com reposição, refaz 1 e 2), percentis 5 e 95.
"""
import math, random

EPS = 1e-6


def projeta_simplex(v):
    """Projeção euclidiana de v no simplex {x >= 0, sum x = 1} (Duchi et al., 2008)."""
    u = sorted(v, reverse=True)
    acum, theta = 0.0, 0.0
    for j, uj in enumerate(u, 1):
        acum += uj
        t = (acum - 1.0) / j
        if uj - t > 0: theta = t
    return [max(0.0, x - theta) for x in v]


def momentos(dados, idx=None):
    """dados: lista de (w, x[R], y[K]) com w normalizado. Devolve (XtWX RxR, XtWY RxK)."""
    R, K = len(dados[0][1]), len(dados[0][2])
    A = [[0.0] * R for _ in range(R)]
    Bm = [[0.0] * K for _ in range(R)]
    it = dados if idx is None else (dados[i] for i in idx)
    for w, x, y in it:
        for r in range(R):
            wx = w * x[r]
            if wx == 0.0: continue
            Ar = A[r]
            for s in range(R): Ar[s] += wx * x[s]
            Br = Bm[r]
            for c in range(K): Br[c] += wx * y[c]
    return A, Bm


def goodman(A, XY, B0=None, lam=0.0, iters=3000, tol=1e-12):
    """Minimiza tr(B'AB) - 2 tr(B'XY) + lam||B-B0||^2 com linhas de B no simplex (FISTA)."""
    R, K = len(XY), len(XY[0])
    if B0 is None: B0 = [[1.0 / K] * K for _ in range(R)]
    Lc = 2.0 * (sum(A[r][r] for r in range(R)) + lam) or 1.0  # traço >= maior autovalor (A é PSD)
    B = [row[:] for row in B0]
    Z = [row[:] for row in B]
    t = 1.0
    for _ in range(iters):
        G = [[2.0 * (sum(A[r][s] * Z[s][c] for s in range(R)) - XY[r][c] + lam * (Z[r][c] - B0[r][c]))
              for c in range(K)] for r in range(R)]
        Bn = [projeta_simplex([Z[r][c] - G[r][c] / Lc for c in range(K)]) for r in range(R)]
        tn = (1.0 + (1.0 + 4.0 * t * t) ** 0.5) / 2.0
        mov = max(abs(Bn[r][c] - B[r][c]) for r in range(R) for c in range(K))
        Z = [[Bn[r][c] + (t - 1.0) / tn * (Bn[r][c] - B[r][c]) for c in range(K)] for r in range(R)]
        B, t = Bn, tn
        if mov < tol: break
    return B


def ipf(semente, linhas, colunas, iters=200, tol=1e-7):
    """Ajuste proporcional iterativo de uma tabela RxK às margens (totais iguais)."""
    R, K = len(linhas), len(colunas)
    T = [[max(semente[r][c], EPS) if linhas[r] > 0 and colunas[c] > 0 else 0.0 for c in range(K)] for r in range(R)]
    for _ in range(iters):
        for r in range(R):
            s = sum(T[r])
            if s > 0:
                f = linhas[r] / s
                T[r] = [v * f for v in T[r]]
        err = 0.0
        for c in range(K):
            s = sum(T[r][c] for r in range(R))
            if s > 0:
                f = colunas[c] / s
                for r in range(R): T[r][c] *= f
        for r in range(R):
            err = max(err, abs(sum(T[r]) - linhas[r]))
        if err < tol * (1.0 + max(linhas)): break
    return T


def reconcilia(B, unidades):
    """unidades: lista de (n, a[R] contagens das linhas, b[K] contagens das colunas). Soma das tabelas ajustadas."""
    R, K = len(B), len(B[0])
    tot = [[0.0] * K for _ in range(R)]
    for _, a, b in unidades:
        T = ipf([[a[r] * B[r][c] for c in range(K)] for r in range(R)], a, b)
        for r in range(R):
            tr, Tr = tot[r], T[r]
            for c in range(K): tr[c] += Tr[c]
    return tot


def para_dados(unidades):
    """(n, a, b) -> (w, x, y) com w = n / soma(n)."""
    N = sum(u[0] for u in unidades) or 1.0
    out = []
    for n, a, b in unidades:
        if n <= 0: continue
        out.append((n / N, [v / n for v in a], [v / n for v in b]))
    return out


def lam_para(n_mun):
    """Peso da âncora nacional: equivale a ~1 município médio (irrelevante em UFs grandes, decisivo no DF)."""
    return 1.0 / max(n_mun, 1)


def estima(unidades, B0=None, lam=0.0):
    """Ponto: (B do Goodman, tabela reconciliada RxK em contagens)."""
    d = para_dados(unidades)
    A, XY = momentos(d)
    B = goodman(A, XY, B0, lam)
    return B, reconcilia(B, unidades)


def bootstrap(unidades, B0, lam, n_boot, semente):
    """Lista de tabelas reconciliadas (RxK) sob reamostragem de municípios. Determinística pela semente."""
    rng = random.Random(semente)
    d = para_dados(unidades)
    # pesos relativos ficam como no original; a reamostragem só repete/omite municípios
    m = len(unidades)
    out = []
    for _ in range(n_boot):
        idx = [rng.randrange(m) for _ in range(m)]
        sw = sum(d[i][0] for i in idx) or 1.0
        A, XY = momentos(d, idx)
        A = [[v / sw for v in row] for row in A]
        XY = [[v / sw for v in row] for row in XY]
        B = goodman(A, XY, B0, lam, iters=1500, tol=1e-10)
        out.append(reconcilia(B, unidades))
    return out


def percentil(vals, p):
    """Percentil com interpolação linear (tipo 7)."""
    v = sorted(vals)
    if not v: return 0.0
    k = (len(v) - 1) * p
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def duncan_davis(unidades, r, c):
    """Limites determinísticos (contagens) da célula (r, c) somados nos municípios."""
    lo = hi = 0.0
    for n, a, b in unidades:
        lo += max(0.0, a[r] + b[c] - n)
        hi += min(a[r], b[c])
    return lo, hi


# ------------------------------------------------------------------ validação com dados sintéticos
B_TESTE = [[0.45, 0.30, 0.18, 0.07],   # eleitores de Lula
           [0.03, 0.82, 0.10, 0.05],   # eleitores de Flávio
           [0.25, 0.20, 0.25, 0.30]]   # outros / brancos / nulos


def _gama(rng, k):
    return rng.gammavariate(k, 1.0)


def simula(rng, n_mun=300, B=None, conc=60.0):
    """Municípios sintéticos com matriz verdadeira conhecida e heterogeneidade realista.
    Cada município tem a própria matriz B_i ~ Dirichlet(conc * B) (varia em torno de B, sem correlação com x).
    Devolve (unidades, tabela_verdadeira 3x4 somada)."""
    B = B or B_TESTE
    R, K = len(B), len(B[0])
    un, verdade = [], [[0.0] * K for _ in range(R)]
    for _ in range(n_mun):
        n = float(int(math.exp(rng.uniform(math.log(2000), math.log(400000)))))
        lu = rng.uniform(0.15, 0.70)
        fl = rng.uniform(0.15, 0.92 - lu) if lu < 0.77 else 0.15
        x = [lu, fl, 1.0 - lu - fl]
        a = [n * v for v in x]
        cols = [0.0] * K
        for r in range(R):
            g = [_gama(rng, conc * B[r][c]) for c in range(K)]
            s = sum(g)
            for c in range(K):
                cel = a[r] * g[c] / s
                cols[c] += cel
                verdade[r][c] += cel
        un.append((n, a, cols))
    return un, verdade


def avalia(un, verdade, n_boot=200, semente="sintetico"):
    """Estima e compara com a verdade. Devolve lista de (r, c, verdade, ponto, lo, hi, ponto_dentro) em proporções da
    linha. A faixa é só o percentil 5-95 das reamostragens: o ponto não é empurrado para dentro (relatado em ponto_dentro)."""
    B, tab = estima(un)
    boots = bootstrap(un, B, 0.0, n_boot, semente)
    out = []
    for r in range(len(tab)):
        tv, tp = sum(verdade[r]), sum(tab[r])
        for c in range(len(tab[0])):
            dist = [bt[r][c] / sum(bt[r]) for bt in boots]
            p = tab[r][c] / tp
            lo, hi = percentil(dist, 0.05), percentil(dist, 0.95)
            out.append((r, c, verdade[r][c] / tv, p, lo, hi, lo <= p <= hi))
    return out


def cobertura(reps=10, n_mun=300, n_boot=200, semente="cobertura"):
    """Fração de células (linhas Lula e Flávio) cujo intervalo de 90% contém a verdade, e erro máximo."""
    rng = random.Random(semente)
    hits = tot = fora = 0
    erro = 0.0
    por_linha = {}
    for i in range(reps):
        un, ver = simula(rng, n_mun)
        for r, c, v, p, lo, hi, dentro in avalia(un, ver, n_boot, f"{semente}-{i}"):
            ok = lo - 1e-12 <= v <= hi + 1e-12
            fora += not dentro
            por_linha.setdefault(r, [0, 0])
            por_linha[r][0] += ok; por_linha[r][1] += 1
            hits += ok; tot += 1
            erro = max(erro, abs(p - v))
    return {"celulas": tot, "cobertura": hits / tot, "erro_max": erro, "ponto_fora": fora,
            "por_linha": {r: h / t for r, (h, t) in por_linha.items()}}
