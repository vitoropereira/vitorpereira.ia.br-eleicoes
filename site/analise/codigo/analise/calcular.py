#!/usr/bin/env python3
"""Gera analise/dados/*.json (página Análise) a partir dos dados versionados do repo. Só biblioteca padrão.

Entradas: municipios/geo/t1/ (2026, 1º turno), municipios/geo/t2022/ (2022), relatorio/dados/ (UF, candidatos),
analise/lados-2026.json, analise/lados-2022.json, analise/fontes/cenarios.json (cenários checados).
Saída: analise/dados/{lados,campos,dividido,cadeiras,divergencias,brancos,fragmentacao,legenda,puxadores,
comparacao2022,cenarios,destaques,faq}.json  (contrato em docs/superpowers/specs/2026-10-08-analise-design.md)

Convenções: L = lado Lula, F = lado Flávio (em 2022: Jair Bolsonaro), C = centro/sem lado.
Lado de um partido na UF = override da UF, se houver; senão o lado nacional (analise/lados-*.json).
Presidente: L = Lula, F = Flávio, C = demais candidatos (o lado do 2º turno é o próprio candidato).

Uso: python3 analise/calcular.py [--saida DIR] [--boot N] [--proc N]"""
import argparse, json, math, re, sys
from multiprocessing import Pool
from pathlib import Path

A = Path(__file__).resolve().parent
R = A.parent
sys.path.insert(0, str(A))
sys.path.insert(0, str(R / "municipios"))
import inferencia as EI  # noqa: E402
from montar import nome as nome_urna  # noqa: E402  (mesma regra de nome do painel)

T1 = R / "municipios" / "geo" / "t1"
T22 = R / "municipios" / "geo" / "t2022"
UFD = R / "relatorio" / "dados"
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
CARGOS = ["presidente", "governador", "senador", "depfed", "depest"]
LEG = ["depfed", "depest", "senador", "governador"]  # cargos comparados com presidente
PROP = ("depfed", "depest")
LADOS = ("L", "F", "C")
N_BOOT = 200
SEMENTE = "analise-2026"
LIMITE = int(2.5 * 1024 * 1024)
MIN_ELEITORES_RANK22 = 10000


def ld(p):
    with open(p, encoding="utf-8") as f: return json.load(f)


def p4(x): return round(float(x), 4)


def lr4(props):
    """Arredonda proporções (soma 1) a 4 casas mantendo a soma exata (maior resto)."""
    u = [x * 10000 for x in props]
    base = [math.floor(x) for x in u]
    falta = 10000 - sum(base)
    ordem = sorted(range(len(u)), key=lambda i: (-(u[i] - base[i]), i))
    for i in ordem[:max(falta, 0)]: base[i] += 1
    return [b / 10000 for b in base]


def floor4(x): return max(0.0, math.floor(x * 10000 + 1e-9) / 10000)


def ceil4(x): return min(1.0, math.ceil(x * 10000 - 1e-9) / 10000)


# ------------------------------------------------------------------ formatação (usada nos textos e nos testes)
def _milhar(n):
    s = f"{abs(int(n)):,}".replace(",", ".")
    return ("-" if n < 0 else "") + s


def fmt(valor, tipo):
    """Formata um número para texto em pt-BR. Tipos: int, mi (milhões, 1 casa), pct (proporção 0-1, 1 casa),
    pct2 (proporção, 2 casas), pct0 (proporção, inteiro), x1 (1 casa)."""
    if tipo == "int": return _milhar(round(valor))
    if tipo == "mi": return f"{valor / 1e6:.1f}".replace(".", ",") + " milhões"
    if tipo == "pct": return f"{valor * 100:.1f}".replace(".", ",") + "%"
    if tipo == "pct2": return f"{valor * 100:.2f}".replace(".", ",") + "%"
    if tipo == "pct0": return f"{valor * 100:.0f}%"
    if tipo == "x1": return f"{valor:.1f}".replace(".", ",")
    raise ValueError(tipo)


NUM = re.compile(r"\d+(?:[.,]\d+)*(?![\dºª°])")
LIVRES = {"2022", "2024", "2026"}  # anos podem aparecer sem referência


def pega(dados, arq, caminho):
    v = dados[arq]
    for k in caminho: v = v[k]
    return v


class Texto:
    """Monta textos cujos números vêm sempre dos dados calculados (cada número guarda arquivo + caminho)."""

    def __init__(self, dados):
        self.dados, self.refs = dados, []

    def n(self, arq, caminho, tipo):
        v = pega(self.dados, arq, caminho)
        s = fmt(v, tipo)
        self.refs.append({"arq": arq, "caminho": list(caminho), "fmt": tipo, "texto": s})
        return s

    def fecha(self):
        r, self.refs = self.refs, []
        return r


# ------------------------------------------------------------------ dados de entrada
class Base:
    def __init__(self):
        self.meta = ld(T1 / "meta.json")
        self.pres = ld(T1 / "presidente.json")
        self.maj = {c: ld(T1 / f"{c}.json") for c in ("governador", "senador")}
        self.part = {c: ld(T1 / f"partidos-{c}.json") for c in CARGOS}
        self.cad = ld(T1 / "cadeiras.json")
        self.l26 = ld(A / "lados-2026.json")
        self.l22 = ld(A / "lados-2022.json")
        cp = self.meta["cand"]["presidente"]
        self.i_lula = next(i for i, c in enumerate(cp) if c["sg"] == "PT")
        self.i_flavio = next(i for i, c in enumerate(cp) if c["sg"] == "PL")
        self.mun = self.meta["mun"]  # cd -> [nome, UF]
        # 2022
        self.m22 = ld(T22 / "meta.json")
        self.p22 = {t: ld(T22 / f"presidente-{t}.json") for t in ("1t", "2t")}
        self.part22 = {c: ld(T22 / f"partidos-{c}.json") for c in CARGOS if c != "presidente"}
        self.cad22 = ld(T22 / "cadeiras.json")
        self.sem_lado = set()

    def lado(self, sg, uf, ano=2026):
        doc = self.l26 if ano == 2026 else self.l22
        p = doc["partidos"].get(sg)
        if p is None:
            self.sem_lado.add((ano, sg))
            return "C"
        return p["uf"].get(uf, p["lado"])


def denso_para_dict(partidos, arr):
    return {partidos[i]: v for i, v in enumerate(arr) if v}


def esparso_para_dict(partidos, e):
    return {partidos[i]: v for i, v in zip(e["i"], e["v"])}


def por_lado(b, votos, uf, ano=2026):
    s = {"L": 0, "F": 0, "C": 0}
    for sg, v in votos.items(): s[b.lado(sg, uf, ano)] += v
    return s


def linha_partidos(d, linha, esparso):
    conv = (lambda e: esparso_para_dict(d["partidos"], e)) if esparso else (lambda a: denso_para_dict(d["partidos"], a))
    return linha[0], conv(linha[1]), conv(linha[2])


# ------------------------------------------------------------------ 1. campos
def campos(b):
    out = {"BR": {}}
    for uf in UFS: out[uf] = {}
    # presidente: pelo candidato
    def pres_linha(l):
        L, F = l[5][b.i_lula], l[5][b.i_flavio]
        return {"L": L, "F": F, "C": l[2] - L - F, "validos": l[2]}
    out["BR"]["presidente"] = pres_linha(b.pres["br"])
    for uf in UFS: out[uf]["presidente"] = pres_linha(b.pres["uf"][uf])
    for c in ("governador", "senador", "depfed", "depest"):
        d = b.part[c]
        tot = {"L": 0, "F": 0, "C": 0, "validos": 0}
        tleg = {"L": 0, "F": 0, "C": 0}
        for uf in UFS:
            v, nom, leg = linha_partidos(d, d["uf"][uf], False)
            s = por_lado(b, nom, uf)
            sl = por_lado(b, leg, uf)
            x = {k: s[k] + sl[k] for k in LADOS}
            x["validos"] = v
            assert sum(x[k] for k in LADOS) == v, (c, uf)
            if c == "senador": x["votos_por_eleitor"] = 2
            if c in PROP: x["legenda"] = sl
            out[uf][c] = x
            for k in LADOS: tot[k] += x[k]; tleg[k] += sl[k]
            tot["validos"] += v
        assert tot["validos"] == d["br"][0], c
        if c == "senador": tot["votos_por_eleitor"] = 2
        if c in PROP: tot["legenda"] = tleg
        out["BR"][c] = tot
    return out


# ------------------------------------------------------------------ 3. cadeiras
def cadeiras(b, cam):
    out = {}
    for geo in ["BR"] + UFS:
        out[geo] = {}
        for c in ("depfed", "depest", "senador"):
            x = cam[geo][c]
            if geo == "BR":
                cad = {"L": 0, "F": 0, "C": 0}
                for uf in UFS:
                    for sg, n in b.cad[c]["uf"].get(uf, {}).items(): cad[b.lado(sg, uf)] += n
            else:
                cad = {"L": 0, "F": 0, "C": 0}
                for sg, n in b.cad[c]["uf"].get(geo, {}).items(): cad[b.lado(sg, geo)] += n
            out[geo][c] = {"votos": {k: p4(x[k] / x["validos"]) if x["validos"] else 0.0 for k in LADOS},
                           "votos_abs": {k: x[k] for k in LADOS}, "cadeiras": cad, "total": sum(cad.values())}
            if c == "senador": out[geo][c]["votos_por_eleitor"] = 2
    return out


# ------------------------------------------------------------------ 2. voto dividido (inferência ecológica)
LINHAS = ("lula", "flavio", "outros")
COLS = ("L", "F", "C", "BN")


def unidades_ei(b, cargo):
    """{UF: [(n, a[3], b[4])]} em eleitores (no Senado, votos/2 = eleitor-equivalente)."""
    d = b.part[cargo]
    gov = b.maj["governador"]["mu"]
    out = {uf: [] for uf in UFS}
    for cd in sorted(b.mun):
        uf = b.mun[cd][1]
        pl = b.pres["mu"].get(cd)
        if pl is None or cd not in d["mu"] or cd not in gov: continue
        n = gov[cd][1]  # comparecimento nos cargos estaduais (o de presidente inclui voto em trânsito)
        cp = pl[1]
        if n <= 0 or cp <= 0: continue
        lu, fl = pl[5][b.i_lula], pl[5][b.i_flavio]
        a = [lu * n / cp, fl * n / cp, (cp - lu - fl) * n / cp]
        v, nom, leg = linha_partidos(d, d["mu"][cd], True)
        s = por_lado(b, nom, uf)
        sl = por_lado(b, leg, uf)
        k = 2.0 if cargo == "senador" else 1.0
        cols = [(s["L"] + sl["L"]) / k, (s["F"] + sl["F"]) / k, (s["C"] + sl["C"]) / k]
        bn = n - sum(cols)
        assert bn >= -1e-6, (cargo, cd)
        cols.append(max(bn, 0.0))
        out[uf].append((float(n), a, cols))
    return out


def _tarefa_boot(args):
    unidades, B0, lam, nb, sem = args
    return EI.bootstrap(unidades, B0, lam, nb, sem)


MIN_MUN_BOOT = 10  # com menos municípios (DF tem 1) a reamostragem não informa: a faixa vira os limites de Duncan-Davis


def resume_tabela(tab, boots, unidades):
    """Converte tabela 3x4 (contagens) + bootstraps em células {v, pct, int} + limites de Duncan-Davis."""
    poucos = len(unidades) < MIN_MUN_BOOT
    out = {}
    lim = {}
    for r, nr in enumerate(LINHAS):
        tot = sum(tab[r])
        props = [tab[r][c] / tot if tot else 0.0 for c in range(4)]
        arr = lr4(props) if tot else [0.0] * 4
        for c, nc in enumerate(COLS):
            k = f"{nr}_para_{nc}"
            dist = []
            for bt in boots:
                tb = sum(bt[r])
                dist.append(bt[r][c] / tb if tb else 0.0)
            lo, hi = EI.duncan_davis(unidades, r, c)
            dlo, dhi = (lo / tot, hi / tot) if tot else (0.0, 0.0)
            if poucos or not dist:
                ilo, ihi = dlo, dhi
            else:
                ilo = min(EI.percentil(dist, 0.05), props[c])
                ihi = max(EI.percentil(dist, 0.95), props[c])
            ilo, ihi = max(ilo, dlo), min(ihi, dhi)
            out[k] = {"v": round(tab[r][c]), "pct": arr[c], "int": [min(floor4(ilo), arr[c]), max(ceil4(ihi), arr[c])]}
            lim[k] = [min(floor4(dlo), arr[c]), max(ceil4(dhi), arr[c])]
        out[f"{nr}_total"] = round(tot)
    out["limites"] = lim
    if poucos: out["poucos_municipios"] = True
    out["est"] = True
    return out


def dividido(b, n_boot, n_proc):
    out = {}
    detalhe = {}
    for cargo in LEG:
        por_uf = unidades_ei(b, cargo)
        todas = [u for uf in UFS for u in por_uf[uf]]
        B0, _ = EI.estima(todas)  # âncora nacional (todos os municípios)
        pontos, args = {}, []
        for uf in UFS:
            un = por_uf[uf]
            lam = EI.lam_para(len(un))
            B, tab = EI.estima(un, B0, lam)
            pontos[uf] = (B, tab, lam)
            args.append((un, B0, lam, n_boot, f"{SEMENTE}|{cargo}|{uf}"))
        if n_proc > 1:
            with Pool(n_proc) as pool: boots = pool.map(_tarefa_boot, args)
        else:
            boots = [_tarefa_boot(a) for a in args]
        boots = dict(zip(UFS, boots))
        br_tab = [[sum(pontos[uf][1][r][c] for uf in UFS) for c in range(4)] for r in range(3)]
        br_boots = [[[sum(boots[uf][i][r][c] for uf in UFS) for c in range(4)] for r in range(3)] for i in range(n_boot)]
        out.setdefault("BR", {})[cargo] = resume_tabela(br_tab, br_boots, todas)
        out["BR"][cargo]["n_mun"] = len(todas)
        for uf in UFS:
            B, tab, lam = pontos[uf]
            out.setdefault(uf, {})[cargo] = resume_tabela(tab, boots[uf], por_uf[uf])
            out[uf][cargo]["n_mun"] = len(por_uf[uf])
        detalhe[cargo] = {"B0": B0}
    meta = {
        "metodo": ("O voto é secreto: ninguém sabe em quem cada eleitor votou. Estimamos por inferência ecológica: "
                   "comparamos, nos municípios de cada estado, a votação de Lula e Flávio com a de cada lado no "
                   "outro cargo. Se onde Lula vai melhor o lado de Flávio também cresce, parte dos eleitores de Lula "
                   "votou nesse lado. Um ajuste com taxas entre 0 e 1 dá a taxa do estado; depois cada município é "
                   f"acertado aos votos oficiais. A faixa de 90% vem de {n_boot} reamostragens e mede só o erro "
                   "estatístico; os limites dão o mínimo e o máximo possíveis. No Senado (2 votos por eleitor), cada "
                   "voto vale meio eleitor. Brasil = soma dos estados, sem o exterior."),
        "linhas": {"lula": "eleitores de Lula", "flavio": "eleitores de Flávio",
                   "outros": "demais candidatos, brancos e nulos para presidente"},
        "colunas": {"L": "lado Lula", "F": "lado Flávio", "C": "centro/sem lado", "BN": "brancos e nulos"},
        "intervalo": 0.9, "boot": n_boot, "semente": SEMENTE,
    }
    return {**meta, **out}, detalhe


# ------------------------------------------------------------------ 4. divergências
def lado_municipio(votos):
    """Lado com mais votos válidos; empate no topo -> C."""
    mx = max(votos[k] for k in LADOS)
    top = [k for k in LADOS if votos[k] == mx]
    return top[0] if len(top) == 1 else "C"


def votos_mu(b, cargo, cd, uf):
    d = b.part[cargo]
    if cd not in d["mu"]: return None, 0
    v, nom, leg = linha_partidos(d, d["mu"][cd], True)
    s = por_lado(b, nom, uf)
    sl = por_lado(b, leg, uf)
    return {k: s[k] + sl[k] for k in LADOS}, v


def divergencias(b):
    mu, base = {}, {}
    for cd in sorted(b.mun):
        nm, uf = b.mun[cd]
        pl = b.pres["mu"].get(cd)
        if pl is None or pl[2] == 0: continue
        lu, fl = pl[5][b.i_lula], pl[5][b.i_flavio]
        pres = "L" if lu > fl else ("F" if fl > lu else "C")
        e = {"pres": pres}
        info = {"nome": nm, "uf": uf, "eleitores": pl[0], "pres": pres,
                "pres_pct": p4(max(lu, fl) / pl[2]), "lula_pct": lu / pl[2], "flavio_pct": fl / pl[2]}
        for c in LEG:
            vs, v = votos_mu(b, c, cd, uf)
            if vs is None or v == 0: continue
            lado = lado_municipio(vs)
            e[c] = lado
            info[c] = (lado, {k: vs[k] / v for k in LADOS})
        if "depfed" in info and pres in ("L", "F"):
            ppres = info["lula_pct"] if pres == "L" else info["flavio_pct"]
            e["gap_depfed"] = p4(ppres - info["depfed"][1][pres])
        mu[cd] = e
        base[cd] = info
    ranking = {}
    ufs = {g: {} for g in ["BR"] + UFS}
    for c in LEG:
        lst = []
        for cd, i in base.items():
            if c not in i or i["pres"] not in ("L", "F"): continue
            leg, sh = i[c]
            if leg in ("L", "F") and leg != i["pres"]:
                lst.append({"cd": cd, "nome": i["nome"], "uf": i["uf"], "pres": i["pres"], "pres_pct": i["pres_pct"],
                            "leg": leg, "leg_pct": p4(sh[leg]), "eleitores": i["eleitores"]})
        top = []
        for dirx in (("L", "F"), ("F", "L")):
            sel = [x for x in lst if (x["pres"], x["leg"]) == dirx]
            sel.sort(key=lambda x: (-x["eleitores"], x["cd"]))
            top += sel[:100]
        ranking[c] = top
        for g in ["BR"] + UFS:
            div = {"divergentes": 0, "lula_e_F": 0, "flavio_e_L": 0, "lula_e_C": 0, "flavio_e_C": 0, "centro": 0, "total": 0}
            for cd, i in base.items():
                if g != "BR" and i["uf"] != g: continue
                if c not in i: continue
                div["total"] += 1
                leg = i[c][0]
                if leg == "C": div["centro"] += 1
                if i["pres"] in ("L", "F") and leg != i["pres"]:  # mesma regra do HUD (hud/calc.js)
                    div["divergentes"] += 1
                    div[("lula" if i["pres"] == "L" else "flavio") + "_e_" + leg] += 1
            ufs[g][c] = div
    return {"mu": mu, "ranking": ranking, "uf": ufs,
            "criterio": ("Lado do município num cargo = lado com mais votos válidos (empate: C). Presidente: quem teve "
                         "mais votos entre Lula e Flávio (empate: C, fica fora da contagem). Divergente = presidente "
                         "com Lula ou Flávio e o cargo com outro lado, inclusive o centro (4 direções: lula_e_F, "
                         "lula_e_C, flavio_e_L, flavio_e_C). centro = municípios em que o centro venceu no cargo. "
                         "Ranking: só Lula x Flávio (sem centro), maiores municípios por eleitores, 100 por direção."),
            "gap_depfed": "% do vencedor para presidente menos % do mesmo lado para deputado federal (proporções)."}


# ------------------------------------------------------------------ 5. brancos e nulos
def brancos(b):
    out = {g: {} for g in ["BR"] + UFS}

    def lin(l): return {"brancos": l[3], "nulos": l[4], "validos": l[2], "comparecimento": l[1], "eleitores": l[0]}
    out["BR"]["presidente"] = lin(b.pres["br"])
    for uf in UFS: out[uf]["presidente"] = lin(b.pres["uf"][uf])
    for c in ("governador", "senador"):
        tot = {"brancos": 0, "nulos": 0, "validos": 0, "comparecimento": 0, "eleitores": 0}
        for uf in UFS:
            x = lin(b.maj[c]["uf"][uf])
            if c == "senador": x["votos_por_eleitor"] = 2
            out[uf][c] = x
            for k in tot: tot[k] += x[k]
        if c == "senador": tot["votos_por_eleitor"] = 2
        out["BR"][c] = tot
    for c, cod in (("depfed", 6), ("depest", 7)):
        tot = {"brancos": 0, "nulos": 0, "validos": 0, "comparecimento": 0, "eleitores": 0}
        for uf in UFS:
            k = 8 if (c == "depest" and uf == "DF") else cod
            d = ld(UFD / f"{uf.lower()}-c{k:04d}.json")
            x = {"brancos": int(d["v"]["vb"]), "nulos": int(d["v"]["tvn"]), "validos": int(d["v"]["vv"]),
                 "comparecimento": int(d["e"]["c"]), "eleitores": int(d["e"]["te"])}
            out[uf][c] = x
            for kk in tot: tot[kk] += x[kk]
        out["BR"][c] = tot
    for g in out:
        for c, x in out[g].items():
            vot = x["comparecimento"] * x.get("votos_por_eleitor", 1)
            x["brancos_pct"] = p4(x["brancos"] / vot) if vot else 0.0
            x["nulos_pct"] = p4(x["nulos"] / vot) if vot else 0.0
    return out


# ------------------------------------------------------------------ 6. fragmentação
def nep(vals):
    t = sum(vals)
    return 1.0 / sum((v / t) ** 2 for v in vals if v) if t else 0.0


def fragmentacao(b):
    out = {g: {} for g in ["BR"] + UFS}
    for c in ("depfed", "depest", "senador"):
        d = b.part[c]
        acc_v, acc_c = {}, {}
        cen_v = cen_c = tv = tc = 0
        for uf in UFS:
            v, nom, leg = linha_partidos(d, d["uf"][uf], False)
            pv = {sg: nom.get(sg, 0) + leg.get(sg, 0) for sg in set(nom) | set(leg)}
            pc = b.cad[c]["uf"].get(uf, {})
            cv = sum(x for sg, x in pv.items() if b.lado(sg, uf) == "C")
            cc = sum(x for sg, x in pc.items() if b.lado(sg, uf) == "C")
            out[uf][c] = {"nep": round(nep(list(pv.values())), 2), "nep_cadeiras": round(nep(list(pc.values())), 2),
                          "partidos_com_voto": sum(1 for x in pv.values() if x),
                          "partidos_com_cadeira": sum(1 for x in pc.values() if x),
                          "centro_pct_votos": p4(cv / v) if v else 0.0,
                          "centro_pct_cadeiras": p4(cc / sum(pc.values())) if pc else 0.0}
            for sg, x in pv.items(): acc_v[sg] = acc_v.get(sg, 0) + x
            for sg, x in pc.items(): acc_c[sg] = acc_c.get(sg, 0) + x
            cen_v += cv; cen_c += cc; tv += v; tc += sum(pc.values())
        out["BR"][c] = {"nep": round(nep(list(acc_v.values())), 2), "nep_cadeiras": round(nep(list(acc_c.values())), 2),
                        "partidos_com_voto": sum(1 for x in acc_v.values() if x),
                        "partidos_com_cadeira": sum(1 for x in acc_c.values() if x),
                        "centro_pct_votos": p4(cen_v / tv), "centro_pct_cadeiras": p4(cen_c / tc)}
    out["nota"] = ("Número efetivo de partidos (Laakso-Taagepera) = 1 / soma dos quadrados das fatias. Conta cada "
                   "partido, não a federação. Centro = partidos sem lado declarado na UF.")
    return out


# ------------------------------------------------------------------ 7. legenda
def legenda(cam):
    out = {}
    for g, x in cam.items():
        out[g] = {}
        for c in PROP:
            y = x[c]
            o = {k: p4(y["legenda"][k] / y[k]) if y[k] else 0.0 for k in LADOS}
            o["total"] = p4(sum(y["legenda"].values()) / y["validos"]) if y["validos"] else 0.0
            o["votos_legenda"] = dict(y["legenda"])
            out[g][c] = o
    return out


# ------------------------------------------------------------------ 8. puxadores
def quociente(validos, vagas):
    """Quociente eleitoral (Código Eleitoral, art. 106): fração > 0,5 arredonda para cima."""
    q, r = divmod(validos, vagas)
    return q + 1 if 2 * r > vagas else q


def puxadores(b):
    out = {}
    resumo = {}
    for c, cod in (("depfed", 6), ("depest", 7)):
        cand = []
        acima = pux = 0
        for uf in UFS:
            k = 8 if (c == "depest" and uf == "DF") else cod
            d = ld(UFD / f"{uf.lower()}-c{k:04d}.json")
            car = d["carg"][0]
            vv, nv = int(d["v"]["vv"]), int(car["nv"])
            q = quociente(vv, nv)
            assert q == int(car["qe"]), (c, uf, q, car["qe"])
            for a in car["agr"]:
                vag = int(a.get("vag") or 0)
                agr = a["nm"]
                for p in a["par"]:
                    for x in p.get("cand", []):
                        if x.get("dvt") != "Válido": continue
                        v = int(x["vap"])
                        pe = max(0, min((v - q) // q, vag - 1)) if v > q else 0
                        if v >= q: acima += 1
                        pux += pe
                        cand.append({"nome": nome_urna(x["nmu"]), "partido": p["sg"], "uf": uf, "votos": v,
                                     "quociente": q, "vezes_quociente": round(v / q, 2), "agremiacao": agr,
                                     "cadeiras_partido": vag, "puxados_estimados": pe,
                                     "eleito": x.get("e") == "s"})
        cand.sort(key=lambda x: (-x["votos"], x["nome"]))
        out[c] = cand[:30]
        resumo[c] = {"acima_do_quociente": acima, "puxados_total": pux}
    out["resumo"] = resumo
    out["nota"] = ("Quociente eleitoral = votos válidos ÷ vagas da UF. Puxados (aproximação) = votos do candidato "
                   "acima de um quociente ÷ quociente, arredondado para baixo, limitado às cadeiras do partido ou "
                   "federação menos 1. Ignora sobras e a cláusula de 10% do quociente para os puxados.")
    return out


# ------------------------------------------------------------------ 9. 2022 x 2026
def lado_pres(lula, outro, k_outro):
    """Vencedor entre Lula e o adversário: "L", k_outro ("B" em 2022, "F" em 2026) ou "E" (empate)."""
    return "L" if lula > outro else (k_outro if outro > lula else "E")


def chave_virada(s22, s26):
    """Tipo de virada; None quando há empate em algum dos anos (fica fora das contagens)."""
    if "E" in (s22, s26): return None
    return ("mantem_lula" if s26 == "L" else "lula_para_flavio") if s22 == "L" else ("bolsonaro_para_lula" if s26 == "L" else "mantem_direita")


def comparacao2022(b, cam, cad):
    m22c = b.m22["cand"]
    i22 = {t: {c["nome"]: i for i, c in enumerate(m22c[f"presidente-{t}"])} for t in ("1t", "2t")}
    L2, B2 = i22["2t"]["Lula"], i22["2t"]["Jair Bolsonaro"]
    L1, B1 = i22["1t"]["Lula"], i22["1t"]["Jair Bolsonaro"]
    mu, base = {}, []
    vir = {"lula_para_flavio": 0, "bolsonaro_para_lula": 0, "mantem_lula": 0, "mantem_direita": 0}
    vir_uf = {uf: dict.fromkeys(vir, 0) for uf in UFS}
    vir2 = dict.fromkeys(vir, 0)  # secundário: 2º turno de 2022 x 1º turno de 2026
    vir2_uf = {uf: dict.fromkeys(vir, 0) for uf in UFS}

    def lados_pct(d, cd, uf, ano):
        if cd not in d["mu"]: return None
        v, nom, leg = linha_partidos(d, d["mu"][cd], True)
        if not v: return None
        s = por_lado(b, nom, uf, ano)
        sl = por_lado(b, leg, uf, ano)
        return {k: p4((s[k] + sl[k]) / v) for k in LADOS}

    for cd in sorted(b.mun):
        nm, uf = b.mun[cd]
        p26 = b.pres["mu"].get(cd)
        p22 = b.p22["1t"]["mu"].get(cd)
        q22 = b.p22["2t"]["mu"].get(cd)
        if not p26 or not p22: continue
        l22, b22 = p22[5][L1], p22[5][B1]
        l26, f26 = p26[5][b.i_lula], p26[5][b.i_flavio]
        if not (l22 + b22) or not (l26 + f26): continue
        s22 = lado_pres(l22, b22, "B")
        s26 = lado_pres(l26, f26, "F")
        e = {"pres22": s22, "pres26": s26, "pres22_pct_lula": p4(l22 / (l22 + b22)),
             "pres26_pct_lula": p4(l26 / (l26 + f26)),
             "pres22_validos_lula": p4(l22 / p22[2]), "pres26_validos_lula": p4(l26 / p26[2]),
             "depfed22": lados_pct(b.part22["depfed"], cd, uf, 2022), "depfed26": lados_pct(b.part["depfed"], cd, uf, 2026)}
        if q22 and (q22[5][L2] + q22[5][B2]):
            e["pres22_2t"] = lado_pres(q22[5][L2], q22[5][B2], "B")
            e["pres22_2t_pct_lula"] = p4(q22[5][L2] / (q22[5][L2] + q22[5][B2]))
            k2 = chave_virada(e["pres22_2t"], s26)
            if k2: vir2[k2] += 1; vir2_uf[uf][k2] += 1
        mu[cd] = e
        k = chave_virada(s22, s26)
        if k: vir[k] += 1; vir_uf[uf][k] += 1
        base.append({"cd": cd, "nome": nm, "uf": uf, "eleitores": p26[0], "pres22_pct_lula": e["pres22_pct_lula"],
                     "pres26_pct_lula": e["pres26_pct_lula"], "delta": p4(e["pres26_pct_lula"] - e["pres22_pct_lula"]),
                     "pres22": s22, "pres26": s26})
    grandes = [x for x in base if x["eleitores"] >= MIN_ELEITORES_RANK22]
    ranking = sorted(grandes, key=lambda x: (-abs(x["delta"]), x["cd"]))[:100]
    ranking_criterio = (f"100 maiores variações (em módulo) entre municípios com {MIN_ELEITORES_RANK22} eleitores ou "
                        "mais: fatia de Lula entre Lula e o adversário, 1º turno de 2022 x 1º turno de 2026.")

    def forma_mu(l22t1, l22t2, l26, d22, d26):
        """Mesmo formato de uma entrada de mu, agregado (d22/d26 = {L,F,C} em proporção do depfed)."""
        l22, b22 = l22t1[5][L1], l22t1[5][B1]
        m22, n22 = l22t2[5][L2], l22t2[5][B2]
        lu, fl = l26[5][b.i_lula], l26[5][b.i_flavio]
        return {"pres22_validos_lula": p4(l22 / l22t1[2]), "pres26_validos_lula": p4(lu / l26[2]),
                "pres22": lado_pres(l22, b22, "B"), "pres26": lado_pres(lu, fl, "F"),
                "pres22_pct_lula": p4(l22 / (l22 + b22)), "pres26_pct_lula": p4(lu / (lu + fl)),
                "depfed22": d22, "depfed26": d26,
                "pres22_2t": lado_pres(m22, n22, "B"), "pres22_2t_pct_lula": p4(m22 / (m22 + n22))}

    def pres_geo(l22a, l22t1, l26):
        x22 = l22a[5][L2] / (l22a[5][L2] + l22a[5][B2])
        return {"lula22_2t": p4(x22), "lula22_1t": p4(l22t1[5][i22["1t"]["Lula"]] / l22t1[2]),
                "lula26_1t": p4(l26[5][b.i_lula] / l26[2]),
                "lula26_vs_flavio": p4(l26[5][b.i_lula] / (l26[5][b.i_lula] + l26[5][b.i_flavio]))}

    def leg22(c, uf):
        d = b.part22[c]
        v, nom, leg = linha_partidos(d, d["uf"][uf], False)
        s = por_lado(b, nom, uf, 2022)
        sl = por_lado(b, leg, uf, 2022)
        return {k: s[k] + sl[k] for k in LADOS}, v

    def cad22(c, uf):
        o = {"L": 0, "F": 0, "C": 0}
        for sg, n in b.cad22[c]["uf"].get(uf, {}).items(): o[b.lado(sg, uf, 2022)] += n
        return o

    geos = {}
    acc = {c: ({"L": 0, "F": 0, "C": 0}, [0]) for c in LEG}
    accc = {c: {"L": 0, "F": 0, "C": 0} for c in ("depfed", "depest", "senador")}
    for uf in UFS:
        g = {"presidente": pres_geo(b.p22["2t"]["uf"][uf], b.p22["1t"]["uf"][uf], b.pres["uf"][uf])}
        for c in LEG:
            s, v = leg22(c, uf)
            for k in LADOS: acc[c][0][k] += s[k]
            acc[c][1][0] += v
            x26 = cam[uf][c]
            g[c] = {"22": {k: p4(s[k] / v) if v else 0.0 for k in LADOS},
                    "26": {k: p4(x26[k] / x26["validos"]) for k in LADOS}}
        g["cadeiras"] = {}
        for c in ("depfed", "depest", "senador"):
            o = cad22(c, uf)
            for k in LADOS: accc[c][k] += o[k]
            g["cadeiras"][c] = {"22": o, "26": cad[uf][c]["cadeiras"]}
        g["viradas"] = vir_uf[uf]
        g["viradas_vs_2t_2022"] = vir2_uf[uf]
        geos[uf] = {**forma_mu(b.p22["1t"]["uf"][uf], b.p22["2t"]["uf"][uf], b.pres["uf"][uf], g["depfed"]["22"], g["depfed"]["26"]), **g}
    gbr = {"presidente": pres_geo(b.p22["2t"]["br"], b.p22["1t"]["br"], b.pres["br"])}
    for c in LEG:
        s, v = acc[c]
        x26 = cam["BR"][c]
        gbr[c] = {"22": {k: p4(s[k] / v[0]) for k in LADOS}, "26": {k: p4(x26[k] / x26["validos"]) for k in LADOS}}
    gbr["cadeiras"] = {c: {"22": accc[c], "26": cad["BR"][c]["cadeiras"]} for c in accc}
    gbr["viradas"] = vir
    gbr["viradas_vs_2t_2022"] = vir2
    gbr = {**forma_mu(b.p22["1t"]["br"], b.p22["2t"]["br"], b.pres["br"], gbr["depfed"]["22"], gbr["depfed"]["26"]), **gbr}
    pl22 = b.cad22["depfed"]["br"].get("PL", 0)
    gbr["pl_depfed"] = {"eleitos_2022": 99, "2022_tse_atual": pl22, "2026": b.cad["depfed"]["br"].get("PL", 0),
                        "nota": "99 eleitos em 2022 (98 após o recálculo das sobras determinado pelo STF). Dados de 2022 = TSE atual."}
    assert pl22 == 98, pl22
    return {"mu": mu, "viradas": vir, "viradas_vs_2t_2022": vir2, "ranking": ranking, "ranking_criterio": ranking_criterio, "BR": gbr, **geos,
            "nota": ("Em 2022 o lado F (ou B) significa Jair Bolsonaro. Presidente, comparação principal: 1º turno de "
                     "2022 x 1º turno de 2026 (fatia de Lula entre Lula e o adversário principal). Secundário, só como "
                     "referência: pres22_2t, pres22_2t_pct_lula e viradas_vs_2t_2022 (2º turno de 2022 x 1º turno de "
                     "2026, comparação desigual). Empate entre Lula e o adversário = E, fora das contagens de viradas. "
                     "Legislativo: lados pelo apoio no 2º turno de cada ano.")}


# ------------------------------------------------------------------ 10. cenários
def regra_pesquisa(p):
    """Publica só pesquisa com 2 fontes independentes (url + url_alt) ou registro conferido no TSE."""
    if p.get("registro_conferido_tse"): return True, "registro conferido no TSE"
    if p.get("url") and p.get("url_alt") and p.get("conferido"): return True, "2 fontes independentes"
    return False, "fonte única e registro não conferido no TSE"


def cenarios(b):
    f = ld(A / "fontes" / "cenarios.json")
    br = b.pres["br"]
    cp = b.meta["cand"]["presidente"]
    V = br[2]
    lu, fl = br[5][b.i_lula], br[5][b.i_flavio]
    elim = V - lu - fl
    minimo = V // 2 + 1
    precisa = {"votos_validos": V, "minimo_para_vencer": minimo, "eliminados_votos": elim,
               "lula_votos_1t": lu, "flavio_votos_1t": fl,
               "flavio_precisa_votos": minimo - fl, "lula_precisa_votos": minimo - lu,
               "flavio_pct_dos_eliminados": round((minimo - fl) / elim, 4),
               "lula_pct_dos_eliminados": round((minimo - lu) / elim, 4)}
    # contrato: proporções 0-1 (a fonte checada traz em %)
    for k in ("votos_validos", "minimo_para_vencer", "eliminados_votos", "flavio_precisa_votos", "lula_precisa_votos"):
        assert precisa[k] == f["precisa"][k], (k, precisa[k], f["precisa"][k])
    for k in ("flavio_pct_dos_eliminados", "lula_pct_dos_eliminados"):
        assert round(precisa[k] * 100, 2) == f["precisa"][k], (k, precisa[k], f["precisa"][k])
    # eliminados: votos do arquivo do TSE; posições da fonte checada
    votos = {c["nome"]: br[5][i] for i, c in enumerate(cp)}
    eliminados, resto = [], 0
    for e in f["eliminados"]:
        if e["nome"] in votos:
            assert votos[e["nome"]] == e["votos"], e["nome"]
            x = {k: e[k] for k in ("nome", "partido", "votos", "apoio_2t", "fonte_url", "fonte_data", "conferido")}
            x["lado_partido"] = b.lado(e["partido"], None)  # lado do partido = analise/lados-2026.json (nacional)
            x["apoio_candidato"] = e.get("apoio_candidato")  # apoio declarado do próprio candidato, com fonte
            assert x["apoio_candidato"] in ("L", "F", "C", None), e["nome"]
            if x["apoio_candidato"] in ("L", "F"): assert x["fonte_url"].startswith("https://") and x["fonte_data"], e["nome"]
            eliminados.append(x)
        else:
            resto = e
    nomeados = {e["nome"] for e in eliminados}
    outros = sum(v for n, v in votos.items() if n not in nomeados and cp[[c["nome"] for c in cp].index(n)]["sg"] not in ("PT", "PL"))
    assert outros == resto["votos"], (outros, resto["votos"])
    eliminados.append({"nome": resto["nome"], "partido": resto["partido"], "votos": outros, "lado_partido": "C",
                       "apoio_candidato": None, "apoio_2t": resto["apoio_2t"], "fonte_url": "", "fonte_data": "",
                       "conferido": False})
    # pesquisas
    pesq, desc = [], []
    for p in f["pesquisas"]:
        ok, motivo = regra_pesquisa(p)
        x = {k: p[k] for k in ("instituto", "campo", "data", "amostra", "margem_pp", "registro_tse", "url", "antes_1t") if k in p}
        if "url_alt" in p: x["url_alt"] = p["url_alt"]
        for k in ("lula", "flavio", "lula_validos", "flavio_validos"):  # a fonte traz em %; contrato em proporção
            if k in p: x[k] = round(p[k] / 100, 4)
        if ok:
            x["criterio"] = motivo
            pesq.append(x)
        else:
            desc.append({"instituto": p["instituto"], "campo": p["campo"], "motivo": motivo})
    pos = [p for p in pesq if not p["antes_1t"] and "lula_validos" in p]
    media = {"n": len(pos), "lula_validos": round(sum(p["lula_validos"] for p in pos) / len(pos), 4) if pos else None,
             "flavio_validos": round(sum(p["flavio_validos"] for p in pos) / len(pos), 4) if pos else None,
             "pesquisas": [f"{p['instituto']} {p['campo']}" for p in pos]}
    # cenários (aritmética refeita aqui)
    def res(gl, gf):  # votos ganhos -> proporção dos válidos
        return round((lu + gl) / V, 4), round((fl + gf) / V, 4)

    cen = []
    l, fv = res(elim / 2, elim / 2)
    cen.append({"id": "neutro", "nome": "Neutro: eliminados se dividem 50/50", "lula": l, "flavio": fv,
                "flavio_pct_eliminados": 0.5})
    apoio_f = sum(e["votos"] for e in eliminados if e["apoio_candidato"] == "F")
    rest = elim - apoio_f
    l, fv = res(rest / 2, apoio_f + rest / 2)
    cen.append({"id": "lado_declarado", "nome": "Apoios declarados: quem apoiou Flávio leva seus eleitores",
                "lula": l, "flavio": fv, "flavio_pct_eliminados": round((apoio_f + rest / 2) / elim, 4),
                "votos_apoiadores_flavio": apoio_f})
    if media["n"]:
        fp = media["flavio_validos"]
        nome = ("Como a média das pesquisas após o 1º turno (votos válidos)" if media["n"] > 1 else
                f"Como a pesquisa {pos[0]['instituto']} após o 1º turno (votos válidos)")
        cen.append({"id": "pesquisa", "nome": nome,
                    "lula": media["lula_validos"], "flavio": fp,
                    "flavio_pct_eliminados": round((fp * V - fl) / elim, 4)})
    p1, p2 = b.p22["1t"]["br"], b.p22["2t"]["br"]
    i1 = {c["nome"]: i for i, c in enumerate(b.m22["cand"]["presidente-1t"])}
    i2 = {c["nome"]: i for i, c in enumerate(b.m22["cand"]["presidente-2t"])}
    l1, b1 = p1[5][i1["Lula"]] / p1[2], p1[5][i1["Jair Bolsonaro"]] / p1[2]
    l2, b2 = p2[5][i2["Lula"]] / p2[2], p2[5][i2["Jair Bolsonaro"]] / p2[2]
    el22 = 1 - l1 - b1
    tl = (l2 - l1) / el22
    l, fv = res(elim * tl, elim * (1 - tl))
    cen.append({"id": "como_2022", "nome": "Transferência como em 2022", "lula": l, "flavio": fv,
                "flavio_pct_eliminados": round(1 - tl, 4),
                "base_2022": {"lula_1t": round(l1, 4), "bolsonaro_1t": round(b1, 4),
                              "lula_2t": round(l2, 4), "bolsonaro_2t": round(b2, 4),
                              "eliminados_pct": round(el22, 4), "lula_pct_dos_eliminados": round(tl, 4)}})
    return {"precisa": precisa, "eliminados": eliminados, "pesquisas": pesq, "pesquisas_descartadas": desc,
            "media_pos_1t": media, "cenarios": cen, "fontes_2022": f["fontes_2022"],
            "metodo": ("Cenários são aritmética transparente, não previsão. Base: votos válidos do 1º turno (TSE) com o "
                       "mesmo total no 2º. Os votos dos eliminados são repartidos pela regra de cada cenário. Apoios "
                       "vêm da imprensa (links); apoio de candidato não garante voto do eleitor. Pesquisas: só as "
                       "confirmadas por 2 fontes independentes ou com registro conferido no TSE; as anteriores ao "
                       "1º turno são só contexto. Números em proporção (0 a 1). lado_partido = lado do partido em "
                       "analise/lados-2026.json; apoio_candidato = apoio declarado do próprio candidato (com fonte)."),
            "verificado_em": f.get("verificado_em")}


# ------------------------------------------------------------------ destaques e FAQ
def destaques(D):
    t = Texto(D)
    out = []

    def item(id_, titulo, numero, texto, est, ancora):
        out.append({"id": id_, "titulo": titulo, "numero": numero, "texto": texto, "est": est, "ancora": ancora,
                    "refs": t.fecha()})

    dv = ["dividido.json", ["BR", "depfed"]]
    num = t.n(dv[0], dv[1] + ["lula_para_F", "v"], "mi")
    item("dividido-br", "Estimativa: eleitor de Lula, deputado do lado de Flávio", num,
         f"Estimativa: {t.n(dv[0], dv[1] + ['lula_para_F', 'pct'], 'pct')} dos eleitores de Lula votaram em deputado "
         f"federal de partido que apoia Flávio (faixa estatística de {t.n('dividido.json', ['intervalo'], 'pct0')}: {t.n(dv[0], dv[1] + ['lula_para_F', 'int', 0], 'pct')} a "
         f"{t.n(dv[0], dv[1] + ['lula_para_F', 'int', 1], 'pct')}; o mínimo e o máximo possíveis, pelos limites de "
         f"Duncan-Davis, vão de {t.n(dv[0], dv[1] + ['limites', 'lula_para_F', 0], 'pct')} a "
         f"{t.n(dv[0], dv[1] + ['limites', 'lula_para_F', 1], 'pct')}; o método tem limitações explicadas abaixo). "
         f"Entre eleitores de Flávio, o caminho inverso foi estimado em "
         f"{t.n(dv[0], dv[1] + ['flavio_para_L', 'pct'], 'pct')}.", True, "#voto-dividido")
    cd = ["cadeiras.json", ["BR", "depfed"]]
    num = t.n(cd[0], cd[1] + ["cadeiras", "L"], "int")
    item("cadeiras-depfed", "Câmara: votos e cadeiras do lado de Lula", num,
         f"Lula teve {t.n('campos.json', ['BR', 'presidente', 'L'], 'mi')} de votos. Os partidos do seu lado fizeram "
         f"{t.n(cd[0], cd[1] + ['votos', 'L'], 'pct')} dos votos para deputado federal e elegeram "
         f"{t.n(cd[0], cd[1] + ['cadeiras', 'L'], 'int')} das {t.n(cd[0], cd[1] + ['total'], 'int')} cadeiras. "
         f"O lado de Flávio elegeu {t.n(cd[0], cd[1] + ['cadeiras', 'F'], 'int')}.", False, "#votos-cadeiras")
    num = t.n("campos.json", ["BR", "depfed", "L"], "mi")
    item("campos-depfed", "Do voto em Lula ao voto em deputado", num,
         f"Lula: {t.n('campos.json', ['BR', 'presidente', 'L'], 'mi')} de votos. Deputados federais dos partidos do "
         f"lado de Lula: {t.n('campos.json', ['BR', 'depfed', 'L'], 'mi')}. Do lado de Flávio: "
         f"{t.n('campos.json', ['BR', 'depfed', 'F'], 'mi')}; do centro: {t.n('campos.json', ['BR', 'depfed', 'C'], 'mi')}.",
         False, "#campos")
    dg = ["divergencias.json", ["uf", "BR", "depfed"]]
    num = t.n(dg[0], dg[1] + ["lula_e_F"], "int")
    item("divergencia-mun", "Lula na frente, deputado do outro lado", num,
         f"Em {t.n(dg[0], dg[1] + ['lula_e_F'], 'int')} municípios Lula teve mais votos que Flávio, mas o lado de "
         f"Flávio somou mais votos para deputado federal. O inverso aconteceu em "
         f"{t.n(dg[0], dg[1] + ['flavio_e_L'], 'int')}.", False, "#divergencias")
    px = ["puxadores.json", ["depfed", 0]]
    item("puxador", "O maior puxador de votos", t.n(px[0], px[1] + ["votos"], "int"),
         f"{pega(D, px[0], px[1] + ['nome'])} ({pega(D, px[0], px[1] + ['partido'])}-{pega(D, px[0], px[1] + ['uf'])}) teve "
         f"{t.n(px[0], px[1] + ['votos'], 'int')} votos, {t.n(px[0], px[1] + ['vezes_quociente'], 'x1')} vezes o quociente "
         f"eleitoral do estado. Pela conta aproximada, ajudou a eleger mais {t.n(px[0], px[1] + ['puxados_estimados'], 'int')} "
         f"colegas.", True, "#puxadores")
    vr = ["comparacao2022.json", ["viradas"]]
    item("viradas", "Viradas desde 2022", t.n(vr[0], vr[1] + ["lula_para_flavio"], "int"),
         f"No 1º turno de 2022 × 1º turno de 2026: {t.n(vr[0], vr[1] + ['lula_para_flavio'], 'int')} municípios deram "
         f"mais votos a Lula que a Bolsonaro em 2022 e agora deram mais votos a Flávio que a Lula. No sentido "
         f"contrário (Bolsonaro em 2022, Lula em 2026): {t.n(vr[0], vr[1] + ['bolsonaro_para_lula'], 'int')}.",
         False, "#comparacao-2022")
    ce = ["cenarios.json", ["precisa"]]
    item("precisa", "Quanto cada um precisa dos eliminados", t.n(ce[0], ce[1] + ["flavio_pct_dos_eliminados"], "pct2"),
         f"Para vencer, Flávio precisa de {t.n(ce[0], ce[1] + ['flavio_pct_dos_eliminados'], 'pct2')} dos "
         f"{t.n(ce[0], ce[1] + ['eliminados_votos'], 'mi')} de votos dos candidatos eliminados; Lula, de "
         f"{t.n(ce[0], ce[1] + ['lula_pct_dos_eliminados'], 'pct2')}. Conta sobre votos válidos, sem prever abstenção.",
         False, "#cenarios-2-turno")
    fr = ["fragmentacao.json", ["BR", "depfed"]]
    item("fragmentacao", "Uma Câmara de muitos partidos", t.n(fr[0], fr[1] + ["partidos_com_cadeira"], "int"),
         f"{t.n(fr[0], fr[1] + ['partidos_com_cadeira'], 'int')} partidos elegeram deputado federal. O número efetivo "
         f"de partidos (que pesa o tamanho de cada um) é {t.n(fr[0], fr[1] + ['nep_cadeiras'], 'x1')}. Partidos sem "
         f"lado no 2º turno ficaram com {t.n(fr[0], fr[1] + ['centro_pct_cadeiras'], 'pct')} das cadeiras.",
         False, "#fragmentacao")
    return out


def faq(D):
    t = Texto(D)
    out = []

    def qa(q, a): out.append({"q": q, "a": a, "refs": t.fecha()})

    c = "campos.json"
    qa("Quantos votos Lula e Flávio tiveram no 1º turno de 2026?",
       f"Flávio Bolsonaro teve {t.n(c, ['BR', 'presidente', 'F'], 'int')} votos e Lula, "
       f"{t.n(c, ['BR', 'presidente', 'L'], 'int')}, de {t.n(c, ['BR', 'presidente', 'validos'], 'int')} votos válidos "
       f"(TSE, apuração do 1º turno).")
    ce = ["cenarios.json", ["precisa"]]
    qa("Quantos votos Flávio e Lula precisam para vencer o 2º turno?",
       f"Mantido o total de {t.n(ce[0], ce[1] + ['votos_validos'], 'int')} votos válidos, vence quem passar de "
       f"{t.n(ce[0], ce[1] + ['minimo_para_vencer'], 'int')}. Flávio precisa de mais "
       f"{t.n(ce[0], ce[1] + ['flavio_precisa_votos'], 'int')} ({t.n(ce[0], ce[1] + ['flavio_pct_dos_eliminados'], 'pct2')} "
       f"dos votos dos eliminados) e Lula, de mais {t.n(ce[0], ce[1] + ['lula_precisa_votos'], 'int')} "
       f"({t.n(ce[0], ce[1] + ['lula_pct_dos_eliminados'], 'pct2')}). É aritmética, não previsão.")
    cd = ["cadeiras.json", ["BR", "depfed"]]
    qa("Por que Lula tem tantos votos e a esquerda elegeu poucos deputados?",
       f"Pela estimativa, {t.n('dividido.json', ['BR', 'depfed', 'lula_para_F', 'pct'], 'pct')} dos eleitores de Lula "
       f"escolheram deputado de partido que apoia Flávio e "
       f"{t.n('dividido.json', ['BR', 'depfed', 'lula_para_C', 'pct'], 'pct')}, de partido sem lado. Os partidos do "
       f"campo de Lula fizeram {t.n(cd[0], cd[1] + ['votos', 'L'], 'pct')} dos votos para deputado federal e ficaram "
       f"com {t.n(cd[0], cd[1] + ['cadeiras', 'L'], 'int')} cadeiras. É estimativa (faixa estatística de "
       f"{t.n('dividido.json', ['BR', 'depfed', 'lula_para_F', 'int', 0], 'pct')} a "
       f"{t.n('dividido.json', ['BR', 'depfed', 'lula_para_F', 'int', 1], 'pct')} para o primeiro número; limites de "
       f"Duncan-Davis de {t.n('dividido.json', ['BR', 'depfed', 'limites', 'lula_para_F', 0], 'pct')} a "
       f"{t.n('dividido.json', ['BR', 'depfed', 'limites', 'lula_para_F', 1], 'pct')}).")
    qa("Como dá para saber em quem o eleitor de Lula votou para deputado se o voto é secreto?",
       f"Não dá para saber de cada eleitor. A estimativa usa inferência ecológica: compara a votação de "
       f"{t.n('dividido.json', ['BR', 'depfed', 'n_mun'], 'int')} municípios e calcula a taxa mais compatível com "
       f"todos eles. A faixa estatística de {t.n('dividido.json', ['intervalo'], 'pct0')} mede só o erro estatístico; "
       f"os limites de Duncan-Davis dão o mínimo e o máximo possíveis. O método tem limitações explicadas na página. "
       f"É estimativa, não contagem.")
    qa("Quantos deputados federais o PL elegeu?",
       f"O PL elegeu {t.n('comparacao2022.json', ['BR', 'pl_depfed', '2026'], 'int')} deputados federais em 2026. Em "
       f"2022 foram {t.n('comparacao2022.json', ['BR', 'pl_depfed', 'eleitos_2022'], 'int')} eleitos "
       f"({t.n('comparacao2022.json', ['BR', 'pl_depfed', '2022_tse_atual'], 'int')} após o recálculo das sobras "
       f"determinado pelo STF).")
    pq = ["puxadores.json", ["depfed", 0]]
    qa("O que é quociente eleitoral?",
       f"É o número de votos válidos de um estado dividido pelo número de vagas. Cada vez que um partido ou "
       f"federação soma um quociente, ganha uma cadeira; as que sobram vão pelas maiores médias. Em "
       f"{pega(D, pq[0], pq[1] + ['uf'])}, o quociente para deputado federal foi "
       f"{t.n(pq[0], pq[1] + ['quociente'], 'int')} votos.")
    bq = ["brancos.json", ["BR", "presidente"]]
    qa("Quantos votos brancos e nulos houve para presidente?",
       f"Foram {t.n(bq[0], bq[1] + ['brancos'], 'int')} votos brancos e {t.n(bq[0], bq[1] + ['nulos'], 'int')} nulos "
       f"para presidente, de {t.n(bq[0], bq[1] + ['comparecimento'], 'int')} eleitores que compareceram.")
    s = ["campos.json", ["BR", "senador"]]
    qa("Por que os votos para o Senado somam mais que o número de eleitores?",
       f"Em 2026 cada estado elegeu dois senadores e cada eleitor teve {t.n(s[0], s[1] + ['votos_por_eleitor'], 'int')} "
       f"votos. Por isso os "
       f"{t.n(s[0], s[1] + ['validos'], 'mi')} de votos válidos para o Senado são votos, não eleitores. Os partidos "
       f"do lado de Flávio fizeram {t.n(s[0], s[1] + ['F'], 'mi')} e os do lado de Lula, "
       f"{t.n(s[0], s[1] + ['L'], 'mi')}.")
    lg = ["legenda.json", ["BR", "depfed"]]
    qa("O que é voto de legenda e quanto ele pesou?",
       f"É o voto só no número do partido, sem escolher candidato. Para deputado federal, foi "
       f"{t.n(lg[0], lg[1] + ['total'], 'pct')} dos votos válidos: {t.n(lg[0], lg[1] + ['L'], 'pct')} no lado de Lula e "
       f"{t.n(lg[0], lg[1] + ['F'], 'pct')} no lado de Flávio.")
    vr = ["comparacao2022.json", ["viradas"]]
    qa("Em quantas cidades Lula perdeu a liderança desde 2022?",
       f"Comparando o 1º turno de 2022 com o 1º turno de 2026: em {t.n(vr[0], vr[1] + ['lula_para_flavio'], 'int')} "
       f"municípios Lula teve mais votos que Bolsonaro em 2022 e ficou atrás de Flávio em 2026. Em "
       f"{t.n(vr[0], vr[1] + ['bolsonaro_para_lula'], 'int')} aconteceu o contrário.")
    qa("Quem apoia Lula e quem apoia Flávio no 2º turno?",
       "A classificação usa só prova pública: nota do partido, coligação registrada ou declaração do dirigente. "
       "Sem prova, o partido fica no centro. Diretórios estaduais podem ter posição própria. A lista completa, com "
       "links, está na página.")
    return out


# ------------------------------------------------------------------ lados (cópia resolvida)
def lados(b):
    def conv(doc):
        return {sg: {"lado": p["lado"], "uf": p["uf"], "provas": [{k: pr[k] for k in ("tipo", "url", "data", "titulo", "uf") if k in pr} for pr in p["provas"]],
                     "obs": p.get("obs", "")} for sg, p in doc["partidos"].items()}
    return {"posicao_em": b.l26["posicao_em"], "2026": conv(b.l26), "2022": conv(b.l22),
            "mapa_siglas_2026": b.l22.get("mapa_siglas_2026", {})}


# ------------------------------------------------------------------ main
def dump(o): return json.dumps(o, separators=(",", ":"), ensure_ascii=False)


def calcula(n_boot=N_BOOT, n_proc=1):
    b = Base()
    D = {}
    D["lados.json"] = lados(b)
    D["campos.json"] = cam = campos(b)
    D["cadeiras.json"] = cad = cadeiras(b, cam)
    D["dividido.json"], _ = dividido(b, n_boot, n_proc)
    D["divergencias.json"] = divergencias(b)
    D["brancos.json"] = brancos(b)
    D["fragmentacao.json"] = fragmentacao(b)
    D["legenda.json"] = legenda(cam)
    D["puxadores.json"] = puxadores(b)
    D["comparacao2022.json"] = comparacao2022(b, cam, cad)
    D["cenarios.json"] = cenarios(b)
    D["destaques.json"] = destaques(D)
    D["faq.json"] = faq(D)
    if b.sem_lado: print("AVISO: siglas sem lado (tratadas como C):", sorted(b.sem_lado), file=sys.stderr)
    return D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=str(A / "dados"))
    ap.add_argument("--boot", type=int, default=N_BOOT)
    ap.add_argument("--proc", type=int, default=8)
    a = ap.parse_args()
    D = calcula(a.boot, a.proc)
    out = Path(a.saida)
    out.mkdir(parents=True, exist_ok=True)
    for nome, obj in D.items():
        s = dump(obj)
        assert len(s.encode()) <= LIMITE, (nome, len(s.encode()))
        (out / nome).write_text(s, encoding="utf-8")
        print(f"{nome}: {len(s.encode()) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
