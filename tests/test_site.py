import re, sys, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import brand
import build_site as B

PALETA_ANTIGA = ["#f7f6f3", "#1b1c1e", "#1a1a19", "#232322", "#2563c9", "#5b8def"]


class Moldura(unittest.TestCase):
    def test_sem_paleta_antiga_na_moldura(self):
        moldura = B.SITE_CSS + B.MEDICAO_CSS + B.MEDICAO_JS + B.FAVICON + B.og_card("t", "s", 47.0, 45.2, "r") + B.head("t", "d", "/", "/og/x.png", [], "a", "b")
        for cor in PALETA_ANTIGA:
            self.assertNotIn(cor, moldura.lower(), cor)

    def test_logo_da_brand(self):
        s = B.sitebar("/")
        self.assertIn("vitor", s); self.assertIn("pereira", s); self.assertIn('class="cursor"', s)

    def test_menu_tem_rastro(self):
        s = B.sitebar("/rastro/")
        self.assertIn('<a href="/rastro/" aria-current=page>Rastro do dinheiro</a>', s)
        self.assertNotIn("aria-current", B.sitebar("/").replace('<a href="/" aria-current=page>', ""))
        self.assertIn('<a href="/rastro/">Rastro do dinheiro</a>', B.sitebar("/"))

    def test_menu_tem_debates(self):
        if not B.debates():
            self.skipTest("nenhum debate com checagens.json")
        self.assertIn('<a href="/debates/" aria-current=page>Debates</a>', B.sitebar("/debates/"))
        self.assertIn('<a href="/debates/">Debates</a>', B.sitebar("/"))
        self.assertIn(f'<a href="{B.debates()[0]["path"]}">', B.banner_debate())

    def test_contador_ao_vivo_no_cabecalho(self):
        s = B.sitebar("/rastro/")
        m = re.search(r'<a class="agora" href="/ao-vivo/" (.*?) hidden>', s)
        self.assertIsNotNone(m, "contador precisa nascer escondido (o pré-render não conta ninguém)")
        cfg = dict(re.findall(r'data-(\w+)="([^"]*)"', m.group(1)))
        self.assertEqual(cfg, B.HUD_PRESENCE)  # mesmo canal do HUD: o número é o total do site
        self.assertTrue(cfg["key"].startswith("sb_publishable_"))
        self.assertIn('<script type="module" src="/hud/topo-pessoas.js"></script>', s)
        self.assertTrue((R / "hud" / "topo-pessoas.js").exists())

    def test_contador_ao_vivo_na_analise(self):
        # a Análise tem topo próprio (moldura=False): o contador entra pelo marcador do template
        h = B.html_analise({}, "2026-10-18T00:00:00-03:00", "2026-10-18T00:00:00-03:00")
        self.assertNotIn("<!--__AGORA__-->", h)
        self.assertEqual(h.count('<a class="agora" href="/ao-vivo/"'), 1)

    def test_foco_usa_brand(self):
        self.assertNotIn("var(--flavio)", B.SITE_CSS + B.MEDICAO_CSS + B.MEDICAO_JS)


class Saida(unittest.TestCase):
    SITE = R / "site"

    @unittest.skipUnless((R / "site" / "index.html").exists(), "rode python3 build_site.py antes")
    def test_fontes_publicadas(self):
        for f in ("inter-latin-wght-normal.woff2", "jetbrains-mono-latin-wght-normal.woff2"):
            self.assertTrue((self.SITE / "fonts" / f).exists(), f)

    @unittest.skipUnless((R / "site" / "index.html").exists(), "rode python3 build_site.py antes")
    def test_paginas_com_brand_e_sem_segredo(self):
        for p in self.SITE.rglob("*.html"):
            h = p.read_text()
            self.assertIn(brand.CSS, h, p)
            self.assertNotIn("eyJhbGci", h, p)
            self.assertNotIn("sbp_", h, p)
        self.assertFalse(any(self.SITE.rglob(".env*")))

    @unittest.skipUnless((R / "site" / "index.html").exists(), "rode python3 build_site.py antes")
    def test_site_sem_link_do_repo(self):
        repo = "github.com/vitoropereira/" + "vitorpereira.ia.br-eleicoes"  # concatenado para o teste não casar consigo mesmo
        com_link = []
        for p in self.SITE.rglob("*"):
            if p.is_file():
                try:
                    if repo in p.read_text(encoding="utf-8"):
                        com_link.append(str(p.relative_to(self.SITE)))
                except UnicodeDecodeError:
                    pass
        self.assertEqual(com_link, [], "o repo pode ser privado: o site não pode linkar para ele")

    @unittest.skipUnless((R / "site" / "index.html").exists(), "rode python3 build_site.py antes")
    def test_codigo_da_analise_espelha_as_fontes(self):
        destino = self.SITE / "analise" / "codigo"
        self.assertTrue((destino / "index.html").exists())
        for rel in B.CODIGO_ANALISE:
            self.assertTrue((destino / rel).exists(), rel)
            self.assertEqual((destino / rel).read_bytes(), (R / rel).read_bytes(), rel)
            self.assertIn(f'href="{rel}"', (destino / "index.html").read_text(), rel)


if __name__ == "__main__":
    unittest.main()
