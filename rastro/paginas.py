"""Páginas estáticas do Rastro: /rastro/ (home), /rastro/metodologia/, uma página por eleito publicado
(/rastro/<cargo>/<uf>/<slug>/) e uma por fornecedor PJ pago por eles (/rastro/fornecedor/<id>/). As correções
(rastro/correcoes.json) entram na página certa. O id do fornecedor é o CNPJ (empresa) ou um hash com sal (MEI).

Funções puras, sem rede e sem Chrome. `gerar` só escreve dentro de `dest` e, antes de gravar qualquer arquivo, varre o
HTML inteiro: CPF válido ou termo proibido levanta ValueError (nada é publicado em silêncio).
Limiares vêm de rastro/config.json; cores e fontes, de brand.css (dados sem cor própria; o ciano é só da moldura).
"""
import hashlib
import hmac
import html
import json
import re
import unicodedata
from collections import Counter
from urllib.parse import quote
from datetime import date
from pathlib import Path

import brand
from debates import pagina as dp
from rastro import busca
from rastro import diagramas
from rastro import indicadores as ind
from rastro.rotulos import peso, rotulo
from rastro.baixar import URL_CAND, url_contas
from rastro.contas import SAL, URL_CONTAS, cpf_valido

AVISO = "Indicador não é prova de irregularidade."
HOMONIMO = {"socio_doador", "socio_ligado", "socio_nomeado"}  # casados por nome: podem ser outra pessoa
CARGOS = {"presidente": "Presidente", "governador": "Governador(a)", "senador": "Senador(a)", "depfed": "Deputado(a) federal",
          "depest": "Deputado(a) estadual", "distrital": "Deputado(a) distrital"}
PROIBIDOS = re.compile(r"fraude|laranja|fict[ií]cia|desvio|suspeit[oa]|esquema|irregular", re.I)
# Únicos usos permitidos de "irregular": o aviso, a frase da metodologia e o nome técnico do indicador (âncora da metodologia)
PERMITIDOS = ("prova de irregularidade", "que houve irregularidade", "situacao_irregular")
RE_CPF_CANDIDATO = re.compile(r"(?<![\d.\-])\d{3}[.\s]?\d{3}[.\s]?\d{3}[\-\s]?\d{2}(?![\d])")
BUSCA_JS = Path(__file__).resolve().parent / "busca.js"
SEM_PRESTACAO = "Esta candidatura está sem prestação parcial publicada até a data da base."


def esc(t):
    return html.escape(str(t), quote=False)


def slug(nome):
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    s = re.sub(r"['’`´]", "", s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def caminho(eleito, sufixo=False):
    """'rastro/depfed/ma/aluisio-mendes/'; sufixo=True acrescenta '-<sq>' (colisão de slug no cargo/UF)."""
    s = slug(eleito["nome_urna"]) or "eleito"
    if sufixo:
        s += "-" + str(eleito["sq"])
    return f"rastro/{eleito['cargo']}/{eleito['uf'].lower()}/{s}/"


def caminhos(eleitos):
    """{sq: caminho} sem colisão: quem repete slug no mesmo cargo/UF recebe '-<sq>' (todos do grupo, para ser estável)."""
    grupos = {}
    for e in eleitos:
        grupos.setdefault(caminho(e), []).append(e)
    return {e["sq"]: caminho(e, sufixo=len(g) > 1) for g in grupos.values() for e in g}


def data_br(iso):
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else None


def ler_sal(caminho=SAL):
    """Só lê o sal (nunca cria no build): sem ele, o hash do MEI não seria reproduzível."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ValueError(f"sem {caminho.name}: não dá para gerar o id de fornecedor MEI; nada publicado")
    return caminho.read_text(encoding="utf-8").strip()


def id_fornecedor(cnpj, mei, sal):
    """PJ: os 14 dígitos do CNPJ. MEI: hmac-sha256(sal, cnpj)[:16], para o CNPJ não aparecer em lugar nenhum."""
    d = ind.digitos(cnpj)
    if len(d) != 14:
        raise ValueError("CNPJ inválido para id de fornecedor")
    if not mei:
        return d
    if not sal:
        raise ValueError("MEI sem sal: id não gerado; nada publicado")
    return hmac.new(sal.encode(), d.encode(), hashlib.sha256).hexdigest()[:16]


def eh_mei(rec):
    """Sem cadastro na Receita não dá para saber: trata como MEI (só CNPJ mascarado)."""
    return rec is None or rec.get("mei") is not False


def termo_proibido(texto):
    """Primeiro termo proibido do texto (match) ou None; as frases de PERMITIDOS não contam."""
    for p in PERMITIDOS:
        texto = re.sub(re.escape(p), " ", texto, flags=re.I)
    return PROIBIDOS.search(texto)


def varrer(nome, texto):
    """Levanta ValueError se o HTML tiver CPF válido ou termo proibido."""
    for m in RE_CPF_CANDIDATO.finditer(texto):
        if cpf_valido(re.sub(r"\D", "", m.group())):
            raise ValueError(f"{nome}: CPF válido no HTML ({m.group()[:3]}…); página não publicada")
    m = termo_proibido(texto)
    if m:
        raise ValueError(f"{nome}: termo proibido {m.group()!r}; página não publicada")


CSS = """<style>
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--font-sans)}
main.rs{max-width:880px;margin:0 auto;padding:24px 18px 56px}
.rs a{color:var(--ink);text-decoration-color:var(--muted);text-underline-offset:3px}
.rs-crumbs{font-size:13px;color:var(--muted);margin:0 0 14px}
.rs-kicker{font:600 12px var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.rs h1{font-size:clamp(26px,5vw,38px);line-height:1.15;margin:0 0 6px}
.rs h2{font-size:20px;margin:34px 0 10px;padding-top:6px;border-top:1px solid var(--line)}
.rs-meta{color:var(--ink2);margin:0 0 4px}
.rs-base{font-size:13px;color:var(--muted);margin:8px 0 0}
.rs-aviso{background:var(--soft);border:1px solid var(--line);border-left:4px solid var(--amber);border-radius:10px;padding:12px 14px;margin:18px 0;color:var(--ink)}
.rs-tab{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:15px}
.rs-tab th,.rs-tab td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.rs-tab td.v,.rs-tab th.v{text-align:right;white-space:nowrap}
.rs-tab small{display:block;color:var(--muted);font-size:12px}
.rs-total{font:600 15px var(--font-mono);margin:0 0 8px}
.rs-vazio{color:var(--ink2);font-style:italic}
.rs-ind{list-style:none;margin:0;padding:0}
.rs-ind li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 10px;overflow-wrap:anywhere}
.rs-ind code{font:600 13px var(--font-mono);color:var(--ink)}
.rs-ind .rs-ctp,.rs-ind .rs-hom{display:block;font-size:13px;color:var(--ink2);margin-top:4px}
.rs-ind .rs-hom{color:var(--amber)}
.rs-contestar{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.rs dl{margin:0}.rs dt{font:600 14px var(--font-mono);margin:18px 0 4px}.rs dd{margin:0;color:var(--ink2)}
details summary{cursor:pointer;color:var(--ink2);margin:8px 0}
.rs-resumo{font:600 15px var(--font-mono);color:var(--ink);margin:10px 0 0;overflow-wrap:anywhere}
.rs-aviso-curto{padding:8px 12px;margin:14px 0}
.rs-sankey{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:8px 0}
.rs-sankey svg{width:100%;height:auto}
.rs-sankey a:focus-visible rect{outline:2px solid var(--amber)}
.rs-nota{font-size:13px;color:var(--ink2);margin:6px 0 0}
.rs-det{border:1px solid var(--line);border-radius:10px;padding:2px 14px;margin:0 0 10px;background:var(--card)}
.rs-det[open]{padding-bottom:12px}
.rs-det summary{color:var(--ink)}
.rs-rodape{margin:40px 0 0;padding-top:12px;border-top:1px solid var(--line);font-size:13px;color:var(--ink2)}
.rs-rodape p{margin:4px 0}
tr:target{background:var(--soft)}
.rs-faixa{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:10px 0;font-size:14px}
.rs-cruz{list-style:none;margin:0;padding:0}
.rs-cruz li{border-bottom:1px solid var(--line);padding:8px 0;overflow-wrap:anywhere}
.rs-cruz small{display:block;color:var(--ink2);font-size:13px}
.rs-so-cel{display:none}
.rs-rot{font:600 13px var(--font-mono);color:var(--ink)}
.rs-cards{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.rs-card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--amber);border-radius:10px;padding:12px 14px;overflow-wrap:anywhere}
.rs-card-t{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;margin:0 0 6px}
.rs-card-t span{font:600 14px var(--font-mono);font-variant-numeric:tabular-nums}
.rs-tags{margin:0 0 6px}.rs-tag{display:inline-block;font:600 12px var(--font-mono);border:1px solid var(--amber);border-radius:999px;padding:1px 8px;margin:0 4px 4px 0}
.rs-card ul{margin:0;padding-left:18px;font-size:14px;color:var(--ink2)}
.rs-card .rs-hom{display:block;font-size:13px;color:var(--amber)}
.rs-card details{font-size:14px;color:var(--ink2)}.rs-card details summary{margin:6px 0 0}
.rs-card-l{font-size:14px;margin:6px 0 0}
.rs-selo{display:inline-block;min-width:18px;text-align:center;font:600 12px var(--font-mono);color:var(--bg);background:var(--amber);border-radius:999px;padding:0 6px;margin-left:6px;cursor:help}
.rs-filtro{display:inline-flex;gap:6px;align-items:center;font-size:14px;margin:4px 0 8px;cursor:pointer}
.rs-filtro[hidden]{display:none}
.rs-topo{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px;margin:0 0 14px}
.rs-topo .rs-crumbs{margin:0}
.rs-busca{position:relative;max-width:100%}
.rs-topo .rs-busca{flex:0 1 320px;min-width:0}
.rs-busca-g{margin:14px 0 6px}
.rs-busca-sem{font-size:14px}
.rs-busca input{box-sizing:border-box;width:100%;font:inherit;font-size:15px;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
.rs-busca-g input{font-size:17px;padding:12px 14px}
.rs-busca input::placeholder{color:var(--muted)}
.rs-busca input:focus{outline:2px solid var(--brand);outline-offset:1px}
.rs-busca ul{position:absolute;z-index:20;left:0;right:0;box-sizing:border-box;max-width:100%;max-height:min(420px,70vh);overflow-y:auto;list-style:none;margin:4px 0 0;padding:4px;background:var(--card);border:1px solid var(--line);border-radius:10px}
.rs-busca li a{display:block;padding:8px 10px;border-radius:8px;text-decoration:none;color:var(--ink);overflow-wrap:anywhere}
.rs-busca li[aria-selected=true] a,.rs-busca li a:hover{background:var(--soft)}
.rs-busca li small{display:block;color:var(--muted);font-size:12px}
.rs-busca-t{display:block;font:600 11px var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.rs-busca-vazio{padding:8px 10px;color:var(--ink2)}
.rs-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
""" + dp.CSS_PLACAR + """.rs-deb .db-nota{font-size:13px;color:var(--ink2);margin:6px 0 10px}
.rs-deb .db-placar{margin:0 0 12px}
.rs-deb ul.rs-afs{margin:0;padding-left:18px;font-size:14px}.rs-afs li{margin:4px 0;overflow-wrap:anywhere}.rs-afs small{color:var(--muted)}
@media (max-width:600px){.rs-topo .rs-busca{flex-basis:100%}}
@media (max-width:600px){.rs-sankey svg{min-width:680px}.rs-rede{display:none}.rs-so-cel{display:block}}
@media (max-width:560px){.rs-tab{font-size:14px}.rs-tab th,.rs-tab td{padding:7px 4px}}
</style>"""


SCRIPT = '<script defer src="/rastro/rastro.js"></script>'


def pagina(titulo, corpo, script=False):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(titulo)}</title>'
            f'<style>{brand.CSS}</style>{CSS}<script src="/rastro/busca.js" defer></script>{SCRIPT if script else ""}</head><body><main id="conteudo" class="rs">{corpo}</main></body></html>')


PLACEHOLDER_BUSCA = "Busque um eleito, uma empresa, um CNPJ ou um sócio"


def caixa_busca(grande=False):
    """Caixa de busca (rastro/busca.js). Sem JS, fica só o link para a lista de eleitos; o JS mostra o campo e esconde o link."""
    return (f'<div class="rs-busca{" rs-busca-g" if grande else ""}" role="search" data-rs-busca>'
            '<a class="rs-busca-sem" href="/rastro/#eleitos">Ver a lista completa de eleitos</a>'
            '<div class="rs-busca-cx" hidden><label class="rs-sr" for="rs-busca-q">Buscar no Rastro do dinheiro</label>'
            '<input id="rs-busca-q" type="search" role="combobox" aria-controls="rs-busca-l" aria-expanded="false" aria-autocomplete="list" '
            f'autocomplete="off" spellcheck="false" placeholder="{PLACEHOLDER_BUSCA}">'
            '<ul id="rs-busca-l" role="listbox" aria-label="Resultados da busca" hidden></ul></div></div>')


def trilha(*passos, busca=True):
    """passos: (rótulo, href|None); o último, sem link. busca=True põe a caixa compacta ao lado (a home tem a grande)."""
    nav = '<nav class="rs-crumbs" aria-label="Trilha">' + " › ".join(
        f'<a href="{h}">{esc(r)}</a>' if h else esc(r) for r, h in passos) + "</nav>"
    return f'<div class="rs-topo">{nav}{caixa_busca()}</div>' if busca else nav


def bloco_contestar(cfg, assunto):
    mail = html.escape(cfg["contato_email"], quote=True)
    return (f'<section id="contestar"><h2>Contestar este dado</h2><div class="rs-contestar"><p>Viu um erro, uma informação '
            f'desatualizada ou uma ligação que não procede? Escreva para <a href="mailto:{mail}?subject={html.escape(quote(assunto), quote=True)}">{esc(cfg["contato_email"])}</a> '
            f'com o endereço desta página e a fonte que corrige o dado. Os dados vêm de bases públicas; a correção, quando '
            f'cabível, é publicada.</p></div></section>')


def aviso_bloco():
    return (f'<p class="rs-aviso"><b>{esc(AVISO)}</b> Cada item abaixo é um fato público, com link para a fonte. '
            f'Como lemos, e o que cada indicador não diz: <a href="/rastro/metodologia/">metodologia</a>.</p>')


def aviso_curto():
    """Uma linha, para a página do eleito; o texto completo fica na metodologia."""
    return f'<p class="rs-aviso rs-aviso-curto"><b>{esc(AVISO)}</b> <a href="/rastro/metodologia/">Como ler esta página</a></p>'


def rodape(cfg, base, assunto):
    """Rodapé único da página do eleito: base, fontes e 'Contestar este dado' compacto."""
    mail = html.escape(cfg["contato_email"], quote=True)
    return (f'<footer class="rs-rodape"><p class="rs-base">Base de dados: {esc(base)}.</p>'
            f'<p>Fontes: <a href="{URL_CONTAS}" rel="noopener">TSE, prestação de contas</a> · '
            f'<a href="{ind.FONTE_RECEITA}" rel="noopener">Receita Federal, cadastro de empresas</a>.</p>'
            f'<section id="contestar"><p><b>Contestar este dado</b>: viu um erro ou uma ligação que não procede? Escreva para '
            f'<a href="mailto:{mail}?subject={html.escape(quote(assunto), quote=True)}">{esc(cfg["contato_email"])}</a> '
            f'com o endereço desta página e a fonte que corrige o dado.</p></section></footer>')


def tabela_receitas(rec):
    linhas = "".join(f'<tr><td>{esc(o)}</td><td class="v">{ind.brl(v)}</td></tr>'
                     for o, v in sorted((rec.get("por_origem") or {}).items(), key=lambda kv: (-kv[1], kv[0])))
    return (f'<p class="rs-total">Total: {ind.brl(rec.get("total") or 0)}</p>'
            f'<table class="rs-tab"><thead><tr><th>Origem</th><th class="v">Valor</th></tr></thead><tbody>{linhas}</tbody></table>')


def nome_fornecedor(f, forn):
    """Nome exibido (sem escape): PJ com cadastro, o nome ou a razão social; MEI ou sem cadastro para saber, só o CNPJ
    mascarado (o nome pode ser o da pessoa). Usado na tabela e no diagrama."""
    cnpj = ind.digitos(f.get("cnpj"))
    rec = (forn or {}).get(cnpj)
    if not eh_mei(rec):
        return f.get("nome") or rec.get("razao") or ind.mascarar_cnpj(cnpj)
    return ind.mascarar_cnpj(cnpj)


def ancora_fornecedor(i, cnpj, ids=None):
    """Âncora da linha do fornecedor na página do eleito ('f-<âncora>'): o id da página dele ou a posição na lista
    (nunca o CNPJ, que no MEI não pode aparecer)."""
    return (ids or {}).get(ind.digitos(cnpj)) or f"n{i}"


def _linha_fornecedor(f, forn, ids=None, i=0, itens=None):
    """itens: indicadores em que `f` é a contraparte (multicampanha conta); com algum, a linha ganha selo e `data-indicio`."""
    cnpj = ind.digitos(f.get("cnpj"))
    rec = (forn or {}).get(cnpj)
    nome = esc(nome_fornecedor(f, forn))
    if ids and cnpj in ids:
        nome = f'<a href="/rastro/fornecedor/{ids[cnpj]}/">{nome}</a>'
    selo = attr = ""
    if itens:
        rots = "; ".join(dict.fromkeys(rotulo(x["nome"]) for x in itens))
        selo = f'<span class="rs-selo" title="{html.escape(rots, quote=True)}">{len(itens)}</span>'
        attr = f' data-indicio="{len(itens)}"'
    if eh_mei(rec):
        nome += f'<small>{"MEI" if rec else "cadastro da Receita não localizado"}</small>'
    tipos = "; ".join(f.get("tipos") or [])
    return (f'<tr id="f-{ancora_fornecedor(i, cnpj, ids)}"{attr}><td>{nome}{selo}{f"<small>{esc(tipos)}</small>" if tipos else ""}</td>'
            f'<td class="v">{ind.brl(f.get("total") or 0)}</td></tr>')


FILTRO = '<label hidden class="rs-filtro"><input type="checkbox"> Só com indício</label>'


def tabela_despesas(desp, forn, ids=None, itens=None):
    pj = desp.get("fornecedores_pj") or []
    cab = '<table class="rs-tab"><thead><tr><th>Fornecedor (pessoa jurídica)</th><th class="v">Contratado</th></tr></thead><tbody>'
    recs = [(forn or {}).get(ind.digitos(f.get("cnpj"))) for f in pj]
    por_linha = [_itens_do_fornecedor(f, r, eh_mei(r), pj, itens or []) if itens else [] for f, r in zip(pj, recs)]
    linhas = [_linha_fornecedor(f, forn, ids, i, por_linha[i]) for i, f in enumerate(pj)]
    out = [f'<p class="rs-total">Contratado: {ind.brl(desp.get("total_contratado") or 0)} · pago: {ind.brl(desp.get("total_pago") or 0)}</p>']
    if pj:
        out.append((FILTRO if any(por_linha) else "") + cab + "".join(linhas[:20]) + "</tbody></table>")
        if len(linhas) > 20:
            out.append(f'<details><summary>Mais {len(linhas) - 20} fornecedores</summary>{cab}{"".join(linhas[20:])}</tbody></table></details>')
    pf = desp.get("fornecedores_pf") or {}
    if pf.get("qtd"):  # pessoa física: nunca nome, só contagem, total e tipo de despesa
        tipos = "".join(f'<tr><td>{esc(t)}</td><td class="v">{ind.brl(v)}</td></tr>' for t, v in sorted((pf.get("por_tipo") or {}).items()))
        out.append(f'<p class="rs-total" style="margin-top:16px">Pessoas físicas: {pf["qtd"]} pagas, {ind.brl(pf.get("total") or 0)}</p>'
                   + (f'<table class="rs-tab"><thead><tr><th>Tipo de despesa</th><th class="v">Valor</th></tr></thead><tbody>{tipos}</tbody></table>' if tipos else ""))
    return "".join(out)


def _hom(i):
    return ('<span class="rs-hom">Casado por nome: pode ser homônimo.</span>'
            if i["nome"] in HOMONIMO and "homônimo" not in i["fato"] else "")


def _fonte(i):
    return f'<a href="{html.escape(i["fonte_url"], quote=True)}" rel="noopener">fonte</a>'


def lista_indicadores(itens, base):
    if not itens:
        return f'<p class="rs-vazio">Nenhum indicador disparado para esta candidatura na base de {esc(base)}.</p>'
    lis = []
    for i in itens:
        quem = "Fornecedores" if i.get("contrapartes") else "Fornecedor"
        extra = f'<span class="rs-ctp">{quem}: {esc("; ".join(i.get("contrapartes") or [i["contraparte"]]))}</span>' if i.get("contraparte") else ""
        lis.append(f'<li><b class="rs-rot">{esc(rotulo(i["nome"]))}</b>: {esc(i["fato"])} {_fonte(i)}{extra}{_hom(i)}</li>')
    return f'<ul class="rs-ind">{"".join(lis)}</ul>'


MAX_DESTAQUES = 5
VALOR_NAO_REAIS = {"gasto_por_voto", "concentracao", "multicampanha"}  # `valor` é custo por voto, % ou contagem, não reais envolvidos


def destaques(itens, contas, forn, cfg, ids=None):
    """Cartões de "O que chama atenção": indicadores agrupados por fornecedor (multicampanha fica de fora), no máximo
    MAX_DESTAQUES, ordenados por (peso de destaque, reais envolvidos, nome). Reais envolvidos: o total contratado do fornecedor
    (o `valor` de concentracao é % e o de multicampanha, contagem); sem fornecedor, o `valor` do item. O peso nunca sai na página.
    Um fornecedor fica num cartão só: se ele está num grupo de `valores_identicos` e tem outro indicador, tudo vai para o
    cartão do grupo. Cartão: {titulo, itens, peso, valor (None quando não é em reais), links: [(nome, href)]}."""
    pj = ((contas or {}).get("despesas") or {}).get("fornecedores_pj") or []
    por_chave, ambiguas = {}, set()
    for n, f in enumerate(pj):
        cnpj = ind.digitos(f.get("cnpj"))
        rec = (forn or {}).get(cnpj)
        for k in _chave_contraparte(f, rec, eh_mei(rec)):
            if k in por_chave and por_chave[k][2] != cnpj:
                ambiguas.add(k)  # ex.: dois MEIs com a mesma máscara: não dá para saber qual é
            por_chave.setdefault(k, (n, f, cnpj))
    for k in ambiguas:
        del por_chave[k]

    def ident(c):  # o mesmo fornecedor pode vir pelo nome ou pela razão social: a identidade é o CNPJ
        if c in ambiguas:
            return object()  # identidade desconhecida: não junta com outro cartão
        return por_chave[c][2] if c in por_chave else c

    grupos = []  # {"ids": identidades dos fornecedores, "nomes": como os indicadores os chamam, "itens"}
    for i in itens or []:
        if i["nome"] == "multicampanha":
            continue
        nomes = list(dict.fromkeys(i.get("contrapartes") or ([i["contraparte"]] if i.get("contraparte") else [])))
        ids_i = {ident(c) for c in nomes}
        juntos = [g for g in grupos if g["ids"] & ids_i]
        if not juntos:
            grupos.append({"ids": ids_i, "nomes": nomes, "itens": [i]})
            continue
        alvo = juntos[0]
        for g in juntos[1:]:
            alvo["ids"] |= g["ids"]
            alvo["nomes"] += g["nomes"]
            alvo["itens"] += g["itens"]
            grupos.remove(g)
        alvo["ids"] |= ids_i
        alvo["itens"].append(i)
        vistos = {ident(c) for c in alvo["nomes"]}
        alvo["nomes"] += [c for c in nomes if c not in alvo["nomes"] and ident(c) not in vistos]
    cartoes = []
    for g in grupos:
        its, links = g["itens"], []
        valor_item = None if its[0]["nome"] in VALOR_NAO_REAIS else float(its[0].get("valor") or 0)
        if not g["nomes"]:
            titulo = rotulo(its[0]["nome"])
            valor = valor_item
        else:
            titulo = "; ".join(g["nomes"])
            achados = {por_chave[c][2]: por_chave[c] for c in g["nomes"] if c in por_chave}
            for pos, _, cnpj in achados.values():
                links.append((nome_fornecedor(pj[pos], forn),
                              f"/rastro/fornecedor/{ids[cnpj]}/" if ids and cnpj in ids else f"#f-{ancora_fornecedor(pos, cnpj, ids)}"))
            valor = sum(float(f.get("total") or 0) for _, f, _ in achados.values()) if achados else valor_item
        cartoes.append({"titulo": titulo, "itens": its, "peso": max(peso(i["nome"], cfg) for i in its), "valor": valor, "links": links})
    cartoes.sort(key=lambda c: (-c["peso"], -(c["valor"] or 0), c["titulo"]))
    return cartoes[:MAX_DESTAQUES]


def bloco_destaques(cartoes, base, cfg):
    """Seção 'O que chama atenção', no topo da página do eleito. Sem cartão, uma linha."""
    cab = '<section id="destaques"><h2>O que chama atenção</h2>'
    if not cartoes:
        return f'{cab}<p class="rs-vazio">Nenhum indicador disparado nesta base ({esc(base)}).</p></section>'
    desc = dict(descricoes(cfg))
    lis = []
    for c in cartoes:
        nomes = list(dict.fromkeys(i["nome"] for i in c["itens"]))
        tags = "".join(f'<span class="rs-tag">{esc(rotulo(n))}</span>' for n in nomes)
        fatos = "".join(f"<li>{esc(i['fato'])} {_fonte(i)}{_hom(i)}</li>" for i in c["itens"])
        valor = f"<span>{ind.brl(c['valor'])}</span>" if c["valor"] is not None else ""
        if len(c["links"]) == 1:
            link = f'<p class="rs-card-l"><a href="{c["links"][0][1]}">ver fornecedor</a></p>'
        elif c["links"]:
            link = ('<p class="rs-card-l">ver fornecedores: '
                    + " · ".join(f'<a href="{h}">{esc(n)}</a>' for n, h in c["links"]) + "</p>")
        else:
            link = ""
        expl = "".join(f'<details><summary>O que é “{esc(rotulo(n))}”</summary>{desc[n]}</details>' for n in nomes if n in desc)
        lis.append(f'<li class="rs-card"><p class="rs-card-t"><b>{esc(c["titulo"])}</b>{valor}</p><p class="rs-tags">{tags}</p>'
                   f"<ul>{fatos}</ul>{link}{expl}</li>")
    return (f'{cab}<p class="rs-nota">Até {MAX_DESTAQUES} fornecedores ou fatos, os de indicador mais forte primeiro. '
            f'A lista completa está em <a href="#indicadores">Indicadores</a>.</p><ul class="rs-cards">{"".join(lis)}</ul></section>')


MAX_CRUZ = 10


def rotulo_eleito(e):
    """NOME · UF · SIGLA: o partido vai junto de todo eleito citado no Rastro (issue #74); sem o dado, fica de fora"""
    return " · ".join(str(x) for x in (e["nome_urna"], e.get("uf"), e.get("partido")) if x)


def secao_cruzada(cruz):
    """'Fornecedores que também atendem outros eleitos'. cruz: [{id, rotulo, outros: [{nome_urna, caminho}]}], rotulo já
    mascarado no MEI. Sem cruzamento, nada."""
    if not cruz:
        return ""
    lis = []
    for c in cruz:
        outros = sorted(c["outros"], key=lambda o: o["nome_urna"])
        links = ", ".join(f'<a href="/{o["caminho"]}">{esc(rotulo_eleito(o))}</a>' for o in outros[:MAX_CRUZ])
        if len(outros) > MAX_CRUZ:
            links += f" e mais {len(outros) - MAX_CRUZ}"
        lis.append(f'<li><a href="/rastro/fornecedor/{c["id"]}/">{esc(c["rotulo"])}</a><small>Também contratado por: {links}</small></li>')
    return ('<section id="rede"><h2>Fornecedores que também atendem outros eleitos</h2><p class="rs-nota">Eleitos publicados que pagaram '
            'o mesmo fornecedor. Contratar o mesmo fornecedor é comum e não indica relação entre as campanhas. Plataformas de pagamento '
            f'e anúncio ficam de fora (<a href="/rastro/metodologia/#rede">metodologia</a>).</p><ul class="rs-cruz">{"".join(lis)}</ul></section>')


def secao_debates(deb):
    """'Nos debates': placar acumulado (o mesmo bloco de /debates/) e, por debate, os links das afirmações checadas.
    deb: um valor de `debates.pagina.placar_por_candidato`. Sem debate checado, nada. O link leva o horário e o tema, não a
    frase: a fala do candidato pode citar um termo que o Rastro não usa (ex.: "a fraude do INSS"), e a frase fica na checagem."""
    if not deb or not deb.get("debates"):
        return ""
    placar = dp._placar_html([(dp._nome(deb), deb["cor"], deb["conta"])], "debates-placar", "Vereditos somados",
                             "Contagem das afirmações checadas dele(a) em todos os debates, com a parte de cada veredito no total.")
    dets = "".join(
        f'<details class="rs-det"><summary><b>{esc(d["rotulo"])}</b> · {len(d["afirmacoes"])} afirmação(ões)</summary>'
        '<ul class="rs-afs">' + "".join(f'<li><a href="{html.escape(a["path"], quote=True)}">Aos {esc(a["timestamp"])} · '
                                        f'{esc(dp.TEMAS.get(a["tema"], a["tema"]))}</a> · '
                                         f'<small>{esc(dp.ROTULOS[a["veredito"]])}</small></li>' for a in d["afirmacoes"])
        + f'</ul><p class="rs-nota"><a href="{html.escape(d["path"], quote=True)}">Todas as checagens deste debate</a></p></details>'
        for d in deb["debates"])
    return (f'<section id="debates" class="rs-deb"><h2>Nos debates</h2><p class="rs-nota">Frases verificáveis checadas nos debates, '
            f'com veredito e fontes. O placar só conta vereditos; não é nota do debate (<a href="/debates/">todas as checagens</a>).</p>'
            f'{placar}{dets}</section>')


def html_eleito(eleito, contas, itens, fornecedores, cfg, bases, ids=None, cruz=None, debates=None):
    """bases: {'contas': iso, 'receita': iso|None}. contas None (ou prestacao_parcial False): sem valores, sem 'R$ 0'.
    cruz: fornecedores deste eleito que outros eleitos publicados também pagaram (ver `secao_cruzada`).
    debates: a entrada dele em `debates.pagina.placar_por_candidato` (seção 'Nos debates'). Presidente leva o kicker de
    candidato(a) ao 2º turno, não de eleito(a)."""
    nome = eleito["nome_urna"]
    partes = [f'{esc(CARGOS.get(eleito["cargo"], eleito["cargo"]))} · {esc(eleito["uf"])} · {esc(eleito["partido"])}']
    base = (f'contas do TSE até {data_br(bases["contas"])}' if bases.get("contas") else "data das contas não informada") + (f' · cadastro de empresas da Receita de {data_br(bases["receita"])}' if bases.get("receita") else "")
    parcial = bool(contas) and contas.get("prestacao_parcial") is not False
    resumo = diag = ""
    if not parcial:
        fin = f'<p class="rs-vazio">{SEM_PRESTACAO}</p>'
        rec_h = desp_h = ""
    else:
        rec = contas.get("receitas")
        desp = contas.get("despesas")
        pj = (desp or {}).get("fornecedores_pj") or []
        partes_r = [f"Recebeu {ind.brl(rec.get('total') or 0)}" if rec else "Receitas não declaradas",
                    f"Contratou {ind.brl(desp.get('total_contratado') or 0)}" if desp else "Despesas não declaradas",
                    f"{len(pj)} fornecedor{'es' if len(pj) != 1 else ''}", f"{len(itens)} indicador{'es' if len(itens) != 1 else ''}"]
        resumo = f'<p class="rs-resumo">{" · ".join(partes_r)}</p>'
        nome_uf = f"{nome} · {eleito['uf']}"
        diag = f'<section class="rs-diagrama"><h2>Caminho do dinheiro</h2>{diagramas.diagrama_campanha(contas, fornecedores, itens, ids, nome_uf, eleito.get("partido"))}</section>'
        n_orig = len((rec or {}).get("por_origem") or {})
        rec_h = (f'<details class="rs-det"><summary><b>Receitas por origem</b> · total {ind.brl(rec.get("total") or 0)} · {n_orig} origem(ns)</summary>{tabela_receitas(rec)}</details>'
                 if rec else '<details class="rs-det"><summary><b>Receitas por origem</b></summary><p class="rs-vazio">Receitas ainda não declaradas na base.</p></details>')
        desp_h = (f'<details class="rs-det"><summary><b>Despesas por fornecedor</b> · contratado {ind.brl(desp.get("total_contratado") or 0)} · {len(pj)} fornecedor(es)</summary>'
                  f'{tabela_despesas(desp, fornecedores, ids, itens)}</details>'
                  if desp else '<details class="rs-det"><summary><b>Despesas por fornecedor</b></summary><p class="rs-vazio">Despesas ainda não declaradas na base.</p></details>')
        fin = ""
    data_ind = data_br(bases["contas"]) or "data não informada"
    ind_h = f'<h2 id="indicadores">Indicadores</h2>{lista_indicadores(itens, data_ind)}' if parcial else ""
    dest_h = bloco_destaques(destaques(itens, contas, fornecedores, cfg, ids), data_ind, cfg) if parcial else ""
    tabs = f'<h2>Tabelas</h2>{rec_h}{desp_h}' if parcial else ""
    com_sg = f'{nome} · {eleito["partido"]}' if eleito.get("partido") else nome
    corpo = (trilha(("Início", "/"), ("Rastro do dinheiro", "/rastro/"), (com_sg, None))
             + f'<p class="rs-kicker">Rastro do dinheiro · {"candidato(a) ao 2º turno" if eleito["cargo"] == "presidente" else "eleito(a) 2026"}</p>'
             f'<h1>{esc(com_sg)}</h1><p class="rs-meta">{partes[0]}</p>{resumo}' + aviso_curto() + fin + dest_h + diag + ind_h + tabs
             + (secao_cruzada(cruz) if parcial else "") + secao_debates(debates)
             + rodape(cfg, base, f"Contestar dado: {rotulo_eleito(eleito)}"))
    return pagina(f"{nome} · Rastro do dinheiro", corpo, script=parcial)


def _pct(v):
    return f"{v * 100:.4g}".replace(".", ",") + "%"


def _n(v):
    return str(v).replace(".", ",")


def descricoes(cfg):
    c = cfg
    return [
        ("mei_acima_teto", f"MEI que recebeu, somando as campanhas de 2026, mais que o teto de faturamento anual do MEI ({ind.brl(c['mei_teto_anual'])}; {esc(c['mei_teto_fonte'])})."),
        ("empresa_recem_aberta", f"Fornecedor aberto menos de {c['recem_aberta_dias']} dias antes do início da campanha ({data_br(c['campanha_inicio'])}) ou depois dele."),
        ("atividade_incompativel", "A atividade principal (CNAE) do fornecedor não corresponde a nenhum dos tipos de despesa que a campanha declarou pagar a ele. Na dúvida, o indicador não dispara."),
        ("socio_doador", "Sócio(a) do fornecedor que consta como doador(a) em campanhas de 2026. O casamento é por nome e pelos seis dígitos do meio do CPF que a Receita publica; pode errar com homônimos."),
        ("socio_ligado", "Sócio(a) do fornecedor que consta como candidato(a), suplente ou servidor com função comissionada, ou que tem o mesmo sobrenome do candidato que contratou. Sobrenome igual é um fato textual, não prova relação; sobrenomes muito comuns são ignorados."),
        ("multicampanha", f"Fornecedor que prestou serviço a {c['multicampanha_min']} campanhas ou mais em 2026."),
        ("situacao_irregular", f"Situação cadastral do fornecedor na Receita entre: {', '.join(c['situacoes_irregulares'])}."),
        ("concentracao", f"Um único fornecedor concentra mais de {c['concentracao_pct']}% do total contratado pela campanha."),
        ("endereco_compartilhado", f"Ao menos {c['endereco_min_fornecedores']} fornecedores da mesma campanha, de empresas diferentes, com o mesmo endereço na Receita. O endereço não é publicado."),
        ("valores_identicos", f"Ao menos 2 fornecedores da mesma campanha, de empresas diferentes (matriz e filial contam como uma), com exatamente o mesmo total contratado. Só valores a partir de {ind.brl(c.get('valores_identicos_min', 5000))} e que não sejam múltiplos de {ind.brl(c.get('valores_identicos_ignorar_multiplo', 10000))}, porque preço redondo é comum. A base publicada traz o total por fornecedor, não cada despesa."),
        ("preco_fora_da_curva", f"Gasto num tipo de despesa acima do percentil {c['percentil_comparacao']} das campanhas do mesmo cargo e UF (comparação só em grupos com {c['min_campanhas_grupo']} campanhas ou mais)."),
        ("gasto_por_voto", f"Custo por voto (contratado dividido pelos votos) acima do percentil {c['percentil_comparacao']} das campanhas do mesmo cargo e UF (grupos com {c['min_campanhas_grupo']} campanhas ou mais)."),
        ("transferencia_candidato", f"Repasse a outro candidato que usou fornecedores em comum. Destacado quando o recebedor teve votação ínfima, menos de {_pct(c['votacao_infima_fracao_eleitorado'])} do eleitorado da UF."),
        ("pessoal_pf", f"Campanha que pagou {c['pf_qtd_min']} pessoas físicas ou mais; pessoas pagas por {c['pf_repetido_min_campanhas']} campanhas ou mais; ao menos {c['pf_redondo_alto_min_qtd']} pagamentos de {ind.brl(c['pf_valor_alto'])} ou mais em múltiplos de {ind.brl(c['pf_redondo_multiplo'])}. Pessoa física aparece só como contagem e total, nunca com nome."),
        ("saque_especie", "Lançamentos de saque ou pagamento em espécie no extrato bancário da conta da campanha."),
        ("pagamento_tardio", f"Pagamentos registrados depois do dia da eleição ({data_br(c['dia_eleicao'])}), ou mais de {_pct(c['tardio_pct_ultimos_dias'])} do total pago nos {c['tardio_dias']} dias até a eleição."),
    ]


def secao_avisos(avisos):
    """Indicadores pulados na geração (fonte fora do ar ou arquivo ausente), lidos de indicadores.json["avisos"]."""
    if not avisos:
        return ""
    lis = "".join(f"<li>{esc(a)}</li>" for a in avisos)
    return ("<h2>Indicadores não calculados nesta base</h2><p>Alguma fonte estava indisponível quando os indicadores foram gerados. "
            f"Estes ficaram de fora e não aparecem em nenhuma página:</p><ul>{lis}</ul>")


def raizes_excluidas(cfg):
    return {ind.digitos(p["raiz"])[:8] for p in cfg.get("rede_excluir_cnpj_raiz") or []}


def secao_rede_metodologia(cfg):
    plats = cfg.get("rede_excluir_cnpj_raiz") or []
    lis = "".join(f'<li>{esc(p["nome"])} (raiz do CNPJ {esc(p["raiz"])})</li>' for p in plats)
    return ('<h2 id="rede">Rede de fornecedores</h2><p>“Atende N eleitos” é uma contagem: quantos eleitos publicados declararam '
            'pagar o mesmo CNPJ. É um fato contábil, não um ranking de risco, e não indica relação entre as campanhas. Entram na '
            'lista da home as empresas com 2 eleitos ou mais, ordenadas pelo número de eleitos e depois pelo total contratado por eles.</p>'
            '<p>Na página do fornecedor, o diagrama mostra as campanhas que o contrataram. Eleitos aparecem com nome (com link quando '
            'a página já existe); campanhas não eleitas entram somadas num único nó, sem nome, com o valor que falta para o total '
            'recebido pelo fornecedor na base. Partidos e estados contam só os eleitos.</p>'
            + (f"<p>Ficam fora da rede (ranking, diagrama da home e lista da página do eleito) as plataformas de pagamento e anúncio, "
               f"que atendem quase todas as campanhas:</p><ul>{lis}</ul>" if lis else ""))


def html_metodologia(cfg, avisos=None):
    dl = "".join(f'<dt>{esc(rotulo(n))} <code id="ind-{n}">{n}</code></dt><dd>{t}</dd>' for n, t in descricoes(cfg))
    niveis = {3: "alto", 2: "médio", 1: "baixo"}
    por_nivel = {}
    for n, _ in descricoes(cfg):
        por_nivel.setdefault(peso(n, cfg), []).append(rotulo(n))
    pesos = "".join(f"<li>Peso {niveis.get(p, p)} ({p}): {esc(', '.join(por_nivel[p]))}.</li>" for p in sorted(por_nivel, reverse=True))
    destaque_h = ('<h2 id="destaques">O que chama atenção</h2><p>No topo da página do eleito, até '
                  f'{MAX_DESTAQUES} cartões juntam os indicadores de um mesmo fornecedor. A ordem segue um peso por indicador '
                  'e, no empate, o valor em reais envolvido e o nome. O peso só ordena os cartões dentro da página: nunca aparece '
                  'como número e não compara candidatos. “Atende muitas campanhas” não vira cartão, porque contratar fornecedor '
                  f'grande é comum; ele continua na lista completa e no selo da tabela.</p><ul>{pesos}</ul>')
    nom = (cfg.get("nomeacoes_fontes") or {}).get("siape") or ""
    nom = nom.format(mes=cfg["nomeacoes_mes"].replace("-", "")) if nom else ""
    fontes = (f'<ul><li>Prestação de contas parcial das campanhas, candidatos e eleitos: <a href="{URL_CONTAS}" rel="noopener">TSE, dados abertos</a> '
              f'e <a href="{URL_CAND}" rel="noopener">cadastro de candidatos</a>.</li>'
              f'<li>Cadastro de empresas (situação, atividade, endereço e quadro societário): <a href="{ind.FONTE_RECEITA}" rel="noopener">Receita Federal, dados abertos do CNPJ</a>.</li>'
              + (f'<li>Servidores com função comissionada ({cfg["nomeacoes_mes"][5:]}/{cfg["nomeacoes_mes"][:4]}): <a href="{nom}" rel="noopener">Portal da Transparência</a>.</li>' if nom else "")
              + "</ul>")
    corpo = (trilha(("Início", "/"), ("Rastro do dinheiro", "/rastro/"), ("Metodologia", None))
             + '<p class="rs-kicker">Rastro do dinheiro</p><h1>Metodologia</h1>'
             '<p class="rs-meta">Como cada página de eleito é montada e o que ela não diz.</p>' + aviso_bloco()
             + "<h2>O que é</h2><p>Para cada eleito publicado, cruzamos a prestação de contas da campanha (TSE) com o cadastro de empresas da "
               "Receita. Mostramos receitas por origem, despesas por fornecedor e os indicadores que dispararam, cada um com o fato e o link da fonte. "
               "Não afirmamos que houve irregularidade: apontamos onde vale conferir.</p>"
             + f"<h2>Fontes</h2>{fontes}"
             + f"<h2>Indicadores e limiares</h2><p>Os limiares abaixo são os do arquivo de configuração do projeto, os mesmos usados para gerar as páginas.</p><dl>{dl}</dl>"
             + destaque_h + secao_rede_metodologia(cfg)
             + '<h2 id="presidente">Presidente e “nos debates”</h2><p>Os dois candidatos do 2º turno a presidente têm página com o mesmo '
               "cruzamento das contas dos eleitos (receitas, despesas, fornecedores e indicadores), mas ficam fora dos totais, da rede de "
               "fornecedores entre eleitos e da lista de eleitos. As comparações com outras campanhas do mesmo cargo (preço fora da "
               "curva e custo por voto) não se aplicam a eles.</p><p>A seção “nos debates” soma os vereditos das afirmações "
               'dele(a) checadas em cada debate da seção <a href="/debates/">Debates</a>, com link para cada checagem. É a mesma contagem do '
               "placar dos debates: só conta vereditos, não é nota.</p>"
             + "<h2>Limites</h2><ul>"
               "<li>Parentesco não consta em nenhuma base pública. Não inferimos parentesco.</li>"
               "<li>“Mesmo sobrenome” é um fato textual: duas pessoas com o mesmo sobrenome não são, por isso, parentes.</li>"
               "<li>O casamento por nome (sócio com doador, candidato ou servidor) pode errar com homônimos; por isso o texto avisa “pode ser homônimo”.</li>"
               "<li>A prestação de contas é parcial e muda até a prestação final; a data da base está em cada página.</li>"
               f"<li>Diagrama do caminho do dinheiro: {diagramas.LIMITACAO} {diagramas.NOTA_TIPO} "
               "Doador pessoa jurídica com menos de 2% das receitas entra em “Outros doadores”; além dos 10 maiores fornecedores, os demais "
               "aparecem somados por tipo.</li>"
               "<li>Pessoas físicas pagas aparecem só como contagem e total; MEI aparece só pelo CNPJ mascarado. Nenhum CPF é publicado.</li></ul>"
             + secao_avisos(avisos)
             + "<h2>Correções</h2><p>Quando um dado publicado é corrigido, a página afetada ganha uma seção “Correções” com a data e o que mudou, "
               "e o registro fica no arquivo <code>rastro/correcoes.json</code> do repositório. Correção não apaga o histórico: ela aparece na própria página.</p>"
             + bloco_contestar(cfg, "Contestar dado do Rastro"))
    return pagina("Metodologia · Rastro do dinheiro", corpo)


def _rotulo_cargo(e):
    return f'{CARGOS.get(e["cargo"], e["cargo"])} · {e["uf"]} · {e["partido"]}'


def _lista_anos(anos):
    anos = [str(a) for a in anos]
    return anos[0] if len(anos) == 1 else ", ".join(anos[:-1]) + " e " + anos[-1]


def secao_anteriores(cnpj, anteriores, cfg):
    """'Em eleições anteriores': por ano, campanhas que o contrataram e total contratado (rastro/dados/anteriores.json).
    Só números e links do pacote do TSE; o mesmo CNPJ não garante a mesma atividade ou o mesmo dono."""
    lidos = [a for a in cfg.get("anteriores_anos") or [] if a in (anteriores.get("anos") or [])]
    if not lidos:
        return ""
    por_ano = (anteriores.get("por_cnpj") or {}).get(ind.digitos(cnpj)) or {}
    com = [a for a in lidos if str(a) in por_ano]
    sem = [a for a in lidos if a not in com]
    linhas = "".join(
        f'<tr><td>{a} <a href="{url_contas(a)}" rel="noopener">fonte</a></td><td class="v">{por_ano[str(a)]["n_campanhas"]} campanha(s)</td>'
        f'<td class="v">{ind.brl(por_ano[str(a)]["total_contratado"])}</td></tr>' for a in com)
    out = ['<h2 id="anteriores">Em eleições anteriores</h2>']
    if com:
        out.append('<table class="rs-tab"><thead><tr><th>Eleição</th><th class="v">Campanhas</th><th class="v">Contratado</th></tr></thead>'
                   f"<tbody>{linhas}</tbody></table>")
    if len(com) == len(cfg["anteriores_anos"]):
        out.append(f'<p class="rs-total">Contratado por campanhas em {_lista_anos(list(com) + [2026])}.</p>')
    if sem:
        out.append(f'<p class="rs-vazio">Sem registro nas eleições de {_lista_anos(sem)} da base do TSE.</p>')
    out.append('<p class="rs-base">Valores contratados (não necessariamente pagos), de despesas com CNPJ de fornecedor. O mesmo CNPJ '
               'não garante a mesma atividade nem o mesmo dono: a empresa pode ter mudado de mãos.</p>')
    return "".join(out)


def faixa_anteriores(cnpj, anteriores, cfg):
    """Uma linha no topo do caminho do dinheiro: 'Também recebeu em 2022 (N campanhas) e 2024 (N campanhas)'."""
    lidos = [a for a in cfg.get("anteriores_anos") or [] if a in ((anteriores or {}).get("anos") or [])]
    por_ano = ((anteriores or {}).get("por_cnpj") or {}).get(ind.digitos(cnpj)) or {}
    com = [f'{a} ({por_ano[str(a)]["n_campanhas"]} campanha{"s" if por_ano[str(a)]["n_campanhas"] != 1 else ""})' for a in lidos if str(a) in por_ano]
    if not com:
        return ""
    return f'<p class="rs-faixa">Também recebeu em {_lista_anos(com)}. <a href="#anteriores">Ver eleições anteriores</a></p>'


def _campanha_diagrama(eleito, total, href):
    return {"sq": str(eleito["sq"]), "nome_urna": eleito["nome_urna"], "cargo": eleito["cargo"], "uf": eleito["uf"],
            "partido": eleito["partido"], "total": total, "href": href}


def html_fornecedor(id_, rec, campanhas, itens, cfg, bases, anteriores=None, pendentes=None, outras=None):
    """Página de um fornecedor PJ. campanhas: [{eleito, caminho, cnpj, nome, total, tipos}] das campanhas publicadas que o
    pagaram; itens: [{eleito, caminho, **indicador}] em que ele é a contraparte. MEI (ou sem cadastro): só o CNPJ mascarado,
    sem razão social, sem sócios. `anteriores` (envelope de rastro/dados/anteriores.json, opcional) acrescenta a seção de
    eleições anteriores; sem ele a página não muda. `endereco_chave` e `cpf_mascarado` nunca saem.
    Diagrama "Caminho do dinheiro": as publicadas (com link), `pendentes` ([{eleito, total}] de eleitos ainda sem página, sem
    link) e `outras` ({n, valor} das campanhas não eleitas, só agregado)."""
    mei = eh_mei(rec)
    mascara = ind.mascarar_cnpj(campanhas[0]["cnpj"])
    nome = f"MEI · CNPJ {mascara}" if mei else (rec.get("razao") or campanhas[0].get("nome") or mascara)
    if rec is None:
        cad = '<p class="rs-vazio">Cadastro da Receita não localizado; por isso o fornecedor aparece só pelo CNPJ mascarado.</p>'
    else:
        sim = lambda v: "sim" if v else "não"
        linhas = [("Situação cadastral", rec.get("situacao") or "não informada"),
                  ("Abertura", data_br(rec.get("abertura")) or "não informada"),
                  ("Atividade principal (CNAE)", rec.get("cnae") or "não informada"),
                  ("Optante pelo Simples", sim(rec.get("simples"))), ("MEI", sim(rec.get("mei")))]
        cad = ('<table class="rs-tab"><tbody>' + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in linhas) + "</tbody></table>")
    socios = ""
    if not mei:
        nomes = sorted({s["nome"] for s in rec.get("socios") or [] if s.get("nome")})
        socios = ("<h2>Quadro societário</h2>" + (f'<ul>{"".join(f"<li>{esc(n)}</li>" for n in nomes)}</ul>' if nomes
                  else '<p class="rs-vazio">Nenhum sócio informado na base.</p>'))
    camp = sorted(campanhas, key=lambda c: (-(c.get("total") or 0), c["eleito"]["nome_urna"]))
    linhas_c = "".join(
        f'<tr><td><a href="/{c["caminho"]}">{esc(c["eleito"]["nome_urna"])}</a><small>{esc(_rotulo_cargo(c["eleito"]))}'
        + (f' · {esc("; ".join(c["tipos"]))}' if c.get("tipos") else "") + f'</small></td><td class="v">{ind.brl(c.get("total") or 0)}</td></tr>'
        for c in camp)
    total = sum(c.get("total") or 0 for c in camp)
    camp_h = (f'<h2>Campanhas publicadas que o contrataram</h2><p class="rs-total">{len(camp)} campanha(s) · contratado: {ind.brl(total)}</p>'
              f'<table class="rs-tab"><thead><tr><th>Eleito(a)</th><th class="v">Contratado</th></tr></thead><tbody>{linhas_c}</tbody></table>')
    ant_h = secao_anteriores(campanhas[0]["cnpj"], anteriores, cfg) if anteriores else ""
    camp_d = ([_campanha_diagrama(c["eleito"], c.get("total") or 0, "/" + c["caminho"]) for c in camp]
              + [_campanha_diagrama(p["eleito"], p.get("total") or 0, None) for p in pendentes or []])
    diag_h = ('<section class="rs-diagrama"><h2>Caminho do dinheiro</h2>'
              + diagramas.diagrama_fornecedor(campanhas[0]["cnpj"], nome, camp_d, outras, int(cfg.get("rede_max_campanhas") or 12), mei)
              + (faixa_anteriores(campanhas[0]["cnpj"], anteriores, cfg) if anteriores else "")
              + '<p class="rs-nota">Valores contratados, da prestação de contas parcial. Campanhas não eleitas entram somadas, sem nome. '
                'Eleitos ainda sem página aparecem sem link.</p></section>')
    if mei:
        itens = [i for i in itens if i["nome"] not in HOMONIMO]  # casamento por nome com sócio: sócio de MEI fica fora
    if itens:
        por_camp = {}
        for i in itens:
            por_camp.setdefault(i["caminho"], []).append(i)
        blocos = []
        for cam_, its in por_camp.items():
            lis = "".join(f'<li><b class="rs-rot">{esc(rotulo(i["nome"]))}</b>: {esc(i["fato"])} {_fonte(i)}{_hom(i)}</li>' for i in its)
            blocos.append(f'<h3>Campanha de <a href="/{cam_}">{esc(rotulo_eleito(its[0]["eleito"]))}</a></h3><ul class="rs-ind">{lis}</ul>')
        ind_h = f'<h2>Indicadores em que é a contraparte</h2>{"".join(blocos)}'
    else:
        ind_h = '<h2>Indicadores em que é a contraparte</h2><p class="rs-vazio">Nenhum indicador disparado para este fornecedor.</p>'
    base = (f'contas do TSE até {data_br(bases["contas"])}' if bases.get("contas") else "data das contas não informada") + (
        f' · cadastro de empresas da Receita de {data_br(bases["receita"])}' if bases.get("receita") else "")
    corpo = (trilha(("Início", "/"), ("Rastro do dinheiro", "/rastro/"), ("Fornecedor", None))
             + f'<p class="rs-kicker">Rastro do dinheiro · fornecedor</p><h1>{esc(nome)}</h1>'
             f'<p class="rs-meta">CNPJ {esc(mascara)}</p><p class="rs-base">Base de dados: {esc(base)}.</p>'
             + aviso_bloco() + f"<h2>Cadastro na Receita</h2>{cad}{socios}{diag_h}{camp_h}{ant_h}{ind_h}"
             + bloco_contestar(cfg, f"Contestar dado: fornecedor {id_[:8]}"))
    return pagina(f"{nome} · Rastro do dinheiro", corpo)


def _parcial_eleito(contas):
    """O que a página do eleito usa para mostrar indicadores: prestação parcial publicada."""
    return bool(contas) and contas.get("prestacao_parcial") is not False


def _parcial(contas):
    return bool(contas) and contas.get("prestacao_parcial") is not False and bool(contas.get("despesas"))


def _ordem_eleitos(entradas):
    ordem = list(CARGOS)
    return sorted(entradas, key=lambda e: (ordem.index(e["eleito"]["cargo"]) if e["eleito"]["cargo"] in ordem else 99,
                                           -(e["eleito"].get("votos") or 0), e["eleito"]["nome_urna"]))


def tabela_pendentes(pendentes):
    """Eleitos fora de publicados.json: nome, cargo, gasto e nº de indicadores, sem link (a página ainda não existe)."""
    if not pendentes:
        return ""
    linhas = []
    for e in _ordem_eleitos(pendentes):
        el = e["eleito"]
        gasto = ind.brl(e["contas"]["despesas"].get("total_contratado") or 0) if _parcial(e["contas"]) else "sem prestação parcial publicada"
        linhas.append(f'<tr id="{busca.ancora_eleito(el["sq"])}"><td>{esc(el["nome_urna"])}<small>{esc(_rotulo_cargo(el))}</small></td><td class="v">{esc(gasto)}</td>'
                      f'<td class="v">{len(e["itens"])}</td></tr>')
    return (f'<h2 id="pendentes">Eleitos ainda sem página</h2><p>{len(pendentes)} eleitos entram nos próximos lotes. Os indicadores contados aqui ainda '
            'não foram revisados numa página própria.</p><table class="rs-tab"><thead><tr><th>Eleito(a)</th><th class="v">Contratado</th>'
            f'<th class="v">Indicadores</th></tr></thead><tbody>{"".join(linhas)}</tbody></table>')


def secao_rede(rede):
    """'Empresas que atendem mais eleitos': rede = {ranking: [{id, rotulo, mei, n_eleitos, n_partidos, total}], diagrama: html}."""
    if rede is None:
        return ""
    linhas = "".join(
        f'<tr><td><a href="/rastro/fornecedor/{r["id"]}/">{esc(r["rotulo"])}</a><small>{r["n_partidos"]} partido(s){" · MEI" if r["mei"] else ""}</small></td>'
        f'<td class="v">{r["n_eleitos"]}</td><td class="v">{ind.brl(r["total"])}</td></tr>' for r in rede["ranking"])
    tab = (f'<table class="rs-tab"><thead><tr><th>Empresa</th><th class="v">Eleitos</th><th class="v">Contratado pelos eleitos</th></tr></thead>'
           f'<tbody>{linhas}</tbody></table>' if linhas else '<p class="rs-vazio">Nenhuma empresa atende 2 ou mais eleitos publicados.</p>')
    return ('<section id="rede"><h2>Empresas que atendem mais eleitos</h2><p class="rs-nota">Número de eleitos publicados que declararam '
            'pagar a empresa: uma contagem, um fato contábil, e não um ranking de risco. Contratar o mesmo fornecedor é comum.</p>'
            + tab + '<p class="rs-nota">Não listadas: plataformas de pagamento e anúncio (lista na <a href="/rastro/metodologia/#rede">metodologia</a>).</p>'
            + (rede.get("diagrama") or "") + "</section>")


def bloco_presidentes(presidentes):
    """'Presidente · 2º turno': um link por candidato, com o contratado (ou a frase de sem prestação, nunca 'R$ 0')."""
    if not presidentes:
        return ""
    linhas = "".join(
        f'<tr id="{busca.ancora_eleito(e["eleito"]["sq"])}"><td><a href="/{e["caminho"]}">{esc(e["eleito"]["nome_urna"])}</a>'
        f'<small>{esc(_rotulo_cargo(e["eleito"]))} · contas e debates</small></td><td class="v">'
        f'{esc(ind.brl(e["contas"]["despesas"].get("total_contratado") or 0) if _parcial(e["contas"]) else "sem prestação parcial publicada")}</td></tr>'
        for e in presidentes)
    return ('<h2 id="presidente">Presidente · 2º turno</h2><p class="rs-nota">Os dois candidatos do 2º turno: contas de campanha e '
            'as afirmações checadas nos debates. Não entram nos totais dos eleitos abaixo.</p><table class="rs-tab"><thead><tr>'
            f'<th>Candidato(a)</th><th class="v">Contratado</th></tr></thead><tbody>{linhas}</tbody></table>')


def html_home(entradas, fornecedores, cfg, bases, pendentes=None, rede=None, presidentes=None):
    """entradas: [{eleito, caminho, contas, itens}] dos publicados; fornecedores: [{id, rotulo, mei, total, n}] já agregados.
    pendentes: [{eleito, contas, itens}] dos eleitos ainda sem página (tabela sem link). rede: ver `secao_rede`.
    presidentes: entradas dos candidatos do 2º turno (bloco próprio, fora das somas).
    Só entra nas somas quem tem prestação parcial publicada; eleito sem contas aparece sem 'R$ 0'."""
    base = (f'contas do TSE até {data_br(bases["contas"])}' if bases.get("contas") else "data das contas não informada") + (
        f' · cadastro de empresas da Receita de {data_br(bases["receita"])}' if bases.get("receita") else "")
    cab = (trilha(("Início", "/"), ("Rastro do dinheiro", None), busca=False) + '<p class="rs-kicker">Rastro do dinheiro · eleições 2026</p>'
           "<h1>Rastro do dinheiro</h1>" + caixa_busca(grande=True) +
           "<p class=\"rs-meta\">Para onde foi o dinheiro de campanha dos eleitos de 2026, cruzando as contas do TSE com o cadastro de empresas da Receita.</p>"
           f'<p class="rs-base">Base de dados: {esc(base)}.</p>' + aviso_bloco() + bloco_presidentes(presidentes))
    fim = bloco_contestar(cfg, "Contestar dado do Rastro")
    pend_h = tabela_pendentes(pendentes)
    if not entradas:
        return pagina("Rastro do dinheiro · Eleições 2026",
                      f'{cab}<p class="rs-vazio" id="eleitos">Nenhuma página publicada ainda. Os primeiros eleitos entram aqui em lotes.</p>{pend_h}{fim}')

    def parcial(e):
        return _parcial(e["contas"])

    por_cargo = {}
    for e in entradas:
        if parcial(e):
            por_cargo[e["eleito"]["cargo"]] = por_cargo.get(e["eleito"]["cargo"], 0) + (e["contas"]["despesas"].get("total_contratado") or 0)
    ordem = list(CARGOS)
    linhas_cargo = "".join(f'<tr><td>{esc(CARGOS.get(c, c))}</td><td class="v">{ind.brl(v)}</td></tr>'
                           for c, v in sorted(por_cargo.items(), key=lambda kv: (ordem.index(kv[0]) if kv[0] in ordem else 99, kv[0])))
    cargo_h = ("<h2>Total contratado por cargo</h2>" + (f'<table class="rs-tab"><thead><tr><th>Cargo</th><th class="v">Contratado</th></tr></thead><tbody>{linhas_cargo}</tbody></table>'
               if linhas_cargo else '<p class="rs-vazio">Nenhum eleito publicado tem prestação parcial publicada ainda.</p>'))
    n = int(cfg.get("home_top_n") or 10)
    top = sorted(fornecedores, key=lambda f: (-f["total"], f["rotulo"]))[:n]
    linhas_f = "".join(f'<tr><td><a href="/rastro/fornecedor/{f["id"]}/">{esc(f["rotulo"])}</a><small>{f["n"]} campanha(s){" · MEI" if f["mei"] else ""}</small></td>'
                       f'<td class="v">{ind.brl(f["total"])}</td></tr>' for f in top)
    forn_h = ("<h2>Maiores fornecedores entre os publicados</h2>" + (f'<table class="rs-tab"><thead><tr><th>Fornecedor</th><th class="v">Contratado</th></tr></thead><tbody>{linhas_f}</tbody></table>'
              if linhas_f else '<p class="rs-vazio">Nenhum fornecedor pessoa jurídica nas páginas publicadas.</p>'))
    linhas_e = []
    for e in _ordem_eleitos(entradas):
        el = e["eleito"]
        gasto = (ind.brl(e["contas"]["despesas"].get("total_contratado") or 0) if parcial(e) else "sem prestação parcial publicada")
        votos = f'{el["votos"]:,}'.replace(",", ".") + " votos" if el.get("votos") else ""
        linhas_e.append(f'<tr id="{busca.ancora_eleito(el["sq"])}"><td><a href="/{e["caminho"]}">{esc(el["nome_urna"])}</a><small>{esc(_rotulo_cargo(el))}'
                        f'{" · " + votos if votos else ""}</small></td><td class="v">{esc(gasto)}</td></tr>')
    eleitos_h = ('<h2 id="eleitos">Eleitos publicados</h2><table class="rs-tab"><thead><tr><th>Eleito(a)</th><th class="v">Contratado</th></tr></thead>'
                 f'<tbody>{"".join(linhas_e)}</tbody></table>')
    cont = Counter(rotulo(i["nome"]) for e in entradas if parcial(e) for i in e["itens"]  # só o que a página do eleito mostra
                   if i["nome"] != "multicampanha")
    lis = "".join(f'<li><b class="rs-rot">{esc(nome)}</b>: {q} ocorrência(s)</li>' for nome, q in sorted(cont.items(), key=lambda kv: (-kv[1], kv[0])))
    ind_h = ("<h2>Indícios mais frequentes entre os publicados</h2>" + (f'<ul class="rs-ind">{lis}</ul><p>O que cada indicador mede: <a href="/rastro/metodologia/">metodologia</a>.</p>'
             if lis else '<p class="rs-vazio">Nenhum indicador disparado nas páginas publicadas.</p>'))
    return pagina("Rastro do dinheiro · Eleições 2026", cab + cargo_h + forn_h + secao_rede(rede) + eleitos_h + ind_h + pend_h + fim)


def aplicar_correcoes(paginas, correcoes):
    """Inclui a seção 'Correções' (data e o que mudou) na página do `path` de cada correção; as outras não mudam.
    Path inexistente ou texto com CPF/termo proibido levanta ValueError. `correcoes`: lista ou envelope {correcoes: [...]}."""
    lista = correcoes.get("correcoes") if isinstance(correcoes, dict) else correcoes
    por_path = {p["path"]: p for p in paginas}
    achadas = {}
    for c in lista or []:
        path = "/" + str(c.get("path") or "").strip("/") + "/"
        if path not in por_path:
            raise ValueError(f"correção com path inexistente: {c.get('path')!r}")
        if not (c.get("o_que_mudou") or "").strip():
            raise ValueError(f"correção sem 'o_que_mudou': {path}")
        data = data_br(c.get("data"))
        if not data:
            raise ValueError(f"correção sem data: {path}")
        url = c.get("fonte_url")
        if url and not str(url).startswith(("https://", "http://")):
            raise ValueError(f"correção com fonte_url inválida: {path}")
        varrer(f"correção {path}", f'{c["o_que_mudou"]} {url or ""}')
        fonte = f' <a href="{html.escape(url, quote=True)}" rel="noopener">fonte</a>' if url else ""
        achadas.setdefault(path, []).append(f'<li><b>{data}</b>: {esc(c["o_que_mudou"].strip())}{fonte}</li>')
    for path, lis in achadas.items():
        p = por_path[path]
        sec = f'<section id="correcoes"><h2>Correções</h2><ul>{"".join(lis)}</ul></section>'
        if '<section id="contestar">' not in p["html"]:
            raise ValueError(f"página sem bloco de contestação: {path}")
        marca = '<footer class="rs-rodape">' if '<footer class="rs-rodape">' in p["html"] else '<section id="contestar">'
        p["html"] = p["html"].replace(marca, sec + marca, 1)
    return paginas


def _meta(path, titulo, desc, html_, passos):
    return {"path": "/" + path, "titulo": titulo, "desc": desc, "html": html_, "crumbs": [("Rastro do dinheiro", "/rastro/")] + passos}


def _chave_contraparte(f, rec, mei):
    """Como o indicador chama este fornecedor: CNPJ mascarado (MEI) ou nome."""
    return {ind.mascarar_cnpj(f["cnpj"])} if mei else {n for n in (f.get("nome"), (rec or {}).get("razao")) if n}


def _itens_do_fornecedor(f, rec, mei, pj_campanha, itens):
    """Indicadores da campanha em que `f` é a contraparte; ambíguo (outro fornecedor da campanha com o mesmo nome/máscara) fica de fora."""
    chaves = _chave_contraparte(f, rec, mei)
    for g in pj_campanha:
        if ind.digitos(g.get("cnpj")) != ind.digitos(f["cnpj"]) and chaves & _chave_contraparte(g, None, eh_mei(None) if mei else False):
            return []
    return [i for i in itens if i.get("contraparte") in chaves or chaves & set(i.get("contrapartes") or [])]


def rede_fornecedores(agg, entradas, pendentes, por_sq, cfg, agregados=None):
    """Rede de fornecedores entre campanhas. Preenche, em cada a de `agg`, `pendentes` ([{eleito, total}] dos eleitos ainda sem
    página) e `outras` ({n, valor} das campanhas não eleitas de agregados.json, valor = total_recebido − soma conhecida, piso 0).
    Devolve (rede da home, {sq: lista cruzada da página do eleito}). Plataformas de `rede_excluir_cnpj_raiz` ficam fora da rede
    (ranking, diagrama e lista cruzada), mas a página delas tem o diagrama normal."""
    por_cnpj_agr = (agregados or {}).get("por_cnpj") or {}
    for a in agg.values():
        a["pendentes"], a["outras"] = [], None
    for p in pendentes:
        if not p["contas"] or p["contas"].get("prestacao_parcial") is False:
            continue
        for f in (p["contas"].get("despesas") or {}).get("fornecedores_pj") or []:
            a = agg.get(ind.digitos(f.get("cnpj")))
            if a:
                a["pendentes"].append({"eleito": p["eleito"], "total": f.get("total") or 0})
    for cnpj, a in agg.items():
        g = por_cnpj_agr.get(cnpj)
        if not g:
            continue
        nao_eleitos = {str(s) for s in g.get("campanhas") or []} - set(por_sq)
        conhecido = sum(c["total"] for c in a["campanhas"]) + sum(p["total"] for p in a["pendentes"])
        if nao_eleitos:
            a["outras"] = {"n": len(nao_eleitos), "valor": max(float(g.get("total_recebido") or 0) - conhecido, 0)}
    fora = raizes_excluidas(cfg)
    na_rede = {c: a for c, a in agg.items() if c[:8] not in fora}
    eleitos_de = {}
    for c, a in na_rede.items():
        vistos = {}
        for camp in a["campanhas"]:
            el = camp["eleito"]
            if el["cargo"] == "presidente":
                continue  # candidato(a) ao 2º turno, não eleito(a): fica fora da rede entre eleitos
            v = vistos.setdefault(str(el["sq"]), {"sq": str(el["sq"]), "nome_urna": el["nome_urna"], "uf": el["uf"], "partido": el["partido"],
                                                  "total": 0, "href": "/" + camp["caminho"], "caminho": camp["caminho"]})
            v["total"] += camp["total"]
        eleitos_de[c] = list(vistos.values())
    ranking = [{"cnpj": c, "id": na_rede[c]["id"], "rotulo": na_rede[c]["rotulo"], "mei": na_rede[c]["mei"], "n_eleitos": len(els),
                "n_partidos": len({e["partido"] for e in els}), "total": sum(e["total"] for e in els)}
               for c, els in eleitos_de.items() if len(els) >= 2]
    ranking.sort(key=lambda r: (-r["n_eleitos"], -r["total"], r["rotulo"]))
    ranking = ranking[:int(cfg.get("rede_top_n") or 15)]
    top = [{"cnpj": r["cnpj"], "rotulo": r["rotulo"], "href": f'/rastro/fornecedor/{r["id"]}/'} for r in ranking[:int(cfg.get("rede_diagrama_n") or 5)]]
    rede = {"ranking": ranking, "diagrama": diagramas.diagrama_rede(top, eleitos_de)}
    cruz = {}
    for c, els in eleitos_de.items():
        if len(els) < 2:
            continue
        for e in els:
            cruz.setdefault(e["sq"], []).append({"id": na_rede[c]["id"], "rotulo": na_rede[c]["rotulo"],
                                                 "outros": [o for o in els if o["sq"] != e["sq"]]})
    for lista in cruz.values():
        lista.sort(key=lambda x: (-len(x["outros"]), x["rotulo"]))
    return rede, cruz


def gerar(dest, publicados, eleitos, dir_contas, indicadores, fornecedores, cfg, envolver=None, correcoes=None, sal=None, anteriores=None,
          agregados=None, presidentes=None, debates=None):
    """Grava dest/rastro/index.html (home), metodologia, uma página por sq de `publicados` e uma por fornecedor PJ pago por eles.
    Devolve a lista de páginas ({path, titulo, desc, html, crumbs}). `envolver(página) -> html` acrescenta a moldura do site (opcional).
    indicadores/fornecedores são os envelopes de rastro/dados/*.json; sem eles (e com publicados) falha. `correcoes` é o envelope de
    rastro/correcoes.json; `sal` só é exigido quando há MEI. `anteriores`: envelope de rastro/dados/anteriores.json (opcional).
    `agregados`: rastro/dados/base/agregados.json (opcional), para somar as campanhas não eleitas no diagrama do fornecedor.
    `presidentes` (rastro/presidentes.json): candidatos do 2º turno a presidente, com página própria fora de eleitos.json, da
    fila e das contas da home; `debates` (modelos de debates.pagina.listar) acrescenta a seção 'Nos debates' casando pelo id_tse.
    Todas as páginas passam por `varrer` antes de qualquer gravação."""
    publicados = list(dict.fromkeys(str(s) for s in publicados))
    presidentes = [dict(p, sq=str(p["sq"])) for p in presidentes or []]
    if (publicados or presidentes) and fornecedores is None:
        raise ValueError("sem fornecedores.json: não dá para saber quem é MEI; nada publicado")
    if (publicados or presidentes) and indicadores is None:
        raise ValueError("sem indicadores.json: nada publicado")
    por_sq = {str(e["sq"]): e for e in (eleitos["eleitos"] if isinstance(eleitos, dict) else eleitos)}
    faltam = [s for s in publicados if s not in por_sq]
    if faltam:
        raise ValueError(f"sq publicado fora de eleitos.json: {faltam}")
    sel = [por_sq[s] for s in publicados]
    cam = {**caminhos(sel), **caminhos(presidentes)}
    forn = (fornecedores or {}).get("fornecedores") or {}
    receita = (fornecedores or {}).get("data_base")
    por_ind = (indicadores or {}).get("indicadores") or {}
    nos_debates = dp.placar_por_candidato(debates or [])
    entradas, pres_entradas, agg = [], [], {}
    for n, e in enumerate(sel + presidentes):
        arq = Path(dir_contas) / f"{e['sq']}.json"
        contas = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
        itens = por_ind.get(str(e["sq"])) or []
        (pres_entradas if n >= len(sel) else entradas).append({"eleito": e, "caminho": cam[e["sq"]], "contas": contas, "itens": itens})
        if not contas or contas.get("prestacao_parcial") is False:
            continue  # sem tabela de fornecedores na página do eleito: sem página de fornecedor
        pj = (contas.get("despesas") or {}).get("fornecedores_pj") or []
        for f in pj:
            cnpj = ind.digitos(f.get("cnpj"))
            if len(cnpj) != 14:
                continue
            rec = forn.get(cnpj)
            a = agg.setdefault(cnpj, {"cnpj": cnpj, "rec": rec, "mei": eh_mei(rec), "campanhas": [], "itens": []})
            a["campanhas"].append({"eleito": e, "caminho": cam[e["sq"]], "cnpj": cnpj, "nome": f.get("nome"), "total": f.get("total") or 0, "tipos": f.get("tipos") or []})
            a["itens"] += [{"eleito": e, "caminho": cam[e["sq"]], **i} for i in _itens_do_fornecedor(f, rec, a["mei"], pj, itens)]
    if any(a["mei"] for a in agg.values()) and not sal:
        raise ValueError("há fornecedor MEI publicado e nenhum sal: nada publicado")
    for a in agg.values():
        a["id"] = id_fornecedor(a["cnpj"], a["mei"], sal)
    ids = {c: a["id"] for c, a in agg.items()}
    pendentes = []
    for sq, e in por_sq.items():
        if sq in publicados:
            continue
        arq = Path(dir_contas) / f"{sq}.json"
        pendentes.append({"eleito": e, "contas": json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None,
                          "itens": por_ind.get(sq) or []})
    bases_g = {"contas": (indicadores or {}).get("data_base") or receita, "receita": receita}
    for a in agg.values():
        a["rotulo"] = ind.mascarar_cnpj(a["cnpj"]) if a["mei"] else (a["rec"].get("razao") or a["campanhas"][0].get("nome") or ind.mascarar_cnpj(a["cnpj"]))
    rede, cruz = rede_fornecedores(agg, entradas, pendentes, {**por_sq, **{p["sq"]: p for p in presidentes}}, cfg, agregados)
    for en in entradas + pres_entradas:
        en["html"] = html_eleito(en["eleito"], en["contas"], en["itens"], forn, cfg,
                                 {"contas": (en["contas"] or {}).get("data_base") or bases_g["contas"], "receita": receita}, ids,
                                 cruz.get(str(en["eleito"]["sq"])), nos_debates.get(str(en["eleito"]["sq"])))
    resumo = []
    pres_sq = {p["sq"] for p in presidentes}
    for a in agg.values():
        camps = [c for c in a["campanhas"] if str(c["eleito"]["sq"]) not in pres_sq]  # presidente fica fora dos totais da home
        if camps:
            resumo.append({"id": a["id"], "rotulo": a["rotulo"], "mei": a["mei"], "n": len(camps), "total": sum(c["total"] for c in camps)})
    paginas = [_meta("rastro/", "Rastro do dinheiro | Eleições 2026",
                     "Para onde foi o dinheiro de campanha dos eleitos de 2026: total por cargo, maiores fornecedores e indicadores, com a fonte de cada dado. " + AVISO,
                     html_home(entradas, resumo, cfg, bases_g, pendentes, rede, pres_entradas), []),
               _meta("rastro/metodologia/", "Metodologia do Rastro do dinheiro | Eleições 2026",
                     "Como o Rastro do dinheiro cruza as contas de campanha com o cadastro da Receita, quais indicadores usa, os limiares e o que eles não dizem.",
                     html_metodologia(cfg, (indicadores or {}).get("avisos")), [("Metodologia", None)])]
    for en in entradas:
        e = en["eleito"]
        nome = f"{e['nome_urna']} ({e['partido']}-{e['uf']})"
        paginas.append(_meta(en["caminho"], f"{nome}: receitas, despesas e indicadores | Rastro do dinheiro",
                             f"Receitas por origem, despesas por fornecedor e indicadores de {e['nome_urna']} ({CARGOS.get(e['cargo'], e['cargo'])}, {e['uf']}), "
                             f"com a fonte de cada dado. {AVISO}", en["html"], [(e["nome_urna"], None)]))
    for en in pres_entradas:
        e = en["eleito"]
        paginas.append(_meta(en["caminho"], f"{e['nome_urna']} ({e['partido']}), candidato(a) a presidente: contas de campanha e debates | Rastro do dinheiro",
                             f"Receitas, despesas por fornecedor e indicadores da campanha de {e['nome_urna']} ({e['partido']}) a presidente "
                             f"no 2º turno, e as afirmações checadas nos debates, com a fonte de cada dado. {AVISO}", en["html"],
                             [(e["nome_urna"], None)]))
    for a in sorted(agg.values(), key=lambda a: a["id"]):
        corpo = html_fornecedor(a["id"], a["rec"], a["campanhas"], a["itens"], cfg, bases_g, anteriores, a["pendentes"], a["outras"])
        quem = f"MEI, CNPJ {ind.mascarar_cnpj(a['cnpj'])}" if a["mei"] else a["rotulo"]
        paginas.append(_meta(f"rastro/fornecedor/{a['id']}/", f"{'MEI ' + ind.mascarar_cnpj(a['cnpj']) if a['mei'] else a['rotulo']}: fornecedor de campanha | Rastro do dinheiro",
                             f"Campanhas de 2026 que contrataram {quem}, situação cadastral e indicadores em que aparece. {AVISO}", corpo,
                             [("Fornecedor", None)]))
    if correcoes:
        aplicar_correcoes(paginas, correcoes)
    for p in paginas:
        varrer(p["path"], p["html"])  # antes de gravar qualquer coisa
    indice = busca.serializar(busca.indice(entradas + pres_entradas, pendentes, agg, _rotulo_cargo, _parcial_eleito))
    for nome, texto in indice.items():
        varrer(nome, texto)
    dest = Path(dest)
    for p in paginas:
        saida = dest / p["path"].strip("/") / "index.html"
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(envolver(p) if envolver else p["html"], encoding="utf-8")
    for nome, texto in indice.items():
        (dest / "rastro" / nome).write_text(texto, encoding="utf-8")
    (dest / "rastro" / "busca.js").write_text(BUSCA_JS.read_text(encoding="utf-8"), encoding="utf-8")
    return paginas
