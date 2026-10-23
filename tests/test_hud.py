"""HUD da apuração (/ao-vivo/): regras de brand, cor de partido, scripts locais e cache na Vercel."""
import colorsys, hashlib, json, re, shutil, subprocess, sys, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B

TEMPLATE = R / "template_hud.html"
HUD = R / "hud"
PARTIDOS = HUD / "partidos.js"
HEX = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def matiz(h):
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    return colorsys.rgb_to_hsv(*(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0] * 360


class Template(unittest.TestCase):
    def test_um_marcador_da_brand(self):
        self.assertEqual(TEMPLATE.read_text().count("/*__BRAND__*/"), 1)

    def test_so_scripts_locais(self):
        h = TEMPLATE.read_text()
        srcs = re.findall(r"<script[^>]*\bsrc=\"([^\"]+)\"", h)
        self.assertTrue(srcs, "o template precisa carregar o app")
        for s in srcs:
            self.assertTrue(s.startswith("/"), s)
            self.assertNotIn("//", s)
        self.assertNotRegex(h, r"<script[^>]*src=\"https?://")
        for js in HUD.glob("*.js"):
            for imp in re.findall(r"\bfrom\s+\"([^\"]+)\"|import\(\s*\"([^\"]+)\"", js.read_text()):
                alvo = imp[0] or imp[1]
                self.assertTrue(alvo.startswith(("/", "./")), f"{js.name}: import externo {alvo}")
                self.assertNotIn("://", alvo, js.name)

    def test_vendor_presente_e_conferido(self):
        v = R / "assets" / "vendor" / "preact-htm.module.js"
        self.assertTrue(v.exists())
        leia = (R / "assets" / "vendor" / "README.md").read_text()
        self.assertIn(hashlib.sha256(v.read_bytes()).hexdigest(), leia, "SHA-256 do vendor diverge do README")
        self.assertIn("htm@3/preact/standalone.module.js", leia)
        for lic in ("LICENSE-htm.txt", "LICENSE-preact.txt"):
            self.assertTrue((R / "assets" / "vendor" / lic).exists(), lic)

    def test_template_antigo_arquivado(self):
        self.assertFalse((R / "template_aovivo.html").exists())
        self.assertTrue((R / "docs" / "old" / "template_aovivo.html").exists())


class CoresDePartido(unittest.TestCase):
    def test_hex_so_em_partidos_js(self):
        fontes = [TEMPLATE] + [p for p in HUD.glob("*.js") if p != PARTIDOS]
        for p in fontes:
            self.assertEqual(HEX.findall(p.read_text()), [], f"{p.name}: cor literal fora de hud/partidos.js")

    def test_partidos_longe_do_ciano(self):
        ciano = matiz("#24C8FF")
        cores = HEX.findall(PARTIDOS.read_text())
        self.assertGreater(len(cores), 15)
        for c in cores:
            d = abs(matiz(c) - ciano); d = min(d, 360 - d)
            self.assertGreaterEqual(d, 25, f"{c} está a {d:.1f}° do ciano da brand")

    def test_pl_e_pt_usam_tokens_da_brand(self):
        js = PARTIDOS.read_text()
        self.assertIn('PL: "--flavio"', js)
        self.assertIn('PT: "--lula"', js)
        self.assertIn("--outros", js)


GEO_T1 = R / "municipios" / "geo" / "t1"


@unittest.skipUnless((GEO_T1 / "governador.json").exists(), "municipios/geo ausente")
class ResultadoOficial(unittest.TestCase):
    """% do governador com o denominador do TSE (válidos + anulados sub judice) e situação oficial no status.json."""
    rel = json.loads((R / "relatorio" / "relatorio.json").read_text())

    def test_percentual_do_governador_bate_com_o_tse(self):
        meta = json.loads((GEO_T1 / "meta.json").read_text()); gov = json.loads((GEO_T1 / "governador.json").read_text())
        self.assertEqual(len(self.rel["gov"]), 27)
        for g in self.rel["gov"]:
            row = gov["uf"][g["uf"]]
            vv, votos, vansj = row[2], row[5], row[6]
            self.assertIn(g["a"]["votos"], votos, g["uf"])
            p = 100 * g["a"]["votos"] / (vv + vansj)  # mesma conta de hud/calc.js linha()
            self.assertAlmostEqual(p, g["a"]["p"], delta=0.005, msg=g["uf"])
        rj = gov["uf"]["RJ"]
        self.assertAlmostEqual(100 * 4271199 / (rj[2] + rj[6]), 49.27, delta=0.005)

    def test_percentual_igual_ao_pvap_do_tse_gov_e_senado(self):
        """a conta do HUD (votos / (validos + vansj)) reproduz o pvap publicado pelo TSE em cada arquivo de UF"""
        for cargo, c in (("governador", 3), ("senador", 5)):
            dados = json.loads((GEO_T1 / f"{cargo}.json").read_text())
            for uf, row in dados["uf"].items():
                bruto = json.loads((R / "relatorio" / "dados" / f"{uf.lower()}-c{c:04d}.json").read_text())
                for a in bruto["carg"][0]["agr"]:
                    for p in a["par"]:
                        for x in p["cand"]:
                            v = int(x["vap"])
                            if v < 1000: continue
                            hud = 100 * v / (row[2] + row[6])
                            self.assertAlmostEqual(hud, float(x["pvap"].replace(",", ".")), delta=0.005, msg=f"{cargo} {uf} {x['nmu']}")

    def test_calc_js_usa_validos_mais_vansj(self):
        js = (HUD / "calc.js").read_text()
        self.assertIn("const base = (vv + vansj)", js)
        self.assertNotRegex(js, r"p1\s*>\s*0\.5")  # eleito nunca sai de porcentagem

    def test_manchetes_nao_deduzem_eleito_de_porcentagem(self):
        for f in ("paineis.js", "app.js"):
            self.assertNotRegex((HUD / f).read_text(), r"(\.p1?|\.p)\s*>\s*0?\.5\b", f)

    def test_status_json_igual_ao_relatorio(self):
        st = B.status_hud()
        self.assertIsNotNone(st)
        oficial = {g["uf"]: g["status"] for g in self.rel["gov"]}
        self.assertEqual({u: v["status"] for u, v in st["governador"].items()}, oficial)
        self.assertEqual(len(st["governador"]), 27)
        self.assertEqual(st["governador"]["RJ"]["status"], "2turno")
        self.assertEqual(st["governador"]["DF"]["status"], "2turno")
        self.assertEqual(st["governador"]["PR"]["status"], "eleito")
        meta = json.loads((GEO_T1 / "meta.json").read_text())
        nome = lambda uf, n: next(c["nome"] for c in meta["cand"]["governador"][uf] if c["n"] == n)
        self.assertEqual(nome("RJ", st["governador"]["RJ"]["a"]), "Douglas Ruas")
        self.assertEqual(len(st["senador"]), 27)
        for uf, v in st["senador"].items():
            self.assertEqual(len(v["eleitos"]), 2, uf)
        self.assertEqual(st["presidente"]["BR"], {"status": "2turno", "a": "22", "b": "13"})


@unittest.skipUnless(shutil.which("node") and (GEO_T1 / "governador.json").exists(), "node ou municipios/geo ausente")
class CalcJS(unittest.TestCase):
    """Roda o hud/calc.js de verdade (node) com a linha real do RJ: % com sub judice e manchete pela situação oficial."""

    def test_rj_governador_no_js(self):
        js = f"""
import {{ readFileSync }} from "node:fs";
const {{ linha, oficial }} = await import({json.dumps((HUD / "calc.js").as_uri())});
const meta = JSON.parse(readFileSync({json.dumps(str(GEO_T1 / "meta.json"))}, "utf8"));
const gov = JSON.parse(readFileSync({json.dumps(str(GEO_T1 / "governador.json"))}, "utf8"));
const lista = meta.cand.governador.RJ;
const r = linha("governador", gov.uf.RJ, lista);
const g = r.cands.find((c) => c.sj);
const st = {{ governador: {{ RJ: {{ status: "2turno", a: r.cands[0].n, b: r.cands[1].n }} }} }};
const of = oficial(st, "governador", "RJ", lista);
console.log(JSON.stringify({{ a: r.cands[0].nome, pa: r.cands[0].p, pb: r.cands[1].p, sj: g && g.nome, psj: g && g.p, st: of.status, ofa: of.a.nome }}));
"""
        out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        d = json.loads(out.stdout)
        self.assertEqual(d["a"], "Douglas Ruas")
        self.assertAlmostEqual(d["pa"] * 100, 49.27, delta=0.005)
        self.assertAlmostEqual(d["pb"] * 100, 42.76, delta=0.005)
        self.assertEqual(d["sj"], "Garotinho")
        self.assertAlmostEqual(d["psj"] * 100, 3.17, delta=0.005)
        self.assertEqual((d["st"], d["ofa"]), ("2turno", "Douglas Ruas"))


class Build(unittest.TestCase):
    def test_cache_de_geo_e_hud(self):
        hs = {h["source"]: h["headers"] for h in B.VERCEL["headers"]}
        self.assertIn({"key": "Cache-Control", "value": "public, max-age=3600"}, hs["/geo/(.*)"])
        # módulos ES sem hash: revalidar sempre
        self.assertIn({"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}, hs["/hud/(.*)"])

    def test_vivo_e_tse_com_cache_de_cdn_no_rewrite_externo(self):
        """issue #133: a origem manda no-cache e a Vercel obedecia (x-vercel-cache: MISS em todo poll); o CDN-Cache-Control
        do vercel.json sobrepõe a origem. A raiz (deploy pelo git) tem que sair igual ao VERCEL."""
        hs = {h["source"]: h["headers"] for h in B.VERCEL["headers"]}
        for src, idade in (("/vivo/(.*)", 15), ("/tse/(.*)", 20)):
            self.assertIn({"key": "CDN-Cache-Control", "value": f"max-age={idade}"}, hs[src], src)
            self.assertIn({"key": "x-vercel-enable-rewrite-caching", "value": "1"}, hs[src], src)
        raiz = json.loads((Path(B.__file__).parent / "vercel.json").read_text())
        self.assertEqual(raiz, {"outputDirectory": "site", **B.VERCEL})

    def test_vivo_reescrito_para_o_storage_com_cache_curto(self):
        rw = {r["source"]: r["destination"] for r in B.VERCEL["rewrites"]}
        self.assertEqual(rw.get("/vivo/:path*"), "https://qzczyicspbizosjogmlq.supabase.co/storage/v1/object/public/vivo/:path*")
        hs = {h["source"]: h["headers"] for h in B.VERCEL["headers"]}
        self.assertIn({"key": "Cache-Control", "value": "public, s-maxage=15, stale-while-revalidate=30"}, hs.get("/vivo/(.*)", []))

    def test_hud_le_vivo_relativo_nunca_o_supabase(self):
        for js in HUD.glob("*.js"):
            self.assertNotIn("supabase.co", js.read_text(), js.name)
        self.assertIn('"/vivo/agora.json"', (HUD / "dados.js").read_text())

    def test_prerender_responde_404_no_vivo(self):
        import json, urllib.request, urllib.error, tempfile
        with tempfile.TemporaryDirectory() as d:
            srv = B.serve(Path(d), port=8797)
            try:
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen("http://127.0.0.1:8797/vivo/agora.json", timeout=5)
                self.assertEqual(e.exception.code, 404); e.exception.close()
            finally:
                srv.shutdown(); srv.server_close()

    def test_malha_leve_das_ufs_publicada(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            B.copiar_hud(Path(d))
            ufs = json.loads((Path(d) / "hud" / "ufs.json").read_text())
            self.assertEqual(len(ufs), 27)
            self.assertTrue((Path(d) / "vendor" / "preact-htm.module.js").exists())

    def test_resumo_para_buscadores(self):
        r = B.resumo_hud()
        self.assertIn("Mapa da apuração por município", r)
        self.assertIn("47,03%", r)
        self.assertIn("45,16%", r)
        self.assertNotIn("<h1", r)  # a página tem um único h1 (o do painel)
        self.assertIn("<table", r)
        self.assertIn("Flávio", r)

    def test_pagina_sem_moldura_nao_ganha_sitebar(self):
        raw = '<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>x</title></head><body><div id="hud"></div></body></html>'
        h = B.montar_pagina(raw, "t", "d", "/ao-vivo/", "/og/x.png", [], "a", "b", "/ao-vivo/", moldura=False)
        self.assertNotIn('class="sitebar"', h)
        self.assertIn('<link rel="canonical" href="https://eleicoes2026.vitorpereira.ia.br/ao-vivo/">', h)

    @unittest.skipUnless((R / "site" / "ao-vivo" / "index.html").exists(), "rode python3 build_site.py antes")
    def test_ao_vivo_publicado(self):
        h = (R / "site" / "ao-vivo" / "index.html").read_text()
        if 'src="/hud/app.js"' not in h:
            self.skipTest("site/ gerado antes do HUD: rode python3 build_site.py")
        self.assertIn("<title>Mapa da apuração por município", h)
        self.assertIn('src="/hud/app.js"', h)


if __name__ == "__main__":
    unittest.main()


class PessoasAgora(unittest.TestCase):
    """window.HUD_PRESENCE vem do build; a chave no repo é a publishable (pública), nunca service_role/secret."""

    def test_build_emite_hud_presence_antes_do_app(self):
        h = B.injetar_presenca(TEMPLATE.read_text())
        m = re.search(r"<script>window\.HUD_PRESENCE=(\{.*?\});</script>\n<script type=\"module\" src=\"/hud/app\.js\"></script>", h)
        self.assertIsNotNone(m, "HUD_PRESENCE precisa vir logo antes do app.js")
        cfg = json.loads(m.group(1))
        self.assertEqual(set(cfg), {"url", "key", "canal"})
        self.assertEqual(cfg["url"], "https://qzczyicspbizosjogmlq.supabase.co")
        self.assertEqual(cfg["canal"], "eleicoes-hud")
        self.assertEqual(cfg["key"], B.SUPABASE_PUBLISHABLE_KEY)

    def test_chave_e_publishable_nunca_secreta(self):
        k = B.SUPABASE_PUBLISHABLE_KEY
        self.assertTrue(k.startswith("sb_publishable_"), "só a publishable key pode ir para o repo/navegador")
        self.assertNotRegex(k, r"^sb_secret_|^eyJ")  # secret key nova ou JWT (anon/service_role legados)
        fontes = [R / "build_site.py", TEMPLATE, *HUD.glob("*.js"), *(R / "supabase").rglob("*.ts"), *(R / "supabase").rglob("*.md")]
        for p in fontes:
            t = p.read_text()
            self.assertNotRegex(t, r"sb_secret_[A-Za-z0-9_\-]{8,}", p.name)
            self.assertNotRegex(t, r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}", f"{p.name}: JWT no repo")

    def test_site_publicado_tem_a_config(self):
        pagina = R / "site" / "ao-vivo" / "index.html"
        if not pagina.exists():
            self.skipTest("site/ não gerado")
        h = pagina.read_text()
        self.assertIn("window.HUD_PRESENCE=", h)
        self.assertNotIn("pessoas agora</span>", h, "o pré-render (headless) não pode contar nem mostrar o contador")


class MenuSecoes(unittest.TestCase):
    """botão "☰ Seções" (issue 138): a lista de seções do site vem de uma fonte só (B.secoes()) e chega igual
    à sitebar, ao painel (window.HUD_SECOES) e à Análise (HTML estático)."""

    def test_secoes_e_a_lista_da_sitebar(self):
        nav = re.search(r'<nav class="top"[^>]*>(.*?)</nav>', B.sitebar("/")).group(1)
        hrefs = re.findall(r'<a href="([^"]+)"', nav)
        self.assertEqual(hrefs, [u for u, _ in B.secoes()])
        for u in ("/", "/ao-vivo/", "/analise/", "/rastro/", "/apuracao/"):
            self.assertIn(u, hrefs)

    def test_painel_recebe_hud_secoes_antes_do_app(self):
        h = B.injetar_presenca(TEMPLATE.read_text())
        m = re.search(r"<script>window\.HUD_SECOES=(\[.*?\]);</script>", h)
        self.assertIsNotNone(m, "HUD_SECOES precisa ser injetada pelo build")
        self.assertLess(h.index("window.HUD_SECOES="), h.index('<script type="module" src="/hud/app.js">'))
        self.assertEqual([tuple(x) for x in json.loads(m.group(1))], [tuple(x) for x in B.secoes()])
        self.assertIn(B.SECOES_CSS, h, "o estilo do menu também vem do build, uma fonte só")

    def test_painel_nao_escreve_secoes_a_mao(self):
        app = (HUD / "app.js").read_text()
        self.assertIn("HUD_SECOES", app)
        self.assertNotIn('href="/rastro/"', app)
        self.assertNotIn('href="/debates/"', app)

    def test_menu_some_na_tela_cheia(self):
        app = (HUD / "app.js").read_text()
        self.assertRegex(app, r"!cheia\s*&&\s*html`<\$\{Secoes\}")
