#!/usr/bin/env python3
"""Gera o site estático em site/: página principal (relatório final), uma página por leitura da apuração,
SEO (meta, Open Graph, JSON-LD, sitemap, robots) e GEO (llms.txt, FAQ visível, texto pré-renderizado).
Pré-renderiza cada página com Chrome headless (--dump-dom) para que o texto já esteja no HTML.
Uso: python3 relatorio/montar.py && python3 build_site.py"""
import json, os, re, shutil, sys, subprocess, threading, functools, html, http.server, socketserver, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import brand
import navegacao as NAV

BASE = "https://eleicoes2026.vitorpereira.ia.br"
SITE_NAME = "Eleições 2026 · Apuração e resultados"
AUTOR = dict(nome="Vitor Onofre Pereira", url="https://vitorpereira.ia.br")
AUTOR_PERFIS = ["https://vitorpereira.ia.br", "https://www.linkedin.com/in/vitor-onofre-pereira/", "https://github.com/vitoropereira",
                "https://x.com/VITORONOFRE", "https://www.instagram.com/vitorpereirasaas/", "https://www.tabnews.com.br/vitorpereirasaas",
                "https://www.youtube.com/@vitoropereira"]
R = Path(__file__).parent


def config(chave, env_file=None):
    """valor de configuração do build: os.environ primeiro, depois CHAVE=valor no .env da raiz; "" se não houver"""
    if os.environ.get(chave):
        return os.environ[chave].strip()
    arq = env_file or R / ".env"
    if arq.exists():
        for linha in arq.read_text().splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                if k.strip() == chave:
                    return v.strip().strip("\"'")
    return ""


# medições: GA4 e Clarity, só depois do consentimento de cookies. Os IDs são públicos, mas ficam fora do código:
# vêm da env/.env (GA_ID, CLARITY_ID) e só vão parar em site/medicao.js
GA_ID = config("GA_ID")
CLARITY_ID = config("CLARITY_ID")
PRIVACIDADE = "https://vitorpereira.ia.br/privacidade"
NOME_EXIBICAO = {"Flavio Bolsonaro": "Flávio Bolsonaro"}  # o TSE publica sem acento
CHROME = next((c for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome") if Path(c).exists()), "google-chrome")
# "Pessoas agora" no HUD (presença no Supabase Realtime, hud/presenca.js). A publishable key é PÚBLICA por desenho:
# vai para o navegador de todo visitante e só faz o que o papel anon pode fazer. Nunca pôr aqui service_role/secret
# (tests/test_hud.py confere o prefixo sb_publishable_).
SUPABASE_URL = "https://qzczyicspbizosjogmlq.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_OBOstHIYUXpk_NvJFtYrVQ_NcOz4XUI"
HUD_PRESENCE = {"url": SUPABASE_URL, "key": SUPABASE_PUBLISHABLE_KEY, "canal": "eleicoes-hud"}
OUT = R / "site"
# resultado por seção e local de votação (municipios/montar_secao.py): sem a pasta, /minha-secao/ sai "em breve"
LOCAIS = R / "municipios" / "geo" / "locais"
BUILD = R / ".build"
ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:00-03:00")
fmt = lambda x, d=1: f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

rel = json.loads((R / "relatorio" / "relatorio.json").read_text())
N = rel["nac"]
cF = next(c for c in N["cand"] if c["nome"].startswith("Flavio")); cL = next(c for c in N["cand"] if c["nome"] == "Lula")
gov2 = [g for g in rel["gov"] if g["status"] == "2turno"]; govIn = [g for g in rel["gov"] if g["status"] == "indefinido"]
govEl = [g for g in rel["gov"] if g["status"] == "eleito"]
plFed = dict(rel["depfed"]["por_partido"]).get("PL", 0); plSen = dict(rel["sen_part"]).get("PL", 0)
ufF = [u for u in rel["pres_uf"] if u["uf"] != "ZZ" and u["saldo"] > 0]; ufL = [u for u in rel["pres_uf"] if u["uf"] != "ZZ" and u["saldo"] < 0]
GOV_OFICIAL = all(g.get("oficial") for g in rel["gov"]); SEN_OFICIAL = all(s.get("oficial") for s in rel["sen"])
DEP_PENDENTES = sorted(set(rel["depfed"].get("ufs_pendentes", []) + rel["depest"].get("ufs_pendentes", [])))
apertado = min((u for u in rel["pres_uf"] if u["uf"] != "ZZ"), key=lambda u: abs(u["saldo"]))
LEITURA = datetime.strptime(f'{N["dg"]} {N["ht"]}', "%d/%m/%Y %H:%M:%S")
DIA_ELEICAO = "04/10/2026"


def hora_leitura(dg, ht):
    """"21:56" para leitura do dia da eleição; de outro dia, com a data: "05/10 12:51" (issue 150)."""
    return ht[:5] if dg == DIA_ELEICAO else f"{dg[:5]} {ht[:5]}"


# partido junto do nome (sigla do TSE, de relatorio.json): "Flávio Bolsonaro (PL)" e "Flávio (PL)"
def rotulo(c):
    return f'{NOME_EXIBICAO.get(c["nome"], c["nome"])} ({c["sg"]})'


def curto(c):
    return f'{NOME_EXIBICAO.get(c["nome"], c["nome"]).split()[0]} ({c["sg"]})'


def textos_principal():
    """(h1, título, descrição) da página principal"""
    c1, c2 = sorted(N["cand"], key=lambda c: -c["p"])[:2]
    h1 = f"Eleições 2026: {rotulo(c1)} e {rotulo(c2)} vão ao 2º turno" if c1["p"] < 50 else f"Eleições 2026: {rotulo(c1)} é eleito no 1º turno"
    # título e descrição (title, og, twitter, og:image:alt) chamam para o 2º turno, sem o placar do 1º (#139)
    titulo = f"Eleições 2026: 2º turno {curto(cF)} × {curto(cL)} em 25/10, apuração ao vivo"
    desc = (f"{rotulo(cF)} e {rotulo(cL)} disputam o 2º turno no domingo, 25/10, com apuração ao vivo a partir das 17h (Brasília). "
            "Resultado de 04/10 por estado, governadores, Senado, Câmara e Assembleias, com dados do TSE.")
    return h1, titulo, desc


def textos_aovivo():
    """(título, descrição) do /ao-vivo/"""
    return ("Mapa da apuração por município | Eleições 2026",
            "Apuração do 2º turno ao vivo no domingo, 25/10, a partir das 17h (Brasília), com os dados do TSE: "
            "presidente nos 5.570 municípios, atualizado sozinho. Fora da noite da apuração, o mapa de 04/10 com todos os cargos.")


TURNO2 = date(2026, 10, 25)


def hoje_brasilia():
    return datetime.now(timezone(timedelta(hours=-3))).date()


def banner_turno2(hoje=None):
    """Faixa de chamada para o 2º turno no topo da home; some no primeiro build depois de 25/10."""
    if (hoje or hoje_brasilia()) > TURNO2:
        return ""
    return ('<div class="banner"><div><b>2º turno: domingo, 25/10.</b> Apuração ao vivo a partir das 17h (Brasília) → '
            '<a href="/ao-vivo/">Ao vivo</a></div></div>')


def textos_leitura(d):
    """(h1, título, descrição) da página de uma leitura parcial"""
    pst = fmt(d["pst"], 1)
    return (f"Apuração com {pst}% das urnas: {curto(cF)} {fmt(d['f'], 2)}% × {curto(cL)} {fmt(d['l'], 2)}%",
            f"Apuração {pst}%: {curto(cF)} × {curto(cL)} | Eleições 2026",
            f"Leitura parcial do TSE às {d['ht'][:5]} de 04/10/2026: {curto(cF)} {fmt(d['f'], 2)}%, {curto(cL)} {fmt(d['l'], 2)}%. "
            f"Projeção do resultado final e chance de cada cenário naquele momento.")


def html_leitura(tpl, d):
    """template.html + dados da leitura; D.sg = siglas de Flávio e Lula, D.sgn = sigla de cada candidato pelo nome"""
    dados = {**d, "sg": {"f": cF["sg"], "l": cL["sg"]}, "sgn": {c["nome"]: c["sg"] for c in N["cand"]}}
    raw = brand.aplicar(tpl.replace("/*__DATA__*/null", json.dumps(dados, ensure_ascii=False)))
    return raw.replace("<h1>Presidente 2026 · 1º turno — apuração e projeções</h1>", f"<h1>{html.escape(textos_leitura(d)[0])}</h1>", 1)

def textos_leitura_2t(d):
    """(h1, título, descrição) da página de uma leitura parcial do 2º turno"""
    pst = fmt(d["pst"], 1)
    return (f"2º turno, apuração com {pst}% das urnas: {curto(cF)} {fmt(d['f'], 2)}% × {curto(cL)} {fmt(d['l'], 2)}%",
            f"2º turno, apuração {pst}%: {curto(cF)} × {curto(cL)} | Eleições 2026",
            f"Leitura parcial do TSE às {d['ht'][:5]} de 25/10/2026: {curto(cF)} {fmt(d['f'], 2)}%, {curto(cL)} {fmt(d['l'], 2)}%. "
            f"Projeção do resultado final e chance de cada um naquele momento.")


def html_leitura_2t(tpl, d):
    """template_2turno.html + dados da leitura (o snapshot já traz D.sg)"""
    raw = brand.aplicar(tpl.replace("/*__DATA__*/null", json.dumps(d, ensure_ascii=False)))
    return raw.replace("<h1>Presidente 2026 · 2º turno — apuração e projeções</h1>", f"<h1>{html.escape(textos_leitura_2t(d)[0])}</h1>", 1)

# ---------------- rodadas da apuração (dados de cada snapshot, renderizados com o template atual)
def dados_snapshot(path):
    if path.startswith("git:"):
        return json.loads(subprocess.check_output(["git", "-C", str(R), "show", path[4:]]).decode())
    return json.loads((R / path).read_text())

RODADAS = [("snapshots/2026-10-04_1832_36.6pct/dados.json", "36-6"),
           ("snapshots/2026-10-04_1906_64.8pct/dados.json", "64-8"),
           ("marcos/75pct/dados.json", "84-9"),
           ("snapshots/2026-10-04_2047_93.2pct/dados.json", "93-2"),
           ("snapshots/2026-10-04_2156_99.7pct/dados.json", "99-7")]
hist_all = json.loads((R / "historico.json").read_text())
rodadas = []
for src, slug in RODADAS:
    d = dados_snapshot(src)
    d["hist"] = [h for h in hist_all if h["pst"] <= d["pst"] + 1e-9]  # trajetória até aquele momento
    rodadas.append(dict(slug=slug, d=d, url=f"/apuracao/{slug}/"))

# 2º turno (25/10): um snapshot por marco em snapshots/2-turno/ (gerar_2turno.py); cada um já leva a trajetória até ali.
# Mesmo % (uma casa) = mesma página: fica a leitura mais recente.
rodadas_2t = {}
for p in sorted((R / "snapshots" / "2-turno").glob("*/dados.json")):
    d = json.loads(p.read_text())
    slug = f"{d['pst']:.1f}".replace(".", "-")
    rodadas_2t[slug] = dict(slug=slug, d=d, url=f"/apuracao/2-turno/{slug}/")
rodadas_2t = sorted(rodadas_2t.values(), key=lambda r: r["d"]["pst"])

# ---------------- peças compartilhadas
FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#070B12"/><rect x="12" y="34" width="10" height="18" rx="2" fill="#5B7FE8"/><rect x="26" y="22" width="10" height="30" rx="2" fill="#E35A4F"/><rect x="42" y="12" width="9" height="40" rx="2" fill="#24C8FF"/></svg>"""

SITE_CSS = """<style id="site-chrome">
.sitebar{background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}
.sitebar .in{box-sizing:border-box;max-width:var(--w-larga);margin:0 auto;padding:10px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.sitebar a{color:var(--ink);text-decoration:none}
.sitebar .brand{font-family:var(--font-mono);font-weight:600;display:flex;align-items:center;gap:8px;letter-spacing:-.01em}
.sitebar .brand .dim{color:var(--muted);margin-left:.45em}
.sitebar .brand .cursor{display:inline-block;width:.5em;height:1.05em;background:var(--brand);margin-left:2px;vertical-align:-.15em}
.sitebar .brand .sep{color:var(--line)}
.sitebar nav.top{display:flex;gap:4px;margin:0 0 0 auto;flex-wrap:wrap}
.sitebar nav.top a{border:0;background:none}
.sitebar nav.top a{font-size:13.5px;color:var(--ink2);padding:5px 10px;border-radius:8px}
.sitebar nav.top a[aria-current=page],.sitebar nav.top a:hover{background:var(--soft,var(--line));color:var(--ink)}
a.agora{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink2);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px;white-space:nowrap}
a.agora[hidden]{display:none}
a.agora:hover{color:var(--ink);border-color:var(--live)}
a.agora svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2}
a.agora b{font-family:var(--font-mono);color:var(--ink);font-variant-numeric:tabular-nums}
a.agora .pulso{width:7px;height:7px;border-radius:50%;background:var(--live);box-shadow:0 0 0 0 color-mix(in srgb,var(--live) 60%,transparent);animation:pulso 2s infinite}
@keyframes pulso{70%{box-shadow:0 0 0 6px transparent}100%{box-shadow:0 0 0 0 transparent}}
@media (prefers-reduced-motion:reduce){a.agora .pulso{animation:none}}
button.tema{display:inline-flex;align-items:center;justify-content:center;flex:none;width:32px;height:32px;padding:0;margin:0;border:1px solid var(--line);border-radius:50%;background:var(--card);color:var(--ink2);cursor:pointer}
button.tema:hover{color:var(--ink);border-color:var(--muted)}
button.tema:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
button.tema svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.tema .lua{display:none}
:root[data-theme="light"] .tema .sol{display:none}:root[data-theme="light"] .tema .lua{display:block}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]) .tema .sol{display:none}:root:not([data-theme="dark"]) .tema .lua{display:block}}
@media (max-width:900px){.sitebar a.agora{order:1;margin-left:auto}.sitebar nav.top{order:2;margin-left:0}.sitebar .tema{order:1}.sitebar a.agora[hidden]~.tema{margin-left:auto}}
@media (max-width:640px){.sitebar .in{gap:8px 14px;padding:8px 16px}.sitebar nav.top{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;width:100%;min-width:0;-webkit-mask-image:linear-gradient(90deg,black 90%,transparent);mask-image:linear-gradient(90deg,black 90%,transparent)}.sitebar nav.top::-webkit-scrollbar{display:none}.sitebar nav.top a{flex:none;white-space:nowrap}}
/* celular (issue 146): até 640 px, todo controle com 40 px de altura */
@media (max-width:640px){.sitebar .brand{min-height:40px;box-sizing:border-box}.sitebar nav.top a{display:inline-flex;align-items:center;min-height:40px;box-sizing:border-box}a.agora{min-height:40px;box-sizing:border-box}button.tema{width:40px;height:40px}.rounds a{display:inline-flex;align-items:center;min-height:40px;box-sizing:border-box}nav.crumbs a{display:inline-block;min-height:40px;box-sizing:border-box;padding:10px 0}footer.site .eu a,footer.site .eu button{display:inline-flex;align-items:center;min-height:40px;box-sizing:border-box}footer.site .eu ul{gap:4px}footer.site .eu ul a{width:40px;height:40px}.faq summary{min-height:40px;box-sizing:border-box;padding-block:10px;margin-block:-10px}}
nav.crumbs{display:block;margin:0 0 14px;font-size:13px;line-height:1.5;color:var(--ink2);overflow-wrap:anywhere}
nav.crumbs a{border:0;padding:0;background:none;font-size:13px;color:var(--ink2);text-decoration:underline;text-decoration-color:var(--muted);text-underline-offset:3px}
nav.crumbs a:hover{color:var(--ink)}
body>nav.crumbs{box-sizing:border-box;max-width:var(--w-larga);margin:14px auto 0;padding:0 16px}
.banner{box-sizing:border-box;max-width:var(--w-larga);margin:14px auto 0;padding:0 16px}
.banner div{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--brand);border-radius:10px;padding:10px 14px;font-size:14px}
.banner a{color:var(--ink);font-weight:600}
.rounds{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.rounds a{font-size:12.5px;border:1px solid var(--line);border-radius:999px;padding:2px 10px;color:var(--ink2);text-decoration:none;font-variant-numeric:tabular-nums}
.rounds a[aria-current=page]{background:var(--ink);color:var(--card);border-color:var(--ink)}
footer.site{border-top:1px solid var(--line);margin-top:20px}
footer.site .in{box-sizing:border-box;max-width:var(--w-larga);margin:0 auto;padding:20px 16px 36px;font-size:13px;color:var(--ink2);display:flex;gap:18px;flex-wrap:wrap;justify-content:space-between}
footer.site a{color:var(--ink2)}
footer.site .eu{border-top:1px solid var(--line)}
footer.site .eu .in{padding:16px 16px 28px;align-items:center;gap:14px 18px}
footer.site .eu nav{display:flex;align-items:center;gap:8px 18px;flex-wrap:wrap}
footer.site .eu a,footer.site .eu button{color:var(--ink2);text-decoration:none;font:inherit;font-size:13.5px;background:none;border:0;padding:0;cursor:pointer}
footer.site .eu a:hover,footer.site .eu button:hover{color:var(--ink)}
footer.site .eu ul{display:flex;align-items:center;gap:14px;list-style:none;margin:0;padding:0}
footer.site .eu ul a{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px}
footer.site .eu svg{width:18px;height:18px;fill:currentColor}
footer.site .eu .tn{font-size:12px;font-weight:700;letter-spacing:-.02em}
footer.site button:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:4px}
.faq details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:0 0 8px}
.faq summary{cursor:pointer;font-weight:600;color:var(--ink);font-size:15px}
.faq p{margin:8px 0 0;color:var(--ink2)}
header p.kicker{margin:0 0 4px;font-size:13px;font-weight:600;text-transform:uppercase;color:var(--ink2)}
.skip{position:absolute;left:-999px}.skip:focus{left:12px;top:12px;z-index:50;background:var(--card);padding:6px 10px;border-radius:8px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:4px}
.grid>*{min-width:0}.ch canvas{max-width:100%}
</style>"""



# ---------------- medições (entram depois do pré-render, para o banner não ficar congelado no HTML)
# Vercel Web Analytics/Speed Insights ficam de fora: não estão ativados no projeto, e os scripts dariam 404.
MEDICAO_CSS = """<style id="consent-css">
.consent{position:fixed;inset:auto 0 0 0;z-index:60;background:var(--card);color:var(--ink);border-top:1px solid var(--line);box-shadow:0 -6px 24px rgba(0,0,0,.12)}
.consent .in{box-sizing:border-box;max-width:var(--w-larga);margin:0 auto;padding:14px 16px;display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.consent p{margin:0;font-size:14px;color:var(--ink2);flex:1 1 320px}
.consent p a{color:var(--ink)}
.consent .bt{display:flex;gap:8px}
.consent button{font:inherit;font-size:14px;font-weight:600;border-radius:8px;padding:8px 16px;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.consent button.ok{background:var(--brand);color:var(--bg);border-color:var(--brand)}
.consent button:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
@media (max-width:520px){.consent .in{padding:8px 16px;gap:8px}.consent p{font-size:13px;line-height:1.4;flex-basis:100%}.consent .bt{width:100%}.consent button{flex:1;padding:6px 12px;font-size:13px}}
@media (max-width:640px){.consent button{min-height:40px;box-sizing:border-box}}
</style>
"""
MEDICAO_JS = """(function(){
  var C="consent";
  function ler(){var m=document.cookie.match(/(?:^|;\\s*)consent=(accepted|rejected)/);return m?m[1]:null}
  function gravar(v){document.cookie=C+"="+v+"; path=/; max-age=31536000; SameSite=Lax"}
  function carregar(){
    if(window.__medindo)return;window.__medindo=true;
__CARREGAR__
  }
  var v=ler();
  if(v==="accepted")carregar();
  window.addEventListener("consent:reopen",mostrar);
  if(!v)mostrar();
  function mostrar(ev){
  if(document.querySelector(".consent"))return;
  var b=document.createElement("div");b.className="consent";b.setAttribute("role","dialog");b.setAttribute("aria-live","polite");b.setAttribute("aria-label","Cookies");
  b.innerHTML='<div class="in"><p>Usamos cookies pra entender como o site é usado e melhorar sua experiência. Você pode aceitar ou recusar. <a href="__PRIV__" rel="noopener">Política de privacidade</a></p><div class="bt"><button type="button" data-v="rejected">Recusar</button><button type="button" class="ok" data-v="accepted">Aceitar</button></div></div>';
  b.addEventListener("click",function(e){var x=e.target.getAttribute&&e.target.getAttribute("data-v");if(!x)return;
    // GA e Clarity não descarregam: quem revoga depois de aceitar recarrega a página sem eles
    var antes=ler();gravar(x);b.remove();if(x==="accepted")carregar();else if(antes==="accepted")location.reload()});
  document.body.appendChild(b);
  if(ev){var ok=b.querySelector("button.ok");if(ok)ok.focus({preventScroll:true})}
  }
})();
"""
MEDICAO_GA = """    var GA=__GA__;
    var g=document.createElement("script");g.async=true;g.src="https://www.googletagmanager.com/gtag/js?id="+GA;document.head.appendChild(g);
    window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments)};gtag("js",new Date());gtag("config",GA,{anonymize_ip:true});"""
MEDICAO_CLARITY = """    var CL=__CL__;
    window.clarity=window.clarity||function(){(window.clarity.q=window.clarity.q||[]).push(arguments)};
    var c=document.createElement("script");c.async=true;c.src="https://www.clarity.ms/tag/"+CL;document.head.appendChild(c);"""


def medicao(ga, clarity):
    """(trecho_html, js): o trecho entra em toda página e só aponta para /medicao.js; o js (None sem nenhum ID) tem os IDs.
    Sem ID não há o que consentir: sem banner, sem script."""
    if not (ga or clarity):
        return "", None
    partes = []
    if ga:
        partes.append(MEDICAO_GA.replace("__GA__", json.dumps(ga)))
    if clarity:
        partes.append(MEDICAO_CLARITY.replace("__CL__", json.dumps(clarity)))
    js = MEDICAO_JS.replace("__CARREGAR__", "\n".join(partes)).replace("__PRIV__", PRIVACIDADE)
    return MEDICAO_CSS + '<script src="/medicao.js" defer></script>\n', js


MEDICAO_HTML, MEDICAO_JS_SAIDA = medicao(GA_ID, CLARITY_ID)


def com_medicao(dom):
    assert "/medicao.js" not in dom, "medição já presente no HTML pré-renderizado"
    return dom.replace("</body>", MEDICAO_HTML + "</body>", 1) if MEDICAO_HTML else dom


def secoes():
    """[(url, rótulo)] das seções do site, na ordem do menu: a fonte única da sitebar, do botão "☰ Seções" do painel
    (window.HUD_SECOES) e da Análise (menu_secoes). Debates só entra quando há debate publicado; Minha seção, quando há
    resultado por seção (municipios/geo/locais/)."""
    from municipios import minha_secao as msec
    return [("/", NAV.INICIO), ("/ao-vivo/", NAV.AO_VIVO)] + ([("/debates/", NAV.DEBATES)] if debates() else []) + [
        ("/analise/", NAV.ANALISE)] + ([("/minha-secao/", NAV.MINHA_SECAO)] if msec.tem_dados(LOCAIS) else []) + [
        ("/rastro/", NAV.RASTRO), ("/apuracao/", NAV.APURACAO), ("/1-turno/#metodo", NAV.METODO)]


def trilha_apuracao(leitura=None):
    """trilha do Histórico da apuração: o índice, ou uma leitura (ex.: "36,6%")"""
    if leitura is None:
        return NAV.trilha((NAV.INICIO, "/"), (NAV.APURACAO, None))
    return NAV.trilha((NAV.INICIO, "/"), (NAV.APURACAO, "/apuracao/"), (leitura, None))


# estilo do botão "☰ Seções" (painel e Análise): só tokens da brand.css; o ciano é a moldura do painel suspenso
SECOES_CSS = """<style>
.secoes{position:relative;flex:none}
.secoes>button{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 12px;cursor:pointer;font:500 13px var(--font-sans);white-space:nowrap}
.secoes>button:hover,.secoes>button[aria-expanded=true]{border-color:var(--brand)}
.secoes>button .ic-m{font-size:15px;line-height:1}
.secoes>nav{position:absolute;top:calc(100% + 8px);left:0;z-index:80;min-width:240px;display:flex;flex-direction:column;gap:2px;padding:6px;background:var(--card);border:1px solid var(--brand);border-radius:12px;box-shadow:0 12px 32px color-mix(in srgb,var(--bg) 60%,transparent)}
.secoes>nav[hidden]{display:none}
.secoes>nav a{display:block;padding:8px 12px;border-radius:8px;color:var(--ink2);text-decoration:none;font-size:14px;white-space:nowrap}
.secoes>nav a:hover,.secoes>nav a:focus-visible{background:var(--soft);color:var(--ink)}
.secoes>nav a[aria-current=page]{color:var(--ink);box-shadow:inset 2px 0 0 var(--brand)}
@media (max-width:640px){
  .secoes{position:static}
  .secoes>nav{left:12px;right:12px;top:calc(100% + 4px);min-width:0}
  .secoes>nav a{padding:11px 12px;font-size:15px}
  .secoes>button{min-height:40px;box-sizing:border-box}
}
</style>
"""


def menu_secoes(atual):
    """botão "☰ Seções" estático (Análise): mesma lista de secoes(); hud/secoes.js liga abrir/fechar/teclado"""
    atr = ' aria-current="page"'
    nav = "".join(f'<a href="{u}"{atr if u == atual else ""}>{html.escape(t)}</a>' for u, t in secoes())
    return (f'<div class="secoes"><button type="button" aria-expanded="false" aria-controls="secoes-menu">'
            f'<span class="ic-m" aria-hidden="true">☰</span><span class="tx">Seções</span></button>'
            f'<nav id="secoes-menu" aria-label="Seções do site" hidden>{nav}</nav></div>'
            f'<script type="module" src="/hud/secoes.js"></script>')


def sitebar(atual):
    nav = "".join(f'<a href="{u}"{" aria-current=page" if u == atual else ""}>{t}</a>' for u, t in secoes())
    return (f'<a class="skip" href="#conteudo">Pular para o conteúdo</a><header class="sitebar"><div class="in">'
            f'<a class="brand" href="/" aria-label="Eleições 2026, por Vitor Pereira">'
            f'<span class="wm">vitor<span class="dim">pereira</span><span class="cursor" aria-hidden="true"></span></span>'
            f'<span class="sep" aria-hidden="true">/</span><span>eleições 2026</span></a>'
            f'<nav class="top" aria-label="Principal">{nav}</nav>{agora_topo()}{TEMA_BOTAO}</div></header>')


# tema claro/escuro (#142). Padrão: segue o sistema (brand.css). A escolha do botão fica em localStorage["tema"] e é
# aplicada como data-theme no <html> por este script, que roda no <head> antes da pintura (sem piscar). Se a escolha
# cair igual ao sistema, a chave é apagada e o site volta a seguir o sistema. Sem "<" no JS (tests/test_tema.py).
TEMA_JS = """<script>(function(){var d=document.documentElement,K="tema",C={light:"#FBFCFE",dark:"#070B12"};
function sis(){return matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"}
function cor(){var t=d.getAttribute("data-theme");document.querySelectorAll('meta[name="theme-color"]').forEach(function(m){m.content=C[t||(/light/.test(m.media)?"light":"dark")]})}
var g=null;try{g=localStorage.getItem(K)}catch(e){}
if(g==="light"||g==="dark"){d.setAttribute("data-theme",g);cor()}
window.temaAlternar=function(){var s=sis(),n=(d.getAttribute("data-theme")||s)==="light"?"dark":"light";
try{if(n===s)localStorage.removeItem(K);else localStorage.setItem(K,n)}catch(e){}
if(n===s)d.removeAttribute("data-theme");else d.setAttribute("data-theme",n);cor()}})()</script>"""
# ícone certo só por CSS (SITE_CSS): sol no escuro, lua no claro
TEMA_BOTAO = ('<button type="button" class="tema" onclick="temaAlternar()" aria-label="Alternar tema claro ou escuro" title="Alternar tema claro ou escuro">'
              '<svg class="sol" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
              '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
              '<svg class="lua" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>')


def agora_topo():
    """contador "pessoas no site agora" (hud/topo-pessoas.js), no mesmo canal de presença do HUD. Nasce escondido: só
    aparece quando o Realtime responde (o pré-render headless não conecta, então o HTML publicado sai sem número)."""
    d = " ".join(f'data-{k}="{html.escape(v, quote=True)}"' for k, v in HUD_PRESENCE.items())
    return (f'<a class="agora" href="/ao-vivo/" {d} hidden><span class="pulso" aria-hidden="true"></span>'
            f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/>'
            f'<circle cx="12" cy="12" r="3"/></svg><b></b></a>'
            f'<script type="module" src="/hud/topo-pessoas.js"></script>')


# rodapé pessoal: mesmo do vitorpereira.ia.br (components/layout/Footer.tsx + SocialLinks + brand/SocialIcons)
SOCIAL = [
    ("LinkedIn", "https://www.linkedin.com/in/vitor-onofre-pereira/", "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"),
    ("GitHub", "https://github.com/vitoropereira", "M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"),
    ("Instagram", "https://www.instagram.com/vitorpereirasaas/", "M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"),
    ("X (Twitter)", "https://x.com/VITORONOFRE", "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"),
    ("YouTube", "https://www.youtube.com/@vitoropereira", "M23.495 6.205a3.007 3.007 0 00-2.088-2.088c-1.87-.501-9.396-.501-9.396-.501s-7.507-.01-9.396.501A3.007 3.007 0 00.527 6.205a31.247 31.247 0 00-.522 5.805 31.247 31.247 0 00.522 5.783 3.007 3.007 0 002.088 2.088c1.868.502 9.396.502 9.396.502s7.506 0 9.396-.502a3.007 3.007 0 002.088-2.088 31.247 31.247 0 00.5-5.783 31.247 31.247 0 00-.5-5.805zM9.609 15.601V8.408l6.264 3.602z"),
    ("TabNews", "https://www.tabnews.com.br/vitorpereirasaas", None),
]


def rodape_pessoal():
    icones = "".join(
        f'<li><a href="{u}" target="_blank" rel="noopener me" aria-label="{n}">'
        + (f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{d}"/></svg>' if d else '<span class="tn" aria-hidden="true">TN</span>')
        + "</a></li>"
        for n, u, d in SOCIAL)
    return (f'<div class="eu"><div class="in"><a href="{AUTOR["url"]}">© 2026 Vitor Pereira</a>'
            f'<nav aria-label="Vitor Pereira"><a href="https://vitorpereira.ia.br/privacidade">Privacidade</a>'
            f'<a href="https://vitorpereira.ia.br/termos">Termos</a>'
            f'<button type="button" onclick="window.dispatchEvent(new CustomEvent(\'consent:reopen\'))">Gerenciar cookies</button>'
            f'<ul>{icones}</ul></nav></div></div>')


def rodape():
    return (f'<footer class="site"><div class="in"><span>Análise independente de <a href="{AUTOR["url"]}" rel="author">{AUTOR["nome"]}</a> '
            f'com dados públicos do <a href="https://resultados.tse.jus.br/oficial/app/index.html" rel="noopener">TSE</a>. '
            f'Não é um site oficial da Justiça Eleitoral.</span><span><a href="/dados/relatorio.json">Baixar dados (JSON)</a> · '
            f'<a href="/sitemap.xml">Sitemap</a> · <a href="/llms.txt">llms.txt</a></span></div>' + rodape_pessoal() + '</footer>')


def jsonld(obj):
    # "</" escapado: texto livre (ex.: trecho de debate) com "</script>" não fecha o bloco
    return f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")}</script>'


def head(title, desc, path, og_img, extra_ld, published, modified):
    url = BASE + path
    return f"""<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<meta name="author" content="{AUTOR["nome"]}">
<meta name="theme-color" content="#FBFCFE" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#070B12" media="(prefers-color-scheme: dark)">
{TEMA_JS}
<link rel="preload" href="/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/jetbrains-mono-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="alternate" type="text/plain" href="/llms.txt" title="Resumo para LLMs">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="pt_BR">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}{og_img}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(title)}">
<meta property="article:published_time" content="{published}">
<meta property="article:modified_time" content="{modified}">
<meta property="article:author" content="{AUTOR["url"]}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(desc)}">
<meta name="twitter:image" content="{BASE}{og_img}">
{"".join(jsonld(x) for x in extra_ld)}
{SITE_CSS}"""


PESSOA = {"@type": "Person", "name": AUTOR["nome"], "url": AUTOR["url"], "sameAs": AUTOR_PERFIS}
FONTE_TSE = {"@type": "Organization", "name": "Tribunal Superior Eleitoral", "url": "https://www.tse.jus.br"}
ELEICAO = {"@type": "Event", "name": "Eleições Gerais 2026 no Brasil — 1º turno", "startDate": "2026-10-04",
           "eventStatus": "https://schema.org/EventScheduled", "location": {"@type": "Country", "name": "Brasil"},
           "organizer": FONTE_TSE}


def montar_pagina(raw_html, title, desc, path, og_img, ld, published, modified, atual, extra_top="", moldura=True):
    """moldura=False: página de tela cheia (HUD) com cabeçalho e rodapé próprios"""
    h = raw_html
    h = re.sub(r"<title>.*?</title>", "", h, count=1, flags=re.S)
    h = h.replace('<meta name="viewport" content="width=device-width, initial-scale=1">',
                  '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + head(title, desc, path, og_img, ld, published, modified), 1)
    if moldura:
        h = h.replace("<body>", "<body>" + sitebar(atual) + extra_top, 1)
        h = h.replace("<main>", '<main id="conteudo">', 1)
        h = h.replace("</body>", rodape() + "</body>", 1)
    # Chart.js: tira do <head> (bloqueante) e carrega logo antes do script da página
    m = re.search(r'<script src="https://cdnjs[^"]+chart[^"]+"[^>]*></script>\n?', h)
    if m:
        tag = m.group(0).strip()
        h = h.replace(m.group(0), "", 1)
        h = h.replace("<script>\nconst D=", tag + "\n<script>\nconst D=", 1)
    return h


# ---------------- Vercel (gravado em site/vercel.json e na raiz)
VERCEL = {
    "cleanUrls": True, "trailingSlash": True,
    # /vivo/* = estado do 2º turno no Storage do Supabase, servido pela função api/vivo.js: o rewrite direto não entrava
    # no cache do CDN (o Storage manda set-cookie), e cada poll de cada visitante ia ao Supabase. O HUD só lê /vivo/ relativo.
    "rewrites": [{"source": "/tse/:path*", "destination": "https://resultados.tse.jus.br/oficial/:path*"},
                 {"source": "/vivo/:path*", "destination": "/api/vivo?p=:path*"}],
    "headers": [{"source": "/(.*)", "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"}, {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"}]},
                {"source": "/fonts/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
                {"source": "/og/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=86400"}]},
                # rewrite externo: a Vercel obedece o cache-control da origem (o TSE e o Storage mandam no-cache); o
                # CDN-Cache-Control daqui sobrepõe a origem e o x-vercel-enable-rewrite-caching liga o cache em projeto
                # anterior a 06/04/2026 (doc "Caching rewrites to external origins"; sem isto todo poll ia à origem)
                {"source": "/tse/(.*)", "headers": [{"key": "Cache-Control", "value": "public, s-maxage=20, stale-while-revalidate=40"},
                                                   {"key": "CDN-Cache-Control", "value": "max-age=20"},
                                                   {"key": "x-vercel-enable-rewrite-caching", "value": "1"}]},
                {"source": "/ao-vivo/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
                {"source": "/geo/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=3600"}]},
                # módulos ES sem hash no nome: sempre revalidar, senão um deploy mistura versões
                {"source": "/hud/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
                {"source": "/rastro/busca(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
                {"source": "/analise/js/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
                {"source": "/analise/codigo/(.*)\\.(py|json|md)", "headers": [{"key": "Content-Type", "value": "text/plain; charset=utf-8"}]},
                {"source": "/analise/dados/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
                # /vivo/: o cache vem da própria função (api/vivo.js), sem cookie e com s-maxage
                ]}


# ---------------- HUD (/ao-vivo/)
def copiar_hud(dest):
    """hud/ → /hud/ (+ ufs.json), assets/vendor/ → /vendor/, municipios/geo/ → /geo/ (se existir; vem do build dos dados)"""
    shutil.copytree(R / "hud", dest / "hud", dirs_exist_ok=True, ignore=shutil.ignore_patterns("*_test.js"))  # testes Deno não vão ao ar
    shutil.copytree(R / "assets" / "vendor", dest / "vendor", dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.md"))
    # malha leve das 27 UFs para aparelho fraco (spec §9): contornos já gerados por relatorio/montar.py
    shutil.copy(R / "relatorio" / "dados" / "mapa.json", dest / "hud" / "ufs.json")
    st = status_hud()
    if st:
        (dest / "hud" / "status.json").write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")))
    geo = R / "municipios" / "geo"
    if geo.is_dir():
        from municipios import pessoas  # posições do modo "Pessoas": só refaz se a malha ou os aptos mudarem
        pessoas.garantir()
        # só o que o front lê (hud/dados.js: t1/<cargo|meta|serie|feed>.json e a malha); t2022/, partidos-*.json e
        # cadeiras.json servem só ao cálculo da Análise (analise/calcular.py) e ficam fora do site
        shutil.copytree(geo, dest / "geo", dirs_exist_ok=True, ignore=shutil.ignore_patterns("t2022", "partidos-*.json", "cadeiras.json"))


def injetar_presenca(h):
    """window.HUD_PRESENCE = {url, key, canal} antes do app do HUD (o contador "pessoas agora" lê daí), mais
    window.HUD_SECOES = secoes() e o estilo do botão "☰ Seções" (fonte única com a sitebar e a Análise)"""
    tag = '<script type="module" src="/hud/app.js"></script>'
    assert h.count(tag) == 1, "template_hud.html: script do app não encontrado"
    cfg = json.dumps(HUD_PRESENCE, separators=(",", ":"))
    sec = json.dumps(secoes(), separators=(",", ":"), ensure_ascii=False)
    h = h.replace("</head>", SECOES_CSS + "</head>", 1)
    return h.replace(tag, f"<script>window.HUD_SECOES={sec};</script>\n<script>window.HUD_PRESENCE={cfg};</script>\n{tag}", 1)


def status_hud():
    """Situação oficial para as manchetes do HUD (eleito / 2º turno), tirada do relatorio.json.
    O HUD nunca deduz isso de porcentagem. Candidatos são identificados pelo NÚMERO, achado pelos votos
    na linha da UF de municipios/geo/t1 (nomes podem divergir na acentuação). Sem a malha de dados, devolve None."""
    t1 = R / "municipios" / "geo" / "t1"
    if not (t1 / "meta.json").exists():
        return None
    meta = json.loads((t1 / "meta.json").read_text())
    linhas = {c: json.loads((t1 / f"{c}.json").read_text()) for c in ("presidente", "governador", "senador")}

    def numero(cargo, uf, votos):
        lista = meta["cand"][cargo] if cargo == "presidente" else meta["cand"][cargo].get(uf, [])
        row = linhas[cargo]["br"] if cargo == "presidente" else linhas[cargo]["uf"].get(uf)
        achados = [c["n"] for c, v in zip(lista, row[5] if row else []) if v == votos]
        assert len(achados) == 1, f"status.json: {cargo} {uf} com {votos} votos casa com {achados}"
        return achados[0]

    top = sorted(N["cand"], key=lambda c: -c["votos"])
    pres = {"status": "eleito" if top[0]["p"] > 50 else "2turno",
            "a": numero("presidente", None, top[0]["votos"]), "b": numero("presidente", None, top[1]["votos"])}
    gov = {g["uf"]: {"status": g["status"], "a": numero("governador", g["uf"], g["a"]["votos"]), "b": numero("governador", g["uf"], g["b"]["votos"])}
           for g in rel["gov"]}
    sen = {x["uf"]: {"eleitos": [numero("senador", x["uf"], e["votos"]) for e in x["eleitos"]]} for x in rel["sen"]}
    return {"fonte": f"relatorio.json ({N['dg']} {N['ht']})", "presidente": {"BR": pres}, "governador": gov, "senador": sen}


def resumo_hud():
    """texto pré-renderizado para buscadores e leitores de tela (o HUD em si é desenhado no navegador)"""
    linhas = "".join(f"<tr><th scope=row>{u['uf']}</th><td>{fmt(u['f'], 2)}%</td><td>{fmt(u['l'], 2)}%</td></tr>"
                     for u in sorted(rel["pres_uf"], key=lambda u: u["uf"]) if u["uf"] != "ZZ")
    return (f'<section class="crawl" id="resumo" aria-label="Resumo do resultado"><h2>Mapa da apuração por município · Eleições 2026</h2>'
            f'<p>1º turno, {fmt(N["pst"], 2)}% das seções apuradas (TSE, {N["dg"]} {N["ht"]}): Flávio Bolsonaro (PL) {fmt(cF["p"], 2)}% '
            f'e Lula (PT) {fmt(cL["p"], 2)}% dos votos válidos. Os dois disputam o 2º turno em 25 de outubro de 2026. '
            f'Flávio venceu em {len(ufF)} unidades da federação e Lula em {len(ufL)}.</p>'
            f'<table><caption>Presidente, 1º turno, por estado (% dos votos válidos)</caption><thead><tr><th scope=col>UF</th>'
            f'<th scope=col>{rotulo(cF)}</th><th scope=col>{curto(cL)}</th></tr></thead><tbody>{linhas}</tbody></table>'
            f'<p><a href="/">Resultado do 1º turno completo</a> · <a href="/apuracao/">Histórico da apuração, leitura a leitura</a></p></section>')


# ---------------- FAQ (visível + FAQPage) — respostas geradas dos dados
def faq():
    pst = fmt(N["pst"], 2)
    qa = [
        ("Quem vai para o 2º turno da eleição presidencial de 2026?",
         f"{rotulo(cF)} e {rotulo(cL)}. Com {pst}% das seções apuradas pelo TSE, Flávio teve {fmt(cF['p'], 2)}% dos votos válidos e Lula, {fmt(cL['p'], 2)}%. Nenhum candidato passou de 50%."),
        ("Quando é o 2º turno das eleições de 2026?",
         "Domingo, 25 de outubro de 2026, o último domingo de outubro, como define a Constituição. Haverá 2º turno para presidente e para governador nos estados em que ninguém passou de 50% dos votos válidos."),
        (f"Em quais estados {rotulo(cF)} e {rotulo(cL)} venceram?",
         f"{curto(cF)} venceu em {len(ufF)} unidades da federação ({', '.join(u['uf'] for u in sorted(ufF, key=lambda u: u['uf']))}). {curto(cL)} venceu em {len(ufL)} ({', '.join(u['uf'] for u in sorted(ufL, key=lambda u: u['uf']))}). A disputa mais apertada foi no {apertado['uf']}, decidida por {fmt(abs(apertado['saldo']), 0)} votos."),
        ("Quais estados terão 2º turno para governador?",
         f"{', '.join(g['uf'] for g in gov2)}" + (f". No {', '.join(g['uf'] for g in govIn)}, o resultado depende do julgamento de uma candidatura sub judice" if govIn else "") +
         f". Os outros {len(govEl)} estados elegeram o governador no 1º turno" + (" (situação oficial do TSE)." if GOV_OFICIAL else " (cálculo pelas regras eleitorais, antes da proclamação oficial).")),
        ("Qual partido elegeu mais deputados federais em 2026?",
         f"O PL, com {plFed} das 513 cadeiras da Câmara, segundo os eleitos marcados pelo TSE" + (f" ({', '.join(rel['depfed']['ufs_pendentes'])} ainda em totalização)" if rel["depfed"].get("ufs_pendentes") else "") + ". Em 2022, o PL tinha eleito 99 deputados."),
        ("Quantas vagas do Senado o PL conquistou em 2026?",
         f"{plSen} das {sum(n for _, n in rel['sen_part'])} vagas em disputa (dois terços do Senado, duas por estado)."),
        ("Qual foi a abstenção no 1º turno de 2026?",
         f"{fmt(N['pa'], 2)}% dos eleitores, cerca de {fmt(N['abstencao'] / 1e6, 1)} milhões de pessoas. Em 2022, a abstenção no 1º turno foi de 20,95%."),
        ("As pesquisas acertaram o 1º turno?",
         f"Para {curto(cL)}, sim. Para {curto(cF)}, a maioria errou: Datafolha, Quaest, PoderData, MDA e AtlasIntel indicavam entre 42,1% e 44,1% dos válidos na véspera, e ele fez {fmt(cF['p'], 1)}%."),
    ]
    vis = '<section id="perguntas" class="faq"><h2>Perguntas frequentes</h2><p class="lead">Respostas curtas, com os números da apuração.</p>' + \
          "".join(f"<details{' open' if i < 2 else ''}><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>" for i, (q, a) in enumerate(qa)) + "</section>"
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}
    return vis, ld, qa


# ---------------- Análise (/analise/): página, páginas de compartilhamento por seção e cartões OG
# Seções e âncoras: mesma lista de analise/js/calc.js (SECOES); tests/test_analise_front.py confere.
SECOES_ANALISE = [
    ("destaques", "Destaques"), ("campos", "Votos por lado e cargo"), ("voto-dividido", "Voto dividido"),
    ("votos-cadeiras", "Votos × cadeiras"), ("divergencias", "Divergências"), ("comparacao-2022", "2022 × 2026"),
    ("terra-gente", "Terra × gente"), ("cenarios-2-turno", "Cenários do 2º turno"), ("brancos-nulos", "Brancos e nulos"), ("fragmentacao", "Fragmentação"),
    ("legenda", "Voto de legenda"), ("puxadores", "Puxadores de voto"), ("faq", "Perguntas frequentes"), ("metodo", "Método"),
]
ANALISE_DADOS = R / "analise" / "dados"
# a Análise foi gerada em 08/10/2026 (posição dos lados e analise/calcular.py); não herda as datas do 1º turno
ANALISE_GERADA = ISO(datetime(2026, 10, 8, 12, 0))
ANALISE_TITULO = "Voto dividido em 2026: Lula (PT), Flávio (PL) e o Congresso | Análise"
ANALISE_DESC = ("Por que Lula (PT) tem tantos votos e o lado dele elege poucos deputados? Voto dividido estimado, votos × cadeiras, "
                "divergências por município e 2022 × 2026, com dados do TSE.")


def analise_dados():
    """analise/dados/*.json (gerados por analise/calcular.py); {} se ainda não existem"""
    if not ANALISE_DADOS.is_dir():
        return {}
    return {p.stem: json.loads(p.read_text()) for p in sorted(ANALISE_DADOS.glob("*.json"))}


def copiar_analise(dest):
    """analise/js → /analise/js (sem testes Deno); analise/dados → /analise/dados (se existir)"""
    shutil.copytree(R / "analise" / "js", dest / "analise" / "js", dirs_exist_ok=True, ignore=shutil.ignore_patterns("*_test.js"))
    if ANALISE_DADOS.is_dir():
        shutil.copytree(ANALISE_DADOS, dest / "analise" / "dados", dirs_exist_ok=True)


CODIGO_ANALISE = ["analise/calcular.py", "analise/inferencia.py", "municipios/montar.py",  # montar.py: calcular.py importa `nome` dele
                  "analise/lados-2022.json", "analise/lados-2026.json", "analise/lados-README.md", "analise/fontes/cenarios.json"]


CODIGO_ANALISE_TITULO = "Código do cálculo | Análise · Eleições 2026"
CODIGO_ANALISE_DESC = "Código-fonte aberto do cálculo das estimativas da Análise (voto dividido, inferência ecológica), em texto puro."


def copiar_codigo_analise(dest, publicado=None, modificado=None):
    """Código do cálculo → /analise/codigo/ (cópia das fontes, com a mesma estrutura) + index.html com a lista"""
    publicado, modificado = publicado or ANALISE_GERADA, modificado or ANALISE_GERADA
    base = dest / "analise" / "codigo"
    for rel in CODIGO_ANALISE:
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(R / rel, base / rel)
    itens = "".join(f'<li><a href="{rel}">{rel}</a></li>' for rel in CODIGO_ANALISE)
    url = BASE + "/analise/codigo/"
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": CODIGO_ANALISE_TITULO, "description": CODIGO_ANALISE_DESC,
           "url": url, "inLanguage": "pt-BR", "author": PESSOA, "datePublished": publicado, "dateModified": modificado},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Início", "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": "Análise", "item": BASE + "/analise/"},
              {"@type": "ListItem", "position": 3, "name": "Código do cálculo", "item": url}]}]
    (base / "index.html").write_text(
        '<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + head(CODIGO_ANALISE_TITULO, CODIGO_ANALISE_DESC, "/analise/codigo/", "/og/index.png", ld, publicado, modificado) +
        f'<style>{brand.CSS}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 var(--font-sans)}}main{{max-width:640px;margin:0 auto;padding:48px 16px}}</style>'
        '</head><body><main id="conteudo"><p class="kicker">Análise · cálculo aberto</p><h1>Código do cálculo</h1>'
        '<p>Código do cálculo das estimativas da Análise, em texto puro.</p>'
        f'<ul>{itens}</ul><p><a href="/analise/">← Voltar à análise</a></p></main></body></html>')


def ld_analise(dados, publicado=None, modificado=None):
    """JSON-LD da /analise/. Datas: sempre ANALISE_GERADA (os parâmetros ficam só por compatibilidade)."""
    publicado = modificado = ANALISE_GERADA
    og = BASE + ("/og/analise-destaques.png" if dados else "/og/index.png")
    ld = [{"@context": "https://schema.org", "@type": "Article", "headline": ANALISE_TITULO[:110], "description": ANALISE_DESC,
           "inLanguage": "pt-BR", "datePublished": publicado, "dateModified": modificado, "author": PESSOA, "publisher": PESSOA,
           "image": [og], "mainEntityOfPage": BASE + "/analise/", "about": ELEICAO, "isBasedOn": "https://resultados.tse.jus.br/oficial/app/index.html",
           "keywords": "voto dividido 2026, eleições 2026, Lula, Flávio Bolsonaro, deputados, Senado, quociente eleitoral, centrão, inferência ecológica"},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Início", "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": "Análise", "item": BASE + "/analise/"}]}]
    faq_a = dados.get("faq") or []
    if faq_a:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage",
                   "mainEntity": [{"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in faq_a]})
    return ld


def html_analise(dados, publicado, modificado):
    raw = brand.aplicar((R / "template_analise.html").read_text()).replace("<!--__RODAPE__-->", rodape(), 1).replace("<!--__AGORA__-->", agora_topo(), 1).replace("<!--__TEMA__-->", TEMA_BOTAO, 1)
    raw = raw.replace("<!--__SECOES__-->", menu_secoes("/analise/"), 1).replace("</head>", SECOES_CSS + "</head>", 1)
    og = "/og/analise-destaques.png" if dados else "/og/index.png"
    return montar_pagina(raw, ANALISE_TITULO, ANALISE_DESC, "/analise/", og, ld_analise(dados, publicado, modificado), publicado, modificado, "/analise/", moldura=False)


def secoes_do_dom(dom):
    """{id: {titulo, numero, rotulo}} lidos do HTML pré-renderizado (data-* de cada <section>): o texto vem do JS, uma fonte só"""
    out = {}
    for tag in re.findall(r"<section\b[^>]*>", dom):
        a = dict((k, html.unescape(v)) for k, v in re.findall(r'\s([\w-]+)="([^"]*)"', tag))
        if a.get("id") in dict(SECOES_ANALISE):
            out[a["id"]] = {"titulo": a.get("data-titulo", ""), "numero": a.get("data-numero", ""), "rotulo": a.get("data-rotulo", "")}
    return out


def pagina_compartilhar(sid, info, publicado, modificado, com_og=True):
    """/analise/<id>/: carrega o OG daquela seção (WhatsApp/X leem daqui) e leva para /analise/#<id>"""
    nome = dict(SECOES_ANALISE)[sid]
    titulo = info.get("titulo") or nome
    desc = " ".join(x for x in (info.get("numero"), info.get("rotulo")) if x) or ANALISE_DESC
    alvo = f"/analise/#{sid}"
    h = head(f"{titulo} | Análise · Eleições 2026", desc, f"/analise/{sid}/", f"/og/analise-{sid}.png" if com_og else "/og/index.png", [], publicado, modificado)
    h = h.replace(f'<link rel="canonical" href="{BASE}/analise/{sid}/">', f'<link rel="canonical" href="{BASE}/analise/">', 1)
    h = h.replace('<meta name="robots" content="index,follow', '<meta name="robots" content="noindex,follow', 1)
    return (f'<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n{h}'
            f'<meta http-equiv="refresh" content="0;url={alvo}">'
            f'<style>{brand.CSS}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 var(--font-sans)}}main{{max-width:640px;margin:0 auto;padding:48px 16px}}</style>'
            f'<script>location.replace("{alvo}")</script></head><body><main id="conteudo"><p class="kicker">Análise · {html.escape(nome)}</p>'
            f'<h1>{html.escape(titulo)}</h1><p>{html.escape(desc)}</p><p><a href="{alvo}">Ver a análise completa →</a></p></main></body></html>')


def og_analise_html():
    """página só do build: o Chrome desenha o cartão de cada seção com os mesmos módulos da página"""
    tpl = (R / "template_analise.html").read_text()
    estilo = re.search(r"<style>(.*?)</style>", tpl, re.S).group(1).replace(brand.MARCADOR, brand.CSS, 1)
    css = """body{margin:0;background:var(--bg)}
.og{width:1200px;height:630px;padding:48px 64px 36px;display:flex;flex-direction:column;background:var(--bg);color:var(--ink);position:relative;overflow:hidden}
.og.social{width:1080px;height:1350px;padding:84px 72px 64px}
.og::before{content:"";position:absolute;left:0;right:0;top:0;height:6px;background:var(--brand)}
.og-k{margin:0;font:500 19px var(--font-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);display:flex;gap:12px;align-items:center}
.og-k .badge{font-size:15px;padding:1px 12px}
.og h1{font:600 38px/1.14 var(--font-mono);letter-spacing:-.02em;margin:16px 0 0}
.social h1{font-size:54px;margin-top:28px}
.og-n{display:flex;align-items:baseline;gap:18px;margin:18px 0 0}
.og-n b{font:600 76px/1 var(--font-mono);letter-spacing:-.03em}
.social .og-n{flex-direction:column;gap:10px;margin-top:40px}.social .og-n b{font-size:120px}
.og-n span{font-size:21px;color:var(--ink2);max-width:640px}
.social .og-n span{font-size:28px;max-width:none}
.og-g{flex:1;min-height:0;margin:18px 0 10px;overflow:hidden}
.social .og-g{margin-top:44px}
.og .ch text{font-size:16px}.og .ch .rl{font-size:17px}.og .ch .vl,.og .ch .vl2{font-size:16px}
.og .leg-l,.og .leg-h{font-size:17px}
.social .ch text{font-size:21px}.social .ch .rl{font-size:22px}.social .ch .vl,.social .ch .vl2{font-size:20px}.social .leg-l,.social .leg-h{font-size:22px}
.og .pm li{padding:14px}.og .pm-t{font-size:17px}.og .pm-n{font-size:30px}
.og-cards,.og-faq{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.og-cards{grid-template-columns:repeat(3,1fr)}.social .og-cards{grid-template-columns:1fr 1fr}
.og-cards li{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;display:flex;flex-direction:column;gap:8px}
.og-cards b{font:600 44px/1 var(--font-mono)}.og-cards span{font-size:18px;color:var(--ink2)}
.og-faq li{font:600 26px/1.3 var(--font-sans);border-left:4px solid var(--line);padding-left:16px}
.og-pe{display:flex;justify-content:space-between;align-items:center;gap:20px;margin:0;font-size:19px;color:var(--muted)}
.social .og-pe{font-size:24px;flex-wrap:wrap}
.og-pe .og-m{color:var(--ink2)}
.og-pe b{color:var(--ink);font:600 21px var(--font-mono)}.og-pe b i{display:inline-block;width:10px;height:22px;background:var(--brand);vertical-align:-4px;margin-left:3px}"""
    return (f'<!doctype html><html lang="pt-BR" data-theme="dark"><head><meta charset="utf-8"><style>{estilo}\n{css}</style></head>'
            f'<body><div id="og"></div><script type="module" src="/analise/js/og.js"></script></body></html>')


# ---------------- servidor local + pré-render
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path.startswith("/vivo/"):  # pré-render: o 2º turno ainda não existe (o HUD mostra "Aguardando o TSE")
            self.send_response(404); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}"); return
        if self.path.startswith("/tse/"):  # mesmo repasse que o vercel.json faz em produção
            import urllib.request
            try:
                body = urllib.request.urlopen("https://resultados.tse.jus.br/oficial/" + self.path[5:], timeout=30).read(); code = 200
            except Exception as e:
                body, code = b"{}", getattr(e, "code", 502)
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()


def serve(dirpath, port=0):  # 0 = porta livre: builds em paralelo (worktrees do dev-flow) não brigam pela mesma
    handler = functools.partial(Quiet, directory=str(dirpath))
    class Srv(socketserver.TCPServer): allow_reuse_address = True
    srv = Srv(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def chrome(*args):
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", *args],
                          capture_output=True, text=True, timeout=90).stdout


def prerender(url):
    dom = chrome("--virtual-time-budget=6000", "--dump-dom", url)
    assert "<html" in dom, f"pré-render vazio: {url}"
    return "<!doctype html>\n" + dom


# ---------------- imagem de compartilhamento (1200×630)
def og_card(titulo, sub, f, l, rodape_txt, linha=None):
    """linha: HTML dos cartões no lugar de Flávio × Lula com f e l (%)"""
    linha = linha or (f'<div class="c" style="--c:#5B7FE8"><div class="n">Flávio Bolsonaro · {html.escape(cF["sg"])}</div><div class="p">{fmt(f, 2)}%</div></div>\n'
                      f'<div class="c" style="--c:#E35A4F"><div class="n">Lula · {html.escape(cL["sg"])}</div><div class="p">{fmt(l, 2)}%</div></div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Inter;font-weight:100 900;src:url(/fonts/inter-latin-wght-normal.woff2)}}
@font-face{{font-family:"JetBrains Mono";font-weight:100 800;src:url(/fonts/jetbrains-mono-latin-wght-normal.woff2)}}
*{{box-sizing:border-box}}body{{margin:0;width:1200px;height:630px;background:#070B12;font-family:Inter,sans-serif;color:#E9EEF7}}
.w{{padding:64px 72px;height:100%;display:flex;flex-direction:column}}
.k{{font:500 22px "JetBrains Mono",monospace;color:#8593AB;letter-spacing:.1em;text-transform:uppercase}}
h1{{font:600 60px/1.05 "JetBrains Mono",monospace;margin:14px 0 0;letter-spacing:-.02em}}
.row{{display:flex;gap:28px;margin-top:auto}}.c{{flex:1;background:#0C121D;border:2px solid #1E2A3D;border-radius:20px;padding:24px 30px;border-top:10px solid var(--c)}}
.n{{font-size:28px;color:#8593AB}}.p{{font:600 92px/1 "JetBrains Mono",monospace;color:var(--c)}}
.f{{margin-top:26px;font-size:22px;color:#8593AB;display:flex;justify-content:space-between}}
.f b{{color:#E9EEF7;font:600 22px "JetBrains Mono",monospace}}.f b i{{display:inline-block;width:11px;height:24px;background:#24C8FF;vertical-align:-4px;margin-left:3px}}</style></head><body><div class="w">
<div class="k">{html.escape(sub)}</div><h1>{html.escape(titulo)}</h1>
<div class="row">{linha}</div>
<div class="f"><span>{html.escape(rodape_txt)}</span><b>vitor pereira<i></i></b></div></div></body></html>"""


def cards_turno2():
    """Cartões OG da home e do /ao-vivo/ até o 2º turno: os dois candidatos sem o percentual do 1º turno."""
    lado = lambda c, cor: (f'<div class="c" style="--c:{cor}"><div class="n">{html.escape(NOME_EXIBICAO.get(c["nome"], c["nome"]))} · '
                           f'{html.escape(c["sg"])}</div><div class="p">{html.escape(curto(c).split()[0])}</div></div>')
    linha = lado(cF, COR_OG["flavio"]) + "\n" + lado(cL, COR_OG["lula"])
    return [("index", og_card("2º turno · domingo, 25/10", "Eleições 2026 · presidente", None, None,
                              "apuração ao vivo a partir das 17h (Brasília)", linha)),
            ("ao-vivo", og_card("Apuração ao vivo em 25/10", "Eleições 2026 · 2º turno · dados do TSE", None, None,
                                "5.570 municípios · a partir das 17h (Brasília)", linha))]


def rastro_envolver(publicado, modificado, moldura=True):
    """Devolve `envolver(página) -> html` do Rastro: moldura do site (montar_pagina) + medição."""
    def envolver(p):
        ld =[{"@context": "https://schema.org", "@type": "WebPage", "name": p["titulo"], "description": p["desc"], "url": BASE + p["path"],
               "inLanguage": "pt-BR", "author": PESSOA, "dateModified": modificado},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": i, "name": n, "item": BASE + (h or p["path"])}
                  for i, (n, h) in enumerate([("Início", "/")] + p["crumbs"], 1)]}]
        h = montar_pagina(p["html"], p["titulo"], p["desc"], p["path"], "/og/index.png", ld, publicado, modificado, "/rastro/", moldura=moldura)
        if not p.get("indexar", True):  # MEI e sem cadastro: no ar, mas fora do índice (título igual entre todos, sem dado a acrescentar)
            h = h.replace('<meta name="robots" content="index,follow', '<meta name="robots" content="noindex,follow', 1)
        return com_medicao(h)
    return envolver


def rastro_sitemap(pags, modificado):
    """Entradas do sitemap das páginas do Rastro, sem as que não indexam (indexar=False)."""
    def prioridade(path):
        if path == "/rastro/":
            return "0.6"
        return "0.5" if path.endswith("/metodologia/") else "0.3" if path.startswith("/rastro/fornecedor/") else "0.4"
    return [(p["path"], modificado, prioridade(p["path"])) for p in pags if p.get("indexar", True)]


def presidentes():
    """Candidatos do 2º turno a presidente com página no Rastro (rastro/presidentes.json; sem o arquivo, nenhum)."""
    p = R / "rastro" / "presidentes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def links_rastro():
    """{id_tse: path da página no Rastro} dos presidentes, para o placar de /debates/."""
    from rastro import paginas as rp
    return {str(sq): "/" + c for sq, c in rp.caminhos(presidentes()).items()}


def rastro_publicar(dest, publicado, modificado, moldura=True):
    """Rastro do dinheiro: metodologia e uma página por sq de rastro/publicados.json, em dest/rastro/. HTML estático, sem
    pré-render; só a moldura do site, a medição, o filtro da tabela (rastro.js) e a busca (busca.js e busca.json, opcionais).
    Devolve as entradas do sitemap."""
    from rastro import paginas as rp
    (Path(dest) / "rastro").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(R / "rastro" / "rastro.js", Path(dest) / "rastro" / "rastro.js")
    lj = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    dados = R / "rastro" / "dados"
    envolver = rastro_envolver(publicado, modificado, moldura)

    from debates import pagina as dp
    publicados = lj(R / "rastro" / "publicados.json") or []
    pres = presidentes()
    forn = lj(dados / "fornecedores.json")
    sal = rp.ler_sal() if (publicados or pres) and rp.SAL.exists() else None  # só lido, nunca criado aqui; gerar exige quando há MEI
    pags = rp.gerar(dest, publicados, lj(dados / "eleitos.json") or {"eleitos": []}, dados / "contas",
                    lj(dados / "indicadores.json"), forn,
                    json.loads((R / "rastro" / "config.json").read_text(encoding="utf-8")), envolver,
                    correcoes=lj(R / "rastro" / "correcoes.json"), sal=sal, anteriores=lj(dados / "anteriores.json"),
                    agregados=lj(dados / "base" / "agregados.json"), presidentes=pres,
                    debates=dp.listar(R / "debates"))
    return rastro_sitemap(pags, modificado)


# ---------------- checagem de debates (debates/pagina.py): estática, um debate por debates/<ano>/<slug>/ com checagens.json
COR_OG = {"flavio": "#5B7FE8", "lula": "#E35A4F", "outros": "#8593AB"}  # os mesmos hex de partido do og_card (tema escuro)


@functools.lru_cache(maxsize=None)
def debates(raiz=R / "debates"):
    """Páginas geradas de cada debate com checagem (dicts de debates.pagina.gerar), do mais novo para o mais antigo."""
    from debates import pagina as dp
    ms = dp.listar(raiz)
    lig = dp.tambem(ms)  # a mesma tese, dita pelo mesmo candidato em outro debate: "Também dito em"
    return [dp.gerar(m, BASE, PESSOA, tambem=lig) for m in ms]


def banner_debate():
    ds = debates()
    if not ds:
        return ""
    d = ds[0]
    return f'<div class="banner"><div>{html.escape(d["og"][1])}: <a href="{d["path"]}">{html.escape(d["og"][4])} →</a></div></div>'


def debates_publicar(dest, raiz=R / "debates"):
    """Escreve dest/debates/ (índice, debate.js e, por debate, a página, a transcrição e uma página por afirmação).
    Sem nenhum debate com checagem, avisa e devolve None. Senão devolve as entradas do sitemap, as linhas do llms.txt
    e os cards OG [(nome, html)]."""
    from debates import pagina as dp
    ds = debates(raiz)
    if not ds:
        print(f"aviso: nenhum {raiz}/<ano>/<slug>/checagens.json: seção de debates não publicada", file=sys.stderr)
        return None
    dest = Path(dest)

    def escrever(p, og):
        pasta = dest / p["path"].strip("/")
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "index.html").write_text(com_medicao(montar_pagina(p["html"], p["titulo"], p["desc"], p["path"], f"/og/{og}.png",
                                                                   p["ld"], p["publicado"], p["modificado"], "/debates/")))
    idx = dp.indice(ds, BASE, PESSOA, links_rastro())
    escrever(idx, ds[0]["og"][0])
    shutil.copyfile(R / "debates" / "debate.js", dest / "debates" / "debate.js")
    sitemap, og = [(idx["path"], idx["modificado"], "0.8")], []
    for d in ds:
        escrever(d, d["og"][0])
        escrever(d["transcricao"], d["og"][0])
        sitemap += [(d["path"], d["modificado"], "0.8"), (d["transcricao"]["path"], d["transcricao"]["modificado"], "0.3")]
        og.append((d["og"][0], og_debate(*d["og"][1:])))
        for a in d["afirmacoes"]:
            escrever(a, a["og"][0])
            sitemap.append((a["path"], a["modificado"], "0.5"))
            og.append((a["og"][0], og_afirmacao(*a["og"][1:])))
    return dict(sitemap=sitemap, llms=idx["llms"] + "".join(d["llms"] for d in ds), og=og)


def og_debate(titulo, sub, por_cand, rodape_txt):
    """Card 1200×630 do debate: quantas afirmações de cada candidato foram checadas, só com as cores de partido."""
    cx = "".join(f'<div class="c" style="--c:{COR_OG[cor]}"><div class="n">{html.escape(nome)} · {html.escape(sg)}</div>'
                 f'<div class="p">{n}</div><div class="n">afirmações</div></div>' for nome, sg, cor, n in por_cand)
    return og_card(titulo, sub, 0, 0, rodape_txt, linha=cx)


def og_afirmacao(frase, quem, cor, veredito):
    """Card 1200×630 de uma afirmação: a frase (cortada em ~180 caracteres), quem disse e o veredito; a cor é a do partido."""
    if len(frase) > 180:
        frase = frase[:177].rsplit(" ", 1)[0] + "…"
    tam = 48 if len(frase) <= 90 else 38
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Inter;font-weight:100 900;src:url(/fonts/inter-latin-wght-normal.woff2)}}
@font-face{{font-family:"JetBrains Mono";font-weight:100 800;src:url(/fonts/jetbrains-mono-latin-wght-normal.woff2)}}
*{{box-sizing:border-box}}body{{margin:0;width:1200px;height:630px;background:#070B12;font-family:Inter,sans-serif;color:#E9EEF7}}
.w{{padding:64px 72px;height:100%;display:flex;flex-direction:column;border-left:14px solid {COR_OG[cor]}}}
.k{{font:500 24px "JetBrains Mono",monospace;color:{COR_OG[cor]};letter-spacing:.06em;text-transform:uppercase}}
q{{display:block;font:600 {tam}px/1.25 Inter,sans-serif;margin:22px 0 0}}
.v{{margin-top:auto;align-self:flex-start;font:600 34px "JetBrains Mono",monospace;border:3px solid #E9EEF7;border-radius:999px;padding:8px 30px}}
.f{{margin-top:26px;font-size:22px;color:#8593AB;display:flex;justify-content:space-between}}
.f b{{color:#E9EEF7;font:600 22px "JetBrains Mono",monospace}}.f b i{{display:inline-block;width:11px;height:24px;background:#24C8FF;vertical-align:-4px;margin-left:3px}}</style></head><body><div class="w">
<div class="k">{html.escape(quem)}</div><q>{html.escape(frase)}</q>
<div class="v">{html.escape(veredito)}</div>
<div class="f"><span>Checagem de debate</span><b>vitor pereira<i></i></b></div></div></body></html>"""


IDX_CSS = """<style>
.rd{display:grid;grid-template-columns:96px 120px 1fr 260px;gap:16px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 10px;color:var(--ink);text-decoration:none}
.rd:hover{border-color:var(--muted)}.rd .t{color:var(--ink2);font-variant-numeric:tabular-nums}.rd .p{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.rd small{display:block;font-size:12px;font-weight:400;color:var(--muted)}.rd .bar{height:12px;border-radius:4px;background:var(--line);display:flex;gap:2px;overflow:hidden}.rd .bar i{display:block;height:100%}
.rd .v{font-size:14px;font-variant-numeric:tabular-nums}.final{border-left:4px solid var(--ink)}
@media (max-width:760px){.rd{grid-template-columns:88px 1fr}.rd .bar,.rd .v{grid-column:1/-1}}</style>"""


def minha_secao_publicar(dest, publicado, modificado, pasta=None, meta=None):
    """/minha-secao/ (municipios/minha_secao.py): com dados, a busca e os índices; sem dados, "em breve" (noindex, fora
    do sitemap e do menu). Sem medição e sem o contador "pessoas agora" (que abre conexão com o Supabase): a página não
    faz requisição para outro domínio. Devolve as entradas do sitemap."""
    from municipios import minha_secao as msec
    p = msec.gerar(dest, LOCAIS if pasta is None else pasta, meta)
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": p["titulo"], "description": p["desc"], "url": BASE + "/minha-secao/",
           "inLanguage": "pt-BR", "author": PESSOA, "about": ELEICAO, "isBasedOn": msec.FONTE, "dateModified": modificado},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": NAV.INICIO, "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": NAV.MINHA_SECAO, "item": BASE + "/minha-secao/"}]}]
    h = montar_pagina(p["html"], p["titulo"], p["desc"], "/minha-secao/", "/og/index.png", ld, publicado, modificado, "/minha-secao/")
    assert h.count(agora_topo()) == 1, "sitebar sem o contador de presença: ajuste minha_secao_publicar"
    h = h.replace(agora_topo(), "", 1)
    if not p["tem"]:
        h = h.replace('<meta name="robots" content="index,follow', '<meta name="robots" content="noindex,follow', 1)
    (Path(dest) / "minha-secao" / "index.html").write_text(h, encoding="utf-8")
    return [("/minha-secao/", modificado, "0.6")] if p["tem"] else []


def linha_rodada(r):
    d = r["d"]; fim = d["traj"]["mc50"][-1] if "traj" in d else d["scen"][0]
    return (f'<a class="rd" href="{r["url"]}"><span class="t">{d["ht"][:5]}</span><span class="p">{fmt(d["pst"], 1)}%<small>apurado</small></span>'
            f'<span class="bar"><i style="width:{d["f"]}%;background:var(--flavio)"></i><i style="width:{d["l"]}%;background:var(--lula)"></i></span>'
            f'<span class="v">{curto(cF)} {fmt(d["f"], 2)}% × {curto(cL)} {fmt(d["l"], 2)}%<small>previsão para o fim da apuração: {fmt(fim["f"], 1)} × {fmt(fim["l"], 1)}</small></span></a>')


def pagina_apuracao(style):
    """/apuracao/: índice das leituras (HTML estático, sem JS); `style` = CSS do relatório"""
    turno2 = ""
    if rodadas_2t:
        turno2 = (f'<section style="margin-top:22px"><h2>2º turno, 25/10</h2><p>Cada página é o painel da projeção como estava naquele momento da noite.'
                  f'{" <a href=\"/estudo-2-turno/\">Estudo: de onde vieram os votos da virada →</a>" if ESTUDO2T_ARQ.exists() else ""}</p>'
                  f'{"".join(linha_rodada(r) for r in reversed(rodadas_2t))}</section><h2 style="margin-top:28px">1º turno, 04/10</h2>')
    linhas = "".join(
        f'<a class="rd" href="{r["url"]}"><span class="t">{r["d"]["ht"][:5]}</span><span class="p">{fmt(r["d"]["pst"], 1)}%<small>apurado</small></span>'
        f'<span class="bar"><i style="width:{r["d"]["f"]}%;background:var(--flavio)"></i><i style="width:{r["d"]["l"]}%;background:var(--lula)"></i></span>'
        f'<span class="v">{curto(cF)} {fmt(r["d"]["f"], 2)}% × {curto(cL)} {fmt(r["d"]["l"], 2)}%<small>previsão para o fim da apuração: {fmt(r["d"]["traj"]["mc50"][-1]["f"] if "traj" in r["d"] else r["d"]["scen"][0]["f"], 1)} × {fmt(r["d"]["traj"]["mc50"][-1]["l"] if "traj" in r["d"] else r["d"]["scen"][0]["l"], 1)}</small></span></a>'
        for r in rodadas)
    rows_final = (f'<a class="rd final" href="/1-turno/"><span class="t">{hora_leitura(N["dg"], N["ht"])}</span><span class="p">{fmt(N["pst"], 2)}%<small>resultado</small></span>'
                  f'<span class="bar"><i style="width:{cF["p"]}%;background:var(--flavio)"></i><i style="width:{cL["p"]}%;background:var(--lula)"></i></span>'
                  f'<span class="v"><b>{curto(cF)} {fmt(cF["p"], 2)}% × {curto(cL)} {fmt(cL["p"], 2)}%</b><small>relatório final completo →</small></span></a>')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>x</title>{style}{IDX_CSS}</head><body><main>
<header><h1>Histórico da apuração: {"1º e 2º turno" if rodadas_2t else "o 1º turno"}, leitura a leitura</h1></header>{turno2}<p>{curto(cF)} começou a noite com mais de 50% porque o Sul e o Centro-Oeste foram apurados mais rápido. Conforme o Nordeste entrou, {curto(cL)} reduziu a diferença, mas não passou. Cada página abaixo é o painel exatamente como estava naquele momento.</p>
<section style="margin-top:22px">{rows_final}{linhas}</section>
<p class="note">As leituras de 24,5% (18:19) e 27,9% (18:23) não têm painel salvo; os números delas aparecem na trajetória de cada página.</p></main></body></html>"""


# ---------------- estudo do 2º turno (/estudo-2-turno/): analise/estudo_2turno.py → analise/estudo2t/estudo.json
ESTUDO2T_ARQ = R / "analise" / "estudo2t" / "estudo.json"
ESTUDO2T_CSS = """<style id="estudo2t">
.e2-num{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin:18px 0}
.e2-num div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.e2-num b{display:block;font:700 26px/1.1 var(--font-mono);font-variant-numeric:tabular-nums}
.e2-num small{color:var(--muted);font-size:12.5px}
.e2-bolo{display:flex;height:22px;border-radius:6px;overflow:hidden;margin:10px 0 6px}
.e2-bolo i{display:block;height:100%}
.e2 table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
.e2 th,.e2 td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right}
.e2 th:first-child,.e2 td:first-child{text-align:left}
.e2 .rol{overflow-x:auto}
.e2 .nota{color:var(--muted);font-size:13px}
</style>"""


def pagina_estudo2t(style, e):
    """/estudo-2-turno/: HTML estático (sem JS). `e` = analise/estudo2t/estudo.json; `style` = CSS do relatório."""
    f = e["fatos"]; t1, t2 = f["t1"], f["t2"]; b = f["bolo"]; g = e["gerado_com"]
    mi = lambda v: fmt(v / 1e6, 2) + " mi"
    sinal = lambda v, d=0: ("+" if v > 0 else "−" if v < 0 else "") + fmt(abs(v), d)
    pL = 100 * f["ganho"]["L"] / b["total"]
    linhas_fato = "".join(
        f"<tr><td>{n}</td><td>{fmt(a, 0)}</td><td>{fmt(c, 0)}</td><td>{sinal(c - a)}</td></tr>"
        for n, a, c in [("Lula (PT)", t1["L"], t2["L"]), ("Flávio Bolsonaro (PL)", t1["F"], t2["F"]),
                        ("Outros candidatos", t1["O"], 0), ("Brancos e nulos", t1["BN"], t2["BN"]),
                        ("Não votaram", t1["A"], t2["A"]), ("Compareceram", t1["comp"], t2["comp"])])
    ufs = "".join(
        f"<tr><td>{u['uf']}</td><td>{sinal(u['saldo1'])}</td><td>{sinal(u['saldo2'])}</td><td><b>{sinal(u['virada'])}</b></td>"
        f"<td>{fmt(u['l1'], 1)}% → {fmt(u['l2'], 1)}%</td><td>{sinal(u['dcomp'])}</td></tr>" for u in e["ufs"])
    viradas = [u["uf"] for u in e["ufs"] if u["saldo1"] < 0 < u["saldo2"]]
    todas = all(u["virada"] > 0 for u in e["ufs"])
    tr = {x["de"]: {c["para"]: c for c in x["para"]} for x in e["transferencia"]}

    def cel(de, para):
        c = tr[de][para]
        return f"<td>{fmt(c['pct'], 0)}%<br><small>{mi(c['votos'])}</small></td>"
    cols = ["Lula", "Flávio", "Branco ou nulo", "Não votou"]
    transf = "".join(f"<tr><td>{de}<br><small>{mi(tr[de]['Lula']['votos'] + tr[de]['Flávio']['votos'] + tr[de]['Branco ou nulo']['votos'] + tr[de]['Não votou']['votos'])}</small></td>"
                     + "".join(cel(de, c) for c in cols) + "</tr>"
                     for de in ["Outros candidatos", "Branco ou nulo", "Não votou", "Flávio", "Lula"])
    bn_l = tr["Branco ou nulo"]["Lula"]
    serie = e["serie"]
    anos = sorted({s["ano"] for s in serie})
    linhas_serie = ""
    for a in anos:
        p, s = [x for x in serie if x["ano"] == a and x["turno"] == 1][0], [x for x in serie if x["ano"] == a and x["turno"] == 2][0]
        linhas_serie += (f"<tr{' style=\"font-weight:700\"' if a == 2026 else ''}><td>{a}</td><td>{fmt(p['abstencao'], 1)}%</td><td>{fmt(s['abstencao'], 1)}%</td>"
                         f"<td>{sinal(s['abstencao'] - p['abstencao'], 1)}</td><td>{fmt(p['bn'], 1)}%</td><td>{fmt(s['bn'], 1)}%</td>"
                         f"<td>{sinal(s['bn'] - p['bn'], 1)}</td></tr>")
    pst = fmt(g["pst2"] or 0, 2)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>x</title>{style}{ESTUDO2T_CSS}</head><body><main class="e2">
<header><p class="kicker">Eleições 2026 · 2º turno · estudo</p><h1>Como Lula virou {mi(f['virada'])} de votos entre o 1º e o 2º turno</h1>
<p>No 1º turno, Flávio Bolsonaro (PL) terminou {mi(-f['saldo1'])} de votos à frente de Lula (PT). No 2º, Lula terminou {mi(f['saldo2'])} à frente. Este estudo mostra, com os números do TSE, de onde veio essa diferença.</p></header>
<div class="e2-num"><div><small>Lula ganhou</small><b>{sinal(f['ganho']['L'])}</b><small>votos do 1º para o 2º turno</small></div>
<div><small>Flávio ganhou</small><b>{sinal(f['ganho']['F'])}</b><small>votos do 1º para o 2º turno</small></div>
<div><small>Foram votar a mais</small><b>{sinal(b['comparecimento'])}</b><small>{fmt(f['pct']['comp1'], 1)}% → {fmt(f['pct']['comp2'], 1)}% do eleitorado</small></div>
<div><small>Brancos e nulos a menos</small><b>{sinal(b['bn'])}</b><small>de {mi(t1['BN'])} para {mi(t2['BN'])}</small></div></div>

<section><h2>A conta que fecha</h2>
<p>Lula e Flávio somaram juntos {mi(b['total'])} de votos a mais no 2º turno. Pelas contagens do TSE, esses votos só podem ter vindo de três lugares: os {mi(b['outros'])} que votaram em outros candidatos no 1º turno, os {mi(b['bn'])} de brancos e nulos a menos e os {mi(b['comparecimento'])} de pessoas a mais que foram votar. <b>Lula ficou com {fmt(pL, 0)}% desses votos novos; Flávio, com {fmt(100 - pL, 0)}%.</b></p>
<div class="e2-bolo" role="img" aria-label="Lula ficou com {fmt(pL, 0)}% dos votos novos e Flávio com {fmt(100 - pL, 0)}%"><i style="width:{pL}%;background:var(--lula)"></i><i style="width:{100 - pL}%;background:var(--flavio)"></i></div>
<div class="rol"><table><tr><th>Brasil</th><th>1º turno</th><th>2º turno</th><th>Variação</th></tr>{linhas_fato}</table></div>
<p class="nota">Fonte: TSE. 2º turno com {pst}% das seções apuradas ({g['hora2']} de 25/10). Inclui o exterior.</p></section>

<section><h2>Onde a diferença mudou</h2>
<p>{'Lula ganhou terreno em todos os estados.' if todas else 'Lula ganhou terreno na maioria dos estados.'}{' Virou em ' + ', '.join(viradas) + '.' if viradas else ''} A coluna "virada" mostra quanto o saldo de Lula sobre Flávio melhorou em votos; estados com saldo negativo são os que Flávio venceu.</p>
<div class="rol"><table><tr><th>UF</th><th>Saldo Lula − Flávio, 1º</th><th>Saldo, 2º</th><th>Virada</th><th>Lula (% válidos)</th><th>Foram votar a mais</th></tr>{ufs}</table></div></section>

<section><h2>Para onde foram os eleitores de cada um (estimativa)</h2>
<p>O voto é secreto, então ninguém sabe ao certo em quem votou, no 2º turno, quem escolheu outro candidato no 1º. Dá para estimar comparando os {fmt(g['municipios'], 0)} municípios: onde havia mais eleitores de um grupo, para quem cresceu o voto. A tabela mostra essa estimativa. É um cálculo, não uma contagem: serve para ver o tamanho de cada movimento, não para cravar números.</p>
<div class="rol"><table><tr><th>No 1º turno votou em…</th><th>Lula</th><th>Flávio</th><th>Branco ou nulo</th><th>Não votou</th></tr>{transf}</table></div>
<p class="nota"><b>Leia com cuidado a linha "Branco ou nulo".</b> A estimativa diz que {fmt(bn_l['pct'], 0)}% de quem anulou ou votou em branco no 1º turno votou em Lula no 2º. Brancos e nulos se concentram nas mesmas regiões onde Lula é forte, e esse tipo de estimativa pode confundir as duas coisas. Só com os resultados por município, o número real pode estar em qualquer ponto entre {mi(bn_l['limites'][0])} e {mi(bn_l['limites'][1])}: é um número possível, não um fato. O que é fato está na conta acima: brancos e nulos caíram {mi(f['bolo']['bn'])} e Lula cresceu mais que Flávio.</p>
<details><summary>Como estimamos</summary><p class="nota">Inferência ecológica (Goodman com restrições + reconciliação por IPF), a mesma de analise/inferencia.py usada na Análise do 1º turno: uma estimativa por UF, com o Brasil como âncora, somada para o país. A reamostragem de municípios ({g['n_boot']} rodadas por UF) dá faixas estreitas, mas elas medem só a variação entre municípios, não o erro do método (o pressuposto de que eleitores de um mesmo grupo se comportam igual em todos os municípios da UF); por isso não são mostradas como margem de erro. Limites de Duncan-Davis somados nos municípios: para brancos e nulos → Lula, de {mi(bn_l['limites'][0])} a {mi(bn_l['limites'][1])}. Eleitorado do 2º turno escalado ao do 1º em cada município (variação menor que 0,1%).</p></details></section>

<section><h2>Abstenção, brancos e nulos desde 2002</h2>
<p>De 2002 a 2018, o 2º turno sempre teve mais abstenção que o 1º. Em 2026, foi o contrário, e com a maior queda da série: mais gente foi votar no 2º turno. Brancos e nulos também caíram, para o menor nível desde 2002.</p>
<div class="rol"><table><tr><th>Ano</th><th>Não votaram, 1º</th><th>2º</th><th>Variação</th><th>Brancos e nulos, 1º</th><th>2º</th><th>Variação</th></tr>{linhas_serie}</table></div>
<p class="nota">Não votaram = % do eleitorado; brancos e nulos = % de quem compareceu. Fontes: 2002 a 2018, tabelas de resultados da Wikipédia (que citam o TSE); 2022 e 2026, TSE.</p></section>
<section><h2>Em breve: quantos votaram depois das 17h</h2>
<p>Uma decisão do STF prorrogou a votação até as 19h nos locais que ainda não tinham encerrado às 17h. O resultado do TSE não separa os votos por horário. Quando o TSE publicar os registros das urnas (com o horário de cada voto, nos dados abertos), este estudo vai mostrar quantos eleitores votaram depois das 17h, onde, e se isso pesou na diferença.</p></section>
<p class="note"><a href="/">Apuração do 2º turno</a> · <a href="/apuracao/">Histórico da apuração</a> · <a href="/1-turno/">Resultado do 1º turno</a></p>
</main></body></html>"""


HOME_CSS = """<style id="home-turno2">
header .kicker{margin:0 0 4px}
.contagem{margin:18px 0 22px;font:600 clamp(17px,3.6vw,22px)/1.3 var(--font-mono);color:var(--ink)}
.portas{display:grid;gap:14px;grid-template-columns:1fr;margin:0 0 22px}
.porta{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;min-width:0}
.porta h2{margin:0 0 6px;font-size:18px}
.porta p{margin:0 0 10px;color:var(--ink2);font-size:14.5px}
.porta ul{list-style:none;margin:0 0 10px;padding:0}
.porta li{margin:0 0 8px;font-size:14.5px}
.porta a.ir{display:inline-block;font-weight:600;padding:6px 0}
.porta small{display:block;color:var(--muted);font-size:12.5px}
.placar{display:grid;gap:22px;grid-template-columns:1fr;margin:18px 0 12px}
.placar .cand{display:grid;gap:6px;min-width:0}
.placar .nome{font-weight:600;color:var(--ink2)}
.placar .pct{font:700 clamp(36px,9vw,64px)/1 var(--font-mono);color:var(--ink);font-variant-numeric:tabular-nums}
.placar .barra{display:block;height:14px;border-radius:5px;background:var(--line);overflow:hidden}
.placar .barra i{display:block;height:100%}
.botao{display:inline-block;margin-top:6px;padding:10px 18px;border:1px solid var(--ink);border-radius:999px;font-weight:600;text-decoration:none}
.botao:hover{background:var(--soft)}
[data-fase][hidden],[data-aguardando][hidden]{display:none}
@media (min-width:641px){.portas{grid-template-columns:repeat(var(--n,3),1fr)}.placar{grid-template-columns:1fr 1fr}}
</style>"""


def home_turno2(style):
    """Home (/): 2º turno em três fases. O HTML publicado sai na Véspera e sem números; home.js troca a fase no navegador
    (apuração a partir das 17h de 25/10 com /vivo/agora.json, resultado quando o TSE marca o eleito). `style` = CSS do relatório."""
    ds = debates()
    portas = []
    if ds:
        lis = "".join(f'<li><a href="{d["path"]}">{html.escape(d["og"][1])}</a><small>{html.escape(d["og"][4])}</small></li>' for d in ds)
        portas.append(f'<div class="porta"><h2>{NAV.DEBATES} checados</h2><p>O que cada candidato disse nos debates, conferido com fontes.</p>'
                      f'<ul>{lis}</ul><a class="ir" href="/debates/">Ver todos →</a></div>')
    from municipios import minha_secao as msec
    if msec.tem_dados(LOCAIS):
        portas.append(f'<div class="porta"><h2>{NAV.MINHA_SECAO}</h2><p>Descubra onde você vota e como a sua seção votou no 1º turno.</p>'
                      '<a class="ir" href="/minha-secao/">Buscar minha seção →</a></div>')
    portas.append('<div class="porta"><h2>Como acompanhar a apuração</h2><p>O mapa mostra a apuração município por município, '
                  'atualizada sozinha a partir das 17h (Brasília).</p><a class="ir" href="/ao-vivo/">Abrir o mapa ao vivo →</a></div>')
    cand = html.escape(json.dumps([{"n": n, "nome": NOME_EXIBICAO.get(c["nome"], c["nome"]), "sg": c["sg"]} for n, c in (("22", cF), ("13", cL))], ensure_ascii=False), quote=True)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>x</title>{style}{HOME_CSS}</head><body><main>
<header><p class="kicker">Eleições 2026 · 2º turno</p><h1>2º turno: {html.escape(rotulo(cF))} × {html.escape(rotulo(cL))}, domingo, 25/10</h1></header>
<section data-fase="vespera">
<p class="contagem">Apuração ao vivo a partir das 17h (Brasília)<span data-faltam></span></p>
<p class="note" data-aguardando hidden>Aguardando os primeiros dados do TSE</p>
<div class="portas" style="--n:{len(portas)}">{"".join(portas)}</div>
<p class="note"><a href="/1-turno/">Resultado do 1º turno (04/10)</a></p>
</section>
<section data-fase="apuracao" data-cand="{cand}" hidden>
<h2>Apuração ao vivo</h2>
<div class="placar" data-placar></div>
<p class="note" data-apurado></p>
<p class="note" data-projecao hidden></p>
<a class="botao" href="/ao-vivo/">Ver o mapa ao vivo</a>
</section>
<section data-fase="resultado" hidden>
<h2 data-eleito></h2>
<p data-eleito-pct></p>
<p><a href="/ao-vivo/">Mapa da apuração por município</a> · <a href="/1-turno/">Resultado do 1º turno</a></p>
</section>
<script type="module" src="/home.js"></script>
</main></body></html>"""


def pagina_404(style):
    """404: atalhos para as seções principais e para a busca do Rastro (issue 150); `style` = CSS do relatório."""
    atalhos = [("/ao-vivo/", f"{NAV.AO_VIVO}: apuração por município")] + (
        [("/debates/", f"{NAV.DEBATES}: o que é verdade")] if debates() else []) + [
        ("/rastro/", f"{NAV.RASTRO}: contas de campanha"), ("/rastro/#busca", "Buscar um eleito, empresa ou CNPJ no Rastro"),
        ("/apuracao/", NAV.APURACAO), ("/1-turno/", NAV.RESULTADO_1T), ("/", f"{NAV.INICIO}: 2º turno, 25/10")]
    lis = "".join(f'<li><a href="{h}">{html.escape(t)}</a></li>' for h, t in atalhos)
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>x</title>{style}</head><body><main><header><h1>Página não encontrada</h1>'
            '<p>O endereço pode ter mudado. Comece por uma destas seções:</p></header>'
            f'<ul class="atalhos-404">{lis}</ul></main></body></html>')


def main():
    for nome, valor in (("GA_ID", GA_ID), ("CLARITY_ID", CLARITY_ID)):
        if not valor:
            print(f"aviso: {nome} não definido (env ou .env): o site sai sem essa medição", file=sys.stderr)
    if BUILD.exists(): shutil.rmtree(BUILD)
    if OUT.exists(): shutil.rmtree(OUT)
    BUILD.mkdir(); OUT.mkdir()
    for dest in (BUILD / "fonts", OUT / "fonts"):
        shutil.copytree(R / "assets" / "fonts", dest, ignore=shutil.ignore_patterns("*.md"))
    srv = serve(BUILD)
    base_url = f"http://127.0.0.1:{srv.server_address[1]}"
    publicado = ISO(datetime(2026, 10, 4, 18, 25)); modificado = ISO(LEITURA)
    paginas = []  # (path, lastmod, prioridade)

    # ---- /1-turno/ = relatório final do 1º turno (era a home até o 2º turno)
    faq_vis, faq_ld, qa = faq()
    raw = (R / "relatorio" / "relatorio_final.html").read_text()
    assert brand.CSS in raw, "relatorio_final.html desatualizado: rode relatorio/montar.py"
    style = re.search(r"<style>.*?</style>", raw, re.S).group(0)
    raw = raw.replace('<section id="metodo">', faq_vis + '\n<section id="metodo">', 1)
    raw = raw.replace('<a href="#metodo">Método e fontes</a>', '<a href="#perguntas">Perguntas</a><a href="#metodo">Método e fontes</a>', 1)
    # H1 com a resposta (AEO); o título antigo vira subtítulo
    h1, titulo, desc = textos_principal()
    antigo = "<h1>Eleições 2026 · Relatório final do 1º turno</h1>"
    assert antigo in raw, "H1 do relatório mudou: ajuste build_site.py"
    raw = raw.replace(antigo, f'<p class="kicker">Relatório final do 1º turno</p>\n  <h1>{html.escape(h1)}</h1>', 1)
    um_turno = BASE + "/1-turno/"
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": BASE + "/", "inLanguage": "pt-BR", "publisher": PESSOA},
          {"@context": "https://schema.org", "@type": "NewsArticle", "headline": titulo[:110], "description": desc, "inLanguage": "pt-BR",
           "datePublished": publicado, "dateModified": modificado, "author": PESSOA, "publisher": PESSOA,
           "image": [BASE + "/og/index.png"], "mainEntityOfPage": um_turno, "about": ELEICAO,
           "isBasedOn": "https://resultados.tse.jus.br/oficial/app/index.html", "keywords": "eleições 2026, resultado 1º turno, Flávio Bolsonaro, Lula, 2º turno, governadores, Senado, Câmara dos Deputados, TSE"},
          {"@context": "https://schema.org", "@type": "Dataset", "name": "Resultados consolidados do 1º turno das Eleições 2026 (por UF e cargo)",
           "description": "Presidente por UF, governadores, Senado e distribuição de vagas para deputados federais, estaduais e distritais, consolidados a partir dos arquivos públicos de divulgação do TSE.",
           "url": um_turno, "creator": PESSOA, "isBasedOn": "https://resultados.tse.jus.br/oficial/app/index.html", "license": "https://creativecommons.org/licenses/by/4.0/",
           "temporalCoverage": "2026-10-04", "spatialCoverage": {"@type": "Country", "name": "Brasil"}, "inLanguage": "pt-BR",
           "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": BASE + "/dados/relatorio.json"}]},
          faq_ld,
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": NAV.INICIO, "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": NAV.RESULTADO_1T, "item": um_turno}]}]
    rounds_nav = "".join(f'<a href="{r["url"]}">{fmt(r["d"]["pst"], 1)}%</a>' for r in rodadas)
    top = NAV.trilha((NAV.INICIO, "/"), (NAV.RESULTADO_1T, None)) + banner_debate() + (
        f'<div class="banner"><div>Resultado com <b>{fmt(N["pst"], 2)}%</b> das seções apuradas (TSE, {N["dg"]} {N["ht"]}). '
        f'Veja como a apuração evoluiu durante a noite: <span class="rounds">{rounds_nav}<a href="/apuracao/">todas as leituras →</a></span></div></div>')
    (BUILD / "1-turno").mkdir()
    (BUILD / "1-turno" / "index.html").write_text(montar_pagina(raw, titulo, desc, "/1-turno/", "/og/index.png", ld, publicado, modificado, "/1-turno/", top))
    paginas.append(("/1-turno/", modificado, "0.9"))

    # ---- home (/): 2º turno em três fases (véspera, apuração, resultado); home.js troca a fase no navegador
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": BASE + "/", "inLanguage": "pt-BR", "publisher": PESSOA},
          {"@context": "https://schema.org", "@type": "WebPage", "name": titulo, "description": desc, "url": BASE + "/", "inLanguage": "pt-BR",
           "author": PESSOA, "about": ELEICAO, "dateModified": modificado}]
    (BUILD / "index.html").write_text(montar_pagina(home_turno2(style), titulo, desc, "/", "/og/index.png", ld, publicado, modificado, "/"))
    shutil.copyfile(R / "home.js", BUILD / "home.js"); shutil.copyfile(R / "home.js", OUT / "home.js")
    paginas.append(("/", modificado, "1.0"))

    # ---- uma página por leitura
    tpl = (R / "template.html").read_text()
    for i, r in enumerate(rodadas):
        d = r["d"]; pst = fmt(d["pst"], 1); hora = d["ht"][:5]
        raw = html_leitura(tpl, d)
        _, titulo, desc = textos_leitura(d)
        nav = "".join(f'<a href="{x["url"]}"{" aria-current=page" if x is r else ""}>{fmt(x["d"]["pst"], 1)}%</a>' for x in rodadas)
        top = (trilha_apuracao(f"{pst}%") +
               f'<div class="banner"><div>Esta é uma <b>leitura parcial</b>: o retrato da apuração às {hora}, com {pst}% das urnas. '
               f'<a href="/1-turno/">Veja o resultado final →</a><span class="rounds">{nav}</span></div></div>')
        path = r["url"]
        ld = [{"@context": "https://schema.org", "@type": "NewsArticle", "headline": titulo[:110], "description": desc, "inLanguage": "pt-BR",
               "datePublished": ISO(datetime.strptime("04/10/2026 " + d["ht"], "%d/%m/%Y %H:%M:%S")), "dateModified": ISO(datetime.strptime("04/10/2026 " + d["ht"], "%d/%m/%Y %H:%M:%S")),
               "author": PESSOA, "publisher": PESSOA, "image": [f"{BASE}/og/apuracao-{r['slug']}.png"], "mainEntityOfPage": BASE + path, "about": ELEICAO},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": NAV.INICIO, "item": BASE + "/"},
                  {"@type": "ListItem", "position": 2, "name": NAV.APURACAO, "item": BASE + "/apuracao/"},
                  {"@type": "ListItem", "position": 3, "name": f"{pst}% apurado", "item": BASE + path}]}]
        (BUILD / path.strip("/")).mkdir(parents=True, exist_ok=True)
        (BUILD / path.strip("/") / "index.html").write_text(montar_pagina(raw, titulo, desc, path, f"/og/apuracao-{r['slug']}.png", ld, publicado, modificado, "/apuracao/", top))
        paginas.append((path, ISO(datetime.strptime("04/10/2026 " + d["ht"], "%d/%m/%Y %H:%M:%S")), "0.6"))

    # ---- uma página por leitura do 2º turno
    tpl2 = (R / "template_2turno.html").read_text()
    for r in rodadas_2t:
        d = r["d"]; pst = fmt(d["pst"], 1); hora = d["ht"][:5]
        raw = html_leitura_2t(tpl2, d)
        _, titulo, desc = textos_leitura_2t(d)
        nav = "".join(f'<a href="{x["url"]}"{" aria-current=page" if x is r else ""}>{fmt(x["d"]["pst"], 1)}%</a>' for x in rodadas_2t)
        top = (trilha_apuracao(f"2º turno, {pst}%") +
               f'<div class="banner"><div>Esta é uma <b>leitura parcial</b> do 2º turno: o retrato da apuração às {hora}, com {pst}% das urnas. '
               f'<a href="/">Veja a apuração agora →</a><span class="rounds">{nav}</span></div></div>')
        path = r["url"]
        quando = ISO(datetime.strptime("25/10/2026 " + d["ht"], "%d/%m/%Y %H:%M:%S"))
        ld = [{"@context": "https://schema.org", "@type": "NewsArticle", "headline": titulo[:110], "description": desc, "inLanguage": "pt-BR",
               "datePublished": quando, "dateModified": quando, "author": PESSOA, "publisher": PESSOA, "image": [f"{BASE}/og/index.png"],
               "mainEntityOfPage": BASE + path, "about": ELEICAO},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": NAV.INICIO, "item": BASE + "/"},
                  {"@type": "ListItem", "position": 2, "name": NAV.APURACAO, "item": BASE + "/apuracao/"},
                  {"@type": "ListItem", "position": 3, "name": f"2º turno, {pst}% apurado", "item": BASE + path}]}]
        (BUILD / path.strip("/")).mkdir(parents=True, exist_ok=True)
        (BUILD / path.strip("/") / "index.html").write_text(montar_pagina(raw, titulo, desc, path, "/og/index.png", ld, publicado, modificado, "/apuracao/", top))
        paginas.append((path, quando, "0.6"))

    # ---- índice da apuração (HTML estático, sem JS)
    base_tpl = (R / "relatorio" / "relatorio_final.html").read_text()
    style = re.search(r"<style>.*?</style>", base_tpl, re.S).group(0)
    titulo = f"Histórico da apuração: {'1º e 2º turno' if rodadas_2t else 'o 1º turno'} de 2026, leitura a leitura"
    desc = "Como a apuração de 04/10/2026 evoluiu: cada leitura do TSE com o % de urnas, os votos de Flávio e Lula e a projeção do resultado naquele momento."
    pagina = pagina_apuracao(style)
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": titulo, "description": desc, "url": BASE + "/apuracao/", "inLanguage": "pt-BR", "author": PESSOA,
           "hasPart": [{"@type": "NewsArticle", "url": BASE + r["url"], "headline": f"Apuração com {fmt(r['d']['pst'], 1)}% das urnas"} for r in rodadas + rodadas_2t]},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": NAV.INICIO, "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": NAV.APURACAO, "item": BASE + "/apuracao/"}]}]
    (BUILD / "apuracao").mkdir(exist_ok=True)
    (BUILD / "apuracao" / "index.html").write_text(montar_pagina(pagina, titulo, desc, "/apuracao/", "/og/index.png", ld, publicado, modificado, "/apuracao/",
                                                              trilha_apuracao()))
    paginas.append(("/apuracao/", modificado, "0.8"))

    # ---- estudo do 2º turno (/estudo-2-turno/): só quando analise/estudo2t/estudo.json existe
    if ESTUDO2T_ARQ.exists():
        est = json.loads(ESTUDO2T_ARQ.read_text())
        f2 = est["fatos"]
        titulo = "Como Lula virou o 2º turno: de onde vieram os votos | Eleições 2026"
        desc = (f"Do 1º para o 2º turno, Lula ganhou {fmt(f2['ganho']['L'] / 1e6, 1)} milhões de votos e Flávio "
                f"{fmt(f2['ganho']['F'] / 1e6, 1)} milhões. Votos dos outros candidatos, brancos e nulos e abstenção, por estado, com dados do TSE.")
        ld = [{"@context": "https://schema.org", "@type": "Article", "headline": titulo[:110], "description": desc, "inLanguage": "pt-BR",
               "author": PESSOA, "publisher": PESSOA, "datePublished": modificado, "dateModified": modificado,
               "mainEntityOfPage": BASE + "/estudo-2-turno/", "about": ELEICAO}]
        (BUILD / "estudo-2-turno").mkdir(exist_ok=True)
        (BUILD / "estudo-2-turno" / "index.html").write_text(montar_pagina(pagina_estudo2t(style, est), titulo, desc, "/estudo-2-turno/",
                                                                         "/og/index.png", ld, publicado, modificado, "/apuracao/",
                                                                         NAV.trilha((NAV.INICIO, "/"), ("Estudo do 2º turno", None))))
        paginas.append(("/estudo-2-turno/", modificado, "0.9"))

    # ---- ao vivo = HUD (mapa por município). Os dados vêm de /geo/ (municipios/geo/, gerado por municipios/montar.py)
    # e, no 2º turno, de /vivo/agora.json. O template antigo está arquivado em docs/old/template_aovivo.html.
    copiar_hud(BUILD); copiar_hud(OUT)
    raw = brand.aplicar((R / "template_hud.html").read_text()).replace("<!--__RESUMO__-->", resumo_hud(), 1)
    raw = injetar_presenca(raw)
    titulo, desc = textos_aovivo()
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": titulo, "description": desc, "url": BASE + "/ao-vivo/", "inLanguage": "pt-BR",
           "author": PESSOA, "about": ELEICAO, "isBasedOn": "https://resultados.tse.jus.br/oficial/app/index.html", "dateModified": modificado},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Início", "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": "Ao vivo", "item": BASE + "/ao-vivo/"}]}]
    (BUILD / "ao-vivo").mkdir(exist_ok=True)
    (BUILD / "ao-vivo" / "index.html").write_text(montar_pagina(raw, titulo, desc, "/ao-vivo/", "/og/ao-vivo.png", ld, publicado, modificado, "/ao-vivo/", moldura=False))
    paginas.append(("/ao-vivo/", modificado, "0.9"))

    # ---- análise (/analise/): o texto e os números do Brasil saem do pré-render; dados em /analise/dados/
    dados_an = analise_dados()
    copiar_analise(BUILD); copiar_analise(OUT); copiar_codigo_analise(OUT)
    (BUILD / "analise").mkdir(exist_ok=True)
    (BUILD / "analise" / "index.html").write_text(html_analise(dados_an, ANALISE_GERADA, ANALISE_GERADA))
    paginas.append(("/analise/", ANALISE_GERADA, "0.9"))
    paginas.append(("/analise/codigo/", ANALISE_GERADA, "0.3"))

    # ---- 404
    (BUILD / "404.html").write_text(montar_pagina(pagina_404(style),
                                                  "Página não encontrada · Eleições 2026", "Página não encontrada.", "/404.html", "/og/index.png", [], publicado, modificado, ""))

    # ---- pré-render de todas as páginas
    for p in ["index.html", "1-turno/index.html", "ao-vivo/index.html", "analise/index.html", "apuracao/index.html", "404.html"] + (["estudo-2-turno/index.html"] if ESTUDO2T_ARQ.exists() else []) + [r["url"].strip("/") + "/index.html" for r in rodadas + rodadas_2t]:
        url = base_url + "/" + p.replace("index.html", "")
        dom = prerender(url)
        # o mapa já está desenhado no HTML: tira os contornos duplicados dos dados embutidos
        m = re.search(r"const D=(\{.*?\});\n", dom, re.S)
        if m and '"mapa"' in m.group(1):
            d = json.loads(m.group(1)); d.pop("mapa", None)
            dom = dom[:m.start(1)] + json.dumps(d, ensure_ascii=False) + dom[m.end(1):]
        dest = OUT / p; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(com_medicao(dom))
    (OUT / "404.html").write_text((OUT / "404.html").read_text().replace('<meta name="robots" content="index,follow', '<meta name="robots" content="noindex,follow', 1))

    # ---- Rastro do dinheiro (/rastro/): estático, vai direto para site/
    paginas += rastro_publicar(OUT, publicado, modificado)

    # ---- checagem dos debates (/debates/...): estática, vai direto para site/; sem checagens.json, só avisa
    deb = debates_publicar(OUT)
    if deb:
        paginas += deb["sitemap"]

    # ---- minha seção (/minha-secao/): estática, vai direto para site/; sem municipios/geo/locais/, "em breve"
    sec = minha_secao_publicar(OUT, publicado, modificado)
    paginas += sec

    # ---- medição: um único arquivo com os IDs (sem ID não há medicao.js)
    if MEDICAO_JS_SAIDA:
        (OUT / "medicao.js").write_text(MEDICAO_JS_SAIDA)

    # ---- imagens OG
    (BUILD / "og").mkdir(exist_ok=True); (OUT / "og").mkdir(exist_ok=True)
    cards = [(f"apuracao-{r['slug']}", f"Apuração com {fmt(r['d']['pst'], 1)}% das urnas", f"Eleições 2026 · 04/10 às {r['d']['ht'][:5]}", r["d"]["f"], r["d"]["l"], "Leitura parcial do TSE") for r in rodadas]
    og_htmls = cards_turno2() + [(nome, og_card(t, s, f, l, rp)) for nome, t, s, f, l, rp in cards]
    og_htmls += deb["og"] if deb else []
    for nome, og_html in og_htmls:
        (BUILD / "og" / f"{nome}.html").write_text(og_html)
        chrome("--window-size=1200,630", "--virtual-time-budget=3000", f"--screenshot={OUT / 'og' / (nome + '.png')}", f"{base_url}/og/{nome}.html")
    # análise: uma página de compartilhar e dois cartões (OG 1200×630, social 1080×1350) por seção
    secs = secoes_do_dom((OUT / "analise" / "index.html").read_text())
    for sid, _ in SECOES_ANALISE:
        (OUT / "analise" / sid).mkdir(parents=True, exist_ok=True)
        (OUT / "analise" / sid / "index.html").write_text(pagina_compartilhar(sid, secs.get(sid, {}), ANALISE_GERADA, ANALISE_GERADA, bool(dados_an)))
    if dados_an:
        (BUILD / "analise" / "og.html").write_text(og_analise_html())
        (OUT / "og" / "social").mkdir(exist_ok=True)
        for sid, _ in SECOES_ANALISE:
            chrome("--window-size=1200,630", "--virtual-time-budget=9000", f"--screenshot={OUT / 'og' / f'analise-{sid}.png'}", f"{base_url}/analise/og.html?s={sid}&f=og")
            chrome("--window-size=1080,1350", "--virtual-time-budget=9000", f"--screenshot={OUT / 'og' / 'social' / f'analise-{sid}.png'}", f"{base_url}/analise/og.html?s={sid}&f=social")
    (BUILD / "og" / "touch.html").write_text(f'<!doctype html><html><body style="margin:0">{FAVICON.replace("<svg ", "<svg width=180 height=180 ")}</body></html>')
    chrome("--window-size=180,180", "--virtual-time-budget=3000", f"--screenshot={OUT / 'apple-touch-icon.png'}", f"{base_url}/og/touch.html")
    srv.shutdown()

    # ---- arquivos estáticos
    (OUT / "favicon.svg").write_text(FAVICON)
    (OUT / "dados").mkdir(); shutil.copy(R / "relatorio" / "relatorio.json", OUT / "dados" / "relatorio.json")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\n# Buscadores e assistentes de IA são bem-vindos\nUser-agent: GPTBot\nAllow: /\nUser-agent: OAI-SearchBot\nAllow: /\nUser-agent: ChatGPT-User\nAllow: /\nUser-agent: ClaudeBot\nAllow: /\nUser-agent: Claude-User\nAllow: /\nUser-agent: PerplexityBot\nAllow: /\nUser-agent: Google-Extended\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
                                     "".join(f"  <url><loc>{BASE}{p}</loc><lastmod>{lm}</lastmod><priority>{pr}</priority></url>\n" for p, lm, pr in paginas) + "</urlset>\n")
    gl = "\n".join(f"- {g['uf']}: {g['a']['nome']} ({g['a']['sg']}) × {g['b']['nome']} ({g['b']['sg']})" for g in gov2 + govIn)
    (OUT / "llms.txt").write_text(f"""# Eleições 2026 · Resultado do 1º turno (Brasil, 04/10/2026)

> Análise independente de {AUTOR['nome']} com dados públicos do TSE ({fmt(N['pst'], 2)}% das seções apuradas, leitura de {N['dg']} {N['ht']}). {"Governadores e Senado: situação oficial do TSE." if GOV_OFICIAL and SEN_OFICIAL else "Os eleitos ainda não tinham sido proclamados oficialmente; governador e Senado foram calculados pelas regras eleitorais."}{" Deputados ainda em totalização em: " + ", ".join(DEP_PENDENTES) + "." if DEP_PENDENTES else ""}

## Presidente
- 2º turno em 25/10/2026: Flávio Bolsonaro (PL) {fmt(cF['p'], 2)}% × Lula (PT) {fmt(cL['p'], 2)}% dos votos válidos.
- Votos: Flávio {fmt(cF['votos'], 0)} · Lula {fmt(cL['votos'], 0)}.
- Flávio venceu em {len(ufF)} UFs, Lula em {len(ufL)}. Disputa mais apertada: {apertado['uf']} ({fmt(abs(apertado['saldo']), 0)} votos).
- Abstenção {fmt(N['pa'], 2)}% · brancos {fmt(N['pb'], 2)}% · nulos {fmt(N['pn'], 2)}%.
- Comparação com o 1º turno de 2022: Lula 48,43% × Jair Bolsonaro 43,20%.

## Governadores
- {len(govEl)} eleitos no 1º turno; 2º turno ou indefinido em:
{gl}

## Congresso
- Câmara (513): PL {plFed} cadeiras (99 em 2022). Distribuição de vagas publicada pelo TSE.
- Senado (54 vagas): PL {plSen}.

## Páginas
- [Início: 2º turno, Flávio Bolsonaro (PL) × Lula (PT), domingo 25/10]({BASE}/): contagem regressiva, debates checados, minha seção e a apuração ao vivo a partir das 17h (Brasília)
- [Resultado do 1º turno completo]({BASE}/1-turno/): mapa por estado, governadores, Senado, Câmara, Assembleias, perguntas frequentes
- [Mapa da apuração por município]({BASE}/ao-vivo/): presidente, governadores, Senado e deputados nos 5.570 municípios; 2º turno ao vivo em 25/10
- [Análise: voto dividido, votos × cadeiras, divergências e 2022 × 2026]({BASE}/analise/): por que Lula (PT) tem tantos votos e o lado dele elege poucos deputados; estimativas marcadas, por estado
- [Histórico da apuração, leitura a leitura]({BASE}/apuracao/)
""" + (f"- [{NAV.MINHA_SECAO}: onde eu voto e quem ganhou ali (presidente, por seção e local de votação)]({BASE}/minha-secao/)\n" if sec else "") + (deb["llms"] if deb else "") + "".join(f"- [Apuração com {fmt(r['d']['pst'], 1)}% das urnas]({BASE}{r['url']})\n" for r in rodadas) +
f"- [Dados consolidados em JSON]({BASE}/dados/relatorio.json)\n", encoding="utf-8")
    (OUT / "vercel.json").write_text(json.dumps(VERCEL, indent=1))  # deploy pela CLI, de dentro de site/
    # deploy pelo git (integração GitHub) parte da raiz do repo: sem isto a Vercel publica a raiz e o site dá 404
    (R / "vercel.json").write_text(json.dumps({"outputDirectory": "site", **VERCEL}, indent=1))
    shutil.rmtree(BUILD)
    tot = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"site/ ok · {len(list(OUT.rglob('*.html')))} páginas · {len(list((OUT / 'og').glob('*.png')))} imagens OG · {tot // 1024} KB")


if __name__ == "__main__":
    main()
