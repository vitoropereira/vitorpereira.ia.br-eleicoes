"""Celular (issue 146): nenhum texto abaixo de 12 px (rótulo em maiúsculas: mínimo 11 px) e, até 640 px, controles com
pelo menos 40 px de altura. O painel ao vivo no desktop continua denso: os 40 px só valem dentro de max-width:640px."""
import re
import unittest
from pathlib import Path

import build_site as B
from debates import pagina as dp
from rastro import diagramas as rd
from rastro import paginas as rp

R = Path(__file__).resolve().parent.parent

# toda fonte de CSS do site: templates, o relatório publicado na home e os CSS montados em Python
FONTES_CSS = {
    "brand.css": (R / "brand.css").read_text(),
    "template.html": (R / "template.html").read_text(),
    "template_hud.html": (R / "template_hud.html").read_text(),
    "template_analise.html": (R / "template_analise.html").read_text(),
    "relatorio/template_relatorio.html": (R / "relatorio" / "template_relatorio.html").read_text(),
    "relatorio/relatorio_final.html": (R / "relatorio" / "relatorio_final.html").read_text(),
    "build_site.py": (R / "build_site.py").read_text(),
    "debates/pagina.py": (R / "debates" / "pagina.py").read_text(),
    "rastro/paginas.py": (R / "rastro" / "paginas.py").read_text(),
    "rastro/diagramas.py": (R / "rastro" / "diagramas.py").read_text(),
}

RE_DECL = re.compile(r"font(-size)?\s*:\s*([^;}\"`]*)")
RE_PX = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)px")


def bloco(txt, i):
    """o bloco de declarações em volta da posição i: de '{' ou '"' até '}' ou '"'"""
    ini = max(txt.rfind("{", 0, i), txt.rfind('"', 0, i))
    fs = [p for p in (txt.find("}", i), txt.find('"', i)) if p != -1]
    return txt[ini + 1:min(fs) if fs else len(txt)]


def tamanhos(txt):
    """[(px, é rótulo em maiúsculas, trecho)] de cada font-size / font em px"""
    out = []
    for m in RE_DECL.finditer(txt):
        val = m.group(2)
        if "clamp(" in val or "var(" in val and not RE_PX.search(val):
            continue
        px = RE_PX.search(val)
        if not px:
            continue
        b = bloco(txt, m.start())
        out.append((float(px.group(1)), "text-transform:uppercase" in b.replace(" ", ""), b.strip()[:90]))
    return out


def regras_640(txt):
    """{seletor: declarações} das regras dentro de @media (max-width:640px)"""
    out = {}
    for m in re.finditer(r"@media \(max-width:640px\)\s*\{", txt):
        i, prof = m.end(), 1
        j = i
        while prof:
            prof += {"{": 1, "}": -1}.get(txt[j], 0)
            j += 1
        for sel, dec in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", txt[i:j - 1], flags=re.S)):
            for s in sel.split(","):
                out[" ".join(s.split())] = out.get(" ".join(s.split()), "") + dec
    return out


def alto(dec):
    d = dec.replace(" ", "")
    return any(f"{p}:{v}px" in d for p in ("min-height", "height") for v in range(40, 49))


class FonteMinima(unittest.TestCase):
    def test_nenhuma_fonte_abaixo_de_11px(self):
        ruins = [(n, px, t) for n, txt in FONTES_CSS.items() for px, _, t in tamanhos(txt) if px < 11]
        self.assertEqual(ruins, [])

    def test_abaixo_de_12px_so_rotulo_em_maiusculas(self):
        ruins = [(n, px, t) for n, txt in FONTES_CSS.items() for px, up, t in tamanhos(txt) if px < 12 and not up]
        self.assertEqual(ruins, [])

    def test_varredura_pega_fonte_pequena(self):
        """o detector funciona: fonte pequena fora de rótulo é apontada; rótulo em maiúsculas de 11 px passa"""
        self.assertEqual([px for px, up, _ in tamanhos(".a{font:500 9.5px var(--font-mono)}") if not up], [9.5])
        self.assertEqual([px for px, up, _ in tamanhos('<text style="font-size:11px;fill:red">') if not up], [11.0])
        self.assertEqual([(px, up) for px, up, _ in tamanhos(".k{font-size:11px;text-transform:uppercase}")],
                         [(11.0, True)])

    def test_diagrama_do_rastro(self):
        self.assertGreaterEqual(rd.FONTE, 12)


class AlvoDeToque(unittest.TestCase):
    CASOS = {
        "SITE_CSS": (B.SITE_CSS, [".sitebar .brand", ".sitebar nav.top a", "a.agora", "button.tema",
                                  ".rounds a", "nav.crumbs a", "footer.site .eu a", "footer.site .eu button",
                                  ".faq summary"]),
        "MEDICAO_CSS": (B.MEDICAO_CSS, [".consent button"]),
        "SECOES_CSS": (B.SECOES_CSS, [".secoes>button"]),
        "template_hud.html": (FONTES_CSS["template_hud.html"],
                              [".seg button", ".seg .aba", ".bt", ".marca", ".trilho input", ".cab a.sub",
                               ".link"]),
        "template_analise.html": (FONTES_CSS["template_analise.html"],
                                  [".seg button", ".seg a", ".indice a", ".bt", ".hud-top .voltar", ".marca",
                                   ".uf-sel select", ".entenda summary", ".faq summary", ".link"]),
        "template.html": (FONTES_CSS["template.html"], ["details summary"]),
        "relatorio (home)": (FONTES_CSS["relatorio/template_relatorio.html"],
                             ["nav a", "details summary", "details.mais>summary"]),
        "relatorio_final.html": (FONTES_CSS["relatorio/relatorio_final.html"],
                                 ["nav a", "details summary", "details.mais>summary"]),
        "debates/pagina.py": (dp.CSS, [".db-rt-filtro select", ".db-filtro select", ".db-metodo summary", ".db-link"]),
        "rastro/paginas.py": (rp.CSS, ["details summary", ".rs-filtro"]),
    }

    def test_controles_com_40px_ate_640px(self):
        faltam = []
        for nome, (css, seletores) in self.CASOS.items():
            r = regras_640(css)
            faltam += [(nome, s) for s in seletores if not alto(r.get(s, ""))]
        self.assertEqual(faltam, [])

    def test_hud_desktop_continua_denso(self):
        """fora do @media (max-width:640px), o painel ao vivo não ganha alvos de 40 px"""
        css = FONTES_CSS["template_hud.html"]
        fora = re.sub(r"@media \(max-width:640px\)\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", css)
        self.assertNotRegex(fora, r"min-height:4\dpx")
        self.assertIn(".seg button{border:0;background:none;color:var(--ink2);padding:5px 12px", fora)

    def test_detector_de_altura(self):
        self.assertFalse(alto("padding:5px 12px"))
        self.assertTrue(alto("min-height:40px;display:inline-flex"))
        self.assertEqual(regras_640("@media (max-width:640px){.a,.b{min-height:40px}}"),
                         {".a": "min-height:40px", ".b": "min-height:40px"})


if __name__ == "__main__":
    unittest.main()
