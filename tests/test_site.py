import re, sys, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import brand
import build_site as B

PALETA_ANTIGA = ["#f7f6f3", "#1b1c1e", "#1a1a19", "#232322", "#2563c9", "#5b8def"]


class HoraDaLeitura(unittest.TestCase):
    """issue 150: leitura de outro dia que não o da eleição (04/10) mostra a data."""

    def test_hora_da_leitura(self):
        self.assertEqual(B.hora_leitura("04/10/2026", "21:56:49"), "21:56")
        self.assertEqual(B.hora_leitura("05/10/2026", "12:51:05"), "05/10 12:51")

    def test_indice_da_apuracao(self):
        h = B.pagina_apuracao("<style></style>")
        final = re.search(r'<a class="rd final" href="/1-turno/"><span class="t">([^<]*)</span>', h)
        self.assertEqual(final.group(1), B.hora_leitura(B.N["dg"], B.N["ht"]))
        if B.N["dg"] != B.DIA_ELEICAO:
            self.assertIn("/", final.group(1))
        for r in B.rodadas:
            self.assertIn(f'<span class="t">{r["d"]["ht"][:5]}</span>', h)  # todas do dia da eleição: só a hora


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

    def test_404_com_atalhos(self):
        # issue 150: a 404 leva às seções principais e à busca do Rastro
        h = B.pagina_404("<style></style>")
        for href in ("/", "/ao-vivo/", "/rastro/", "/rastro/#busca", "/apuracao/"):
            self.assertIn(f'href="{href}"', h)
        self.assertEqual('href="/debates/"' in h, bool(B.debates()))

    def test_busca_do_rastro_tem_ancora(self):
        from rastro import paginas as rp
        self.assertIn('id="busca"', rp.caixa_busca(grande=True))
        self.assertNotIn('id="busca"', rp.caixa_busca())

    def test_cookies_compacto_no_celular(self):
        m = re.search(r"@media \(max-width:520px\)\{(.*?)\}\n", B.MEDICAO_CSS, re.S)
        self.assertIsNotNone(m)
        css = m.group(1)
        self.assertRegex(css, r"\.consent \.in\{[^}]*padding:\s*8px")
        self.assertRegex(css, r"\.consent p\{[^}]*font-size:\s*13px")

    def test_cabecalho_compacto_no_celular(self):
        m = re.search(r"@media \(max-width:640px\)\{(.*?)\}\}", B.SITE_CSS, re.S)
        self.assertIsNotNone(m)
        css = m.group(1)
        nav = re.search(r"\.sitebar nav\.top\{([^}]*)\}", css)
        self.assertIsNotNone(nav)
        self.assertIn("flex-wrap:nowrap", nav.group(1))
        self.assertIn("overflow-x:auto", nav.group(1))
        links = re.search(r"\.sitebar nav\.top a\{([^}]*)", css)
        self.assertIsNotNone(links)
        self.assertIn("white-space:nowrap", links.group(1))


class Turno2(unittest.TestCase):
    """Até o 2º turno (25/10): faixa de chamada na home; OG da home e do /ao-vivo/ sem o resultado do 1º turno."""
    PROIBIDO = ("1º turno", "47,0", "45,2", "47,03", "45,16")

    def test_faixa_ate_25_10(self):
        from datetime import date
        f = B.banner_turno2(date(2026, 10, 22))
        self.assertIn('class="banner"', f)
        self.assertIn("2º turno: domingo, 25/10", f)
        self.assertIn("17h (Brasília)", f)
        self.assertIn('href="/ao-vivo/"', f)
        self.assertTrue(B.banner_turno2(date(2026, 10, 25)))
        self.assertEqual(B.banner_turno2(date(2026, 10, 26)), "")

    def og(self, titulo, desc):
        h = B.head(titulo, desc, "/", "/og/x.png", [], "a", "b")
        return dict(re.findall(r'<meta (?:property|name)="((?:og|twitter):[\w:]+)" content="([^"]*)"', h))

    def test_og_da_home_sem_1o_turno(self):
        _, titulo, desc = B.textos_principal()
        og = self.og(titulo, desc)
        for k in ("og:title", "og:description", "og:image:alt", "twitter:title", "twitter:description"):
            for x in self.PROIBIDO:
                self.assertNotIn(x, og[k], k)
        self.assertIn("2º turno", og["og:title"])

    def test_og_do_ao_vivo_sem_1o_turno(self):
        titulo, desc = B.textos_aovivo()
        og = self.og(titulo, desc)
        for k in ("og:title", "og:description", "og:image:alt"):
            for x in self.PROIBIDO:
                self.assertNotIn(x, og[k], k)
        self.assertIn("25/10", og["og:description"])

    def test_imagens_og_sem_percentual_do_1o_turno(self):
        cards = dict(B.cards_turno2())
        self.assertEqual(set(cards), {"index", "ao-vivo"})
        for nome, h in cards.items():
            for x in self.PROIBIDO:
                self.assertNotIn(x, h, nome)
            self.assertIn("25/10", h, nome)
            self.assertIn("Flávio Bolsonaro", h, nome); self.assertIn("Lula", h, nome)


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
            # o site/ commitado só é regenerado pelo lote: confere que a brand está lá, não que é a brand.css de hoje
            # (mudar um token na brand.css não pode quebrar o PR antes do lote rodar)
            self.assertIn("/* Brand vitorpereira.ia.br", h, p)
            self.assertIn("--brand:#24C8FF", h, p)
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
        # monta em tmp: o site/ commitado só é regenerado pelo lote, então PR que muda calcular.py não pode quebrar aqui
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        B.copiar_codigo_analise(Path(tmp.name))
        destino = Path(tmp.name) / "analise" / "codigo"
        self.assertTrue((destino / "index.html").exists())
        for rel in B.CODIGO_ANALISE:
            self.assertTrue((destino / rel).exists(), rel)
            self.assertEqual((destino / rel).read_bytes(), (R / rel).read_bytes(), rel)
            self.assertIn(f'href="{rel}"', (destino / "index.html").read_text(), rel)


if __name__ == "__main__":
    unittest.main()


class PortaLivre(unittest.TestCase):
    def test_dois_servidores_ao_mesmo_tempo(self):
        """builds em paralelo (um por worktree) não podem brigar pela mesma porta"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a, b = B.serve(d), B.serve(d)
            try:
                self.assertNotEqual(a.server_address[1], b.server_address[1])
            finally:
                a.shutdown(); b.shutdown()
