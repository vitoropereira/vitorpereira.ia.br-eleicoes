"""Home do 2º turno (issue 205): três fases na `/` e o relatório do 1º turno em `/1-turno/`.
Monta o site num diretório temporário (test_tema.montar_em_tmp: sem Chrome, sal descartável); nunca lê o site/ commitado."""
import re, sys, tempfile, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B
from municipios import minha_secao as msec
from tests.test_tema import montar_em_tmp

RE_SCRIPT = re.compile(r"<script(?P<attrs>[^>]*)>(?P<corpo>.*?)</script>", re.S)
RE_FASE = re.compile(r'<section\b[^>]*\bdata-fase="(\w+)"[^>]*>')


class HomeTurno2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.site = montar_em_tmp(Path(tmp.name))
        cls.home = (cls.site / "index.html").read_text(encoding="utf-8")
        cls.t1 = (cls.site / "1-turno" / "index.html").read_text(encoding="utf-8")

    def secao(self, fase):
        m = re.search(rf'<section\b[^>]*\bdata-fase="{fase}"[^>]*>', self.home)
        self.assertIsNotNone(m, fase)
        return m.group(0), self.home[m.end():]

    def test_tres_fases_so_a_vespera_visivel(self):
        self.assertEqual(RE_FASE.findall(self.home), ["vespera", "apuracao", "resultado"])
        self.assertNotIn("hidden", self.secao("vespera")[0])
        self.assertRegex(self.secao("apuracao")[0], r"\bhidden\b")
        self.assertRegex(self.secao("resultado")[0], r"\bhidden\b")

    def test_h1_da_vespera_sem_numero_do_1o_turno(self):
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", self.home, re.S).group(1)
        self.assertEqual(h1, f"2º turno: {B.rotulo(B.cF)} × {B.rotulo(B.cL)}, domingo, 25/10")
        topo = self.home[:self.home.index('data-fase="apuracao"')]
        for n in (B.fmt(B.cF["p"], 2), B.fmt(B.cL["p"], 2)):
            self.assertNotIn(n, topo)
        self.assertIn("Apuração ao vivo a partir das 17h (Brasília)", self.home)

    def test_portas(self):
        for d in B.debates():
            self.assertIn(f'href="{d["path"]}"', self.home)
        if B.debates():
            self.assertIn('href="/debates/"', self.home)
        self.assertIn('href="/ao-vivo/"', self.home)
        self.assertIn('href="/1-turno/"', self.home)
        self.assertEqual('href="/minha-secao/"' in self.home.split("<main")[1], msec.tem_dados(B.LOCAIS))

    def test_script_modulo_e_nenhum_inline_novo(self):
        self.assertIn('<script type="module" src="/home.js"></script>', self.home)
        # os inlines que já existem em toda página (tema no head, JSON-LD) ficam; a home não ganha nenhum
        ref = (self.site / "apuracao" / "index.html").read_text(encoding="utf-8")
        inline = lambda h: sorted(m.group("corpo") for m in RE_SCRIPT.finditer(h) if "src=" not in m.group("attrs") and "ld+json" not in m.group("attrs"))
        extras = [c for c in inline(self.home) if c not in inline(ref)]
        self.assertEqual(extras, [])
        self.assertTrue((self.site / "home.js").exists())
        self.assertNotIn("_test", " ".join(p.name for p in self.site.rglob("home*")))

    def test_sem_banner_de_chamada_e_com_moldura(self):
        self.assertNotIn("2º turno: domingo, 25/10.</b>", self.home)  # a home já é a chamada
        if B.banner_debate():
            self.assertNotIn(B.banner_debate(), self.home)
        self.assertIn('class="sitebar"', self.home)
        self.assertIn('<footer class="site">', self.home)
        self.assertIn('class="agora"', self.home)
        self.assertEqual(len(re.findall(r'class="tema"', self.home)), 1)

    def test_jsonld_da_home_sem_dataset(self):
        tipos = re.findall(r'"@type": "(\w+)"', "".join(re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.home, re.S)))
        self.assertIn("WebSite", tipos); self.assertIn("WebPage", tipos)
        self.assertNotIn("Dataset", tipos); self.assertNotIn("NewsArticle", tipos)

    def test_cores_so_de_tokens(self):
        trecho = re.search(r'<style id="home-turno2">(.*?)</style>', self.home, re.S)
        self.assertIsNotNone(trecho)
        self.assertNotRegex(trecho.group(1), r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotRegex(trecho.group(1), r"rgba?\(")


class UmTurno(unittest.TestCase):
    """/1-turno/ = o relatório que era a home, com os mesmos números"""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.site = montar_em_tmp(Path(tmp.name))
        cls.t1 = (cls.site / "1-turno" / "index.html").read_text(encoding="utf-8")
        cls.relatorio = (R / "relatorio" / "relatorio_final.html").read_text(encoding="utf-8")

    def test_mesmos_numeros_do_relatorio(self):
        self.assertIn(B.textos_principal()[0], self.t1)  # o H1 de antes
        self.assertIn('id="perguntas"', self.t1)  # FAQ visível
        self.assertIn(f'{B.fmt(B.N["pst"], 2)}%</b> das seções apuradas', self.t1)  # faixa das rodadas
        self.assertIn('href="/apuracao/"', self.t1)
        for id_ in ("presidente", "governadores", "senado", "camara", "assembleias", "metodo"):
            self.assertIn(f'id="{id_}"', self.t1)

    def test_canonical_e_jsonld_em_1_turno(self):
        self.assertIn(f'<link rel="canonical" href="{B.BASE}/1-turno/">', self.t1)
        for tipo in ("NewsArticle", "Dataset", "FAQPage"):
            self.assertIn(f'"@type": "{tipo}"', self.t1)
        self.assertIn(f'"mainEntityOfPage": "{B.BASE}/1-turno/"', self.t1)
        self.assertIn(f'"url": "{B.BASE}/1-turno/"', self.t1)

    def test_trilha(self):
        self.assertIn("Resultado do 1º turno", self.t1)
        self.assertRegex(self.t1, r'href="/">Início</a>')

    def test_sitemap_e_llms(self):
        sm = (self.site / "sitemap.xml").read_text()
        self.assertIn(f"<loc>{B.BASE}/1-turno/</loc>", sm)
        self.assertRegex(sm, rf"<loc>{re.escape(B.BASE)}/1-turno/</loc><lastmod>[^<]*</lastmod><priority>0.9</priority>")
        self.assertIn(f"<loc>{B.BASE}/</loc>", sm)
        llms = (self.site / "llms.txt").read_text()
        self.assertIn(f"({B.BASE}/1-turno/)", llms)
        self.assertLess(llms.index(f"({B.BASE}/)"), llms.index(f"({B.BASE}/1-turno/)"))

    def test_sem_link_para_ancora_da_home(self):
        self.assertFalse([k for k, _ in B.secoes() if k.startswith("/#")])
        self.assertIn(("/1-turno/#metodo", B.NAV.METODO), B.secoes())
        achados = [str(p.relative_to(self.site)) for p in self.site.rglob("*.html") if 'href="/#' in p.read_text(encoding="utf-8")]
        self.assertEqual(achados, [])


if __name__ == "__main__":
    unittest.main()
