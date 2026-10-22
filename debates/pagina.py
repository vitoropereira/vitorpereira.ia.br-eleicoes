"""Seção /debates/: uma página por debate, uma por afirmação checada, a transcrição e o índice com o placar acumulado.
Lê debates/<ano>/<slug>/ (debate.json, afirmacoes.json, transcricao.md e checagens.json; formato em debates/README.md)
e valida com debates/validar.py. Funções puras, sem rede e sem Chrome, no padrão de rastro/paginas.py: devolvem o HTML
do conteúdo (a moldura e a medição entram pelo build_site), o JSON-LD e o resto do que o build publica. Todo texto sobre
um debate vem dos JSON; aqui só ficam os rótulos e o "como checamos", iguais para todos.
Só entra afirmação de autoria `certa`. Cores: só as de partido do brand.css (o ciano é da moldura). Placar neutro:
contagem de vereditos, sem nota nem "quem ganhou".
"""
import html
import json
import re
from datetime import date
from pathlib import Path

import brand
from debates import validar as V

ROTULOS = {"verdadeiro": "Verdadeiro", "falso-ou-exagerado": "Falso ou exagerado", "nao-comprovado": "Não comprovado",
           "pendente-ou-condicionado": "Pendente ou condicionado", "situacao-identificada": "Situação identificada"}
ORDEM_VEREDITOS = list(V.VEREDITO)
TEMAS = {"seguranca": "Segurança", "economia": "Economia", "social": "Social", "saude": "Saúde",
         "internacional": "Internacional", "corrupcao-acusacoes": "Corrupção e acusações", "outros": "Outros"}
DEFINICOES = {"verdadeiro": "a afirmação central se confirma nas fontes",
              "falso-ou-exagerado": "é desmentida pelas fontes, ou o número central foi inflado",
              "nao-comprovado": "não há evidência pública que confirme nem desminta, ou é acusação sem registro",
              "pendente-ou-condicionado": "promessa que ainda não existe e depende de Congresso, custo ou detalhe",
              "situacao-identificada": "a promessa já existe, ou a acusação tem investigação, denúncia ou condenação"}
# placar em três blocos (21/10/2026): promessa nunca é "verdadeira", então somar tudo junto distorcia a comparação
GRUPOS = {"fatos": ("Fatos e dados", ("dado", "fato")), "promessas": ("Promessas", ("promessa",)),
          "acusacoes": ("Acusações", ("acusacao",))}
GRUPO_DO_TIPO = {t: g for g, (_, tipos) in GRUPOS.items() for t in tipos}
# a ordem de exibição é a do placar; a de desempate é validar.ETIQUETAS
ETIQUETAS = {"ataque-critica": "Ataques e críticas", "proposta": "Propostas", "apelo": "Apelo pessoal ou emocional",
             "dado": "Dados e evidências"}
MEDIACAO = {"id": V.MEDIACAO, "nome_urna": "Mediação", "partido": "", "cor": "outros"}


def esc(t):
    return html.escape(str(t), quote=False)


def attr(t):
    return html.escape(str(t), quote=True)


def data_br(iso):
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def ancora(ts):
    """Âncora da marcação H:MM:SS (ou M:SS) na página da transcrição: t-H-MM-SS."""
    p = [int(x) for x in ts.split(":")]
    h, m, s = ([0] + p)[-3:]
    return f"t-{h}-{m:02d}-{s:02d}"


def no_video(url, ts):
    """URL do vídeo (debate.json `video`) aberta no segundo da marcação H:MM:SS (ou M:SS)."""
    p = [int(x) for x in ts.split(":")]
    h, m, s = ([0] + p)[-3:]
    return f'{url}{"&" if "?" in url else "?"}t={h * 3600 + m * 60 + s}s'


def _json(p):
    return json.loads(p.read_text(encoding="utf-8"))


def carregar(pasta):
    """Modelo de um debate, ou None se ainda não há checagens.json. Erro de dado levanta ValueError com id e campo
    (nada é publicado pela metade). Checagem de afirmação que não é `certa` fica de fora do modelo."""
    pasta = Path(pasta)
    if not (pasta / "checagens.json").exists():
        return None
    try:
        debate, itens, chs = (_json(pasta / f) for f in ("debate.json", "afirmacoes.json", "checagens.json"))
        transcricao = (pasta / "transcricao.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        raise ValueError(f"{pasta}: {e}") from e
    erros = V.validar_debate(debate) + V.validar_pasta(pasta, debate) + V.validar(itens, transcricao, debate)
    if not erros:
        certas = {i["id"]: i for i in itens if i["autoria"] == "certa"}
        chs = [c for c in chs if not isinstance(c, dict) or c.get("id") in certas] if isinstance(chs, list) else chs
        erros = V.validar_checagens(chs, itens)
        # a mediação não entra na checagem publicada (decisão do Vitor, 21/10/2026); o dado fica no arquivo
        chs = [c for c in chs if certas[c["id"]]["quem"] != V.MEDIACAO] if not erros else chs
    retorica = None
    if not erros and (pasta / "retorica.json").exists():
        try:
            retorica = _json(pasta / "retorica.json")
        except (OSError, ValueError) as e:
            raise ValueError(f"{pasta}: {e}") from e
        erros = V.validar_retorica(retorica, transcricao, debate)
    if erros:
        raise ValueError(f"{pasta}: " + "; ".join(erros))
    cands = {c["id"]: {**c, "cor": c.get("cor", "outros")} for c in debate["candidatos"]}
    cands[V.MEDIACAO] = MEDIACAO
    return dict(debate=debate, cands=cands, itens=certas, checagens=chs, transcricao=transcricao, retorica=retorica,
                path=f"/debates/{debate['ano']}/{debate['slug']}/")


def listar(raiz):
    """Modelos de todos os debates com checagem em raiz/<ano>/<slug>/, do mais novo para o mais antigo."""
    ms = [m for m in (carregar(p.parent) for p in sorted(Path(raiz).glob("*/*/debate.json"))) if m]
    return sorted(ms, key=lambda m: (m["debate"]["data"], m["path"]), reverse=True)


def _ordenar(conta):
    """{grupo: {veredito: n}} na ordem de GRUPOS e de ORDEM_VEREDITOS, sem grupo vazio."""
    return {g: {v: conta[g][v] for v in ORDEM_VEREDITOS if v in conta[g]} for g in GRUPOS if g in conta}


def total(conta):
    return sum(sum(c.values()) for c in conta.values())


def placar(m):
    """{quem: {grupo: {veredito: n}}} sobre todas as checagens do debate. Em cada grupo entram os vereditos que
    aparecem nele no debate, zero incluído, para os blocos dos candidatos ficarem comparáveis."""
    usados = {}
    for c in m["checagens"]:
        usados.setdefault(GRUPO_DO_TIPO[m["itens"][c["id"]]["tipo"]], set()).add(c["veredito"])
    quem = [q for q in m["cands"] if any(m["itens"][c["id"]]["quem"] == q for c in m["checagens"])]
    conta = {q: _ordenar({g: dict.fromkeys(vs, 0) for g, vs in usados.items()}) for q in quem}
    for c in m["checagens"]:
        it = m["itens"][c["id"]]
        conta[it["quem"]][GRUPO_DO_TIPO[it["tipo"]]][c["veredito"]] += 1
    return conta


def pct(n, total):
    return round(100 * n / total) if total else 0


def placar_retorica(m):
    """{quem: {etiqueta: n}} sobre o retorica.json (as 6 etiquetas, zero incluído; candidato sem frase fica de fora)."""
    conta = {q: dict.fromkeys(ETIQUETAS, 0) for q in m["cands"] if any(r["quem"] == q for r in m["retorica"] or [])}
    for r in m["retorica"] or []:
        conta[r["quem"]][r["etiqueta"]] += 1
    return conta


def pct_100(conta):
    """{chave: %} inteiros que somam exatamente 100 (maior resto; empate vai para a chave que vem antes)."""
    total = sum(conta.values())
    if not total:
        return dict.fromkeys(conta, 0)
    base = {k: 100 * n // total for k, n in conta.items()}
    resto = sorted(conta, key=lambda k: -(100 * conta[k] % total))
    for k in resto[:100 - sum(base.values())]:
        base[k] += 1
    return base


def placar_por_candidato(modelos):
    """{id_tse: {nome_urna, partido, cor, conta: {grupo: {veredito: n}}, debates: [{rotulo, path, afirmacoes: [{path, afirmacao,
    veredito, timestamp, tema}]}]}} somando todos os debates (modelos de `listar`, do mais novo para o mais antigo). Só candidato com
    `id_tse`; a mediação fica de fora. Nome, partido e cor ficam os do debate mais novo."""
    out = {}
    for m in modelos:
        deb = m["debate"]
        rotulo = f"Debate {deb['emissora']} {deb['turno']}º turno {deb['ano']}"
        for q, c in m["cands"].items():
            if q == V.MEDIACAO or not c.get("id_tse"):
                continue
            chs = [ch for ch in m["checagens"] if m["itens"][ch["id"]]["quem"] == q]
            if not chs:
                continue
            p = out.setdefault(str(c["id_tse"]), {"nome_urna": c["nome_urna"], "partido": c["partido"], "cor": c["cor"],
                                                  "conta": {}, "debates": []})
            for ch in chs:
                g = p["conta"].setdefault(GRUPO_DO_TIPO[m["itens"][ch["id"]]["tipo"]], {})
                g[ch["veredito"]] = g.get(ch["veredito"], 0) + 1
            p["debates"].append({"rotulo": rotulo, "path": m["path"], "afirmacoes": [
                {"path": f"{m['path']}{ch['id']}/", "afirmacao": m["itens"][ch["id"]]["afirmacao"], "veredito": ch["veredito"],
                 "timestamp": m["itens"][ch["id"]]["timestamp"], "tema": m["itens"][ch["id"]]["tema"]}
                for ch in chs]})
    for p in out.values():
        p["conta"] = _ordenar(p["conta"])
    return out


CSS_PLACAR = """.db-placar{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.db-pc{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--c);border-radius:10px;padding:10px 14px}
.db-pc h3{margin:0 0 6px;font-size:16px}
.db-pc ul{list-style:none;margin:0;padding:0}
.db-pc li{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding:4px 0;font-size:14px;font-variant-numeric:tabular-nums}
.db-pc li:last-child{border-bottom:0}
.db-pc h4{display:flex;justify-content:space-between;gap:12px;margin:10px 0 2px;font:600 12px var(--font-mono);letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.db-pc h4:first-of-type{margin-top:0}
.db-pc .db-tot{border-top:1px solid var(--line);margin-top:6px;font-weight:600}
.db-pc .db-bar{display:block;border-bottom:1px solid var(--line)}
.db-pc .db-bar b{font-size:16px}.db-pc .db-bar small{font-size:12px;color:var(--muted);margin-left:4px}
.db-bar span{display:flex;justify-content:space-between;gap:12px}
.db-bar i{display:block;height:8px;margin:3px 0 2px;border-radius:4px;background:var(--c);min-width:1px}
"""

CSS = """<style>
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--font-sans)}
main.db{max-width:880px;margin:0 auto;padding:24px 18px 56px}
.db a{color:var(--ink);text-decoration-color:var(--muted);text-underline-offset:3px}
.db-crumbs{font-size:13px;color:var(--muted);margin:0 0 14px;overflow-wrap:anywhere}
.db-kicker{font:600 12px var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.db h1{font-size:clamp(24px,5vw,36px);line-height:1.2;margin:0 0 10px;overflow-wrap:anywhere}
.db h2{font-size:20px;margin:34px 0 10px;padding-top:6px;border-top:1px solid var(--line)}
.db-lead{color:var(--ink2);margin:0}
.db-nota{font-size:13px;color:var(--ink2);margin:6px 0 10px}
""" + CSS_PLACAR + """.db-filtro{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:24px 0 0;font-size:14px}
.db-filtro[hidden],.db-rt-filtro[hidden],.db-rt li[hidden]{display:none}
.db-rt-filtro{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:16px 0 0;font-size:14px}
.db-rt-filtro select,.db-filtro select{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 8px;margin-left:6px;max-width:100%}
.db-filtro output,.db-rt-filtro output{color:var(--muted)}
.db-rt{list-style:none;margin:12px 0 0;padding:0;max-height:70vh;overflow-y:auto;border:1px solid var(--line);border-radius:10px}
.db-rt li{border-left:4px solid var(--c);border-bottom:1px solid var(--line);padding:8px 12px;overflow-wrap:anywhere}
.db-rt li:last-child{border-bottom:0}
.db-rt-t{display:flex;flex-wrap:wrap;gap:4px 12px;font:600 13px var(--font-mono)}
.db-rt-t .db-tempo{color:var(--muted);font-weight:400}.db-rt-t .db-tempo a{color:inherit}
.db-rt q{display:block;margin:4px 0 0;font-size:15px;color:var(--ink2)}
.db-lista{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.db-af{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:12px 14px;overflow-wrap:anywhere}
.db-af[hidden],.db-tema[hidden]{display:none}
.db-af:target{background:var(--soft)}
.db-af-t{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;font:600 13px var(--font-mono)}
.db-af-t .db-tempo{color:var(--muted);font-weight:400}.db-af-t .db-tempo a{color:inherit}
.db-af .db-frase{margin:8px 0 0;font-size:17px;line-height:1.45;color:var(--ink);font-weight:600}
.db-af blockquote{margin:6px 0 8px;font-size:14px;color:var(--ink2);border-left:2px solid var(--line);padding-left:10px}
.db-selo{display:inline-block;font:600 12px var(--font-mono);text-transform:uppercase;letter-spacing:.04em;border:1px solid var(--ink2);border-radius:999px;padding:1px 9px}
.db-af p{margin:8px 0 0;font-size:15px;color:var(--ink2)}
.db-outro{border-top:1px dashed var(--line);padding-top:6px}
.db-fontes{font-size:14px}
.db-link{display:inline-block;margin-top:8px;font-size:13px;color:var(--muted)}
.db-cta p{margin:6px 0;font-size:17px}
.db-deb{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 10px;text-decoration:none}
.db-deb b{display:block;font-size:17px}.db-deb span{color:var(--ink2);font-size:14px}
.db-tr p{margin:6px 0}.db-tr p:target{background:var(--soft)}.db-tr b{font:600 13px var(--font-mono);color:var(--muted)}
@media (max-width:760px){.db-lista{grid-template-columns:1fr}}
</style>"""


def _doc(titulo, corpo, js=False):
    script = '<script defer src="/debates/debate.js"></script>' if js else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(titulo)}</title>'
            f'<style>{brand.CSS}</style>{CSS}{script}</head>'
            f'<body><main id="conteudo" class="db">{corpo}</main></body></html>')


def _trilha(itens):
    """[(nome, path ou None)] → HTML da trilha (o último sem link)."""
    return ('<nav class="db-crumbs" aria-label="Trilha">'
            + " › ".join(f'<a href="{attr(h)}">{esc(n)}</a>' if h else esc(n) for n, h in itens) + "</nav>")


def _breadcrumb(base, itens):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": base + h} for i, (n, h) in enumerate(itens, 1)]}


def _nome(c):
    return f'{c["nome_urna"]} ({c["partido"]})' if c["partido"] else c["nome_urna"]


def _placar_html(linhas, id_titulo, titulo, nota, links=None):
    """linhas: [(nome, cor, {grupo: {veredito: n}})] em blocos verticais (cabe em 360 px), um sub-bloco por grupo com o
    percentual dentro do grupo. links: {nome: href} põe o link no título do bloco de quem tem página."""
    def h3(nome):
        href = (links or {}).get(nome)
        return f'<a href="{attr(href)}">{esc(nome)}</a>' if href else esc(nome)

    def grupo(g, c):
        n_g = sum(c.values())
        return (f'<h4><span>{esc(GRUPOS[g][0])}</span><span>{n_g}</span></h4><ul>'
                + "".join(f"<li><span>{esc(ROTULOS[v])}</span><span>{n} ({pct(n, n_g)}%)</span></li>" for v, n in c.items())
                + "</ul>")
    blocos = "".join(
        f'<div class="db-pc" style="--c:var(--{cor})"><h3>{h3(nome)}</h3>'
        + "".join(grupo(g, c) for g, c in conta.items() if sum(c.values()))
        + f'<ul class="db-tot"><li><span>Total</span><span>{total(conta)}</span></li></ul></div>'
        for nome, cor, conta in linhas)
    return (f'<section aria-labelledby="{id_titulo}"><h2 id="{id_titulo}">{esc(titulo)}</h2>'
            f'<p class="db-nota">{esc(nota)}</p><div class="db-placar">{blocos}</div></section>')


def _barras_retorica(linhas):
    """linhas: [(nome, cor, {etiqueta: n})] → um bloco vertical por candidato, uma barra por etiqueta (cabe em 360 px)."""
    def bloco(nome, cor, conta):
        p = pct_100(conta)
        # o percentual vem na frente: quem fala mais frases tem contagem maior em tudo, e a comparação é pela parte
        barras = "".join(f'<li class="db-bar"><span><span>{esc(ETIQUETAS[e])}</span>'
                         f'<span><b>{p[e]}%</b> <small>{n}</small></span></span>'
                         f'<i style="width:{p[e]}%" aria-hidden="true"></i></li>' for e, n in conta.items())
        return (f'<div class="db-pc" style="--c:var(--{cor})"><h3>{esc(nome)}</h3><ul>{barras}'
                f"<li><span>Total</span><span>{sum(conta.values())} frases</span></li></ul></div>")
    totais = [f"{esc(nome)}, {sum(conta.values())}" for nome, _, conta in linhas]
    nota = (f'<p class="db-nota">Frases de cada um: {"; ".join(totais)}. Como o número de frases é diferente, '
            'compare pelo percentual; o número pequeno ao lado é a contagem.</p>') if len(linhas) > 1 else ""
    return nota + '<div class="db-placar">' + "".join(bloco(*x) for x in linhas) + "</div>"


def como_etiquetamos():
    ordem = ", ".join(ETIQUETAS[e].lower() for e in V.ETIQUETAS)
    return ('<p class="db-nota">Cada frase dita por um candidato recebeu uma etiqueta pelo ponto central dela: ataques e '
            'críticas (ataca ou critica o adversário, o governo, o partido ou aliados, sem que o ponto central seja um '
            'dado), propostas (diz o que vai fazer), apelo pessoal ou emocional (fala de si ou apela a medo, raiva, pena '
            'ou esperança) e dados e evidências (número, data ou fato verificável). '
            'Cada etiqueta é uma leitura da frase, não um fato. '
            'Foi feita por vários modelos de IA, cada um sem saber quem falou; onde eles divergiram, um desempate pela '
            'regra decidiu. Dado errado conta como dado: se ele confere é a checagem das afirmações que diz. '
            f'Quando ainda empata, vale a primeira desta ordem: {esc(ordem)}. Ficam de fora a mediação, cumprimentos, '
            'agradecimentos, perguntas de regra e os trechos em que não dá para ter certeza de quem fala.</p>')


def como_checamos():
    escala = "; ".join(f"{ROTULOS[v].lower()} ({DEFINICOES[v]})" for v in ORDEM_VEREDITOS)
    return ('<section aria-labelledby="metodo"><h2 id="metodo">Como checamos</h2>'
            '<p>Selecionamos as frases dos candidatos que dá para conferir com dado público (a mediação fica de fora). '
            f'Cada uma recebe um de cinco vereditos: {esc(escala)}. A afirmação é checada no sentido em que foi dita: '
            '"a criminalidade explodiu" olha o crime em geral, não só um indicador.</p>'
            '<p>Toda checagem cita as fontes, com a data de acesso, e diz o que o outro lado responde quando há resposta. '
            'O trecho entre aspas é o da transcrição automática, com os erros dela; a frase acima dele é a versão limpa '
            'da afirmação. Quando uma checagem é corrigida, a data de atualização muda.</p>'
            '<p>O placar separa fatos e dados, promessas e acusações, e o percentual é dentro de cada bloco: promessa não '
            'tem como ser "verdadeira", então misturar tudo puniria quem promete mais. O placar só conta vereditos. Não é '
            'nota do debate: a seleção cobre só frases verificáveis.</p></section>')


def gerar(m, base, autor):
    """Páginas de um debate: dict com path, titulo, desc, html, ld, publicado, modificado, og, llms, afirmacoes
    (uma página por checagem), transcricao, placar e resumo (para o índice e o banner)."""
    deb, cands, itens, chs = m["debate"], m["cands"], m["itens"], m["checagens"]
    emissora, turno, ano, dia = deb["emissora"], deb["turno"], deb["ano"], data_br(deb["data"])
    path, url = m["path"], base + m["path"]
    tpath = path + "transcricao/"
    publicado = deb.get("publicado_em") or deb["data"]
    modificado = max([publicado] + [c["atualizado_em"] for c in chs])
    n = len(chs)
    candidatos = [c for i, c in cands.items() if i != V.MEDIACAO]
    nomes = " x ".join(c["nome_urna"] for c in candidatos)
    rotulo = f"Debate {emissora} {turno}º turno {ano}"
    titulo = f"{rotulo}: o que é verdade"
    desc = (f"Checagem do debate {nomes} para {deb['cargo']} na {emissora}, em {dia}: {n} afirmações com veredito, "
            f"explicação e fontes.")
    trilha = [("Início", "/"), ("Debates", "/debates/"), (rotulo, path)]
    og = f"debate-{ano}-{deb['slug']}"

    def af_path(i):
        return f"{path}{i}/"

    def autor_claim(q):
        if q == V.MEDIACAO:
            return {"@type": "Organization", "name": f"Mediação do debate {emissora}"}
        return {"@type": "Person", "name": cands[q]["nome_urna"]}

    def claim(c):
        a = itens[c["id"]]
        return {"@context": "https://schema.org", "@type": "ClaimReview", "url": base + af_path(c["id"]),
                "claimReviewed": a["afirmacao"], "datePublished": publicado, "dateModified": c["atualizado_em"],
                "author": autor, "inLanguage": "pt-BR",
                "itemReviewed": {"@type": "Claim", "author": autor_claim(a["quem"]), "datePublished": deb["data"],
                                 "appearance": {"@type": "CreativeWork", "name": f"Transcrição do debate {emissora}, {dia}",
                                                "url": f"{base}{tpath}#{ancora(a['timestamp'])}"}},
                "reviewRating": {"@type": "Rating", "alternateName": ROTULOS[c["veredito"]]}}

    def tempo_html(ts):
        na_transcricao = f'<a href="{tpath}#{ancora(ts)}">'
        if deb.get("video"):
            return (f'<span class="db-tempo"><a href="{attr(no_video(deb["video"], ts))}" target="_blank" rel="noopener">'
                    f'▶ {esc(ts)} no vídeo</a> · {na_transcricao}transcrição</a></span>')
        return f'<span class="db-tempo">{na_transcricao}aos {esc(ts)} na transcrição</a></span>'

    def cartao(c, link=True):
        a = itens[c["id"]]
        cd = cands[a["quem"]]
        fontes = "; ".join(f'<a href="{attr(f["url"])}" target="_blank" rel="noopener">{esc(f["titulo"])}</a> ({esc(f["orgao"])})'
                           for f in c["fontes"])
        outro = f'<p class="db-outro"><b>Outro lado:</b> {esc(c["outro_lado"])}</p>' if c.get("outro_lado") else ""
        pagina = f'<a class="db-link" href="{af_path(a["id"])}">Página desta checagem</a>' if link else ""
        tempo = tempo_html(a["timestamp"])
        return (f'<article class="db-af" id="{a["id"]}" data-candidato="{attr(a["quem"])}" data-tema="{attr(a["tema"])}" '
                f'data-veredito="{attr(c["veredito"])}" style="--c:var(--{cd["cor"]})"><div class="db-af-t">'
                f'<span>{esc(_nome(cd))}</span>{tempo}</div>'
                f'<p class="db-frase">{esc(a["afirmacao"])}</p><blockquote>“{esc(a["trecho"])}”</blockquote>'
                f'<span class="db-selo">{esc(ROTULOS[c["veredito"]])}</span>'
                f'<p>{esc(c["explicacao"])}</p>{outro}<p class="db-fontes">Fontes: {fontes}</p>{pagina}</article>')

    conta = placar(m)
    linhas = [(_nome(cands[q]), cands[q]["cor"], conta[q]) for q in conta]
    placar_html = _placar_html(linhas, "placar", "Vereditos por quem falou",
                               "Afirmações checadas de cada um, separadas em fatos e dados, promessas e acusações. "
                               "Compare bloco com bloco: o percentual é dentro de cada um.")
    temas_usados = [t for t in V.TEMAS if any(itens[c["id"]]["tema"] == t for c in chs)]
    vereditos = [v for v in ORDEM_VEREDITOS if any(c["veredito"] == v for c in chs)]

    def opcoes(nome, rot, pares):
        return (f'<label>{rot}<select name="{nome}"><option value="">Todos</option>'
                + "".join(f'<option value="{attr(v)}">{esc(t)}</option>' for v, t in pares) + "</select></label>")
    filtro = ('<form class="db-filtro" aria-label="Filtrar afirmações" hidden>'
              + opcoes("candidato", "Quem", [(q, cands[q]["nome_urna"]) for q in conta])
              + opcoes("tema", "Tema", [(t, TEMAS[t]) for t in temas_usados])
              + opcoes("veredito", "Veredito", [(v, ROTULOS[v]) for v in vereditos])
              + f'<output aria-live="polite">{n} de {n} afirmações</output></form>')
    temas = "".join(
        f'<section class="db-tema" id="tema-{t}"><h2>{esc(TEMAS[t])}</h2><div class="db-lista">'
        + "".join(cartao(c) for c in chs if itens[c["id"]]["tema"] == t) + "</div></section>" for t in temas_usados)

    rt, conta_rt, retorica_html = m.get("retorica"), placar_retorica(m), ""
    if rt:
        linhas_rt = [(_nome(cands[q]), cands[q]["cor"], conta_rt[q]) for q in conta_rt]
        filtro_rt = ('<form class="db-rt-filtro" aria-label="Filtrar frases" hidden>'
                     + opcoes("candidato", "Quem", [(q, cands[q]["nome_urna"]) for q in conta_rt])
                     + opcoes("etiqueta", "Etiqueta", [(e, ETIQUETAS[e]) for e in ETIQUETAS])
                     + f'<output aria-live="polite">{len(rt)} de {len(rt)} frases</output></form>')
        lista_rt = "".join(
            f'<li id="{r["id"]}" data-candidato="{attr(r["quem"])}" data-etiqueta="{attr(r["etiqueta"])}" '
            f'style="--c:var(--{cands[r["quem"]]["cor"]})"><div class="db-rt-t"><span>{esc(_nome(cands[r["quem"]]))}</span>'
            f'<span>{esc(ETIQUETAS[r["etiqueta"]])}</span>{tempo_html(r["timestamp"])}</div><q>{esc(r["frase"])}</q></li>'
            for r in rt)
        retorica_html = ('<section aria-labelledby="retorica"><h2 id="retorica">Como cada um argumentou</h2>'
                         f'<p class="db-nota">{len(rt)} frases dos candidatos, cada uma com uma etiqueta. A barra é a '
                         'parte de cada etiqueta nas frases do candidato.</p>'
                         f'{_barras_retorica(linhas_rt)}{como_etiquetamos()}{filtro_rt}'
                         f'<ul class="db-rt" aria-label="Frases etiquetadas">{lista_rt}</ul></section>')

    corpo = (_trilha(trilha[:2] + [(rotulo, None)])
             + f'<p class="db-kicker">Checagem · {esc(deb["cargo"])} · {turno}º turno · {dia}</p>'
             f'<h1>Debate {esc(emissora)} do {turno}º turno: o que é verdade</h1>'
             f'<p class="db-lead">Debate para {esc(deb["cargo"])} entre {esc(" e ".join(_nome(c) for c in candidatos))}, '
             f'na {esc(emissora)}, em {dia}. Checamos {n} afirmações: cada uma tem a frase, o trecho da transcrição, '
             f'o veredito, a explicação e as fontes.</p>'
             f'{placar_html}{retorica_html}{filtro}{temas}'
             f'<section class="db-cta" aria-labelledby="depois"><h2 id="depois">A eleição</h2>'
             f'<p><a href="/ao-vivo/">Apuração ao vivo, por município →</a></p>'
             f'<p><a href="/">Resultado do 1º turno →</a></p>'
             f'<p><a href="{tpath}">Transcrição integral do debate →</a></p></section>{como_checamos()}')
    ld = [claim(c) for c in chs]
    ld += [{"@context": "https://schema.org", "@type": "Article", "headline": titulo[:110], "description": desc,
            "inLanguage": "pt-BR", "datePublished": publicado, "dateModified": modificado, "author": autor,
            "publisher": autor, "image": [f"{base}/og/{og}.png"], "mainEntityOfPage": url},
           _breadcrumb(base, trilha)]

    afs = []
    for c in chs:
        a = itens[c["id"]]
        cd = cands[a["quem"]]
        p = af_path(a["id"])
        frase = a["afirmacao"]
        curta = frase if len(frase) <= 90 else frase[:87].rsplit(" ", 1)[0] + "…"
        t = f"{cd['nome_urna']}: “{curta}” · {ROTULOS[c['veredito']]}"
        corpo_af = (_trilha(trilha + [(a["id"], None)])
                    + f'<p class="db-kicker">Checagem · {esc(rotulo)} · {esc(TEMAS[a["tema"]])}</p>'
                    f'<h1>{esc(cd["nome_urna"])}: “{esc(frase)}”</h1>{cartao(c, link=False)}'
                    f'<p><a href="{path}#{a["id"]}">← Todas as checagens do debate {esc(emissora)}</a></p>'
                    f'{como_checamos()}')
        afs.append(dict(path=p, titulo=t, desc=f"Veredito: {ROTULOS[c['veredito']]}. {c['explicacao']}"[:300],
                        html=_doc(t, corpo_af), publicado=publicado, modificado=c["atualizado_em"],
                        ld=[claim(c), _breadcrumb(base, trilha + [(a["id"], p)])],
                        og=(f"{og}-{a['id']}", frase, _nome(cd), cd["cor"], ROTULOS[c["veredito"]])))

    tt = f"Transcrição do debate {emissora} ({turno}º turno, {dia})"
    trilha_t = trilha + [("Transcrição", tpath)]
    transcricao = dict(path=tpath, titulo=tt, desc=f"Transcrição automática integral do debate {nomes} na {emissora}.",
                       html=_doc(tt, _trilha(trilha + [("Transcrição", None)]) + f"<h1>{esc(tt)}</h1>"
                                 + _transcricao_html(m["transcricao"])),
                       ld=[_breadcrumb(base, trilha_t)], publicado=publicado, modificado=publicado)

    por_cand = [(c["nome_urna"], c["partido"], c["cor"], total(conta.get(c["id"], {}))) for c in candidatos]
    return dict(path=path, titulo=titulo, desc=desc, html=_doc(titulo, corpo, js=True), ld=ld, publicado=publicado,
                modificado=modificado, og=(og, f"Checagem do debate {emissora}", f"{deb['cargo']} · {turno}º turno · {dia}",
                                           por_cand, f"{n} afirmações checadas"),
                llms=(f"- [Checagem do debate {emissora} ({deb['cargo']}, {turno}º turno, {dia})]({url}): {n} afirmações "
                      f"de {nomes}, com veredito, explicação e fontes\n"),
                afirmacoes=afs, transcricao=transcricao, placar=conta, retorica=conta_rt, cands=cands, rotulo=rotulo, n=n,
                data=deb["data"])


def _transcricao_html(md):
    """transcricao.md escapado: ## vira h2, cada **H:MM:SS** — texto vira um parágrafo com âncora t-H-MM-SS
    (a primeira, se a marcação se repetir); links do markdown viram só o texto."""
    out, vistos = ['<div class="db-tr">'], set()
    for linha in md.splitlines():
        linha = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", linha.strip())
        if not linha or linha.startswith("# ") or set(linha) <= set("|-: "):
            continue
        if s := V.RE_SECAO.match(linha):
            out.append(f"<h2>{esc(s.group(1))}</h2>")
        elif mk := V.RE_MARCA.match(linha):
            a = ancora(mk.group(1))
            ident = f' id="{a}"' if a not in vistos else ""
            vistos.add(a)
            out.append(f"<p{ident}><b>{esc(mk.group(1))}</b> {esc(mk.group(2))}</p>")
        else:
            out.append(f"<p>{esc(linha.lstrip('>-| ').replace('**', '').replace(' | ', ': ').rstrip('| '))}</p>")
    return "".join(out) + "</div>"


def indice(gerados, base, autor, links=None):
    """/debates/: lista dos debates (gerados já do mais novo para o mais antigo) e placar acumulado por candidato
    (soma por id, que é estável entre debates; a mediação fica de fora). links: {id_tse: href} da página do candidato
    no Rastro; o título do bloco dele vira link."""
    soma, quem = {}, {}
    for g in reversed(gerados):  # o mais novo por último: nome, partido e cor ficam os dele
        for q, conta in g["placar"].items():
            if q == V.MEDIACAO:
                continue
            quem[q] = g["cands"][q]
            for grupo, c in conta.items():
                for v, k in c.items():
                    soma.setdefault(q, {}).setdefault(grupo, {}).setdefault(v, 0)
                    soma[q][grupo][v] += k
    usados = {g: {v for c in soma.values() for v in c.get(g, {})} for g in GRUPOS}
    soma = {q: _ordenar({g: {v: c.get(g, {}).get(v, 0) for v in vs} for g, vs in usados.items() if vs}) for q, c in soma.items()}
    linhas = [(_nome(quem[q]), quem[q]["cor"], soma[q]) for q in soma]
    soma_rt, quem_rt = {}, {}
    for g in reversed(gerados):  # só os debates com retorica.json; o placar deles já traz as 6 etiquetas
        for q, conta in g.get("retorica", {}).items():
            quem_rt[q] = g["cands"][q]
            for e, k in conta.items():
                soma_rt.setdefault(q, dict.fromkeys(ETIQUETAS, 0))[e] += k
    retorica_html = ""
    quem_rt.update({q: c for q, c in quem.items() if q in quem_rt})  # o nome do placar de vereditos, se houver
    if soma_rt:
        com = sum(1 for g in gerados if g.get("retorica"))
        retorica_html = ('<section aria-labelledby="retorica"><h2 id="retorica">Como cada um argumentou, somado</h2>'
                         f'<p class="db-nota">Soma das frases etiquetadas de cada candidato em {com} '
                         f'{"debate" if com == 1 else "debates"}, sem a mediação.</p>'
                         + _barras_retorica([(_nome(quem_rt[q]), quem_rt[q]["cor"], c) for q, c in soma_rt.items()])
                         + como_etiquetamos() + "</section>")
    total = sum(g["n"] for g in gerados)
    titulo = "Checagem dos debates das eleições: o que é verdade"
    desc = f"Todas as checagens de debates: {len(gerados)} debates, {total} afirmações com veredito, explicação e fontes."
    lista = "".join(f'<a class="db-deb" href="{g["path"]}"><b>{esc(g["rotulo"])}</b>'
                    f'<span>{data_br(g["data"])} · {g["n"]} afirmações checadas</span></a>' for g in gerados)
    corpo = (_trilha([("Início", "/"), ("Debates", None)])
             + f'<p class="db-kicker">Checagem</p><h1>Debates: o que é verdade</h1>'
             f'<p class="db-lead">Checamos as frases verificáveis dos debates: {total} afirmações em {len(gerados)} '
             f'{"debate" if len(gerados) == 1 else "debates"}. Cada uma tem página própria com veredito e fontes.</p>'
             f'<section aria-labelledby="lista"><h2 id="lista">Debates checados</h2>{lista}</section>'
             + _placar_html(linhas, "placar", "Vereditos somados por candidato",
                            "Soma das afirmações checadas de cada candidato em todos os debates acima, sem a mediação. "
                            "Compare bloco com bloco: o percentual é dentro de cada um.",
                            {_nome(quem[q]): (links or {}).get(str(quem[q].get("id_tse"))) for q in soma})
             + retorica_html + como_checamos())
    modificado = max(g["modificado"] for g in gerados)
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": titulo, "description": desc,
           "url": base + "/debates/", "inLanguage": "pt-BR", "author": autor, "dateModified": modificado},
          _breadcrumb(base, [("Início", "/"), ("Debates", "/debates/")])]
    return dict(path="/debates/", titulo=titulo, desc=desc, html=_doc(titulo, corpo), ld=ld,
                publicado=min(g["publicado"] for g in gerados), modificado=modificado, placar=soma, retorica=soma_rt,
                llms=f"- [Checagem dos debates]({base}/debates/): {total} afirmações checadas em {len(gerados)} debates\n")
