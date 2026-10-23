"""Seção /debates/ (debates/pagina.py + build_site.debates_publicar): debate, afirmação, transcrição e índice."""
import html, json, re, shutil, sys, tempfile, unittest
from collections import Counter
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B
from debates import pagina as dp
from debates import validar as V
import navegacao as NAV

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


class Selo(unittest.TestCase):
    """issue 150: selo de veredito com ícone + texto, em tons fora da paleta de partido."""
    PARTIDO = re.compile(r"var\(--(flavio|lula|live|outros|[br][1-4])\)")

    def test_icone_e_texto_por_veredito(self):
        icones = set()
        for v in V.VEREDITO:
            s = dp.selo(v)
            m = re.fullmatch(rf'<span class="db-selo db-selo-{v}"><i aria-hidden="true">(.+?)</i> (.+)</span>', s)
            self.assertIsNotNone(m, s)
            self.assertEqual(m.group(2), dp.ROTULOS[v])  # o texto continua: o ícone não é a única pista
            icones.add(m.group(1))
        self.assertEqual(len(icones), len(V.VEREDITO))

    def test_tons_fora_da_paleta_de_partido(self):
        for v in V.VEREDITO:
            regra = re.search(rf"\.db-selo-{v}\{{([^}}]*)\}}", dp.CSS_SELO)
            self.assertIsNotNone(regra, v)
            self.assertNotRegex(regra.group(1), self.PARTIDO, v)
        self.assertNotRegex(dp.CSS_SELO, self.PARTIDO)
        self.assertIn(dp.CSS_SELO, dp.CSS)

    def test_cartao_usa_o_selo(self):
        g = gerar()
        for a in g["afirmacoes"]:
            v = next(k for k, r in dp.ROTULOS.items() if a["desc"].startswith(f"Veredito: {r}."))
            self.assertIn(dp.selo(v), a["html"])


class OrdemCandidatos(unittest.TestCase):
    """issue 150: a mesma ordem em todo o site, pela votação do 1º turno (Flávio 47,0%, Lula 45,2%)."""

    def test_ordem_do_1o_turno(self):
        cands = [{"partido": "PT", "n": "Lula"}, {"partido": None, "n": "Mediação"}, {"partido": "PL", "n": "Flávio"}]
        self.assertEqual([c["n"] for c in NAV.ordem_candidatos(cands)], ["Flávio", "Lula", "Mediação"])

    def test_debate_real_segue_a_ordem(self):
        deb = json_de(REAL, "debate.json")
        partidos = [c["partido"] for c in deb["candidatos"] if c.get("partido")]
        self.assertEqual(partidos, [c["partido"] for c in NAV.ordem_candidatos(deb["candidatos"]) if c.get("partido")])

    def test_indice_segue_a_ordem_mesmo_com_debate_invertido(self):
        g = dp.gerar(dp.carregar(REAL), B.BASE, B.PESSOA)
        g["placar"] = dict(reversed(list(g["placar"].items())))  # Lula antes, como no Rastro antigo
        idx = dp.indice([g], B.BASE, B.PESSOA)["html"]
        self.assertLess(idx.index("Flávio Bolsonaro (PL)"), idx.index("Lula (PT)"))


class Carregar(unittest.TestCase):
    def test_incerta_fica_de_fora(self):
        m = dp.carregar(TESTE)
        self.assertNotIn("seg-02", m["itens"])
        self.assertNotIn("seg-02", [c["id"] for c in m["checagens"]])
        self.assertEqual(len(m["checagens"]), 3)  # 4 certas, menos a da mediação, que não se publica

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
        tipo = {i["id"]: i["tipo"] for i in json_de(pasta, "afirmacoes.json")}
        esperado = Counter((quem[c["id"]], dp.GRUPO_DO_TIPO[tipo[c["id"]]], c["veredito"])
                           for c in json_de(pasta, "checagens.json") if c["id"] in quem)
        conta = dp.placar(m)
        self.assertEqual(sum(dp.total(c) for c in conta.values()), len(m["checagens"]))
        for q, gs in conta.items():
            self.assertEqual(list(gs), [g for g in dp.GRUPOS if g in gs], "mesma ordem de GRUPOS")
            for g, c in gs.items():
                self.assertEqual(list(c), [v for v in dp.ORDEM_VEREDITOS if v in c], "mesma ordem de validar.VEREDITO")
                for v, n in c.items():
                    self.assertEqual(n, esperado[(q, g, v)], (q, g, v))
        h = gerar(pasta)["html"]
        sec = re.search(r'<section aria-labelledby="placar">.*?</section>', h).group(0)
        for q, gs in conta.items():
            self.assertIn(f"<li><span>Total</span><span>{dp.total(gs)}</span></li>", sec)
            for g, c in gs.items():
                n_g = sum(c.values())
                if n_g:
                    self.assertIn(f"<h4><span>{html.escape(dp.GRUPOS[g][0], quote=False)}</span><span>{n_g}</span></h4>", sec)
                for v, n in c.items():
                    if n_g:  # o percentual é dentro do grupo
                        self.assertIn(f"<li><span>{html.escape(dp.ROTULOS[v], quote=False)}</span><span>{n} ({round(100 * n / n_g)}%)</span></li>", sec)
        self.assertNotRegex(sec, PROIBIDAS)

    def test_fixture(self):
        self.checar(TESTE)
        conta = dp.placar(dp.carregar(TESTE))
        self.assertNotIn("mediacao", conta)  # mediação fora da checagem publicada (21/10/2026)
        self.assertEqual({v for gs in conta.values() for c in gs.values() for v in c} - set(dp.ROTULOS), set())

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

    def test_transcricao_sem_anotacoes_internas(self):
        proibidos = ("Campo | Valor", "[NÃO VERIFICADO]", "[INFERIDO", "colada pelo", "Fidelidade")
        for pasta in (TESTE, FICT) + ((REAL,) if (REAL / "checagens.json").exists() else ()):
            m = dp.carregar(pasta)
            h = dp.gerar(m, B.BASE, B.PESSOA)["transcricao"]["html"]
            for s in proibidos:
                self.assertNotIn(s, h, f"{pasta.name}: {s}")
        md = ("# Debate\n\n| Campo | Valor |\n|---|---|\n| Fidelidade | [INFERIDO] colada pelo Vitor |\n\n"
              "> [NÃO VERIFICADO] mediador\n\n## Índice\n\n- [Abertura](#abertura)\n\n---\n\n"
              "## Abertura\n\n**0:08** — fala\n")
        h = dp._transcricao_html(md)
        for s in proibidos + ("Índice",):
            self.assertNotIn(s, h)
        self.assertEqual(re.findall(r"<h2>(.*?)</h2>", h), ["Abertura"])
        self.assertIn('<p id="t-0-00-08"><b>0:08</b> fala</p>', h)

    def test_transcricao_linha_publica(self):
        m = dp.carregar(TESTE)
        t = dp.gerar(m, B.BASE, B.PESSOA)["transcricao"]["html"]
        linha = re.search(r'<p class="db-tr-fonte">(.*?)</p>', t).group(1)
        self.assertIn(html.escape(m["debate"]["emissora"]), linha)
        self.assertIn(dp.data_br(m["debate"]["data"]), linha)
        self.assertRegex(linha, r"duração ~\d+h\d{2}")
        self.assertIn("transcrição sem edição", linha)  # fonte colada
        self.assertNotIn("youtube.com", t)
        m["debate"]["video"] = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        linha = re.search(r'<p class="db-tr-fonte">(.*?)</p>',
                          dp.gerar(m, B.BASE, B.PESSOA)["transcricao"]["html"]).group(1)
        self.assertIn('<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"', linha)
        m["debate"]["fonte_transcricao"] = "youtube-auto"
        self.assertIn("transcrição automática, sem edição",
                      dp.gerar(m, B.BASE, B.PESSOA)["transcricao"]["html"])

    def test_retorica_percentual_na_frente(self):
        """quem fala mais frases tem contagem maior em tudo: o destaque é o percentual, e a nota dá o total de cada um"""
        m = dp.carregar(TESTE)
        h = dp.gerar(m, B.BASE, B.PESSOA)["html"]
        conta = dp.placar_retorica(m)
        self.assertIn("compare pelo percentual", h)
        for q, c in conta.items():
            self.assertIn(f'{html.escape(dp._nome(m["cands"][q]))}, {sum(c.values())}', h)
        self.assertRegex(h, r'<b>\d+%</b> <small>\d+</small>')

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
        # vídeo e fontes saem do site: abrem em aba nova; a transcrição é do site e abre na mesma
        externos = re.findall(r'<a href="https://[^"]*"[^>]*>', h)
        self.assertTrue(externos)
        for tag in externos:
            self.assertIn('target="_blank" rel="noopener"', tag)
        self.assertNotRegex(h, r'<a href="[^"]*transcricao/#[^"]*" target=')


class PaginaAfirmacao(unittest.TestCase):
    def test_uma_por_checagem_com_og_propria(self):
        g = gerar()
        self.assertEqual([a["path"] for a in g["afirmacoes"]],
                         [f"{g['path']}{i}/" for i in ("seg-01", "eco-01", "soc-01")])  # eco-02 é da mediação: não se publica
        ogs = [a["og"][0] for a in g["afirmacoes"]]
        self.assertEqual(len(set(ogs)), len(ogs))
        self.assertEqual(ogs[0], "debate-2026-presidente-2-turno-teste-seg-01")
        for a in g["afirmacoes"]:
            crs = [x for x in a["ld"] if x["@type"] == "ClaimReview"]
            self.assertEqual(len(crs), 1)
            self.assertEqual(crs[0]["url"], B.BASE + a["path"])
            self.assertIn('href="/debates/"', a["html"])
            self.assertIn(f'href="{g["path"]}#', a["html"])

    def test_titulo_sem_aspas_e_trilha_sem_id(self):
        m = dp.carregar(TESTE)
        g = dp.gerar(m, B.BASE, B.PESSOA)
        for a in g["afirmacoes"]:
            ident = a["path"].rstrip("/").rsplit("/", 1)[1]
            item = m["itens"][ident]
            prefixo = f"Afirmação de {dp._nome(g['cands'][item['quem']])}: "
            self.assertTrue(a["titulo"].startswith(prefixo), a["titulo"])
            for aspa in "“”\"":
                self.assertNotIn(aspa, a["titulo"])
            h1 = re.search(r"<h1>(.*?)</h1>", a["html"]).group(1)
            self.assertTrue(h1.startswith(prefixo), h1)
            for aspa in ("“", "”", "&quot;"):
                self.assertNotIn(aspa, h1)
            self.assertIn(item["afirmacao"][:30], h1)
            titulo_html = re.search(r"<title>(.*?)</title>", a["html"]).group(1)
            self.assertNotIn("“", titulo_html)
            self.assertNotIn("”", titulo_html)
            self.assertIn("<blockquote", a["html"])
            self.assertIn(f"“{html.escape(item['trecho'], quote=False)}”", a["html"])
            nav = re.search(r'<nav class="crumbs".*?</nav>', a["html"], re.S).group(0)
            self.assertNotIn(ident, nav)
            self.assertIn(dp.TEMAS[item["tema"]], nav)
            bc = [x for x in a["ld"] if x["@type"] == "BreadcrumbList"][0]
            self.assertNotIn(ident, [i["name"] for i in bc["itemListElement"]])

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
        soma = {q: Counter({v: n for c in gs.values() for v, n in c.items() if n}) for q, gs in idx["placar"].items()}
        self.assertEqual(soma["ana-silva-pa"], {"verdadeiro": 1, "falso-ou-exagerado": 1, "pendente-ou-condicionado": 1})  # está nos dois debates
        self.assertEqual(soma["bruno-lima-pb"], {"falso-ou-exagerado": 1})
        self.assertEqual(soma["carla-souza-pc"], {"verdadeiro": 1})
        self.assertNotIn("verdadeiro", idx["placar"]["ana-silva-pa"].get("promessas", {}))  # promessa não vira verdadeiro
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
            direto = {}
            for c in chs:
                if itens[c["id"]]["quem"] == q:
                    g = direto.setdefault(dp.GRUPO_DO_TIPO[itens[c["id"]]["tipo"]], Counter())
                    g[c["veredito"]] += 1
            self.assertEqual(pc[sq]["conta"], {g: dict(c) for g, c in direto.items()}, q)
            (d,) = pc[sq]["debates"]
            self.assertEqual((d["rotulo"], d["path"]), ("Debate Band 2º turno 2026", "/debates/2026/presidente-2-turno-band/"))
            self.assertEqual(sorted(a["path"] for a in d["afirmacoes"]),
                             sorted(f"{d['path']}{c['id']}/" for c in chs if itens[c["id"]]["quem"] == q))

    def test_sem_id_tse_fica_de_fora(self):
        self.assertEqual(dp.placar_por_candidato(dp.listar(FIXTURE)), {})


class TambemDito(unittest.TestCase):
    """A mesma tese (mesmo quem) em outro debate publicado liga as duas afirmações, nos dois sentidos."""
    PT = "/debates/2026/presidente-2-turno-teste/"
    PF = "/debates/2030/governador-1-turno-fict/"

    def montar(self, tmp):
        """TESTE e FICT copiados para tmp: seg-01 (ana) com a mesma tese nos dois; eco-01 com a mesma tese, mas
        dita por bruno num e por carla no outro."""
        for src in (TESTE, FICT):
            shutil.copytree(src, Path(tmp) / src.parent.name / src.name)
        d = Path(tmp) / "2030" / "governador-1-turno-fict"
        its = json_de(d, "afirmacoes.json")
        for it in its:
            it["tese"] = {"seg-01": "roubos-caem-metade", "eco-01": "minimo-sobe-5"}.get(it["id"], it["tese"])
        (d / "afirmacoes.json").write_text(json.dumps(its, ensure_ascii=False), encoding="utf-8")
        return dp.listar(tmp)

    def test_liga_nos_dois_sentidos_e_so_mesmo_quem(self):
        with tempfile.TemporaryDirectory() as tmp:
            lig = dp.tambem(self.montar(tmp))
        self.assertEqual(lig[(self.PT, "seg-01")], [(self.PF + "seg-01/", "Fict", "Debate Fict 1º turno 2030")])
        self.assertEqual(lig[(self.PF, "seg-01")], [(self.PT + "seg-01/", "Teste", "Debate Teste 2º turno 2026")])
        self.assertNotIn((self.PT, "eco-01"), lig)
        self.assertNotIn((self.PF, "eco-01"), lig)

    def test_fixtures_versionadas_nao_ligam(self):
        self.assertEqual(dp.tambem(dp.listar(FIXTURE)), {})

    def test_html_bloco_e_selo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ms = self.montar(tmp)
        lig = dp.tambem(ms)
        for m in ms:
            outro = self.PT if m["path"] == self.PF else self.PF
            emissora = "Teste" if m["path"] == self.PF else "Fict"
            g = dp.gerar(m, B.BASE, B.PESSOA, tambem=lig)
            af = {a["path"]: a["html"] for a in g["afirmacoes"]}
            h = af[m["path"] + "seg-01/"]
            self.assertIn('<h2 id="tambem">Também dito em</h2>', h)
            self.assertIn(f'href="{outro}seg-01/"', h)
            self.assertNotIn("Também dito em", af[m["path"] + "eco-01/"])
            cartoes = {x.group(1): x.group(0) for x in re.finditer(r'<article class="db-af" id="([^"]+)".*?</article>', g["html"], re.S)}
            self.assertIn(f'<span class="db-tambem">dito também em {emissora}</span>', cartoes["seg-01"])
            self.assertNotIn("db-tambem", cartoes["eco-01"])

    def test_selo_escapa_emissora_e_nao_repete(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.montar(tmp)[1]
        lig = {(m["path"], "seg-01"): [("/a/", "A&B", "Debate A&B 1º turno"), ("/b/", "A&B", "Debate A&B 2º turno")]}
        g = dp.gerar(m, B.BASE, B.PESSOA, tambem=lig)
        self.assertIn('<span class="db-tambem">dito também em A&amp;B</span>', g["html"])
        h = next(a["html"] for a in g["afirmacoes"] if a["path"].endswith("/seg-01/"))
        self.assertIn('<a href="/a/">Debate A&amp;B 1º turno</a>', h)
        self.assertIn('<a href="/b/">Debate A&amp;B 2º turno</a>', h)

    def test_sem_ligacao_html_igual(self):
        for m in dp.listar(FIXTURE):
            a, b = dp.gerar(m, B.BASE, B.PESSOA), dp.gerar(m, B.BASE, B.PESSOA, tambem={})
            self.assertEqual(a["html"], b["html"])
            self.assertEqual([x["html"] for x in a["afirmacoes"]], [x["html"] for x in b["afirmacoes"]])
            self.assertNotIn("Também dito em", a["html"] + "".join(x["html"] for x in a["afirmacoes"]))

    def test_build_liga(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.montar(tmp)
            B.debates.cache_clear()
            try:
                gs = B.debates(Path(tmp))
            finally:
                B.debates.cache_clear()
        h = next(a["html"] for g in gs for a in g["afirmacoes"] if a["path"] == self.PT + "seg-01/")
        self.assertIn(f'href="{self.PF}seg-01/"', h)


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
            self.assertEqual(len(out["og"]), 2 + 5)  # a checagem da mediação (eco-02) não gera página nem card
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
        # o site/ commitado pode estar atrás do lote: publica em tmp e compara o JS
        with tempfile.TemporaryDirectory() as tmp:
            B.debates_publicar(tmp)
            self.assertEqual((Path(tmp) / "debates" / "debate.js").read_bytes(),
                             (R / "debates" / "debate.js").read_bytes())


if __name__ == "__main__":
    unittest.main()


class Hierarquia(unittest.TestCase):
    """#144: afirmações antes da retórica, índice de temas, lista de frases recolhida, voltar ao topo."""

    def pastas(self):
        return [p for p in (TESTE, FICT, REAL) if p.exists() and (p / "checagens.json").exists()]

    def test_ordem_das_secoes(self):
        for p in self.pastas():
            with self.subTest(p.name):
                h = gerar(p)["html"]
                pos = [h.index('aria-labelledby="placar"'), h.index('aria-labelledby="afirmacoes"'),
                       h.index('class="db-tema"')]
                if 'aria-labelledby="retorica"' in h:
                    pos.append(h.index('aria-labelledby="retorica"'))
                    self.assertLess(h.rindex('<article class="db-af"'), pos[-1])
                pos.append(h.index('id="metodo"'))
                self.assertEqual(pos, sorted(pos))

    def test_indice_de_temas_com_ancoras_validas(self):
        for p in self.pastas():
            with self.subTest(p.name):
                h = gerar(p)["html"]
                nav = re.search(r'<nav class="db-temas"[^>]*>.*?</nav>', h, re.S)
                self.assertTrue(nav)
                self.assertLess(nav.start(), h.index('class="db-tema"'))
                hrefs = re.findall(r'href="#([^"]+)"', nav.group(0))
                self.assertEqual(hrefs, re.findall(r'<section class="db-tema" id="([^"]+)">', h))
                for href in hrefs:
                    sec = re.search(rf'<section class="db-tema" id="{href}">.*?</section>', h, re.S).group(0)
                    n = len(re.findall(r'<article class="db-af"', sec))
                    self.assertRegex(nav.group(0), rf'href="#{href}">[^<]*<span>{n}</span>')

    def test_retorica_placar_visivel_lista_recolhida(self):
        m = dp.carregar(TESTE)
        h = gerar(TESTE)["html"]
        n = len(m["retorica"])
        det = re.search(r'<details class="db-rt-lista"><summary>Ver as %d frases</summary>(.*?)</details>' % n, h, re.S)
        self.assertTrue(det)
        self.assertEqual(det.group(1).count('<li id="r-'), n)
        self.assertEqual(h.count('<li id="r-'), n)
        self.assertIn('db-rt-filtro', det.group(1))
        self.assertEqual(h.count('<form class="db-rt-filtro"'), 1)
        self.assertNotIn('<div class="db-placar"', det.group(0))
        self.assertIn('<div class="db-placar"', h)

    def test_voltar_ao_topo(self):
        for p in self.pastas():
            with self.subTest(p.name):
                h = gerar(p)["html"]
                self.assertIn('<main id="conteudo"', h)
                self.assertRegex(h, r'<a class="db-topo" href="#conteudo">[^<]*Voltar ao topo</a></main>')

    def test_sem_nome_de_debate_no_codigo(self):
        for f in ("pagina.py", "debate.js"):
            src = (R / "debates" / f).read_text(encoding="utf-8")
            for nome in ("Band", "Globo", "Flávio", "Lula", "presidente-2-turno"):
                self.assertNotIn(nome, src, f"{f}: {nome}")
