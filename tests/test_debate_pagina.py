"""Seção /debates/ (debates/pagina.py + build_site.debates_publicar): debate, afirmação, transcrição e índice."""
import html, json, re, shutil, sys, tempfile, unittest
from collections import Counter
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B
from debates import pagina as dp
from debates import validar as V

FIXTURE = R / "tests" / "fixtures" / "debates"
TESTE = FIXTURE / "2026" / "presidente-2-turno-teste"
FICT = FIXTURE / "2030" / "governador-1-turno-fict"
REAL = R / "debates" / "2026" / "presidente-2-turno-band"
PROIBIDAS = re.compile(r"\b(venceu|vencedor|ganhou|perdeu|mentiu|mentiros[oa]|destruiu|humilhou|arrasou|massacrou)\b", re.I)


def gerar(pasta=TESTE):
    return dp.gerar(dp.carregar(pasta), B.BASE, B.PESSOA)


def ld_de(h):
    return [json.loads(x.replace("<\\/", "</")) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]


def json_de(pasta, nome):
    return json.loads((pasta / nome).read_text(encoding="utf-8"))


class Carregar(unittest.TestCase):
    def test_incerta_fica_de_fora(self):
        m = dp.carregar(TESTE)
        self.assertNotIn("seg-02", m["itens"])
        self.assertNotIn("seg-02", [c["id"] for c in m["checagens"]])
        self.assertEqual(len(m["checagens"]), 4)

    def test_sem_checagens_nao_publica(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026" / "presidente-2-turno-teste"
            shutil.copytree(TESTE, d)
            (d / "checagens.json").unlink()
            self.assertIsNone(dp.carregar(d))
            self.assertEqual(dp.listar(tmp), [])

    def test_checagem_quebrada_levanta_com_id_e_campo(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026" / "presidente-2-turno-teste"
            shutil.copytree(TESTE, d)
            chs = json_de(d, "checagens.json")
            del chs[1]["explicacao"]
            (d / "checagens.json").write_text(json.dumps(chs), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"eco-01.*explicacao"):
                dp.carregar(d)

    def test_cor_padrao_e_mediacao(self):
        m = dp.carregar(FICT)
        self.assertEqual(m["cands"]["carla-souza-pc"]["cor"], "outros")
        self.assertEqual(m["cands"]["mediacao"]["cor"], "outros")

    def test_rotulos_cobrem_vereditos(self):
        self.assertEqual(set(dp.ROTULOS), {v for vs in V.VEREDITOS.values() for v in vs})
        self.assertEqual(set(dp.TEMAS), set(V.TEMAS))


class Placar(unittest.TestCase):
    def checar(self, pasta):
        m = dp.carregar(pasta)
        quem = {i["id"]: i["quem"] for i in json_de(pasta, "afirmacoes.json") if i["autoria"] == "certa"}
        esperado = Counter((quem[c["id"]], c["veredito"]) for c in json_de(pasta, "checagens.json") if c["id"] in quem)
        conta = dp.placar(m)
        self.assertEqual(sum(sum(c.values()) for c in conta.values()), len(m["checagens"]))
        for q, c in conta.items():
            self.assertEqual(list(c), [v for v in dp.ORDEM_VEREDITOS if v in c], "mesma ordem de validar.VEREDITOS")
            for v, n in c.items():
                self.assertEqual(n, esperado[(q, v)], (q, v))
        h = gerar(pasta)["html"]
        sec = re.search(r'<section aria-labelledby="placar">.*?</section>', h).group(0)
        for q, c in conta.items():
            total = sum(c.values())
            for v, n in c.items():
                self.assertIn(f"<li><span>{html.escape(dp.ROTULOS[v], quote=False)}</span><span>{n} ({round(100 * n / total)}%)</span></li>", sec)
        self.assertNotRegex(sec, PROIBIDAS)

    def test_fixture(self):
        self.checar(TESTE)
        self.assertEqual(dp.placar(dp.carregar(TESTE))["mediacao"]["verdadeiro-com-ressalva"], 1)

    @unittest.skipUnless((REAL / "checagens.json").exists(), "debate da Band ainda sem checagens.json")
    def test_band(self):
        self.checar(REAL)

    def test_sem_palavra_de_placar_de_luta_fora_das_citacoes(self):
        for g in (gerar(TESTE), gerar(FICT)):
            texto = re.sub(r"<blockquote>.*?</blockquote>|<p class=\"db-frase\">.*?</p>", "", g["html"])
            for c in dp.carregar(TESTE)["checagens"] + dp.carregar(FICT)["checagens"]:
                texto = texto.replace(html.escape(c["explicacao"], quote=False), "")
            self.assertNotRegex(texto, PROIBIDAS)


class PaginaDebate(unittest.TestCase):
    def checar(self, pasta):
        m = dp.carregar(pasta)
        g = dp.gerar(m, B.BASE, B.PESSOA)
        h = g["html"]
        self.assertEqual(g["path"], f"/debates/{m['debate']['ano']}/{m['debate']['slug']}/")
        for c in m["checagens"]:
            a = m["itens"][c["id"]]
            self.assertRegex(h, rf'<article class="db-af" id="{c["id"]}" data-candidato="{a["quem"]}" '
                                rf'data-tema="{a["tema"]}" data-veredito="{c["veredito"]}"')
            self.assertIn(html.escape(a["trecho"], quote=False), h)
            self.assertIn(html.escape(c["explicacao"], quote=False), h)
            self.assertIn(f'href="{g["path"]}{c["id"]}/"', h)
            for f in c["fontes"]:
                self.assertIn(f'<a href="{html.escape(f["url"])}"', h)
        self.assertIn(f"Checamos {len(m['checagens'])} afirmações", h)
        # ordem dos temas = validar.TEMAS
        temas = re.findall(r'<section class="db-tema" id="tema-([a-z-]+)">', h)
        self.assertEqual(temas, [t for t in V.TEMAS if t in temas])
        # JSON-LD
        ld = ld_de(B.jsonld(g["ld"]))[0]
        crs = [x for x in ld if x["@type"] == "ClaimReview"]
        self.assertEqual(len(crs), len(m["checagens"]))
        for cr, c in zip(crs, m["checagens"]):
            a = m["itens"][c["id"]]
            self.assertEqual(cr["url"], B.BASE + g["path"] + c["id"] + "/")
            self.assertEqual(cr["claimReviewed"], a["afirmacao"])
            self.assertEqual(cr["reviewRating"]["alternateName"], dp.ROTULOS[c["veredito"]])
            self.assertEqual(cr["itemReviewed"]["author"]["@type"], "Organization" if a["quem"] == "mediacao" else "Person")
            self.assertTrue(cr["itemReviewed"]["appearance"]["url"].endswith(f"transcricao/#{dp.ancora(a['timestamp'])}"))
        self.assertEqual({x["@type"] for x in ld} - {"ClaimReview"}, {"Article", "BreadcrumbList"})
        art = next(x for x in ld if x["@type"] == "Article")
        self.assertEqual(art["dateModified"], max([art["datePublished"]] + [c["atualizado_em"] for c in m["checagens"]]))
        return g

    def test_fixture(self):
        g = self.checar(TESTE)
        self.assertEqual(g["publicado"], "2026-10-12")  # publicado_em do debate.json
        self.assertEqual(g["modificado"], "2026-10-14")  # maior atualizado_em
        self.assertNotIn('id="seg-02"', g["html"])
        self.assertNotIn("Frase de autoria incerta", g["html"])
        self.assertEqual(gerar(FICT)["publicado"], "2030-09-01")  # sem publicado_em: a data do debate

    @unittest.skipUnless((REAL / "checagens.json").exists(), "debate da Band ainda sem checagens.json")
    def test_band(self):
        g = self.checar(REAL)
        self.assertEqual(g["path"], "/debates/2026/presidente-2-turno-band/")

    def test_filtro_escondido_sem_script_inline(self):
        h = gerar()["html"]
        self.assertIn('<form class="db-filtro" aria-label="Filtrar afirmações" hidden>', h)
        for nome in ("candidato", "tema", "veredito"):
            self.assertIn(f'<select name="{nome}">', h)
        self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", h), [])

    def test_transcricao_tem_ancora_de_todo_timestamp(self):
        for pasta in (TESTE, FICT) + ((REAL,) if (REAL / "checagens.json").exists() else ()):
            m = dp.carregar(pasta)
            t = dp.gerar(m, B.BASE, B.PESSOA)["transcricao"]
            self.assertEqual(t["path"], m["path"] + "transcricao/")
            for a in m["itens"].values():
                self.assertIn(f'id="{dp.ancora(a["timestamp"])}"', t["html"], a["id"])
            ids = re.findall(r' id="(t-[^"]+)"', t["html"])
            self.assertEqual(len(ids), len(set(ids)), "âncora repetida")

    def test_ancora(self):
        self.assertEqual(dp.ancora("4:33"), "t-0-04-33")
        self.assertEqual(dp.ancora("1:07:25"), "t-1-07-25")

    def test_no_video(self):
        self.assertEqual(dp.no_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "9:52"),
                         "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=592s")
        self.assertEqual(dp.no_video("https://youtu.be/dQw4w9WgXcQ", "1:07:25"), "https://youtu.be/dQw4w9WgXcQ?t=4045s")

    def test_tempo_leva_ao_video_quando_tem_video(self):
        m = dp.carregar(TESTE)
        self.assertNotIn("youtube.com", dp.gerar(m, B.BASE, B.PESSOA)["html"])
        m["debate"]["video"] = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        h = dp.gerar(m, B.BASE, B.PESSOA)["html"]
        for a in m["itens"].values():
            if a["id"] in [c["id"] for c in m["checagens"]]:
                self.assertIn(html.escape(dp.no_video(m["debate"]["video"], a["timestamp"])), h, a["id"])
                self.assertIn(f'transcricao/#{dp.ancora(a["timestamp"])}"', h, a["id"])


class PaginaAfirmacao(unittest.TestCase):
    def test_uma_por_checagem_com_og_propria(self):
        g = gerar()
        self.assertEqual([a["path"] for a in g["afirmacoes"]],
                         [f"{g['path']}{i}/" for i in ("seg-01", "eco-01", "eco-02", "soc-01")])
        ogs = [a["og"][0] for a in g["afirmacoes"]]
        self.assertEqual(len(set(ogs)), len(ogs))
        self.assertEqual(ogs[0], "debate-2026-presidente-2-turno-teste-seg-01")
        for a in g["afirmacoes"]:
            crs = [x for x in a["ld"] if x["@type"] == "ClaimReview"]
            self.assertEqual(len(crs), 1)
            self.assertEqual(crs[0]["url"], B.BASE + a["path"])
            self.assertIn('href="/debates/"', a["html"])
            self.assertIn(f'href="{g["path"]}#', a["html"])

    def test_og_afirmacao_corta_frase(self):
        h = B.og_afirmacao("palavra " * 60, "Ana Silva (PA)", "flavio", "Falso")
        q = re.search(r"<q>(.*?)</q>", h).group(1)
        self.assertLessEqual(len(q), 181)
        self.assertTrue(q.endswith("…"))
        self.assertIn(B.COR_OG["flavio"], h)


class Indice(unittest.TestCase):
    def test_ordem_e_placar_acumulado(self):
        gs = [dp.gerar(m, B.BASE, B.PESSOA) for m in dp.listar(FIXTURE)]
        self.assertEqual([g["path"] for g in gs], ["/debates/2030/governador-1-turno-fict/", "/debates/2026/presidente-2-turno-teste/"])
        idx = dp.indice(gs, B.BASE, B.PESSOA)
        soma = {q: {v: n for v, n in c.items() if n} for q, c in idx["placar"].items()}
        self.assertEqual(soma["ana-silva-pa"], {"verdadeiro": 1, "falso": 1, "viavel": 1})  # está nos dois debates
        self.assertEqual(soma["bruno-lima-pb"], {"falso": 1})
        self.assertEqual(soma["carla-souza-pc"], {"verdadeiro": 1})
        self.assertNotIn("mediacao", idx["placar"])
        h = idx["html"]
        self.assertLess(h.index("/debates/2030/governador-1-turno-fict/"), h.index("/debates/2026/presidente-2-turno-teste/"))
        self.assertNotRegex(h, PROIBIDAS)

    def test_link_do_rastro_so_no_bloco_de_quem_tem_pagina(self):
        gs = [dp.gerar(m, B.BASE, B.PESSOA) for m in dp.listar(REAL.parent.parent)]
        idx = dp.indice(gs, B.BASE, B.PESSOA, links={"280002542548": "/rastro/presidente/br/lula/"})
        blocos = re.findall(r'<div class="db-pc"[^>]*><h3>(.*?)</h3>', idx["html"])
        self.assertIn('<a href="/rastro/presidente/br/lula/">Lula (PT)</a>', blocos)
        self.assertIn("Flávio Bolsonaro (PL)", blocos)
        self.assertEqual(idx["html"].count("/rastro/"), 1)
        sem = dp.indice(gs, B.BASE, B.PESSOA)
        self.assertNotIn("/rastro/", sem["html"])


class PlacarPorCandidato(unittest.TestCase):
    def test_band_bate_com_checagens(self):
        pc = dp.placar_por_candidato(dp.listar(REAL.parent.parent))
        itens = {i["id"]: i for i in json_de(REAL, "afirmacoes.json") if i["autoria"] == "certa"}
        chs = [c for c in json_de(REAL, "checagens.json") if c["id"] in itens]
        quem = {c["id"]: c["id_tse"] for c in json_de(REAL, "debate.json")["candidatos"]}
        self.assertEqual(set(pc), {"280002542548", "280002551544"})  # mediação fora
        for q, sq in quem.items():
            direto = Counter(c["veredito"] for c in chs if itens[c["id"]]["quem"] == q)
            self.assertEqual(pc[sq]["conta"], dict(direto), q)
            (d,) = pc[sq]["debates"]
            self.assertEqual((d["rotulo"], d["path"]), ("Debate Band 2º turno 2026", "/debates/2026/presidente-2-turno-band/"))
            self.assertEqual(sorted(a["path"] for a in d["afirmacoes"]),
                             sorted(f"{d['path']}{c['id']}/" for c in chs if itens[c["id"]]["quem"] == q))

    def test_sem_id_tse_fica_de_fora(self):
        self.assertEqual(dp.placar_por_candidato(dp.listar(FIXTURE)), {})


class Publicar(unittest.TestCase):
    def test_segundo_debate_sem_codigo_novo(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = B.debates_publicar(tmp, raiz=FIXTURE)
            paths = [p for p, _, _ in out["sitemap"]]
            for g in [dp.gerar(m, B.BASE, B.PESSOA) for m in dp.listar(FIXTURE)]:
                for p in [g["path"], g["transcricao"]["path"]] + [a["path"] for a in g["afirmacoes"]]:
                    self.assertIn(p, paths)
                    h = (Path(tmp) / p.strip("/") / "index.html").read_text()
                    self.assertIn('<a href="/debates/" aria-current=page>Debates</a>', h)
                    self.assertIn(f'<link rel="canonical" href="{B.BASE}{p}">', h)
                for a in g["afirmacoes"]:
                    h = (Path(tmp) / a["path"].strip("/") / "index.html").read_text()
                    self.assertIn(f'<meta property="og:image" content="{B.BASE}/og/{a["og"][0]}.png">', h)
            self.assertIn("/debates/", paths)
            self.assertNotIn("/debates/2026/presidente-2-turno-teste/seg-02/", paths)
            self.assertFalse((Path(tmp) / "debates" / "2026" / "presidente-2-turno-teste" / "seg-02").exists())
            prio = {p: pr for p, _, pr in out["sitemap"]}
            self.assertEqual(prio["/debates/"], "0.8")
            self.assertEqual(prio["/debates/2026/presidente-2-turno-teste/"], "0.8")
            self.assertEqual(prio["/debates/2026/presidente-2-turno-teste/seg-01/"], "0.5")
            self.assertEqual(prio["/debates/2026/presidente-2-turno-teste/transcricao/"], "0.3")
            self.assertEqual((Path(tmp) / "debates" / "debate.js").read_bytes(), (R / "debates" / "debate.js").read_bytes())
            self.assertEqual(len(out["og"]), 2 + 6)
            self.assertIn(f"{B.BASE}/debates/", out["llms"])

    def test_build_sem_nome_de_debate(self):
        src = (R / "build_site.py").read_text()
        for nome in ("Band", "band", "Flávio Bolsonaro", "presidente-2-turno"):
            self.assertNotIn(nome, src[src.index("# ---------------- checagem de debates"):src.index("IDX_CSS")], nome)

    def test_sem_debate_nao_publica(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(B.debates_publicar(tmp, raiz=Path(tmp) / "nada"))


@unittest.skipUnless((R / "site" / "debates" / "index.html").exists(), "rode python3 build_site.py antes")
class Saida(unittest.TestCase):
    def test_uma_pasta_por_checagem_e_sitemap(self):
        sitemap = (R / "site" / "sitemap.xml").read_text()
        for m in dp.listar(R / "debates"):
            for c in m["checagens"]:
                p = m["path"] + c["id"] + "/"
                self.assertTrue((R / "site" / p.strip("/") / "index.html").exists(), p)
                self.assertIn(f"<loc>{B.BASE}{p}</loc>", sitemap)
                self.assertTrue((R / "site" / "og" / f"debate-{m['debate']['ano']}-{m['debate']['slug']}-{c['id']}.png").exists())
        self.assertEqual((R / "site" / "debates" / "debate.js").read_bytes(), (R / "debates" / "debate.js").read_bytes())


if __name__ == "__main__":
    unittest.main()
