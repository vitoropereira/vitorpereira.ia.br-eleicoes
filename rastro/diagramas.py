"""Diagramas do Rastro em SVG estático, gerados no build (Python puro, sem JS).

`layout_sankey` só calcula geometria (sem HTML); `sankey` desenha o SVG; `fluxos_campanha` monta, a partir de
rastro/dados/contas/<sq>.json, o caminho do dinheiro da campanha: origem → campanha → tipo de gasto → fornecedor.
Cores só por `var(--…)` de brand.css (nenhuma cor literal). Pessoa física nunca tem nome; MEI e fornecedor sem cadastro
aparecem só pelo CNPJ mascarado (mesma regra da tabela da página).
"""
import html
import re

from rastro import indicadores as ind

SEM_DIAGRAMA = "Sem prestação na base para o diagrama."
LIMITACAO = "A base não liga cada receita a cada despesa; o diagrama não mostra que fonte pagou qual fornecedor."
NOTA_TIPO = ("Fornecedor com mais de um tipo de gasto entra inteiro no tipo de maior valor da campanha; "
             "por isso o valor de um tipo pode diferir do total declarado por tipo.")
TOL = 0.01
MIN_PX = 1.0  # espessura visual mínima de nó e faixa com valor > 0
LARGURA = 900
NO_W = 10
GAP = 16  # espaço vertical entre nós da mesma coluna: maior que a linha do rótulo, que não se sobrepõe
FONTE = 11
XS = (200, 360, 480, 662)
MAX_ORIGENS = 6
MAX_TIPOS = 8
MAX_FORN = 10
PCT_DOADOR = 0.02
RE_PF = re.compile(r"pessoas? f[ií]sicas?", re.I)
RE_PROPRIOS = re.compile(r"pr[óo]prios", re.I)
RE_PARTIDO = re.compile(r"partid|fundo especial|fefc", re.I)


def esc(t):
    return html.escape(str(t), quote=True)


def brl_curto(v):
    """'R$ 4,5 mi', 'R$ 38 mil', 'R$ 125'."""
    if v >= 1e6:
        return f"R$ {v / 1e6:.1f} mi".replace(".", ",")
    if v >= 1e3:
        return f"R$ {v / 1e3:.0f} mil"
    return f"R$ {v:.0f}"


def cortar(t, n):
    t = str(t)
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


# ---------- layout ----------

def layout_sankey(colunas, fluxos, altura, largura=LARGURA, xs=None, gap=GAP, no_w=NO_W, topo=0):
    """colunas: [[{id, ...}, ...], ...]; fluxos: [{de, para, valor}]. Devolve {nos: {id: {x, y, h, valor, col}}, faixas:
    [{de, para, valor, x0, x1, y0, y1, espessura}], altura}. O valor do nó é max(entra, sai); a escala é a mesma em todas
    as colunas (a mais cheia cabe em `altura`). Faixa ou nó com valor > 0 tem pelo menos MIN_PX, sem mudar o valor."""
    ncol = len(colunas)
    if xs is None:
        passo = (largura - no_w) / max(ncol - 1, 1)
        xs = [i * passo for i in range(ncol)]
    entra, sai = {}, {}
    for f in fluxos:
        sai[f["de"]] = sai.get(f["de"], 0) + f["valor"]
        entra[f["para"]] = entra.get(f["para"], 0) + f["valor"]
    valor = {n["id"]: max(entra.get(n["id"], 0), sai.get(n["id"], 0)) for col in colunas for n in col}
    escalas = []
    for col in colunas:
        tot = sum(valor[n["id"]] for n in col)
        livre = altura - gap * (len(col) - 1)
        if tot > 0 and livre > 0:
            escalas.append(livre / tot)
    k = min(escalas) if escalas else 0
    nos, fim = {}, topo
    for c, col in enumerate(colunas):
        hs = [max(valor[n["id"]] * k, MIN_PX) if valor[n["id"]] > 0 else 0 for n in col]
        usado = sum(hs) + gap * (len(col) - 1)
        y = topo + max((altura - usado) / 2, 0)
        for n, h in zip(col, hs):
            nos[n["id"]] = {"x": xs[c], "y": y, "h": h, "valor": valor[n["id"]], "col": c}
            y += h + gap
        fim = max(fim, y - gap)
    faixas = []
    for f in fluxos:
        if f["valor"] <= 0:
            continue
        faixas.append({"de": f["de"], "para": f["para"], "valor": f["valor"], "espessura": max(f["valor"] * k, MIN_PX)})
    # empilha as faixas em cada nó na ordem vertical do outro extremo (menos cruzamentos)
    off_sai, off_entra = {}, {}
    for fx in sorted(faixas, key=lambda f: (nos[f["de"]]["y"], nos[f["para"]]["y"])):
        o = off_sai.get(fx["de"], 0)
        fx["y0"] = nos[fx["de"]]["y"] + o + fx["espessura"] / 2
        off_sai[fx["de"]] = o + fx["espessura"]
    for fx in sorted(faixas, key=lambda f: (nos[f["para"]]["y"], nos[f["de"]]["y"])):
        o = off_entra.get(fx["para"], 0)
        fx["y1"] = nos[fx["para"]]["y"] + o + fx["espessura"] / 2
        off_entra[fx["para"]] = o + fx["espessura"]
    for fx in faixas:
        fx["x0"] = nos[fx["de"]]["x"] + no_w
        fx["x1"] = nos[fx["para"]]["x"]
    return {"nos": nos, "faixas": faixas, "altura": fim}


# ---------- SVG ----------

def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def sankey(colunas, fluxos, opcoes):
    """SVG acessível: role="img", <title> (opcoes['titulo']) e <desc> (opcoes['resumo']); um <title> por faixa e por nó
    com o valor em R$. Nó com 'alerta' ganha borda var(--amber) e link para opcoes do nó ('href', âncora na página).
    Nó com 'tom': 'muted' sai em cinza. viewBox sem width/height: a largura vem do CSS."""
    pre = opcoes.get("id", "sk")
    largura = opcoes.get("largura", LARGURA)
    xs = opcoes.get("xs", XS)
    corte = opcoes.get("corte", (34, 34, 27, 33))  # caracteres por rótulo (nome + valor) que cabem no espaço da coluna
    acima = opcoes.get("rotulo_acima", 1)  # coluna com o rótulo de duas linhas acima do nó (None: todas ao lado)
    n_max = max((len(c) for c in colunas), default=1)
    topo = 40 if acima is not None else 8  # espaço para o rótulo de duas linhas da campanha, acima do nó
    altura = max(260, n_max * (GAP + 10))
    lay = layout_sankey(colunas, fluxos, altura, largura, xs=xs, topo=topo)
    total_h = lay["altura"] + 12
    out = [f'<svg viewBox="0 0 {largura} {_f(total_h)}" role="img" aria-labelledby="{pre}-t {pre}-d" '
           f'style="font:{FONTE}px var(--font-sans);display:block">',
           f'<title id="{pre}-t">{esc(opcoes["titulo"])}</title><desc id="{pre}-d">{esc(opcoes["resumo"])}</desc>']
    por_id = {n["id"]: n for col in colunas for n in col}
    out.append('<g style="fill:none;stroke:var(--neutral);stroke-opacity:.45">')
    for fx in lay["faixas"]:
        xm = (fx["x0"] + fx["x1"]) / 2
        d = f'M{_f(fx["x0"])} {_f(fx["y0"])}C{_f(xm)} {_f(fx["y0"])} {_f(xm)} {_f(fx["y1"])} {_f(fx["x1"])} {_f(fx["y1"])}'
        tom = ";stroke:var(--muted);stroke-opacity:.2" if por_id[fx["para"]].get("tom") == "muted" or por_id[fx["de"]].get("tom") == "muted" else ""
        nome = f'{por_id[fx["de"]].get("titulo") or por_id[fx["de"]]["rotulo"]} → {por_id[fx["para"]].get("titulo") or por_id[fx["para"]]["rotulo"]}'
        out.append(f'<path d="{d}" style="stroke-width:{_f(fx["espessura"])}{tom}"><title>{esc(nome)}: {esc(ind.brl(fx["valor"]))}</title></path>')
    out.append("</g>")
    halo = "paint-order:stroke;stroke:var(--bg);stroke-width:3px;stroke-linejoin:round"
    for c, col in enumerate(colunas):
        for n in col:
            g = lay["nos"][n["id"]]
            if g["valor"] <= 0:
                continue
            nome = n.get("titulo") or n["rotulo"]
            cor = "var(--muted)" if n.get("tom") == "muted" else "var(--ink2)"
            borda = ";stroke:var(--amber);stroke-width:2" if n.get("alerta") else ""
            rect = (f'<rect x="{_f(g["x"])}" y="{_f(g["y"])}" width="{NO_W}" height="{_f(g["h"])}" style="fill:{cor}{borda}">'
                    f'<title>{esc(nome)}: {esc(ind.brl(g["valor"]))}</title></rect>')
            cy = g["y"] + g["h"] / 2
            val = brl_curto(g["valor"])
            rot = cortar(n["rotulo"], corte[min(c, len(corte) - 1)] - (0 if c == acima else len(val) + 1 + 2 * bool(n.get("alerta"))))
            if c == acima:  # campanha: nome e linha extra acima do nó
                cx = g["x"] + NO_W / 2
                txt = (f'<text x="{_f(cx)}" y="{_f(g["y"] - 22)}" style="text-anchor:middle;fill:var(--ink);font-weight:600;{halo}">{esc(rot)}</text>'
                       + (f'<text x="{_f(cx)}" y="{_f(g["y"] - 7)}" style="text-anchor:middle;fill:var(--ink2);{halo}">{esc(n["linha2"])}</text>' if n.get("linha2") else ""))
            elif c == 0:
                txt = (f'<text x="{_f(g["x"] - 6)}" y="{_f(cy)}" dy=".35em" style="text-anchor:end;fill:var(--ink);{halo}">'
                       f'{esc(rot)} <tspan style="fill:var(--muted)">{esc(val)}</tspan><title>{esc(nome)}</title></text>')
            else:
                marca = '<tspan style="fill:var(--amber)">● </tspan>' if n.get("alerta") else ""
                txt = (f'<text x="{_f(g["x"] + NO_W + 6)}" y="{_f(cy)}" dy=".35em" style="fill:var(--ink);{halo}">'
                       f'{marca}{esc(rot)} <tspan style="fill:var(--muted)">{esc(val)}</tspan><title>{esc(nome)}</title></text>')
            item = rect + txt
            if n.get("href"):
                item = f'<a href="{esc(n["href"])}">{item}</a>'
            out.append(item)
    out.append("</svg>")
    return "".join(out)


# ---------- dados da campanha ----------

def _tipo_principal(f, por_tipo):
    tipos = f.get("tipos") or []
    if not tipos:
        return "Tipo não informado"
    return sorted(tipos, key=lambda t: (-(por_tipo.get(t) or 0), t))[0]


def fluxos_campanha(contas, fornecedores, indicadores, ids=None, nome=None):
    """contas/<sq>.json -> {colunas, fluxos, resumo, campanha} ou None quando não há prestação para desenhar.
    `fornecedores`: {cnpj: cadastro} (fornecedores.json); `indicadores`: itens da campanha (indicadores[sq]);
    `ids`: {cnpj: id da página do fornecedor} (só para a âncora da linha da tabela, nunca link para fora)."""
    from rastro import paginas as pg  # tardio: paginas importa este módulo

    contas = contas or {}
    rec, desp = contas.get("receitas"), contas.get("despesas")
    if not rec or not desp:
        return None
    R = float(rec.get("total") or 0)
    C = float(desp.get("total_contratado") or 0)
    pago = float(desp.get("total_pago") or 0)
    pj = [f for f in desp.get("fornecedores_pj") or [] if (f.get("total") or 0) > 0]
    pf = desp.get("fornecedores_pf") or {}
    pf_total = float(pf.get("total") or 0)
    S = sum(f["total"] for f in pj) + pf_total
    D = max(C, S)
    if max(R, D) <= 0:
        return None
    campanha = nome or contas.get("nome_urna") or "Campanha"
    fluxos, colunas = [], [[], [], [], []]

    # coluna 1: origens
    origem = rec.get("por_origem") or {}
    v_pf = sum(v for k, v in origem.items() if RE_PF.search(k))
    v_prop = sum(v for k, v in origem.items() if RE_PROPRIOS.search(k))
    doadores = sorted((d for d in rec.get("doadores_pj") or [] if (d.get("total") or 0) > 0), key=lambda d: (-d["total"], d.get("nome") or ""))
    v_pj = sum(d["total"] for d in doadores)
    v_outros = R - v_pj - v_pf - v_prop
    excesso = D - R  # contratado além do recebido: nó cinza, sem inventar origem
    fixos = [n for n in (("pf", "Pessoas físicas", v_pf), ("prop", "Recursos próprios", v_prop), ("outros", "Outros", v_outros)) if n[2] > TOL]
    vagas = MAX_ORIGENS - len(fixos) - (excesso > TOL)
    grandes = [d for d in doadores if R > 0 and d["total"] >= PCT_DOADOR * R]
    if len(grandes) < len(doadores) or len(grandes) > vagas:
        grandes = grandes[:max(vagas - 1, 0)]  # uma vaga fica para "Outros doadores"
    resto = v_pj - sum(d["total"] for d in grandes)
    for i, d in enumerate(grandes):
        colunas[0].append({"id": f"o{i}", "rotulo": d.get("nome") or ind.mascarar_cnpj(d.get("cnpj")), "valor": d["total"]})
    if resto > TOL:
        colunas[0].append({"id": "o-resto", "rotulo": "Outros doadores", "valor": resto})
    for k, rot, v in fixos:
        colunas[0].append({"id": f"o-{k}", "rotulo": rot, "valor": v})
    if excesso > TOL:
        colunas[0].append({"id": "o-excesso", "rotulo": "Contratado além do recebido na base", "valor": excesso, "tom": "muted"})
    for n in colunas[0]:
        fluxos.append({"de": n["id"], "para": "camp", "valor": n.pop("valor")})
    entrada = sum(f["valor"] for f in fluxos)

    # coluna 2: campanha
    colunas[1].append({"id": "camp", "rotulo": campanha, "linha2": f"Contratado {brl_curto(C)} · pago {brl_curto(pago)}",
                       "titulo": f"{campanha}: contratado {ind.brl(C)}, pago {ind.brl(pago)}"})

    # coluna 3: tipos de gasto (fornecedores PJ inteiros no tipo principal) e sumidouros
    por_tipo_decl = desp.get("por_tipo") or {}
    itens = indicadores or []
    forn_info = []
    for i, f in enumerate(desp.get("fornecedores_pj") or []):
        if (f.get("total") or 0) <= 0:
            continue
        cnpj = ind.digitos(f.get("cnpj"))
        r = (fornecedores or {}).get(cnpj)
        mei = pg.eh_mei(r)
        alerta = bool(pg._itens_do_fornecedor(f, r, mei, pj, itens))
        forn_info.append({"i": i, "nome": pg.nome_fornecedor(f, fornecedores), "total": f["total"],
                          "tipo": _tipo_principal(f, por_tipo_decl), "alerta": alerta,
                          "ancora": pg.ancora_fornecedor(i, cnpj, ids)})
    soma_tipo = {}
    for fi in forn_info:
        soma_tipo[fi["tipo"]] = soma_tipo.get(fi["tipo"], 0) + fi["total"]
    tipos = sorted(soma_tipo, key=lambda t: (-soma_tipo[t], t))
    if len(tipos) > MAX_TIPOS:
        juntar = set(tipos[MAX_TIPOS - 1:])
        for fi in forn_info:
            if fi["tipo"] in juntar:
                fi["tipo"] = "Outros tipos"
        soma_tipo = {}
        for fi in forn_info:
            soma_tipo[fi["tipo"]] = soma_tipo.get(fi["tipo"], 0) + fi["total"]
        tipos = sorted((t for t in soma_tipo if t != "Outros tipos"), key=lambda t: (-soma_tipo[t], t)) + ["Outros tipos"]
    id_tipo = {t: f"t{j}" for j, t in enumerate(tipos)}
    for t in tipos:
        colunas[2].append({"id": id_tipo[t], "rotulo": t})
        fluxos.append({"de": "camp", "para": id_tipo[t], "valor": soma_tipo[t]})
    saida = sum(soma_tipo.values()) + pf_total + max(D - S, 0)
    # o que entrou e não saiu (recebido > contratado, ou origens que somam mais que o total): cinza, para fechar o fluxo
    sumidouros = [("t-pf", f"Pessoas físicas ({int(pf.get('qtd') or 0)} pagas)", pf_total, None),
                  ("t-outras", "Outras despesas declaradas", D - S, "muted"),
                  ("t-nao", "Ainda não gasto / não declarado", entrada - saida, "muted")]
    for k, rot, v, tom in sumidouros:
        if v > TOL:
            colunas[2].append({"id": k, "rotulo": rot, **({"tom": tom} if tom else {})})
            fluxos.append({"de": "camp", "para": k, "valor": v})

    # coluna 4: os maiores fornecedores e, por tipo, "Mais N fornecedores"
    top = sorted(forn_info, key=lambda f: (-f["total"], f["nome"]))[:MAX_FORN]
    top_i = {f["i"] for f in top}
    for t in tipos:
        do_tipo = sorted((f for f in top if f["tipo"] == t), key=lambda f: (-f["total"], f["nome"]))
        for fi in do_tipo:
            nid = f"f{fi['i']}"
            colunas[3].append({"id": nid, "rotulo": fi["nome"], "alerta": fi["alerta"],
                               **({"href": f"#f-{fi['ancora']}"} if fi["alerta"] else {})})
            fluxos.append({"de": id_tipo[t], "para": nid, "valor": fi["total"]})
        fora = [f for f in forn_info if f["tipo"] == t and f["i"] not in top_i]
        if fora:
            n = len(fora)
            colunas[3].append({"id": f"m{id_tipo[t]}", "rotulo": f"Mais {n} fornecedor{'es' if n > 1 else ''}",
                               "titulo": f"Mais {n} fornecedor{'es' if n > 1 else ''} ({t})"})
            fluxos.append({"de": id_tipo[t], "para": f"m{id_tipo[t]}", "valor": sum(f["total"] for f in fora)})

    # frase-resumo
    v_partido = sum(v for k, v in origem.items() if RE_PARTIDO.search(k))
    pct = f" ({round(100 * v_partido / R)}% do partido)" if R > 0 and v_partido > 0 else ""
    destinos = [f"{f['nome']} ({ind.brl(f['total'])})" for f in top[:3]]
    if destinos:
        alvo = "os 3 maiores destinos foram " if len(destinos) == 3 else ("os maiores destinos foram " if len(destinos) > 1 else "o maior destino foi ")
        fim = alvo + (", ".join(destinos[:-1]) + " e " + destinos[-1] if len(destinos) > 1 else destinos[0])
    else:
        fim = "nenhum fornecedor pessoa jurídica declarado"
    resumo = f"{ind.brl(R)} entraram{pct}; {fim}."
    return {"colunas": colunas, "fluxos": fluxos, "resumo": resumo, "campanha": campanha}


def diagrama_campanha(contas, fornecedores, indicadores, ids=None, nome=None):
    """HTML do bloco do diagrama: SVG + linha de limitação, ou a frase de prestação vazia (sem <svg>)."""
    d = fluxos_campanha(contas, fornecedores, indicadores, ids, nome)
    if not d:
        return f'<p class="rs-vazio">{SEM_DIAGRAMA}</p>'
    svg = sankey(d["colunas"], d["fluxos"], {"titulo": f"Caminho do dinheiro da campanha de {d['campanha']}", "resumo": d["resumo"]})
    return (f'<div class="rs-sankey">{svg}</div><p class="rs-nota">{esc(d["resumo"])}</p>'
            f'<p class="rs-nota">{LIMITACAO} {NOTA_TIPO}</p>')


# ---------- rede de fornecedores (2 colunas) ----------

XS2 = (380, 600)
CORTE2 = (62, 46)
MAX_REDE_ELEITOS = 20
SEM_REDE = "Nenhuma campanha na base para o diagrama."


def _plural(n, um, varios):
    return f"{n} {um if n == 1 else varios}"


def _rotulo_campanha(c):
    from rastro import paginas as pg  # tardio: paginas importa este módulo

    return f'{c["nome_urna"]} · {pg.CARGOS.get(c["cargo"], c["cargo"])} · {c["uf"]}'


def fluxos_fornecedor(cnpj, rotulo, campanhas, outras=None, max_campanhas=12, mei=False):
    """Campanhas → empresa. campanhas: [{nome_urna, cargo, uf, partido, total, href|None}] dos eleitos (href só nos
    publicados); `outras`: {n, valor} das campanhas não eleitas, que entram num nó cinza só agregado (nunca com nome nem
    link). Além de `max_campanhas`, as menores viram "Mais N campanhas". MEI (ou rotulo vazio): só o CNPJ mascarado.
    Devolve {colunas, fluxos, resumo, total} ou None sem valor nenhum."""
    rot_emp = ind.mascarar_cnpj(cnpj) if mei or not rotulo else rotulo
    camp = sorted((c for c in campanhas if (c.get("total") or 0) > 0), key=lambda c: (-c["total"], c["nome_urna"]))
    v_outras = float((outras or {}).get("valor") or 0)
    n_outras = int((outras or {}).get("n") or 0)
    total = sum(c["total"] for c in camp) + (v_outras if n_outras and v_outras > TOL else 0)
    if total <= 0:
        return None
    col0, fluxos = [], []
    for i, c in enumerate(camp[:max_campanhas]):
        r = _rotulo_campanha(c)
        col0.append({"id": f"c{i}", "rotulo": r, "titulo": f'{r} · {c["partido"]}', **({"href": c["href"]} if c.get("href") else {})})
        fluxos.append({"de": f"c{i}", "para": "emp", "valor": c["total"]})
    resto = camp[max_campanhas:]
    if resto:
        col0.append({"id": "c-mais", "rotulo": f"Mais {_plural(len(resto), 'campanha', 'campanhas')}"})
        fluxos.append({"de": "c-mais", "para": "emp", "valor": sum(c["total"] for c in resto)})
    if n_outras and v_outras > TOL:
        col0.append({"id": "c-outras", "rotulo": "Outra campanha (não eleita)" if n_outras == 1 else f"Outras {n_outras} campanhas (não eleitas)", "tom": "muted"})
        fluxos.append({"de": "c-outras", "para": "emp", "valor": v_outras})
    partidos = {c["partido"] for c in camp}
    ufs = {c["uf"] for c in camp}
    n_outras = n_outras if v_outras > TOL else 0
    onde = f"de {_plural(len(partidos), 'partido', 'partidos')} em {_plural(len(ufs), 'estado', 'estados')}"
    resumo = f"Recebeu {ind.brl(total)} de {_plural(len(camp) + n_outras, 'campanha', 'campanhas')}"
    if not n_outras:
        resumo += f" {onde}."
    elif not camp:
        resumo += " não eleitas." if n_outras > 1 else " não eleita."
    else:
        resumo += f": {len(camp)} de eleitos, {onde}, e {_plural(n_outras, 'não eleita', 'não eleitas')}."
    return {"colunas": [col0, [{"id": "emp", "rotulo": rot_emp}]], "fluxos": fluxos, "resumo": resumo, "total": total}


def diagrama_fornecedor(cnpj, rotulo, campanhas, outras=None, max_campanhas=12, mei=False):
    """HTML do bloco: SVG + linha-resumo, ou a frase de base vazia (sem <svg>)."""
    d = fluxos_fornecedor(cnpj, rotulo, campanhas, outras, max_campanhas, mei)
    if not d:
        return f'<p class="rs-vazio">{SEM_REDE}</p>'
    emp = d["colunas"][1][0]["rotulo"]
    svg = sankey(d["colunas"], d["fluxos"], {"id": "skf", "titulo": f"Campanhas que pagaram {emp}", "resumo": d["resumo"],
                                             "xs": XS2, "corte": CORTE2, "rotulo_acima": None})
    return f'<p class="rs-resumo">{esc(d["resumo"])}</p><div class="rs-sankey">{svg}</div>'


def fluxos_rede(empresas, eleitos_por_cnpj, max_eleitos=MAX_REDE_ELEITOS):
    """Eleitos → empresas. empresas: [{cnpj, rotulo, href}] (já mascaradas quando MEI); eleitos_por_cnpj: {cnpj: [{sq,
    nome_urna, uf, partido, total, href}]}. Cada eleito é um nó só, com uma faixa por empresa; além dos `max_eleitos` de
    maior valor, os demais viram "Mais N eleitos" por empresa."""
    soma = {}
    info = {}
    for e in empresas:
        for el in eleitos_por_cnpj.get(e["cnpj"]) or []:
            if (el.get("total") or 0) > 0:
                soma[el["sq"]] = soma.get(el["sq"], 0) + el["total"]
                info[el["sq"]] = el
    if not soma:
        return None
    ordem = sorted(soma, key=lambda s: (-soma[s], info[s]["nome_urna"], s))
    dentro = set(ordem[:max_eleitos])
    col0 = [{"id": f"e{s}", "rotulo": f'{info[s]["nome_urna"]} · {info[s]["uf"]}', "titulo": f'{info[s]["nome_urna"]} · {info[s]["uf"]} · {info[s]["partido"]}',
             **({"href": info[s]["href"]} if info[s].get("href") else {})} for s in ordem[:max_eleitos]]
    col1, fluxos, mais = [], [], []
    for j, e in enumerate(empresas):
        col1.append({"id": f"p{j}", "rotulo": e["rotulo"], **({"href": e["href"]} if e.get("href") else {})})
        fora = []
        for el in eleitos_por_cnpj.get(e["cnpj"]) or []:
            if (el.get("total") or 0) <= 0:
                continue
            if el["sq"] in dentro:
                fluxos.append({"de": f"e{el['sq']}", "para": f"p{j}", "valor": el["total"]})
            else:
                fora.append(el)
        if fora:
            mais.append({"id": f"m{j}", "rotulo": f"Mais {_plural(len(fora), 'eleito', 'eleitos')}", "titulo": f"Mais {_plural(len(fora), 'eleito', 'eleitos')} ({e['rotulo']})"})
            fluxos.append({"de": f"m{j}", "para": f"p{j}", "valor": sum(el["total"] for el in fora)})
    resumo = (f"{_plural(len(soma), 'eleito publicado pagou', 'eleitos publicados pagaram')} as "
              f"{_plural(len(empresas), 'empresa', 'empresas')} que atendem mais eleitos: {ind.brl(sum(soma.values()))}.")
    return {"colunas": [col0 + mais, col1], "fluxos": fluxos, "resumo": resumo}


def diagrama_rede(empresas, eleitos_por_cnpj, max_eleitos=MAX_REDE_ELEITOS):
    d = fluxos_rede(empresas, eleitos_por_cnpj, max_eleitos)
    if not d:
        return ""
    svg = sankey(d["colunas"], d["fluxos"], {"id": "skr", "titulo": "Eleitos publicados e as empresas que atendem mais eleitos",
                                             "resumo": d["resumo"], "xs": XS2, "corte": CORTE2, "rotulo_acima": None})
    return (f'<div class="rs-sankey rs-rede">{svg}</div><p class="rs-nota rs-rede">{esc(d["resumo"])}</p>'
            '<p class="rs-nota rs-so-cel">O diagrama da rede aparece em telas maiores; no celular, veja a tabela acima.</p>')
