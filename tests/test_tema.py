"""Botão claro/escuro (#142): script do tema no <head> de toda página e botão sol/lua em toda página com cabeçalho.
O teste de saída monta o site num diretório temporário (build_site.main com OUT/BUILD em tmp, sem Chrome e com sal
descartável): nunca depende do site/ commitado, que só o lote regenera."""
import re, shutil, sys, tempfile, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B

RE_TEMA_JS = re.compile(r"<script>[^<]*localStorage[^<]*</script>")
BOTAO = '<button type="button" class="tema"'


def montar_em_tmp(tmp):
    """build_site.main() em tmp: pré-render devolve o HTML montado (sem Chrome), imagens OG não são geradas e o Rastro
    usa um sal descartável em memória (nada é gravado em rastro/)."""
    import rastro.paginas as rp
    salvo = dict(OUT=B.OUT, BUILD=B.BUILD, prerender=B.prerender, chrome=B.chrome)
    sal = (rp.ler_sal, rp.SAL)
    vercel = (R / "vercel.json").read_bytes()  # main() regrava o da raiz (mesmo conteúdo); devolvido intacto no fim

    def prerender(url):
        p = url.split("/", 3)[3]
        return (B.BUILD / (p + "index.html" if p == "" or p.endswith("/") else p)).read_text()
    B.OUT, B.BUILD = tmp / "site", tmp / ".build"
    B.prerender, B.chrome = prerender, lambda *a: ""
    rp.ler_sal, rp.SAL = (lambda *a, **k: "sal-descartavel-do-teste"), R / "build_site.py"
    try:
        B.main()
    finally:
        for k, v in salvo.items():
            setattr(B, k, v)
        rp.ler_sal, rp.SAL = sal
        (R / "vercel.json").write_bytes(vercel)
    return tmp / "site"


class ScriptDoHead(unittest.TestCase):
    def test_script_no_head(self):
        h = B.head("t", "d", "/", "/og/x.png", [], "a", "b")
        m = RE_TEMA_JS.search(h)
        self.assertIsNotNone(m, "head() sem o script do tema")
        js = m.group(0)
        self.assertRegex(js, r"try\{[^}]*localStorage", "localStorage pode lançar (aba privada): precisa de try/catch")
        self.assertIn("catch", js)
        self.assertIn("temaAlternar", js)
        # só aceita valor gravado válido; sem valor, não mexe (segue o sistema)
        self.assertIn('"light"', js); self.assertIn('"dark"', js)
        # vem antes do CSS para a tela não piscar
        self.assertLess(h.index(js), h.index('<style id="site-chrome">'))

    def test_theme_color_acompanha(self):
        js = RE_TEMA_JS.search(B.head("t", "d", "/", "/og/x.png", [], "a", "b")).group(0)
        self.assertIn("theme-color", js)
        self.assertIn("#FBFCFE", js); self.assertIn("#070B12", js)

    def test_codigo_da_analise_tem_script(self):
        with tempfile.TemporaryDirectory() as d:
            B.copiar_codigo_analise(Path(d))
            self.assertRegex((Path(d) / "analise" / "codigo" / "index.html").read_text(), RE_TEMA_JS)


class Botao(unittest.TestCase):
    def test_botao_na_moldura(self):
        s = B.sitebar("/")
        self.assertEqual(s.count(BOTAO), 1)
        b = s[s.index(BOTAO):]
        b = b[:b.index("</button>")]
        self.assertIn("aria-label=", b)
        self.assertIn('onclick="temaAlternar()"', b)
        self.assertIn('class="sol"', b); self.assertIn('class="lua"', b)

    def test_botao_na_analise(self):
        h = B.html_analise({}, "2026-10-18T00:00:00-03:00", "2026-10-18T00:00:00-03:00")
        self.assertNotIn("<!--__TEMA__-->", h)
        self.assertEqual(h.count(BOTAO), 1)

    def test_botao_no_hud(self):
        js = (R / "hud" / "app.js").read_text()
        topo = js[js.index("function Topo("):js.index("// ---------------- barra de modos")]
        self.assertIn('class="tema"', topo)
        self.assertIn("temaAlternar", topo)

    def test_icone_so_por_css(self):
        """sol no escuro, lua no claro, sem JS: vale para o sistema e para o data-theme"""
        css = B.SITE_CSS
        self.assertIn('[data-theme="light"] .tema .sol', css)
        self.assertIn('[data-theme="dark"]', css)

    def test_canvas_da_analise_redesenha(self):
        for f in ("analise/js/graficos.js", "analise/js/mapas.js"):
            js = (R / f).read_text()
            self.assertIn('attributeFilter: ["data-theme"]', js, f)
            self.assertIn(".disconnect()", js, f)


class Saida(unittest.TestCase):
    """site inteiro montado em tmp: toda página publicada tem o script; toda página com cabeçalho tem o botão"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="tema-"))
        cls.site = montar_em_tmp(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def paginas(self):
        return [p for p in self.site.rglob("*.html") if p.relative_to(self.site).parts[0] != "og"]

    def test_todas_com_script_e_sem_tema_forcado(self):
        ps = self.paginas()
        self.assertGreater(len(ps), 10)
        sem, forcado = [], []
        for p in ps:
            h = p.read_text()
            if not RE_TEMA_JS.search(h):
                sem.append(str(p.relative_to(self.site)))
            if re.search(r"<html[^>]*data-theme=", h):
                forcado.append(str(p.relative_to(self.site)))
        self.assertEqual(sem, [], "página sem o script do tema")
        self.assertEqual(forcado, [], "o HTML publicado sai neutro (segue o sistema)")

    def test_botao_em_toda_pagina_com_cabecalho(self):
        """menos /analise/codigo/ e /analise/<id>/ (redirect) e /ao-vivo/ (o botão vem do Preact, ver Botao.test_botao_no_hud)"""
        sem = []
        for p in self.paginas():
            rel = p.relative_to(self.site)
            if rel.parts[0] == "analise" and rel != Path("analise/index.html"):
                continue
            if rel == Path("ao-vivo/index.html"):
                continue
            if p.read_text().count(BOTAO) != 1:
                sem.append(str(rel))
        self.assertEqual(sem, [])

    def test_paginas_principais_presentes(self):
        for rel in ("index.html", "ao-vivo/index.html", "analise/index.html", "apuracao/index.html", "404.html",
                    "rastro/index.html", "analise/codigo/index.html"):
            self.assertTrue((self.site / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
