"""Página de checagem do debate (/debates/<emissora>-<turno>-turno/), gerada por debates/pagina.py a partir dos JSON."""
import copy, html, json, re, shutil, sys, tempfile, unittest
from collections import Counter
from pathlib import Path
from unittest import mock

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B
from debates import pagina as dp

FIXTURE = R / "tests" / "fixtures" / "debates"
REAL = R / "debates" / "2026-10-18-band"
ADJETIVOS = re.compile(r"\b(venceu|vencedor|ganhou|perdeu|mentiros[oa]|destruiu|humilhou|arrasou|massacrou)\b", re.I)


def gerar(pasta=FIXTURE):
    return dp.gerar(*dp.ler(pasta), B.BASE, B.PESSOA)


def ld_de(h):
    return [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]


class Cobertura(unittest.TestCase):
    def checar(self, pasta):
        afs, chs = dp.ler(pasta)
        p = dp.gerar(afs, chs, B.BASE, B.PESSOA)
        h = p["html"]
        por_id = {a["id"]: a for a in afs["afirmacoes"]}
        for c in chs["checagens"]:
            self.assertIn(f'id="{c["id"]}"', h, c["id"])
            self.assertIn(html.escape(por_id[c["id"]]["trecho"], quote=False), h, c["id"])
            self.assertIn(html.escape(c["veredito"], quote=False), h, c["id"])
            self.assertIn(html.escape(c["explicacao"], quote=False), h, c["id"])
            for f in c["fontes"]:
                self.assertRegex(h, r'<a href="' + re.escape(html.escape(f["url"])) + r'"[^>]*>', f["url"])
            if c.get("outro_lado"):
                self.assertIn(html.escape(c["outro_lado"], quote=False), h)
        self.assertIn(f"Checamos {len(chs['checagens'])} afirmações", h)

    def test_fixture(self):
        self.checar(FIXTURE)

    @unittest.skipUnless((REAL / "checagens.json").exists(), "dados do debate ainda não publicados (#88/#89)")
    def test_dados_reais(self):
        self.checar(REAL)

    def test_path_vem_dos_dados(self):
        self.assertEqual(gerar()["path"], "/debates/band-2-turno/")

    def test_campo_faltando_falha_claro(self):
        afs, chs = dp.ler(FIXTURE)
        sem = copy.deepcopy(chs); del sem["checagens"][0]["veredito"]
        with self.assertRaisesRegex(ValueError, "a01.*veredito"):
            dp.gerar(afs, sem, B.BASE, B.PESSOA)
        orfa = copy.deepcopy(chs); orfa["checagens"][0]["id"] = "zz"
        with self.assertRaisesRegex(ValueError, "zz"):
            dp.gerar(afs, orfa, B.BASE, B.PESSOA)
        ruim = copy.deepcopy(chs); ruim["checagens"][0]["fontes"] = [{"url": "javascript:alert(1)"}]
        with self.assertRaisesRegex(ValueError, "a01.*fonte"):
            dp.gerar(afs, ruim, B.BASE, B.PESSOA)
        cor = copy.deepcopy(afs); cor["debate"]["candidatos"][0]["cor"] = "brand"
        with self.assertRaisesRegex(ValueError, "cor"):
            dp.gerar(cor, chs, B.BASE, B.PESSOA)

    def test_turno_e_ids_repetidos_falham(self):
        afs, chs = dp.ler(FIXTURE)
        tur = copy.deepcopy(afs); tur["debate"]["turno"] = '2"><script>'
        with self.assertRaisesRegex(ValueError, "turno"):
            dp.gerar(tur, chs, B.BASE, B.PESSOA)
        dup = copy.deepcopy(afs); dup["afirmacoes"].append(dict(dup["afirmacoes"][0]))
        with self.assertRaisesRegex(ValueError, "a01.*repetida"):
            dp.gerar(dup, chs, B.BASE, B.PESSOA)
        cdup = copy.deepcopy(afs); cdup["debate"]["candidatos"].append(dict(cdup["debate"]["candidatos"][0]))
        with self.assertRaisesRegex(ValueError, "flavio.*repetido"):
            dp.gerar(cdup, chs, B.BASE, B.PESSOA)

    def test_transcricao_sem_http_nao_vai_pro_ld(self):
        afs, chs = dp.ler(FIXTURE)
        afs = copy.deepcopy(afs); afs["debate"]["transcricao"] = "javascript:alert(1)"
        p = dp.gerar(afs, chs, B.BASE, B.PESSOA)
        cr = next(x for x in p["ld"] if x["@type"] == "ClaimReview")
        self.assertEqual(cr["itemReviewed"]["appearance"]["url"], B.BASE + p["path"])

    def test_ld_nao_fecha_script(self):
        self.assertNotIn("</script>", B.jsonld({"x": "</script><b>"})[:-len("</script>")])

    def test_ler_sem_dados_devolve_none(self):
        self.assertIsNone(dp.ler(R / "debates" / "nao-existe"))


class Placar(unittest.TestCase):
    def test_contagem_por_candidato(self):
        afs, chs = dp.ler(FIXTURE)
        h = gerar()["html"]
        cand = {a["id"]: a["candidato"] for a in afs["afirmacoes"]}
        esperado = Counter((cand[c["id"]], c["veredito"]) for c in chs["checagens"])
        tabela = re.search(r'<table class="db-placar">(.*?)</table>', h, re.S).group(1)
        for c in afs["debate"]["candidatos"]:
            linha = re.search(r'<tr data-candidato="' + c["id"] + r'">(.*?)</tr>', tabela, re.S).group(1)
            nums = [int(x) for x in re.findall(r"<td[^>]*>(\d+)</td>", linha)]
            self.assertEqual(nums[:-1], [esperado[(c["id"], v)] for v in chs["vereditos"]], c["id"])
            self.assertEqual(nums[-1], sum(esperado[(c["id"], v)] for v in chs["vereditos"]))

    def test_sem_adjetivos_fora_das_citacoes(self):
        h = re.sub(r"<blockquote.*?</blockquote>", "", gerar()["html"], flags=re.S)
        self.assertIsNone(ADJETIVOS.search(h))

    def test_temas_em_ordem_fixa(self):
        h = gerar()["html"]
        temas = re.findall(r'<section class="db-tema" id="tema-([a-z0-9-]+)"', h)
        self.assertEqual(temas, ["seguranca", "economia", "saude", "social", "corrupcao-e-acusacoes", "internacional", "educacao"])

    def test_so_cores_de_partido_no_conteudo(self):
        h = gerar()["html"]
        self.assertNotIn("var(--brand)", dp.CSS)
        for cor in re.findall(r"var\(--(\w+)\)", h.rsplit("</style>", 1)[1]):
            self.assertIn(cor, dp.CORES)

    def test_uma_coluna_no_celular(self):
        self.assertIn("@media (max-width:760px)", dp.CSS)


class JsonLd(unittest.TestCase):
    def test_claimreview_por_checagem(self):
        afs, chs = dp.ler(FIXTURE)
        p = gerar()
        lds = p["ld"]
        self.assertEqual([json.loads(json.dumps(x)) for x in lds], lds)
        crs = [x for x in lds if x["@type"] == "ClaimReview"]
        self.assertEqual(len(crs), len(chs["checagens"]))
        nomes = {c["id"]: c["nome"] for c in afs["debate"]["candidatos"]}
        por_id = {a["id"]: a for a in afs["afirmacoes"]}
        for cr, c in zip(crs, chs["checagens"]):
            a = por_id[c["id"]]
            self.assertEqual(cr["url"], B.BASE + p["path"] + "#" + c["id"])
            self.assertEqual(cr["claimReviewed"], a["trecho"])
            self.assertEqual(cr["itemReviewed"]["@type"], "Claim")
            self.assertEqual(cr["itemReviewed"]["author"], {"@type": "Person", "name": nomes[a["candidato"]]})
            self.assertEqual(cr["itemReviewed"]["datePublished"], afs["debate"]["data"])
            self.assertIn("url", cr["itemReviewed"]["appearance"])
            self.assertEqual(cr["reviewRating"]["alternateName"], c["veredito"])
            self.assertEqual(cr["author"], B.PESSOA)
        tipos = [x["@type"] for x in lds]
        self.assertIn("Article", tipos); self.assertIn("BreadcrumbList", tipos)

    def test_ld_valido_na_pagina_publicada(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(B, "DEBATE_DADOS", FIXTURE):
            B.debate_publicar(Path(d))
            h = (Path(d) / "debates" / "band-2-turno" / "index.html").read_text()
        lds = ld_de(h)
        self.assertEqual(sum(x["@type"] == "ClaimReview" for x in lds), len(dp.ler(FIXTURE)[1]["checagens"]))


class Filtro(unittest.TestCase):
    def test_controles_nascem_escondidos(self):
        h = gerar()["html"]
        self.assertRegex(h, r'<form class="db-filtro"[^>]*hidden')
        self.assertIn('<script defer src="/debates/debate.js"></script>', h)
        self.assertEqual(len(re.findall(r'<article class="db-af"[^>]*data-candidato="\w+" data-veredito="[a-z0-9-]+"', h)), 7)


class Build(unittest.TestCase):
    def publicar(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        with mock.patch.object(B, "DEBATE_DADOS", FIXTURE):
            return d, B.debate_publicar(d)

    def test_publica_pagina_js_sitemap_e_llms(self):
        d, info = self.publicar()
        h = (d / "debates" / "band-2-turno" / "index.html").read_text()
        self.assertIn('class="sitebar"', h)
        self.assertIn('<link rel="canonical" href="' + B.BASE + '/debates/band-2-turno/">', h)
        self.assertIn('content="' + B.BASE + '/og/debate-band.png"', h)
        self.assertEqual((d / "debates" / "debate.js").read_bytes(), (R / "debates" / "debate.js").read_bytes())
        self.assertEqual(info["sitemap"], [("/debates/band-2-turno/", "2026-10-19T12:00:00-03:00", "0.8")])
        self.assertIn(B.BASE + "/debates/band-2-turno/", info["llms"])
        self.assertEqual(info["og"][0], "debate-band")

    def test_isolamento_de_scripts(self):
        from tests.test_rastro_publicado import scripts_fora
        d, _ = self.publicar()
        h = (d / "debates" / "band-2-turno" / "index.html").read_text()
        self.assertEqual(scripts_fora(h) - {"/debates/debate.js"}, set())

    def test_sem_dados_pula(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(B, "DEBATE_DADOS", Path(d) / "nada"):
            self.assertIsNone(B.debate_publicar(Path(d)))
            self.assertFalse((Path(d) / "debates").exists())

    def test_og_so_cores_de_partido(self):
        _, info = self.publicar()
        card = B.og_debate(*info["og"][1:])
        self.assertNotIn("#24C8FF", card.split("</style>", 1)[1])
        self.assertIn("Flávio Bolsonaro", card)


class Navegacao(unittest.TestCase):
    def test_menu_e_home_com_debate(self):
        with mock.patch.object(B, "DEBATE_DADOS", FIXTURE):
            s = B.sitebar("/debates/band-2-turno/")
            self.assertIn('<a href="/debates/band-2-turno/" aria-current=page>Debate Band</a>', s)
            self.assertIn('<a href="/debates/band-2-turno/">Debate Band</a>', B.sitebar("/"))
            self.assertIn('href="/debates/band-2-turno/"', B.banner_debate())

    def test_sem_dados_sem_link(self):
        with mock.patch.object(B, "DEBATE_DADOS", R / "debates" / "nao-existe"):
            self.assertNotIn("/debates/", B.sitebar("/"))
            self.assertEqual(B.banner_debate(), "")


if __name__ == "__main__":
    unittest.main()
