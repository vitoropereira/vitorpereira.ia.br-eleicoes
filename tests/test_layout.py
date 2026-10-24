"""Layout (issue 145): uma largura de texto e uma larga (tokens da brand.css), um componente de trilha e um nome por
seção (menu = trilha = título)."""
import html
import re
import tempfile
import unittest
from pathlib import Path

import brand
import build_site as B
import navegacao as N
from debates import pagina as dp
from rastro import paginas as pg
from tests.test_rastro_paginas import CFG, ELEITOS, FIX, FORN, INDS, PUBL, SAL

R = Path(__file__).resolve().parent.parent
RE_TRILHA = re.compile(r'<nav class="crumbs" aria-label="Trilha">(.*?)</nav>', re.S)


def passos(h):
    """[(rótulo, href|None)] da (única) trilha da página"""
    ts = RE_TRILHA.findall(h)
    assert len(ts) == 1, f"esperava 1 trilha, achei {len(ts)}"
    out = []
    for p in ts[0].split(" › "):
        m = re.fullmatch(r'<a href="([^"]*)">(.*)</a>', p.strip(), re.S)
        out.append((html.unescape(m.group(2)), m.group(1)) if m else (html.unescape(p.strip()), None))
    return out


def h1(h):
    return html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<h1>(.*?)</h1>", h, re.S).group(1)))


class UmNomePorSecao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nome = dict(B.secoes())
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        pags = pg.gerar(Path(tmp.name) / "out", PUBL, ELEITOS, FIX / "contas", INDS, FORN, CFG, sal=SAL)
        cls.rastro = {p["path"]: p["html"] for p in pags}

    def test_inicio(self):
        self.assertEqual(self.nome["/"], "Início")
        self.assertNotIn("Resultado final", self.nome.values())

    def test_menu_vem_de_navegacao(self):
        for u, rot in [("/", N.INICIO), ("/ao-vivo/", N.AO_VIVO), ("/analise/", N.ANALISE), ("/rastro/", N.RASTRO),
                       ("/apuracao/", N.APURACAO), ("/1-turno/#metodo", N.METODO)]:
            self.assertEqual(self.nome[u], rot, u)

    def test_debates(self):
        ds = B.debates()
        if not ds:
            self.skipTest("nenhum debate com checagens.json")
        idx = dp.indice(ds, B.BASE, B.PESSOA, B.links_rastro())
        nome = self.nome["/debates/"]
        self.assertEqual(passos(idx["html"]), [(self.nome["/"], "/"), (nome, None)])
        self.assertTrue(h1(idx["html"]).startswith(nome), h1(idx["html"]))
        for p in [ds[0], ds[0]["transcricao"], ds[0]["afirmacoes"][0]]:
            self.assertEqual(passos(p["html"])[:2], [(self.nome["/"], "/"), (nome, "/debates/")], p["path"])

    def test_rastro(self):
        nome = self.nome["/rastro/"]
        home = self.rastro["/rastro/"]
        self.assertEqual(passos(home), [(self.nome["/"], "/"), (nome, None)])
        self.assertEqual(h1(home), nome)
        for path, h in self.rastro.items():
            if path != "/rastro/":
                self.assertEqual(passos(h)[:2], [(self.nome["/"], "/"), (nome, "/rastro/")], path)

    def test_apuracao(self):
        nome = self.nome["/apuracao/"]
        self.assertEqual(passos(B.trilha_apuracao()), [(self.nome["/"], "/"), (nome, None)])
        self.assertEqual(passos(B.trilha_apuracao("36,6%"))[:2], [(self.nome["/"], "/"), (nome, "/apuracao/")])
        self.assertTrue(h1(B.pagina_apuracao("<style></style>")).startswith(nome))

    def test_um_componente_de_trilha(self):
        for f in ["build_site.py", "debates/pagina.py", "rastro/paginas.py"]:
            t = (R / f).read_text()
            self.assertNotRegex(t, r"db-crumbs|rs-crumbs", f)
            self.assertNotIn('aria-label="Trilha"', t, f"{f}: use navegacao.trilha()")


class Larguras(unittest.TestCase):
    def test_tokens_na_brand(self):
        root = re.search(r":root\{([^}]*)\}", brand.CSS).group(1)
        self.assertIn("--w-texto:", root)
        self.assertIn("--w-larga:", root)

    def test_sem_largura_literal_nos_conteineres(self):
        fontes = {"SITE_CSS": B.SITE_CSS, "MEDICAO_CSS": B.MEDICAO_CSS, "debates": dp.CSS, "rastro": pg.CSS,
                  "template.html": (R / "template.html").read_text(),
                  "template_relatorio.html": (R / "relatorio" / "template_relatorio.html").read_text()}
        for nome, css in fontes.items():
            self.assertNotRegex(css, r"max-width:(1160|1120|880)px", nome)

    def test_texto_e_larga(self):
        def regra(css, sel):
            return re.search(re.escape(sel) + r"\{([^}]*)\}", css).group(1)
        for css, sel, w in [(dp.CSS, "main.db", "texto"), (pg.CSS, "main.rs", "texto"), (B.SITE_CSS, ".sitebar .in", "larga"),
                            (B.SITE_CSS, "body>nav.crumbs", "larga"), (B.SITE_CSS, "footer.site .in", "larga")]:
            r = regra(css, sel)
            self.assertIn(f"max-width:var(--w-{w})", r, sel)
            self.assertIn("box-sizing:border-box", r, f"{sel}: sem border-box a largura muda de página para página")
        self.assertIn("main{max-width:var(--w-larga)", (R / "relatorio" / "template_relatorio.html").read_text())
        self.assertIn("main{max-width:var(--w-larga)", (R / "template.html").read_text())

    def test_relatorio_final_com_a_brand_atual(self):
        h = (R / "relatorio" / "relatorio_final.html").read_text()
        self.assertIn(brand.CSS, h)
        self.assertIn("main{max-width:var(--w-larga)", h)


if __name__ == "__main__":
    unittest.main()
