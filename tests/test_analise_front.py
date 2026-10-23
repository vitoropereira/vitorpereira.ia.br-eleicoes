"""Página /analise/ e integração com o painel: brand, scripts locais, cores, SEO, compartilhamento e saída do build."""
import json, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import brand
import build_site as B

TEMPLATE = R / "template_analise.html"
JS = R / "analise" / "js"
HEX = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
FAQ = [{"q": "O que é voto dividido?", "a": "Votar em lados diferentes para cargos diferentes."}]
PUB, MOD = "2026-10-04T18:25:00-03:00", "2026-10-08T12:00:00-03:00"


def ld_tipos(h):
    return [json.loads(x).get("@type") for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]


class Template(unittest.TestCase):
    def test_um_marcador_da_brand(self):
        self.assertEqual(TEMPLATE.read_text().count("/*__BRAND__*/"), 1)

    def test_so_scripts_locais(self):
        h = TEMPLATE.read_text()
        srcs = re.findall(r"<script[^>]*\bsrc=\"([^\"]+)\"", h)
        self.assertIn("/analise/js/app.js", srcs)
        for s in srcs:
            self.assertTrue(s.startswith("/") and "//" not in s, s)
        self.assertNotRegex(h, r"<script[^>]*src=\"https?://")
        self.assertNotRegex(h, r"<link[^>]*href=\"https?://[^\"]*\.(?:css|js)")

    def test_modulos_so_importam_local(self):
        for js in JS.glob("*.js"):
            for imp in re.findall(r"\bfrom\s+\"([^\"]+)\"|import\(\s*\"([^\"]+)\"", js.read_text()):
                alvo = imp[0] or imp[1]
                self.assertTrue(alvo.startswith(("/vendor/", "/hud/", "./")), f"{js.name}: import {alvo}")
                self.assertNotIn("://", alvo, js.name)

    def test_cabecalho_com_analise_ativa_e_abas_do_painel(self):
        h = TEMPLATE.read_text()
        self.assertRegex(h, r'<a href="/analise/" aria-current="page">Análise</a>')
        for c in ("presidente", "governador", "senador", "depfed", "depest"):
            self.assertIn(f'href="/ao-vivo/?cargo={c}"', h)


class Cores(unittest.TestCase):
    """cor literal de dado só em hud/partidos.js; a Análise usa só tokens de campo (--lula, --flavio, --outros)"""

    def test_sem_hex_na_analise(self):
        for p in [TEMPLATE, *JS.glob("*.js")]:
            self.assertEqual(HEX.findall(p.read_text()), [], f"{p.name}: cor literal")

    def test_lados_usam_tokens_de_campo(self):
        calc = (JS / "calc.js").read_text()
        self.assertIn('L: "--lula"', calc)
        self.assertIn('F: "--flavio"', calc)
        self.assertIn('C: "--outros"', calc)
        self.assertNotIn("--brand", calc + (JS / "graficos.js").read_text(), "ciano é só moldura")

    def test_hex_continua_so_em_partidos_js(self):
        for p in [R / "template_hud.html", *[x for x in (R / "hud").glob("*.js") if x.name != "partidos.js"]]:
            self.assertEqual(HEX.findall(p.read_text()), [], p.name)


class Secoes(unittest.TestCase):
    def test_lista_do_build_igual_a_do_js(self):
        js = (JS / "calc.js").read_text()
        bloco = js[js.index("export const SECOES"):]
        ids = re.findall(r'\["([a-z0-9-]+)", "', bloco[:bloco.index("];")])
        self.assertEqual(ids, [i for i, _ in B.SECOES_ANALISE])
        self.assertEqual(ids[0], "destaques")
        self.assertEqual(ids[-1], "metodo")

    def test_secoes_do_dom(self):
        dom = ('<section id="campos" class="sec" data-titulo="Campo de Lula: 45%" data-numero="−19 p.p." data-rotulo="a &amp; b">'
               '<section id="outra" data-titulo="x"><section id="faq" class="sec faq" data-titulo="Perguntas" data-numero="" data-rotulo="">')
        s = B.secoes_do_dom(dom)
        self.assertEqual(set(s), {"campos", "faq"})
        self.assertEqual(s["campos"]["titulo"], "Campo de Lula: 45%")
        self.assertEqual(s["campos"]["rotulo"], "a & b")


class SEO(unittest.TestCase):
    def test_faqpage_quando_ha_faq(self):
        self.assertIn("FAQPage", [x["@type"] for x in B.ld_analise({"faq": FAQ}, PUB, MOD)])
        self.assertNotIn("FAQPage", [x["@type"] for x in B.ld_analise({}, PUB, MOD)])

    def test_pagina_tem_brand_seo_e_app(self):
        h = B.html_analise({"faq": FAQ}, PUB, MOD)
        self.assertIn(brand.CSS, h)
        self.assertIn(f'<link rel="canonical" href="{B.BASE}/analise/">', h)
        self.assertIn("voto dividido", h.lower())
        self.assertIn('<script type="module" src="/analise/js/app.js"></script>', h)
        self.assertIn("og:image", h)
        self.assertIn("/og/analise-destaques.png", h)
        tipos = ld_tipos(h)
        for t in ("Article", "FAQPage", "BreadcrumbList"):
            self.assertIn(t, tipos)
        self.assertIn('<footer class="site">', h)
        self.assertNotIn('<header class="sitebar">', h, "a Análise usa o cabeçalho do painel")

    def test_sem_dados_usa_og_geral(self):
        h = B.html_analise({}, PUB, MOD)
        self.assertIn("/og/index.png", h)
        self.assertNotIn("FAQPage", ld_tipos(h))

    def test_sitebar_tem_analise(self):
        self.assertIn('href="/analise/"', B.sitebar("/"))


class Datas(unittest.TestCase):
    def test_jsonld_com_data_da_geracao(self):
        """/analise/ foi gerada em 08/10/2026: o Article não herda as datas do 1º turno (04/10)"""
        art = next(x for x in B.ld_analise({"faq": FAQ}, PUB, MOD) if x["@type"] == "Article")
        self.assertEqual(art["datePublished"], B.ANALISE_GERADA)
        self.assertEqual(art["dateModified"], B.ANALISE_GERADA)
        self.assertTrue(B.ANALISE_GERADA.startswith("2026-10-08"))


class Textos(unittest.TestCase):
    """neutralidade e precisão dos textos fixos"""
    def test_titulo_neutro(self):
        app = (JS / "app.js").read_text()
        h1 = re.search(r"<h1>(.*?)</h1>", app).group(1)
        for t in (h1, B.ANALISE_TITULO, B.ANALISE_DESC):
            self.assertNotIn("esquerda", t)
        self.assertIn("campo dele", h1)
        self.assertIn("campo dele", B.ANALISE_DESC)

    def test_sem_opiniao_sem_dado(self):
        tx = (JS / "textos.js").read_text()
        for f in ("costuma ter peso decisivo", "eleitorado mais fiel à sigla", "5.570", "sobras de 2024"):
            self.assertNotIn(f, tx)
        for f in ("5.571 municípios", "não cobre as limitações do método", "têm mais dificuldade de conseguir vaga",
                  "1º turno × 1º turno", "quem teve mais votos entre Lula (PT) e o adversário"):
            self.assertIn(f, tx)

    def test_compartilhar_tem_imagem_social(self):
        app = (JS / "app.js").read_text()
        self.assertIn("/og/social/analise-${id}.png", app)
        self.assertIn("<span>Imagem</span>", app)

    def test_legenda_dos_eliminados(self):
        self.assertIn("apoio declarado do candidato", (JS / "app.js").read_text())


class Compartilhar(unittest.TestCase):
    def test_pagina_de_compartilhar(self):
        h = B.pagina_compartilhar("voto-dividido", {"titulo": "Estimativa: 4 em cada 10", "numero": "7,2 mi", "rotulo": "eleitores"}, PUB, MOD)
        self.assertIn(brand.CSS, h)
        self.assertIn(f'<meta property="og:image" content="{B.BASE}/og/analise-voto-dividido.png">', h)
        self.assertIn(f'<meta property="og:url" content="{B.BASE}/analise/voto-dividido/">', h)
        self.assertIn(f'<link rel="canonical" href="{B.BASE}/analise/">', h)
        self.assertIn('content="noindex,follow', h)
        self.assertIn('url=/analise/#voto-dividido', h)
        self.assertIn("Estimativa: 4 em cada 10", h)
        self.assertNotRegex(h, r"<script[^>]*src=")

    def test_sem_dados_usa_og_geral(self):
        h = B.pagina_compartilhar("campos", {}, PUB, MOD, com_og=False)
        self.assertIn("/og/index.png", h)
        self.assertIn("Votos por campo e cargo", h)

    def test_botoes_sem_script_de_terceiros(self):
        app = (JS / "app.js").read_text()
        self.assertIn("https://wa.me/?text=", app)
        self.assertIn("https://x.com/intent/post?", app)
        self.assertIn("clipboard", app)
        self.assertIn("/analise/${id}/", app)

    def test_cartao_tem_marca_fonte_e_dominio(self):
        og = (JS / "og.js").read_text()
        for t in ("Fonte: TSE", "eleicoes2026.vitorpereira.ia.br", "@vitorpereirasaas"):
            self.assertIn(t, og)
        h = B.og_analise_html()
        self.assertIn("1200px", h); self.assertIn("1080px", h); self.assertIn("1350px", h)
        self.assertIn('src="/analise/js/og.js"', h)


class Copia(unittest.TestCase):
    def test_sem_dados_pula_em_silencio(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(B, "ANALISE_DADOS", Path(t) / "nao-existe"):
                B.copiar_analise(Path(t))
                self.assertEqual(B.analise_dados(), {})
            self.assertTrue((Path(t) / "analise" / "js" / "app.js").exists())
            self.assertFalse((Path(t) / "analise" / "dados").exists())
            self.assertFalse(list((Path(t) / "analise" / "js").glob("*_test.js")), "testes Deno não vão ao ar")

    def test_com_dados_copia(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "dados"; d.mkdir(); (d / "faq.json").write_text(json.dumps(FAQ))
            with mock.patch.object(B, "ANALISE_DADOS", d):
                B.copiar_analise(Path(t) / "out")
                self.assertEqual(B.analise_dados(), {"faq": FAQ})
            self.assertTrue((Path(t) / "out" / "analise" / "dados" / "faq.json").exists())

    def test_geo_sem_arquivos_que_o_front_nao_le(self):
        """/geo/ vai ao ar sem t2022/, partidos-*.json e cadeiras.json (só o cálculo da Análise usa)"""
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(B, "status_hud", return_value=None):
                B.copiar_hud(Path(t))
            g = Path(t) / "geo"
            self.assertTrue((g / "t1" / "presidente.json").exists())
            self.assertTrue((g / "t1" / "meta.json").exists())
            self.assertFalse((g / "t2022").exists())
            self.assertFalse(list((g / "t1").glob("partidos-*.json")))
            self.assertFalse((g / "t1" / "cadeiras.json").exists())

    def test_cache_na_vercel(self):
        fontes = {h["source"]: h["headers"][0]["value"] for h in B.VERCEL["headers"]}
        self.assertIn("must-revalidate", fontes["/analise/js/(.*)"])
        self.assertIn("/analise/dados/(.*)", fontes)


class CodigoAnalise(unittest.TestCase):
    """issue #149: /analise/codigo/ com description, canonical, og e JSON-LD"""

    def test_metas(self):
        with tempfile.TemporaryDirectory() as t:
            B.copiar_codigo_analise(Path(t))
            h = (Path(t) / "analise" / "codigo" / "index.html").read_text()
        self.assertEqual(h.count("<title>"), 1)
        self.assertIn("<title>Código do cálculo | Análise · Eleições 2026</title>", h)
        self.assertRegex(h, r'<meta name="description" content="[^"]+">')
        self.assertIn(f'<link rel="canonical" href="{B.BASE}/analise/codigo/">', h)
        for prop in ("og:title", "og:description", "og:url", "og:image"):
            self.assertIn(f'<meta property="{prop}"', h)
        self.assertIn(f'<meta property="og:url" content="{B.BASE}/analise/codigo/">', h)
        self.assertIn('<meta name="robots" content="index,follow', h)
        self.assertIn("WebPage", ld_tipos(h))
        bc = next(json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
                  if json.loads(x)["@type"] == "BreadcrumbList")
        self.assertEqual([i["name"] for i in bc["itemListElement"]], ["Início", "Análise", "Código do cálculo"])
        self.assertIn('<a href="analise/calcular.py">', h)


class Painel(unittest.TestCase):
    app = (R / "hud" / "app.js").read_text()

    def test_aba_analise_e_cargo_pela_url(self):
        self.assertIn('href="/analise/"', self.app)
        self.assertIn('.get("cargo")', self.app)

    def test_modo_divergencia_e_destaques(self):
        self.assertIn('"divergencia", "Divergência"', (R / "hud" / "calc.js").read_text())
        self.assertIn('analise("divergencias")', self.app)
        self.assertIn('analise("destaques")', self.app)
        self.assertIn("/analise/dados/", (R / "hud" / "dados.js").read_text())

    def test_mapa_embutido_nao_sequestra_a_rolagem(self):
        self.assertIn("rolagemLivre", (R / "hud" / "mapa.js").read_text())
        self.assertIn("rolagemLivre: true", (JS / "mapas.js").read_text())


@unittest.skipUnless(shutil.which("deno") and (R / "analise" / "dados" / "divergencias.json").exists(), "precisa de deno e dos dados")
class MesmoDenominador(unittest.TestCase):
    """O painel (hud/calc.js contaDivergencia) e a /analise/ (analise/js/calc.js secDivergencias) mostram o mesmo
    "N de T municípios": roda a lógica real de cada um sobre analise/dados/divergencias.json."""

    def test_hud_igual_analise(self):
        js = (f'import {{ contaDivergencia }} from "{(R / "hud" / "calc.js").as_uri()}";'
              f'import {{ secDivergencias }} from "{(JS / "calc.js").as_uri()}";'
              f'const dv = JSON.parse(Deno.readTextFileSync("{R / "analise" / "dados" / "divergencias.json"}"));'
              'const out = {};'
              'for (const c of ["depfed", "depest", "senador", "governador"]) {'
              ' const h = contaDivergencia(dv.mu, c === "depfed" ? "presidente" : c), a = secDivergencias({ divergencias: dv }, "BR", c);'
              ' out[c] = { hud: [h.n, h.t, h.empates], analise: [a.div, a.tot] }; }'
              'console.log(JSON.stringify(out));')
        r = subprocess.run(["deno", "eval", "--ext=js", js], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        for c, x in out.items():
            self.assertEqual(x["hud"][:2], x["analise"], c)
        self.assertEqual(out["depfed"]["hud"], [2283, 5571, 2])


@unittest.skipUnless((R / "site" / "analise" / "index.html").exists(), "rode python3 build_site.py antes")
class Saida(unittest.TestCase):
    """Confere o site/ montado contra ele mesmo: as seções vêm do pré-render (site/analise/index.html), não da lista do
    código, porque o site/ commitado só é regenerado pelo lote (seção nova no código não pode quebrar aqui)."""
    SITE = R / "site"

    def secoes(self):
        ids = B.secoes_do_dom((self.SITE / "analise" / "index.html").read_text())
        self.assertIn("campos", ids)
        return [sid for sid, _ in B.SECOES_ANALISE if sid in ids]

    def test_pagina_e_compartilhar(self):
        h = (self.SITE / "analise" / "index.html").read_text()
        self.assertIn("/* Brand vitorpereira.ia.br", h)  # a brand do build que gerou o site/, não a de hoje
        self.assertIn('id="campos"', h, "pré-render sem as seções")
        for sid in self.secoes():
            self.assertTrue((self.SITE / "analise" / sid / "index.html").exists(), sid)

    def test_faqpage_quando_ha_faq(self):
        if not (self.SITE / "analise" / "dados" / "faq.json").exists():
            self.skipTest("sem faq.json")
        self.assertIn("FAQPage", ld_tipos((self.SITE / "analise" / "index.html").read_text()))

    def test_sitemap_e_llms(self):
        self.assertIn(f"<loc>{B.BASE}/analise/</loc>", (self.SITE / "sitemap.xml").read_text())
        self.assertIn(f"{B.BASE}/analise/", (self.SITE / "llms.txt").read_text())
        self.assertNotIn("/analise/campos/", (self.SITE / "sitemap.xml").read_text(), "páginas de compartilhar ficam fora do sitemap")

    def test_cartoes_quando_ha_dados(self):
        if not (self.SITE / "analise" / "dados").is_dir():
            self.skipTest("sem dados da análise")
        for sid in self.secoes():
            self.assertTrue((self.SITE / "og" / f"analise-{sid}.png").exists(), sid)
            self.assertTrue((self.SITE / "og" / "social" / f"analise-{sid}.png").exists(), sid)


class MenuSecoes(unittest.TestCase):
    """menu "☰ Seções" da Análise (issue 138): gerado no build a partir de B.secoes(), nada escrito à mão no template"""

    def test_template_tem_o_marcador_e_nenhum_link_de_secao_a_mao(self):
        t = TEMPLATE.read_text()
        self.assertEqual(t.count("<!--__SECOES__-->"), 1)
        for u in ("/rastro/", "/debates/", "/apuracao/"):
            self.assertNotIn(f'href="{u}"', t, "a lista vem de B.secoes(), não do template")

    def test_pagina_gerada_tem_o_menu_com_a_mesma_lista(self):
        h = B.html_analise({}, PUB, MOD)
        m = re.search(r'<div class="secoes">.*?</div>', h, re.S)
        self.assertIsNotNone(m, "menu de seções ausente na Análise")
        menu = m.group(0)
        self.assertEqual(re.findall(r'<a href="([^"]+)"', menu), [u for u, _ in B.secoes()])
        self.assertIn('aria-expanded="false"', menu)
        self.assertRegex(menu, r'<nav[^>]*\bhidden\b')
        self.assertRegex(menu, r'<a href="/analise/" aria-current="page"')
        self.assertIn('<script type="module" src="/hud/secoes.js"></script>', h)
        self.assertIn(B.SECOES_CSS, h)

    def test_css_do_menu_sem_hex(self):
        self.assertEqual(HEX.findall(B.SECOES_CSS), [])


if __name__ == "__main__":
    unittest.main()
