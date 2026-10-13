"""Páginas estáticas do Rastro: /rastro/metodologia/ e uma página por eleito publicado (/rastro/<cargo>/<uf>/<slug>/).

Funções puras, sem rede e sem Chrome. `gerar` só escreve dentro de `dest` e, antes de gravar qualquer arquivo, varre o
HTML inteiro: CPF válido ou termo proibido levanta ValueError (nada é publicado em silêncio).
Limiares vêm de rastro/config.json; cores e fontes, de brand.css (dados sem cor própria; o ciano é só da moldura).
"""
import html
import json
import re
import unicodedata
from urllib.parse import quote
from datetime import date
from pathlib import Path

import brand
from rastro import indicadores as ind
from rastro.baixar import URL_CAND
from rastro.contas import URL_CONTAS, cpf_valido

AVISO = "Indicador não é prova de irregularidade."
HOMONIMO = {"socio_doador", "socio_ligado", "socio_nomeado"}  # casados por nome: podem ser outra pessoa
CARGOS = {"governador": "Governador(a)", "senador": "Senador(a)", "depfed": "Deputado(a) federal",
          "depest": "Deputado(a) estadual", "distrital": "Deputado(a) distrital"}
PROIBIDOS = re.compile(r"fraude|laranja|fict[ií]cia", re.I)
RE_CPF_CANDIDATO = re.compile(r"(?<![\d.\-])\d{3}[.\s]?\d{3}[.\s]?\d{3}[\-\s]?\d{2}(?![\d])")
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


def varrer(nome, texto):
    """Levanta ValueError se o HTML tiver CPF válido ou termo proibido."""
    for m in RE_CPF_CANDIDATO.finditer(texto):
        if cpf_valido(re.sub(r"\D", "", m.group())):
            raise ValueError(f"{nome}: CPF válido no HTML ({m.group()[:3]}…); página não publicada")
    m = PROIBIDOS.search(texto)
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
@media (max-width:560px){.rs-tab{font-size:14px}.rs-tab th,.rs-tab td{padding:7px 4px}}
</style>"""


def pagina(titulo, corpo):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(titulo)}</title>'
            f'<style>{brand.CSS}</style>{CSS}</head><body><main id="conteudo" class="rs">{corpo}</main></body></html>')


def trilha(*passos):
    """passos: (rótulo, href|None); o último, sem link."""
    return '<nav class="rs-crumbs" aria-label="Trilha">' + " › ".join(
        f'<a href="{h}">{esc(r)}</a>' if h else esc(r) for r, h in passos) + "</nav>"


def bloco_contestar(cfg, assunto):
    mail = html.escape(cfg["contato_email"], quote=True)
    return (f'<section id="contestar"><h2>Contestar este dado</h2><div class="rs-contestar"><p>Viu um erro, uma informação '
            f'desatualizada ou uma ligação que não procede? Escreva para <a href="mailto:{mail}?subject={html.escape(quote(assunto), quote=True)}">{esc(cfg["contato_email"])}</a> '
            f'com o endereço desta página e a fonte que corrige o dado. Os dados vêm de bases públicas; a correção, quando '
            f'cabível, é publicada.</p></div></section>')


def aviso_bloco():
    return (f'<p class="rs-aviso"><b>{esc(AVISO)}</b> Cada item abaixo é um fato público, com link para a fonte. '
            f'Como lemos, e o que cada indicador não diz: <a href="/rastro/metodologia/">metodologia</a>.</p>')


def tabela_receitas(rec):
    linhas = "".join(f'<tr><td>{esc(o)}</td><td class="v">{ind.brl(v)}</td></tr>'
                     for o, v in sorted((rec.get("por_origem") or {}).items(), key=lambda kv: (-kv[1], kv[0])))
    return (f'<p class="rs-total">Total: {ind.brl(rec.get("total") or 0)}</p>'
            f'<table class="rs-tab"><thead><tr><th>Origem</th><th class="v">Valor</th></tr></thead><tbody>{linhas}</tbody></table>')


def _linha_fornecedor(f, forn):
    cnpj = ind.digitos(f.get("cnpj"))
    rec = (forn or {}).get(cnpj)
    if rec is not None and rec.get("mei") is False:
        nome = esc(f.get("nome") or rec.get("razao") or ind.mascarar_cnpj(cnpj))
    else:  # MEI, ou sem cadastro para saber: só o CNPJ mascarado (o nome pode ser o da pessoa)
        nome = f'{ind.mascarar_cnpj(cnpj)}<small>{"MEI" if rec else "cadastro da Receita não localizado"}</small>'
    tipos = "; ".join(f.get("tipos") or [])
    return (f'<tr><td>{nome}{f"<small>{esc(tipos)}</small>" if tipos else ""}</td>'
            f'<td class="v">{ind.brl(f.get("total") or 0)}</td></tr>')


def tabela_despesas(desp, forn):
    pj = desp.get("fornecedores_pj") or []
    cab = '<table class="rs-tab"><thead><tr><th>Fornecedor (pessoa jurídica)</th><th class="v">Contratado</th></tr></thead><tbody>'
    linhas = [_linha_fornecedor(f, forn) for f in pj]
    out = [f'<p class="rs-total">Contratado: {ind.brl(desp.get("total_contratado") or 0)} · pago: {ind.brl(desp.get("total_pago") or 0)}</p>']
    if pj:
        out.append(cab + "".join(linhas[:20]) + "</tbody></table>")
        if len(linhas) > 20:
            out.append(f'<details><summary>Mais {len(linhas) - 20} fornecedores</summary>{cab}{"".join(linhas[20:])}</tbody></table></details>')
    pf = desp.get("fornecedores_pf") or {}
    if pf.get("qtd"):  # pessoa física: nunca nome, só contagem, total e tipo de despesa
        tipos = "".join(f'<tr><td>{esc(t)}</td><td class="v">{ind.brl(v)}</td></tr>' for t, v in sorted((pf.get("por_tipo") or {}).items()))
        out.append(f'<p class="rs-total" style="margin-top:16px">Pessoas físicas: {pf["qtd"]} pagas, {ind.brl(pf.get("total") or 0)}</p>'
                   + (f'<table class="rs-tab"><thead><tr><th>Tipo de despesa</th><th class="v">Valor</th></tr></thead><tbody>{tipos}</tbody></table>' if tipos else ""))
    return "".join(out)


def lista_indicadores(itens, base):
    if not itens:
        return f'<p class="rs-vazio">Nenhum indicador disparado para esta candidatura na base de {esc(base)}.</p>'
    lis = []
    for i in itens:
        extra = f'<span class="rs-ctp">Fornecedor: {esc(i["contraparte"])}</span>' if i.get("contraparte") else ""
        hom = ('<span class="rs-hom">Casado por nome: pode ser homônimo.</span>'
               if i["nome"] in HOMONIMO and "homônimo" not in i["fato"] else "")
        lis.append(f'<li><code>{esc(i["nome"])}</code>: {esc(i["fato"])} <a href="{html.escape(i["fonte_url"], quote=True)}" rel="noopener">fonte</a>{extra}{hom}</li>')
    return f'<ul class="rs-ind">{"".join(lis)}</ul>'


def html_eleito(eleito, contas, itens, fornecedores, cfg, bases):
    """bases: {'contas': iso, 'receita': iso|None}. contas None (ou prestacao_parcial False): sem valores, sem 'R$ 0'."""
    nome = eleito["nome_urna"]
    partes = [f'{esc(CARGOS.get(eleito["cargo"], eleito["cargo"]))} · {esc(eleito["uf"])} · {esc(eleito["partido"])}']
    base = (f'contas do TSE até {data_br(bases["contas"])}' if bases.get("contas") else "data das contas não informada") + (f' · cadastro de empresas da Receita de {data_br(bases["receita"])}' if bases.get("receita") else "")
    parcial = bool(contas) and contas.get("prestacao_parcial") is not False
    if not parcial:
        fin = f'<p class="rs-vazio">{SEM_PRESTACAO}</p>'
        rec_h = desp_h = ""
    else:
        rec = contas.get("receitas")
        desp = contas.get("despesas")
        rec_h = f'<h2>Receitas por origem</h2>{tabela_receitas(rec) if rec else "<p class=rs-vazio>Receitas ainda não declaradas na base.</p>"}'
        desp_h = f'<h2>Despesas por fornecedor</h2>{tabela_despesas(desp, fornecedores) if desp else "<p class=rs-vazio>Despesas ainda não declaradas na base.</p>"}'
        fin = ""
    ind_h = f'<h2>Indicadores</h2>{lista_indicadores(itens, data_br(bases["contas"]) or "data não informada")}' if parcial else ""
    corpo = (trilha(("Início", "/"), ("Metodologia do Rastro", "/rastro/metodologia/"), (nome, None))
             + f'<p class="rs-kicker">Rastro do dinheiro · eleito(a) 2026</p><h1>{esc(nome)}</h1>'
             f'<p class="rs-meta">{partes[0]}</p><p class="rs-base">Base de dados: {esc(base)}.</p>'
             + aviso_bloco() + fin + rec_h + desp_h + ind_h
             + bloco_contestar(cfg, f"Contestar dado: {nome} ({eleito['uf']})"))
    return pagina(f"{nome} · Rastro do dinheiro", corpo)


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
        ("preco_fora_da_curva", f"Gasto num tipo de despesa acima do percentil {c['percentil_comparacao']} das campanhas do mesmo cargo e UF (comparação só em grupos com {c['min_campanhas_grupo']} campanhas ou mais)."),
        ("gasto_por_voto", f"Custo por voto (contratado dividido pelos votos) acima do percentil {c['percentil_comparacao']} das campanhas do mesmo cargo e UF (grupos com {c['min_campanhas_grupo']} campanhas ou mais)."),
        ("transferencia_candidato", f"Repasse a outro candidato que usou fornecedores em comum. Destacado quando o recebedor teve votação ínfima, menos de {_pct(c['votacao_infima_fracao_eleitorado'])} do eleitorado da UF."),
        ("pessoal_pf", f"Campanha que pagou {c['pf_qtd_min']} pessoas físicas ou mais; pessoas pagas por {c['pf_repetido_min_campanhas']} campanhas ou mais; ao menos {c['pf_redondo_alto_min_qtd']} pagamentos de {ind.brl(c['pf_valor_alto'])} ou mais em múltiplos de {ind.brl(c['pf_redondo_multiplo'])}. Pessoa física aparece só como contagem e total, nunca com nome."),
        ("saque_especie", "Lançamentos de saque ou pagamento em espécie no extrato bancário da conta da campanha."),
        ("pagamento_tardio", f"Pagamentos registrados depois do dia da eleição ({data_br(c['dia_eleicao'])}), ou mais de {_pct(c['tardio_pct_ultimos_dias'])} do total pago nos {c['tardio_dias']} dias até a eleição."),
    ]


def html_metodologia(cfg):
    dl = "".join(f"<dt>{n}</dt><dd>{t}</dd>" for n, t in descricoes(cfg))
    nom = (cfg.get("nomeacoes_fontes") or {}).get("siape") or ""
    nom = nom.format(mes=cfg["nomeacoes_mes"].replace("-", "")) if nom else ""
    fontes = (f'<ul><li>Prestação de contas parcial das campanhas, candidatos e eleitos: <a href="{URL_CONTAS}" rel="noopener">TSE, dados abertos</a> '
              f'e <a href="{URL_CAND}" rel="noopener">cadastro de candidatos</a>.</li>'
              f'<li>Cadastro de empresas (situação, atividade, endereço e quadro societário): <a href="{ind.FONTE_RECEITA}" rel="noopener">Receita Federal, dados abertos do CNPJ</a>.</li>'
              + (f'<li>Servidores com função comissionada ({cfg["nomeacoes_mes"][5:]}/{cfg["nomeacoes_mes"][:4]}): <a href="{nom}" rel="noopener">Portal da Transparência</a>.</li>' if nom else "")
              + "</ul>")
    corpo = (trilha(("Início", "/"), ("Metodologia do Rastro", None))
             + '<p class="rs-kicker">Rastro do dinheiro</p><h1>Metodologia</h1>'
             '<p class="rs-meta">Como cada página de eleito é montada e o que ela não diz.</p>' + aviso_bloco()
             + "<h2>O que é</h2><p>Para cada eleito publicado, cruzamos a prestação de contas da campanha (TSE) com o cadastro de empresas da "
               "Receita. Mostramos receitas por origem, despesas por fornecedor e os indicadores que dispararam, cada um com o fato e o link da fonte. "
               "Não afirmamos que houve irregularidade: apontamos onde vale conferir.</p>"
             + f"<h2>Fontes</h2>{fontes}"
             + f"<h2>Indicadores e limiares</h2><p>Os limiares abaixo são os do arquivo de configuração do projeto, os mesmos usados para gerar as páginas.</p><dl>{dl}</dl>"
             + "<h2>Limites</h2><ul>"
               "<li>Parentesco não consta em nenhuma base pública. Não inferimos parentesco.</li>"
               "<li>“Mesmo sobrenome” é um fato textual: duas pessoas com o mesmo sobrenome não são, por isso, parentes.</li>"
               "<li>O casamento por nome (sócio com doador, candidato ou servidor) pode errar com homônimos; por isso o texto avisa “pode ser homônimo”.</li>"
               "<li>A prestação de contas é parcial e muda até a prestação final; a data da base está em cada página.</li>"
               "<li>Pessoas físicas pagas aparecem só como contagem e total; MEI aparece só pelo CNPJ mascarado. Nenhum CPF é publicado.</li></ul>"
             + bloco_contestar(cfg, "Contestar dado do Rastro"))
    return pagina("Metodologia · Rastro do dinheiro", corpo)


def _meta(path, titulo, desc, html_, passos):
    return {"path": "/" + path, "titulo": titulo, "desc": desc, "html": html_, "crumbs": passos}


def gerar(dest, publicados, eleitos, dir_contas, indicadores, fornecedores, cfg, envolver=None):
    """Grava dest/rastro/metodologia/index.html e uma página por sq de `publicados`. Devolve a lista de páginas
    ({path, titulo, desc, html, crumbs}). `envolver(página) -> html` acrescenta a moldura do site (opcional).
    indicadores/fornecedores são os envelopes de rastro/dados/*.json; sem eles (e com publicados) falha."""
    publicados = list(dict.fromkeys(str(s) for s in publicados))
    if publicados and fornecedores is None:
        raise ValueError("sem fornecedores.json: não dá para saber quem é MEI; nada publicado")
    if publicados and indicadores is None:
        raise ValueError("sem indicadores.json: nada publicado")
    por_sq = {str(e["sq"]): e for e in (eleitos["eleitos"] if isinstance(eleitos, dict) else eleitos)}
    faltam = [s for s in publicados if s not in por_sq]
    if faltam:
        raise ValueError(f"sq publicado fora de eleitos.json: {faltam}")
    sel = [por_sq[s] for s in publicados]
    cam = caminhos(sel)
    forn = (fornecedores or {}).get("fornecedores") or {}
    receita = (fornecedores or {}).get("data_base")
    por_ind = (indicadores or {}).get("indicadores") or {}
    paginas = [_meta("rastro/metodologia/", "Metodologia do Rastro do dinheiro | Eleições 2026",
                     "Como o Rastro do dinheiro cruza as contas de campanha com o cadastro da Receita, quais indicadores usa, os limiares e o que eles não dizem.",
                     html_metodologia(cfg), [("Metodologia", None)])]
    for e in sel:
        arq = Path(dir_contas) / f"{e['sq']}.json"
        contas = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
        base_contas = (contas or {}).get("data_base") or (indicadores or {}).get("data_base") or receita
        corpo = html_eleito(e, contas, por_ind.get(str(e["sq"])) or [], forn, cfg, {"contas": base_contas, "receita": receita})
        nome = f"{e['nome_urna']} ({e['partido']}-{e['uf']})"
        paginas.append(_meta(cam[e["sq"]], f"{nome}: receitas, despesas e indicadores | Rastro do dinheiro",
                             f"Receitas por origem, despesas por fornecedor e indicadores de {e['nome_urna']} ({CARGOS.get(e['cargo'], e['cargo'])}, {e['uf']}), "
                             f"com a fonte de cada dado. {AVISO}", corpo,
                             [(e["nome_urna"], None)]))
    for p in paginas:
        varrer(p["path"], p["html"])  # antes de gravar qualquer coisa
    dest = Path(dest)
    for p in paginas:
        saida = dest / p["path"].strip("/") / "index.html"
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(envolver(p) if envolver else p["html"], encoding="utf-8")
    return paginas
