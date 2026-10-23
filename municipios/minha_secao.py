#!/usr/bin/env python3
"""Página "Minha seção" (/minha-secao/, issue #155): onde a pessoa vota e quem ganhou ali (presidente).
Lê o resultado por seção e local de votação de municipios/geo/locais/ (montar_secao.py; o build_site copia a pasta para
/geo/locais/) e grava, em <dest>/minha-secao/, os índices que o navegador usa:
  indice.json   {"mun": [[ibge, nome, UF, arquivo, lat, lon], ...], "part": {número: sigla}, "piso": PISO}
                (arquivo = nome do JSON em /geo/locais/: o código IBGE ou a UF; lat/lon = centro dos locais, ou null)
  cep/<pp>.json {cep5: [ibge, ...]} por fatia dos 2 primeiros dígitos do CEP
  secao.js      a busca (municipios/minha_secao.js), toda no navegador, sem requisição para outro domínio
Sem dados (pasta vazia ou ausente), a página sai "em breve", sem JS. Dado que fure o piso de privacidade barra o build."""
import html
import json
import shutil
from pathlib import Path

import brand
from municipios.montar_secao import PISO

H = Path(__file__).resolve().parent
LOCAIS = H / "geo" / "locais"
META = H / "geo" / "t1" / "meta.json"
JS = H / "minha_secao.js"
FONTE = "https://dadosabertos.tse.jus.br/"
TITULO = "Minha seção: onde eu voto e quem ganhou ali · Eleições 2026"
DESC = ("Busque pela zona e seção do título de eleitor, pelo CEP ou pela sua localização e veja o resultado de presidente "
        "na sua seção e no seu local de votação, com dados abertos do TSE.")


def _arquivos(pasta):
    pasta = Path(pasta)
    return sorted(pasta.glob("*.json")) if pasta.is_dir() else []


def tem_dados(pasta=LOCAIS):
    return bool(_arquivos(pasta))


def carregar(pasta=LOCAIS):
    """{ibge: {"cand", "t", "arq"}} de <ibge>.json (um por município) ou <UF>.json ({ibge: registro}); {} sem dados."""
    dados = {}
    for p in _arquivos(pasta):
        obj = json.loads(p.read_text(encoding="utf-8"))
        regs = {p.stem: obj} if p.stem.isdigit() else obj
        for cdi, reg in regs.items():
            dados[cdi] = {"cand": reg["cand"], "t": reg["t"], "arq": p.stem}
    return dados


def conferir_piso(dados):
    """ValueError se algum local ou seção com comparecimento abaixo do PISO trouxer voto por candidato ou brancos/nulos."""
    for cdi, reg in dados.items():
        for t, locais in reg["t"].items():
            for lc in locais:
                if lc[6] < PISO and (lc[7] is not None or lc[8] is not None):
                    raise ValueError(f"{cdi} turno {t}: local {lc[2]!r} com comparecimento {lc[6]} < {PISO} traz voto")
                for s in lc[9]:
                    if s[3] < PISO and (s[4] is not None or s[5] is not None):
                        raise ValueError(f"{cdi} turno {t}: zona {s[0]} seção {s[1]} com comparecimento {s[3]} < {PISO} traz voto")


def _centro(reg):
    vistos, pts = set(), []
    for locais in reg["t"].values():
        for lc in locais:
            if lc[0] is not None and lc[1] is not None and (lc[0], lc[1], lc[2]) not in vistos:
                vistos.add((lc[0], lc[1], lc[2]))
                pts.append((lc[0], lc[1]))
    if not pts:
        return [None, None]
    return [round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4)]


def indice(dados, meta):
    """indice.json: municípios com dados (ordem: UF, nome), siglas por número do candidato e o piso."""
    nomes = meta.get("mun", {})
    mun = []
    for cdi, reg in dados.items():
        nome, uf = nomes.get(cdi) or [cdi, "" if reg["arq"].isdigit() else reg["arq"]]
        mun.append([cdi, nome, uf, reg["arq"]] + _centro(reg))
    mun.sort(key=lambda m: (m[2], m[1], m[0]))
    part = {str(c["n"]): c["sg"] for c in meta.get("cand", {}).get("presidente", []) if c.get("sg")}
    return {"mun": mun, "part": part, "piso": PISO}


def indice_cep(dados):
    """{2 primeiros dígitos: {cep5: [ibge, ...]}} dos locais com CEP."""
    cep = {}
    for cdi, reg in dados.items():
        for locais in reg["t"].values():
            for lc in locais:
                c = lc[4]
                if c and len(c) == 5 and c.isdigit():
                    lista = cep.setdefault(c[:2], {}).setdefault(c, [])
                    if cdi not in lista:
                        lista.append(cdi)
    return {pp: {c: sorted(v) for c, v in sorted(d.items())} for pp, d in sorted(cep.items())}


CSS = """<style>
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--font-sans)}
main.ms{max-width:880px;margin:0 auto;padding:24px 16px 56px}
.ms a{color:var(--ink);text-decoration-color:var(--muted);text-underline-offset:3px}
.ms-kicker{font:600 12px var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.ms h1{font-size:clamp(24px,5vw,36px);line-height:1.2;margin:0 0 10px;overflow-wrap:anywhere}
.ms h2{font-size:18px;margin:0 0 10px}
.ms-lead{color:var(--ink2);margin:0}
.ms-aviso{margin:18px 0 0;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--amber);border-radius:10px;padding:10px 14px;font-size:15px;color:var(--ink2)}
.ms-aviso b{color:var(--ink)}
.ms-breve{margin:18px 0 0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.ms-breve p{margin:6px 0 0;color:var(--ink2)}
#ms-app[hidden]{display:none}
.ms-buscas{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0 0}
.ms-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0;min-width:0}
.ms-card p{margin:0 0 10px;font-size:14px;color:var(--ink2)}
.ms-campos{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.ms-campos .ms-l{grid-column:1/-1}
.ms label{display:block;font-size:13px;color:var(--ink2)}
.ms input,.ms select{box-sizing:border-box;width:100%;margin-top:3px;font:inherit;font-size:16px;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:0}
.ms input:focus,.ms select:focus,.ms button:focus-visible{outline:2px solid var(--brand);outline-offset:1px}
.ms button{margin-top:10px;width:100%;font:600 15px var(--font-sans);color:var(--ink);background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:9px 12px;cursor:pointer}
.ms button:hover{border-color:var(--muted)}
.ms button:disabled{opacity:.6;cursor:wait}
#ms-res{margin:22px 0 0}
#ms-res:empty{display:none}
.ms-msg{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;color:var(--ink2)}
.ms-res-t{font:600 12px var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.ms-local{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 12px;overflow-wrap:anywhere}
.ms-local h3{font-size:17px;margin:0}
.ms-onde{font-size:14px;color:var(--ink2);margin:2px 0 0}
.ms-turno{margin:12px 0 0;padding:10px 0 0;border-top:1px solid var(--line)}
.ms-turno h4{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;margin:0 0 6px;font:600 12px var(--font-mono);letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.ms-venc{font-size:15px;margin:0 0 8px}
.ms-cands{list-style:none;margin:0;padding:0}
.ms-cands li{margin:0 0 6px}
.ms-cands span{display:flex;justify-content:space-between;gap:12px;font-size:14px}
.ms-cands b{font-variant-numeric:tabular-nums}
.ms-cands i{display:block;height:8px;margin-top:3px;border-radius:4px;background:var(--c);min-width:1px}
.ms-num{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;margin:6px 0 0}
.ms-sig{font-size:14px;color:var(--ink2);margin:0}
.ms-secao{border-left:4px solid var(--brand)}
.ms-sobre{margin:34px 0 0;padding-top:6px;border-top:1px solid var(--line);font-size:14px;color:var(--ink2)}
.ms-sobre h2{margin-top:18px}
.ms-sobre p{margin:6px 0}
@media (max-width:760px){.ms-buscas{grid-template-columns:1fr}}
</style>"""

AVISO = ('<div class="ms-aviso" role="note"><b>Local de votação não é onde a pessoa mora.</b> '
         'O eleitor vota onde o título foi registrado, que pode ser longe de casa (e muita gente nunca transfere). '
         'O resultado de uma escola mostra como votou quem vota ali, não quem mora no bairro.</div>')

SOBRE = f"""<section class="ms-sobre"><h2>Fonte e sigilo</h2>
<p>Votação por seção eleitoral e locais de votação das Eleições 2026, do <a href="{FONTE}" rel="noopener">Portal de Dados Abertos do TSE</a>. Só presidente.</p>
<p>Para proteger o sigilo do voto, seção ou local com menos de {PISO} eleitores que compareceram aparece só com o número de aptos e de comparecimento, sem voto por candidato. Quando esconder um só deixaria o voto dele ser deduzido pela diferença do total, outro item pequeno também perde o voto por candidato.</p>
<p>Seção agregada a outra (no mesmo local) aparece com o número da seção principal.</p>
</section>"""

PRIVACIDADE = ("<p>Sua localização nunca sai do seu aparelho: a distância é calculada aqui, no navegador. "
               "Para mostrar o resultado, a página baixa do próprio site o arquivo do município (ou da faixa de CEP). "
               "Esse pedido é visível ao servidor, como qualquer busca, mas não leva a sua posição.</p>")


def _doc(corpo, js=False):
    script = '<script src="/minha-secao/secao.js" defer></script>' if js else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(TITULO)}</title>'
            f'<style>{brand.CSS}</style>{CSS}</head>'
            f'<body><main class="ms">{corpo}</main>{script}</body></html>')


CABECALHO = ('<header><p class="ms-kicker">Minha seção · presidente</p><h1>Onde eu voto e quem ganhou ali</h1>'
             '<p class="ms-lead">Pela zona e seção do título de eleitor (ou do e-Título), pelo CEP ou pela sua localização: '
             'o local de votação e o resultado de presidente na seção e no local.</p></header>')


def html_com_dados():
    buscas = """<div id="ms-app" hidden><div class="ms-buscas">
<form class="ms-card" id="ms-f-secao" novalidate><h2>Pelo título</h2><p>Zona e seção estão no título e no e-Título.</p>
<div class="ms-campos"><label>UF<select id="ms-uf" required></select></label>
<label>Zona<input id="ms-zona" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="off" required></label>
<label class="ms-l">Município<select id="ms-mun" required></select></label>
<label class="ms-l">Seção<input id="ms-secao" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="off" required></label></div>
<button type="submit">Buscar seção</button></form>
<form class="ms-card" id="ms-f-cep" novalidate><h2>Pelo CEP</h2><p>Locais de votação com o mesmo começo de CEP (5 dígitos).</p>
<label>CEP<input id="ms-cep" inputmode="numeric" maxlength="9" autocomplete="off" placeholder="00000-000" required></label>
<button type="submit">Buscar por CEP</button></form>
<div class="ms-card"><h2>Perto de mim</h2>""" + PRIVACIDADE + """<button type="button" id="ms-perto">Usar minha localização</button></div>
</div><section id="ms-res" aria-live="polite"></section></div>
<noscript><p class="ms-msg">A busca roda no seu navegador e precisa de JavaScript.</p></noscript>"""
    return _doc(CABECALHO + AVISO + buscas + SOBRE, js=True)


def html_em_breve():
    breve = ('<div class="ms-breve"><h2>Em breve</h2><p>O resultado por seção e por local de votação ainda está sendo '
             'preparado a partir dos arquivos do TSE. Quando estiver pronto, esta página passa a ter a busca.</p></div>')
    return _doc(CABECALHO + AVISO + breve + SOBRE)


def gerar(dest, pasta=LOCAIS, meta=None):
    """Escreve dest/minha-secao/ (índices e secao.js, só com dados) e devolve {"tem", "html", "titulo", "desc"};
    o html ainda não tem a moldura do site (build_site.montar_pagina). Confere o piso antes de gravar qualquer coisa."""
    dados = carregar(pasta)
    out = Path(dest) / "minha-secao"
    if not dados:
        out.mkdir(parents=True, exist_ok=True)
        return {"tem": False, "html": html_em_breve(), "titulo": TITULO, "desc": DESC}
    conferir_piso(dados)
    if meta is None:
        meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    js = lambda o: json.dumps(o, separators=(",", ":"), ensure_ascii=False)
    (out / "cep").mkdir(parents=True, exist_ok=True)
    (out / "indice.json").write_text(js(indice(dados, meta)), encoding="utf-8")
    for pp, d in indice_cep(dados).items():
        (out / "cep" / f"{pp}.json").write_text(js(d), encoding="utf-8")
    shutil.copyfile(JS, out / "secao.js")
    return {"tem": True, "html": html_com_dados(), "titulo": TITULO, "desc": DESC}
