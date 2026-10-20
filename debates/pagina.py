"""Página de checagem de um debate (/debates/<emissora>-<turno>-turno/), a partir de debates/<id>/afirmacoes.json e
checagens.json. Função pura, sem rede e sem Chrome, no padrão de rastro/paginas.py: devolve o HTML do conteúdo (a moldura
e a medição entram pelo build_site), o JSON-LD (ClaimReview por checagem, Article e BreadcrumbList) e o resto do que o
build publica. Todo texto sobre o debate vem dos JSON; aqui só ficam os rótulos da moldura.
Cores: só as de partido do brand.css (o ciano é da moldura). Placar neutro: contagem de vereditos, sem nota nem "quem ganhou".
"""
import html
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import brand

CORES = {"flavio", "lula", "outros"}  # variáveis de partido do brand.css
ORDEM_TEMAS = ["seguranca", "economia", "saude", "social", "corrupcao", "internacional"]  # o resto vai no fim
RE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def esc(t):
    return html.escape(str(t), quote=False)


def attr(t):
    return html.escape(str(t), quote=True)


def slug(t):
    s = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def data_br(iso):
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def ler(pasta):
    """(afirmacoes, checagens) da pasta do debate, ou None se algum dos dois ainda não existe."""
    pasta = Path(pasta)
    arqs = [pasta / "afirmacoes.json", pasta / "checagens.json"]
    if not all(a.exists() for a in arqs):
        return None
    return tuple(json.loads(a.read_text(encoding="utf-8")) for a in arqs)


def _exigir(obj, campos, onde):
    for c in campos:
        if obj.get(c) in (None, "", []):
            raise ValueError(f"{onde}: falta o campo {c!r}")


def validar(afs, chs):
    """Levanta ValueError com o id e o campo do primeiro problema (nada é publicado pela metade)."""
    deb = afs.get("debate") or {}
    _exigir(deb, ["emissora", "data", "turno", "candidatos"], "afirmacoes.json/debate")
    date.fromisoformat(deb["data"])
    cands = {}
    for c in deb["candidatos"]:
        _exigir(c, ["id", "nome", "partido", "cor"], f"candidato {c.get('id')!r}")
        if c["cor"] not in CORES:
            raise ValueError(f"candidato {c['id']!r}: cor {c['cor']!r} não é cor de partido ({', '.join(sorted(CORES))})")
        cands[c["id"]] = c
    por_id = {}
    for a in afs.get("afirmacoes") or []:
        _exigir(a, ["id", "candidato", "tema", "timestamp", "trecho"], f"afirmação {a.get('id')!r}")
        if not RE_ID.match(a["id"]):
            raise ValueError(f"afirmação {a['id']!r}: id precisa ser [a-z0-9-] (vira âncora)")
        if a["candidato"] not in cands:
            raise ValueError(f"afirmação {a['id']!r}: candidato {a['candidato']!r} não está em debate.candidatos")
        por_id[a["id"]] = a
    if not chs.get("checagens"):
        raise ValueError("checagens.json: lista 'checagens' vazia")
    vistos = set()
    for c in chs["checagens"]:
        _exigir(c, ["id", "veredito", "explicacao", "fontes"], f"checagem {c.get('id')!r}")
        if c["id"] not in por_id:
            raise ValueError(f"checagem {c['id']!r}: não há afirmação com esse id")
        if c["id"] in vistos:
            raise ValueError(f"checagem {c['id']!r}: repetida")
        vistos.add(c["id"])
        for f in c["fontes"]:
            if not isinstance(f, dict) or not re.match(r"^https?://", f.get("url") or ""):
                raise ValueError(f"checagem {c['id']!r}: fonte sem url http(s): {f!r}")
    if chs.get("vereditos"):
        fora = {c["veredito"] for c in chs["checagens"]} - set(chs["vereditos"])
        if fora:
            raise ValueError(f"checagens.json: veredito fora da lista 'vereditos': {sorted(fora)}")
    return deb, cands, por_id


def _rank_tema(s):
    return next((i for i, t in enumerate(ORDEM_TEMAS) if s == t or s.startswith(t + "-")), len(ORDEM_TEMAS))


CSS = """<style>
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--font-sans)}
main.db{max-width:880px;margin:0 auto;padding:24px 18px 56px}
.db a{color:var(--ink);text-decoration-color:var(--muted);text-underline-offset:3px}
.db-crumbs{font-size:13px;color:var(--muted);margin:0 0 14px}
.db-kicker{font:600 12px var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.db h1{font-size:clamp(26px,5vw,38px);line-height:1.15;margin:0 0 10px}
.db h2{font-size:20px;margin:34px 0 10px;padding-top:6px;border-top:1px solid var(--line)}
.db-lead{color:var(--ink2);margin:0}
.db-nota{font-size:13px;color:var(--ink2);margin:6px 0 10px}
.db-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.db-placar{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:15px}
.db-placar th,.db-placar td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.db-placar th:first-child{text-align:left;border-left:4px solid var(--c,transparent);padding-left:10px}
.db-placar thead th{font:600 12px var(--font-mono);color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.db-placar td:last-child{font-weight:600}
.db-filtro{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:24px 0 0;font-size:14px}
.db-filtro[hidden]{display:none}
.db-filtro select{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 8px;margin-left:6px}
.db-filtro output{color:var(--muted)}
.db-lista{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.db-af{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:12px 14px;overflow-wrap:anywhere}
.db-af[hidden],.db-tema[hidden]{display:none}
.db-af:target{background:var(--soft)}
.db-af-t{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;font:600 13px var(--font-mono)}
.db-af-t .db-tempo{color:var(--muted);font-weight:400}
.db-af blockquote{margin:8px 0;font-size:17px;line-height:1.45}
.db-selo{display:inline-block;font:600 12px var(--font-mono);text-transform:uppercase;letter-spacing:.04em;border:1px solid var(--ink2);border-radius:999px;padding:1px 9px}
.db-af p{margin:8px 0 0;font-size:15px;color:var(--ink2)}
.db-outro{border-top:1px dashed var(--line);padding-top:6px}
.db-fontes{font-size:14px}
.db-link{display:inline-block;margin-top:8px;font-size:12px;color:var(--muted)}
.db-cta p{margin:6px 0;font-size:17px}
@media (max-width:760px){.db-lista{grid-template-columns:1fr}}
</style>"""


def gerar(afs, chs, base, autor):
    """dict com path, titulo, desc, html (conteúdo, sem moldura), ld, publicado, modificado, og e llms."""
    deb, cands, por_id = validar(afs, chs)
    emissora, turno, dia = deb["emissora"], deb["turno"], data_br(deb["data"])
    path = f"/debates/{slug(emissora)}-{turno}-turno/"
    url = base + path
    publicado = chs.get("publicado") or deb["data"] + "T23:59:00-03:00"
    modificado = chs.get("atualizado") or publicado
    checagens = chs["checagens"]
    vereditos = chs.get("vereditos") or list(dict.fromkeys(c["veredito"] for c in checagens))
    n = len(checagens)
    nomes = " e ".join(f'{c["nome"]} ({c["partido"]})' for c in cands.values())
    titulo = f"Checagem do debate da {emissora} ({turno}º turno, {dia}): {n} afirmações"
    desc = (f"As {n} afirmações checadas do debate entre {nomes} na {emissora}, em {dia}: "
            f"trecho, veredito, explicação e fontes de cada uma.")

    # placar: contagem simples por candidato × veredito
    conta = {(cid, v): 0 for cid in cands for v in vereditos}
    for c in checagens:
        conta[(por_id[c["id"]]["candidato"], c["veredito"])] += 1
    cab = "".join(f"<th scope=col>{esc(v)}</th>" for v in vereditos)
    linhas = "".join(
        f'<tr data-candidato="{attr(cid)}"><th scope=row style="--c:var(--{c["cor"]})">{esc(c["nome"])} ({esc(c["partido"])})</th>'
        + "".join(f"<td>{conta[(cid, v)]}</td>" for v in vereditos)
        + f"<td>{sum(conta[(cid, v)] for v in vereditos)}</td></tr>"
        for cid, c in cands.items())
    placar = (f'<section aria-labelledby="placar"><h2 id="placar">Vereditos por candidato</h2>'
              f'<p class="db-nota">Contagem das afirmações checadas de cada candidato. Não é nota do debate: '
              f'a seleção cobre só frases verificáveis com dado público.</p>'
              f'<div class="db-scroll"><table class="db-placar"><thead><tr><th scope=col>Candidato</th>{cab}<th scope=col>Total</th></tr></thead>'
              f'<tbody>{linhas}</tbody></table></div></section>')

    filtro = ('<form class="db-filtro" aria-label="Filtrar afirmações" hidden>'
              '<label>Candidato<select name="candidato"><option value="">Todos</option>'
              + "".join(f'<option value="{attr(cid)}">{esc(c["nome"])}</option>' for cid, c in cands.items())
              + '</select></label><label>Veredito<select name="veredito"><option value="">Todos</option>'
              + "".join(f'<option value="{attr(slug(v))}">{esc(v)}</option>' for v in vereditos)
              + f'</select></label><output aria-live="polite">{n} de {n} afirmações</output></form>')

    def cartao(c):
        a = por_id[c["id"]]; cd = cands[a["candidato"]]
        fontes = ", ".join(f'<a href="{attr(f["url"])}" rel="noopener">{esc(f.get("titulo") or f["url"])}</a>' for f in c["fontes"])
        outro = f'<p class="db-outro"><b>Outro lado:</b> {esc(c["outro_lado"])}</p>' if c.get("outro_lado") else ""
        return (f'<article class="db-af" id="{a["id"]}" data-candidato="{attr(a["candidato"])}" data-veredito="{slug(c["veredito"])}" '
                f'style="--c:var(--{cd["cor"]})"><div class="db-af-t"><span>{esc(cd["nome"])} ({esc(cd["partido"])})</span>'
                f'<span class="db-tempo">{esc(a["timestamp"])}</span></div>'
                f'<blockquote>“{esc(a["trecho"])}”</blockquote><span class="db-selo">{esc(c["veredito"])}</span>'
                f'<p>{esc(c["explicacao"])}</p>{outro}<p class="db-fontes">Fontes: {fontes}</p>'
                f'<a class="db-link" href="#{a["id"]}">Link desta checagem</a></article>')

    grupos = {}
    for c in checagens:
        tema = por_id[c["id"]]["tema"]
        grupos.setdefault(slug(tema), (tema, []))[1].append(c)
    ordem = sorted(grupos, key=lambda s: (_rank_tema(s), list(grupos).index(s)))
    temas = "".join(f'<section class="db-tema" id="tema-{s}"><h2>{esc(grupos[s][0])}</h2>'
                    f'<div class="db-lista">{"".join(cartao(c) for c in grupos[s][1])}</div></section>' for s in ordem)

    metodo = f'<p>{esc(chs["metodo"])}</p>' if chs.get("metodo") else ""
    transc = (f'<p><a href="{attr(deb["transcricao"])}" rel="noopener">Transcrição integral do debate</a></p>'
              if re.match(r"^https?://", deb.get("transcricao") or "") else "")
    como = f'<section aria-labelledby="metodo"><h2 id="metodo">Como checamos</h2>{metodo}{transc}</section>' if metodo or transc else ""

    corpo = (f'<nav class="db-crumbs" aria-label="Trilha"><a href="/">Início</a> › Debate {esc(emissora)} ({turno}º turno)</nav>'
             f'<p class="db-kicker">Checagem · {turno}º turno · {dia}</p>'
             f'<h1>Checagem do debate da {esc(emissora)}</h1>'
             f'<p class="db-lead">Debate entre {esc(nomes)} na {esc(emissora)}, em {dia}. '
             f'Checamos {n} afirmações: cada uma tem o trecho, o veredito, a explicação e as fontes.</p>'
             f'{placar}{filtro}{temas}'
             f'<section class="db-cta" aria-labelledby="depois"><h2 id="depois">A eleição</h2>'
             f'<p><a href="/ao-vivo/">Apuração do 2º turno ao vivo, por município →</a></p>'
             f'<p><a href="/">Resultado do 1º turno →</a></p></section>{como}')
    pagina = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
              f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(titulo)}</title>'
              f'<style>{brand.CSS}</style>{CSS}<script defer src="/debates/debate.js"></script></head>'
              f'<body><main id="conteudo" class="db">{corpo}</main></body></html>')

    og = f"debate-{slug(emissora)}"
    aparicao = {"@type": "CreativeWork", "name": f"Debate da {emissora}, {dia}", "url": deb.get("transcricao") or url}
    ld = [{"@context": "https://schema.org", "@type": "ClaimReview", "url": f"{url}#{c['id']}",
           "claimReviewed": por_id[c["id"]]["trecho"], "datePublished": publicado, "author": autor, "inLanguage": "pt-BR",
           "itemReviewed": {"@type": "Claim", "author": {"@type": "Person", "name": cands[por_id[c["id"]]["candidato"]]["nome"]},
                            "datePublished": deb["data"], "appearance": aparicao},
           "reviewRating": {"@type": "Rating", "alternateName": c["veredito"]}} for c in checagens]
    ld += [{"@context": "https://schema.org", "@type": "Article", "headline": titulo[:110], "description": desc, "inLanguage": "pt-BR",
            "datePublished": publicado, "dateModified": modificado, "author": autor, "publisher": autor,
            "image": [f"{base}/og/{og}.png"], "mainEntityOfPage": url},
           {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
               {"@type": "ListItem", "position": 1, "name": "Início", "item": base + "/"},
               {"@type": "ListItem", "position": 2, "name": f"Debate {emissora} ({turno}º turno)", "item": url}]}]

    por_cand = [(c["nome"], c["partido"], c["cor"], sum(conta[(cid, v)] for v in vereditos)) for cid, c in cands.items()]
    llms = (f"- [Checagem do debate da {emissora} ({turno}º turno, {dia})]({url}): {n} afirmações de {nomes}, "
            f"com veredito, explicação e fontes\n")
    return dict(path=path, titulo=titulo, desc=desc, html=pagina, ld=ld, publicado=publicado, modificado=modificado,
                og=(og, f"Checagem do debate da {emissora}", f"{turno}º turno · {dia}", por_cand, f"{n} afirmações checadas"),
                llms=llms, rotulo=f"Debate {emissora}")
