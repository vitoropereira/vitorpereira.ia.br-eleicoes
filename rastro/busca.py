"""Índice estático da busca do Rastro (site/rastro/busca.json), lido por rastro/busca.js só quando o campo ganha foco.

Entram: eleitos (publicados com link para a página; os ainda sem página com âncora na tabela da home), empresas PJ não MEI com
página e os sócios delas (só o nome, ligado à empresa). Ficam fora, por LGPD: MEI e fornecedor sem cadastro (o nome pode ser o
da pessoa e o CNPJ não pode aparecer), sócio de MEI, CPF e cpf_mascarado, pessoa física paga e doador PF (que nem chegam aqui).

Chaves curtas: t (e = eleito, f = empresa, s = sócio), n (nome exibido), c (contexto), u (URL), k (texto normalizado para a
busca; na empresa, também os 14 dígitos do CNPJ) e p (eleito: 1 publicado, 0 ainda sem página).
"""
import json
import re
import unicodedata

from rastro import indicadores as ind

LIMITE = 1_500_000  # bytes; acima disso o índice é dividido em partes com um manifesto
RE_DIACRITICO = re.compile(r"[\u0300-\u036f]")


def normalizar(t):
    """Mesmos passos de `normalizar` em busca.js: NFD, sem diacríticos, minúsculas, espaços juntos."""
    t = RE_DIACRITICO.sub("", unicodedata.normalize("NFD", str(t or "")))
    return re.sub(r"\s+", " ", t.lower()).strip()


def ancora_eleito(sq):
    """Âncora da linha do eleito na home ('e-' + sq em hexadecimal): o sq cru tem 11 ou 12 dígitos e às vezes passa no
    dígito verificador de CPF; em hexadecimal nunca há 11 dígitos seguidos."""
    sq = str(sq)
    return "e-" + (format(int(sq), "x") if sq.isdigit() else re.sub(r"[^a-z0-9]+", "-", sq.lower()))


def _plural(n, s, p):
    return f"{n} {s if n == 1 else p}"


def indice(entradas, pendentes, agg, rotulo_cargo, parcial):
    """entradas/pendentes/agg: as estruturas de `paginas.gerar` (agg já com id e rótulo). rotulo_cargo(eleito) e parcial(contas)
    vêm de paginas, para o contexto ser o mesmo da home. Devolve a lista de itens, ordenada."""
    itens = []
    for e in entradas:
        el = e["eleito"]
        c = rotulo_cargo(el) + (f" · {_plural(len(e['itens']), 'indicador', 'indicadores')}" if parcial(e["contas"]) else "")
        itens.append({"t": "e", "n": el["nome_urna"], "c": c, "u": "/" + e["caminho"], "k": normalizar(el["nome_urna"]), "p": 1})
    for e in pendentes:
        el = e["eleito"]
        c = rotulo_cargo(el) + f" · {_plural(len(e['itens']), 'indicador', 'indicadores')}"
        itens.append({"t": "e", "n": el["nome_urna"], "c": c, "u": f"/rastro/#{ancora_eleito(el['sq'])}", "k": normalizar(el["nome_urna"]), "p": 0})
    for a in agg.values():
        if a["mei"]:
            continue  # MEI e sem cadastro: o nome pode ser o da pessoa e o CNPJ não pode aparecer
        u = f"/rastro/fornecedor/{a['id']}/"
        nomes = dict.fromkeys(n for n in [a["rotulo"]] + [c.get("nome") for c in a["campanhas"]] if n)
        n_camp = len(a["campanhas"])
        total = sum(c["total"] for c in a["campanhas"])
        itens.append({"t": "f", "n": a["rotulo"], "c": f"recebeu {ind.brl(total)} de {_plural(n_camp, 'campanha', 'campanhas')}",
                      "u": u, "k": normalizar(" ".join(nomes)) + " " + a["cnpj"]})
        for s in sorted({s["nome"] for s in (a["rec"] or {}).get("socios") or [] if s.get("nome")}):
            itens.append({"t": "s", "n": s, "c": f"sócio(a) de {a['rotulo']}", "u": u, "k": normalizar(s)})
    ordem = {"e": 0, "f": 1, "s": 2}
    itens.sort(key=lambda i: (ordem[i["t"]], i["k"], i["u"]))
    return itens


def serializar(itens, limite=LIMITE):
    """{nome do arquivo: texto}. Cabendo no limite, só busca.json ({"itens": [...]}); senão, partes busca-1.json… e busca.json
    vira o manifesto ({"partes": [...]}), que busca.js lê inteiro (a busca é por trecho, não por letra inicial)."""
    def dump(o):
        return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

    texto = dump({"itens": itens})
    if len(texto.encode("utf-8")) <= limite or len(itens) < 2:
        return {"busca.json": texto}
    partes, atual, tam = [], [], 0
    for i in itens:
        t = len(dump(i).encode("utf-8")) + 1
        if atual and tam + t > limite:
            partes.append(atual)
            atual, tam = [], 0
        atual.append(i)
        tam += t
    partes.append(atual)
    out = {f"busca-{n}.json": dump({"itens": p}) for n, p in enumerate(partes, 1)}
    out["busca.json"] = dump({"partes": [f"/rastro/{nome}" for nome in out]})
    return out
