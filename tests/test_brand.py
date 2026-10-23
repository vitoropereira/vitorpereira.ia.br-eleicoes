import colorsys, re, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(R))
import brand


def bloco(seletor_regex):
    m = re.search(seletor_regex + r"\s*\{([^}]*)\}", brand.CSS)
    assert m, f"bloco não encontrado: {seletor_regex}"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


def tema(nome):
    base = bloco(r":root")
    return base if nome == "escuro" else {**base, **bloco(r":root\[data-theme=\"light\"\]")}


def lum(hexcor):
    h = hexcor.strip().lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contraste(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class Brand(unittest.TestCase):
    def test_valores_da_brand(self):
        e, c = tema("escuro"), tema("claro")
        self.assertEqual((e["--bg"], e["--card"], e["--brand"]), ("#070B12", "#0C121D", "#24C8FF"))
        self.assertEqual((c["--bg"], c["--card"], c["--brand"]), ("#FBFCFE", "#FFFFFF", "#0A76AD"))
        self.assertEqual((e["--line"], e["--ink"], e["--muted"], e["--flavio"]), ("#1E2A3D", "#E9EEF7", "#8593AB", "#5B7FE8"))
        self.assertEqual((c["--line"], c["--ink"], c["--muted"], c["--flavio"]), ("#E2E8F1", "#0B1220", "#566072", "#2F5BD3"))

    def test_claro_do_sistema_igual_ao_claro_manual(self):
        m = re.search(r'@media \(prefers-color-scheme: light\)\{:root:not\(\[data-theme="dark"\]\)\{([^}]*)\}', brand.CSS)
        self.assertTrue(m, "bloco do tema claro pelo sistema não encontrado")
        auto = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))
        self.assertEqual(auto, bloco(r":root\[data-theme=\"light\"\]"))

    def test_contraste_aa_nos_dois_temas(self):
        for nome in ("escuro", "claro"):
            t = tema(nome)
            for fg in ("--ink", "--ink2", "--muted"):
                for bg in ("--bg", "--card"):
                    self.assertGreaterEqual(contraste(t[fg], t[bg]), 4.5, f"{nome}: {fg} sobre {bg}")
            self.assertGreaterEqual(contraste(t["--bg"], t["--brand"]), 4.5, f"{nome}: --bg sobre --brand (botão)")
            # cores de partido aparecem em números grandes: AA para texto grande
            for fg in ("--flavio", "--lula"):
                self.assertGreaterEqual(contraste(t[fg], t["--card"]), 3.0, f"{nome}: {fg} sobre --card")

    def test_alerta_do_selo_fora_da_paleta_de_partido(self):
        # issue 150: o tom do selo de veredito (--alerta) é texto AA nos dois temas e fica longe do azul, do vermelho
        # (partidos) e do verde (--live); medido: matiz 40° nos dois temas, ~36° do --lula
        hue = lambda x: colorsys.rgb_to_hsv(*(int(x.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0] * 360
        for nome in ("escuro", "claro"):
            t = tema(nome)
            self.assertIn("--alerta", t, nome)
            for bg in ("--bg", "--card", "--soft"):
                self.assertGreaterEqual(contraste(t["--alerta"], t[bg]), 4.5, f"{nome}: --alerta sobre {bg}")
            for outra in ("--flavio", "--lula", "--live"):
                d = abs(hue(t["--alerta"]) - hue(t[outra])) % 360
                self.assertGreaterEqual(min(d, 360 - d), 25, f"{nome}: --alerta perto de {outra}")

    def test_pl_longe_do_ciano(self):
        for nome in ("escuro", "claro"):
            t = tema(nome)
            hue = lambda x: colorsys.rgb_to_hsv(*(int(x.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0] * 360
            # medido: escuro 29,6°, claro 23,7° (no claro a luminosidade também separa)
            self.assertGreaterEqual(abs(hue(t["--flavio"]) - hue(t["--brand"])), 20, nome)

    def test_claro_tambem_pelo_sistema(self):
        self.assertIn('@media (prefers-color-scheme: light){:root:not([data-theme="dark"])', brand.CSS)

    def test_aplicar(self):
        self.assertIn("--bg:#070B12", brand.aplicar("<style>/*__BRAND__*/body{}</style>"))
        with self.assertRaises(ValueError):
            brand.aplicar("<style>body{}</style>")


TEMPLATES = [R / "template.html", R / "template_hud.html", R / "relatorio" / "template_relatorio.html"]


class Templates(unittest.TestCase):
    def test_um_marcador_e_sem_tokens_proprios(self):
        for t in TEMPLATES:
            h = t.read_text()
            self.assertEqual(h.count("/*__BRAND__*/"), 1, t.name)
            self.assertNotRegex(h, r"--(bg|ink|card|flavio|lula)\s*:\s*#", f"{t.name} ainda define cor própria")

    def test_todo_token_usado_existe(self):
        da_brand = set(re.findall(r"(--[\w-]+)\s*:", brand.CSS))
        for t in TEMPLATES:
            h = t.read_text()
            definidos = da_brand | set(re.findall(r"(--[\w-]+)\s*:", h))  # locais, ex.: style="--c:…"
            # var(--b${i}) é montado em JS; os tokens --b1..4/--r1..4 abaixo cobrem essa família
            usados = set(re.findall(r"var\((--[\w-]+)(?!\$)", h)) | set(re.findall(r"css\('(--[\w-]+)'\)", h))
            self.assertEqual(usados - definidos, set(), t.name)
            if "var(--b${" in h:
                self.assertLessEqual({f"--{c}{i}" for c in "br" for i in range(1, 5)}, definidos, t.name)

    def test_fonte_do_corpo_tem_fallback(self):
        self.assertIn("-apple-system", brand.CSS)
        for t in TEMPLATES:
            self.assertNotIn("-apple-system", t.read_text(), f"{t.name}: use var(--font-sans)")

    def test_fontes_existem(self):
        for f in re.findall(r"url\(/fonts/([^)]+)\)", brand.CSS):
            p = R / "assets" / "fonts" / f
            self.assertTrue(p.exists() and p.stat().st_size > 10_000, f)


if __name__ == "__main__":
    unittest.main()
