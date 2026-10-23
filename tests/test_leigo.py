"""Texto para leigo (issue #143): o jargão de método só aparece dentro de um <details> recolhido.

Vale para a home (relatório final), a Análise, as páginas de leitura da apuração e a página de um debate. Cada
grupo afirma o caso proibido também: o mesmo termo fora de <details> é achado."""
import json, re, shutil, sys, tempfile, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "relatorio"))
sys.path.insert(0, str(R / "analise"))
import build_site as B
import pagina as P
import calcular as CALC
from debates import pagina as dp

TEM_CHROME = bool(shutil.which(B.CHROME) or Path(B.CHROME).exists())

# jargão que só pode aparecer recolhido; "campo" (classificação dos partidos) virou "lado" no texto visível.
# "Campo" com maiúscula só conta como rótulo ("Campo de Lula"): nome de município e de pessoa fica de fora.
TERMOS = [r"Duncan-Davis", r"[Ff]aixa estat[ií]stica", r"[Pp]artidos efetivos", r"[Nn][uú]mero efetivo",
          r"[Pp]roje[cç][aã]o final", r"[Pp]roje[cç][aã]o mediana", r"Laakso", r"\bcampos?\b",
          r"\bCampos? (?:de|em) (?:Lula|Fl[aá]vio|2022|2026)"]


def fora_de_details(h):
    """texto visível fora de qualquer <details> (aninhados inclusive), sem script, style, comentário e atributos"""
    h = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->", " ", h, flags=re.S | re.I)
    while True:
        n = re.sub(r"<details\b(?:(?!<details\b).)*?</details>", " ", h, flags=re.S | re.I)
        if n == h:
            break
        h = n
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def achados(h):
    t = fora_de_details(h)
    return [(termo, t[max(0, m.start() - 50):m.end() + 30]) for termo in TERMOS for m in re.finditer(termo, t)]


def summaries(h):
    return [re.sub(r"<[^>]+>", "", s).strip() for s in re.findall(r"<summary\b[^>]*>(.*?)</summary>", h, re.S)]


class Detector(unittest.TestCase):
    """o próprio filtro: termo dentro de <details> passa, fora é achado"""

    def test_dentro_passa_fora_falha(self):
        dentro = "<p>Resumo simples.</p><details><summary>Como calculamos</summary><p>limites de Duncan-Davis</p></details>"
        self.assertEqual(achados(dentro), [])
        self.assertNotEqual(achados("<p>limites de Duncan-Davis</p>"), [])
        self.assertNotEqual(achados("<details><summary>x</summary></details><p>o campo de Lula</p>"), [])

    def test_aninhado(self):
        h = "<details><summary>a</summary><details><summary>b</summary>partidos efetivos</details>número efetivo</details>"
        self.assertEqual(achados(h), [])

    def test_nome_proprio_nao_conta(self):
        self.assertEqual(achados("<p>São Bernardo do Campo, Pedro Campos (PSB-PE), Campo Grande</p>"), [])
        self.assertNotEqual(achados("<td>Campo de Lula (PT)</td>"), [])


class Destaques(unittest.TestCase):
    """cartões da Análise (analise/dados/destaques.json): uma frase simples, sem jargão"""

    def dados(self):
        return {p.name: json.loads(p.read_text()) for p in (R / "analise" / "dados").glob("*.json")}

    def test_destaques_publicados_sem_jargao(self):
        for d in json.loads((R / "analise" / "dados" / "destaques.json").read_text()):
            with self.subTest(d["id"]):
                self.assertEqual(achados(f'<p>{d["titulo"]}</p><p>{d["texto"]}</p>'), [])

    def test_destaques_regerados_iguais_aos_publicados(self):
        """destaques.json e faq.json estão em dia com analise/calcular.py"""
        D = self.dados()
        self.assertEqual(CALC.destaques(D), D["destaques.json"])
        self.assertEqual(CALC.faq(D), D["faq.json"])


class Debate(unittest.TestCase):
    def setUp(self):
        self.p = dp.gerar(dp.carregar(R / "tests" / "fixtures" / "debates" / "2026" / "presidente-2-turno-teste"),
                          B.BASE, B.PESSOA)

    def test_metodo_recolhido(self):
        h = self.p["html"]
        s = summaries(h)
        self.assertIn("Como checamos", s)
        self.assertIn("Como etiquetamos", s)
        fora = fora_de_details(h)
        for frase in ("Selecionamos as frases", "Cada frase dita por um candidato recebeu uma etiqueta"):
            self.assertIn(frase, h)
            self.assertNotIn(frase, fora)
        self.assertIn('id="metodo"', h)  # âncora mantida
        self.assertEqual(achados(h), [])

    def test_pagina_da_afirmacao_tambem(self):
        h = self.p["afirmacoes"][0]["html"]
        self.assertIn("Como checamos", summaries(h))
        self.assertNotIn("Selecionamos as frases", fora_de_details(h))

    def test_indice(self):
        h = dp.indice([self.p], B.BASE, B.PESSOA)["html"]
        self.assertIn("Como checamos", summaries(h))
        self.assertNotIn("Selecionamos as frases", fora_de_details(h))


class Estatico(unittest.TestCase):
    """textos que não precisam de navegador"""

    def test_analise_desc_e_secoes(self):
        for t in [B.ANALISE_DESC] + [x for _, x in B.SECOES_ANALISE]:
            self.assertEqual(achados(f"<p>{t}</p>"), [], t)

    def test_indice_da_apuracao(self):
        self.assertEqual(achados(B.pagina_apuracao("")), [])


@unittest.skipUnless(TEM_CHROME, "Chrome headless indisponível")
class Renderizado(unittest.TestCase):
    """páginas montadas e rodadas no Chrome (o texto delas sai do JS)"""

    def render(self, doc):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "index.html"
            arq.write_text(doc)
            return B.prerender(arq.as_uri())

    def test_home(self):
        rel = json.loads((R / "relatorio" / "relatorio.json").read_text())
        rel["mapa"] = json.loads((R / "relatorio" / "dados" / "mapa.json").read_text())
        doc = self.render(P.html_relatorio((R / "relatorio" / "template_relatorio.html").read_text(), rel, P.siglas_2022()))
        self.assertIn('id="hl"><li', doc)  # o script rodou
        self.assertIn("Como calculamos", summaries(doc))
        self.assertEqual(achados(doc), [])

    def test_leitura(self):
        r = next(x for x in B.rodadas if x["slug"] == "84-9")
        doc = self.render(B.html_leitura((R / "template.html").read_text(), r["d"]))
        self.assertIn("Vantagem final de Flávio", doc)  # o script rodou até o fim
        self.assertIn("Como calculamos", summaries(doc))
        self.assertEqual(achados(doc), [])

    @unittest.skipUnless((R / "site" / "vendor").exists(), "site/ não construído (python3 build_site.py)")
    def test_analise(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for x in ("vendor", "hud", "geo"):
                (d / x).symlink_to(R / "site" / x)
            B.copiar_analise(d)
            (d / "analise" / "index.html").write_text(B.html_analise(B.analise_dados(), B.ANALISE_GERADA, B.ANALISE_GERADA))
            srv = B.serve(d)
            try:
                doc = B.prerender(f"http://127.0.0.1:{srv.server_address[1]}/analise/")
            finally:
                srv.shutdown(); srv.server_close()
        self.assertIn('id="metodo"', doc)  # o app montou até a última seção
        self.assertIn("Como calculamos", summaries(doc))
        self.assertNotIn("Entenda", summaries(doc))
        self.assertEqual(achados(doc), [])


if __name__ == "__main__":
    unittest.main()
