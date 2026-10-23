"""Página "Minha seção" (/minha-secao/, issue #155): índices do build, piso de privacidade, página sem dados,
lista de seções e nenhuma requisição para outro domínio. Dados: os de montar_secao.py a partir das fixtures da #154."""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

import build_site as B
import navegacao as NAV
from municipios import minha_secao as msec
from municipios import montar_secao as ms
from tests.test_secao import FX, zipar

R = Path(__file__).resolve().parent.parent
META = {"mun": {"1200401": ["Rio Branco", "AC"], "3550308": ["São Paulo", "SP"]},
        "cand": {"presidente": [{"n": "22", "nome": "X", "sg": "PL"}, {"n": "13", "nome": "Y", "sg": "PT"}]}}
PUB, MOD = "2026-10-04T18:25:00-03:00", "2026-10-05T12:51:00-03:00"


def montar_locais(td, por_uf=False, turnos=("votacao_t1.csv", "votacao_t2.csv")):
    """municipios/geo/locais/ da fixture da #154, em td/geo/locais/"""
    br = Path(td) / "brutos"
    br.mkdir(exist_ok=True)
    zipar(br / ms.ZIP_SECAO, {f"votacao_secao_2026_T{i}.csv": fx for i, fx in enumerate(turnos, 1)})
    zipar(br / ms.ZIP_LOCAIS, {"eleitorado_local_votacao_2026.csv": "locais.csv"})
    shutil.copy(FX / "mun-config.json", br / ms.CFG)
    with redirect_stdout(io.StringIO()):
        ms.montar(br, Path(td) / "geo", por_uf=por_uf)
    return Path(td) / "geo" / "locais"


class Base(unittest.TestCase):
    por_uf = False

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.locais = montar_locais(self.td, self.por_uf)


class TestCarregar(Base):
    def test_um_arquivo_por_municipio(self):
        dados = msec.carregar(self.locais)
        self.assertEqual(sorted(dados), ["1200401", "3550308"])
        self.assertEqual(dados["1200401"]["arq"], "1200401")
        self.assertEqual(sorted(dados["3550308"]["t"]), ["1", "2"])

    def test_sem_pasta_ou_vazia_nao_tem_dados(self):
        self.assertEqual(msec.carregar(self.td / "nada"), {})
        (self.td / "vazia").mkdir()
        self.assertEqual(msec.carregar(self.td / "vazia"), {})
        self.assertFalse(msec.tem_dados(self.td / "nada"))
        self.assertFalse(msec.tem_dados(self.td / "vazia"))
        self.assertTrue(msec.tem_dados(self.locais))


class TestCarregarPorUF(Base):
    por_uf = True

    def test_arquivo_por_uf(self):
        dados = msec.carregar(self.locais)
        self.assertEqual(sorted(dados), ["1200401", "3550308"])
        self.assertEqual((dados["1200401"]["arq"], dados["3550308"]["arq"]), ("AC", "SP"))


class TestPiso(Base):
    def test_fixture_respeita_o_piso(self):
        msec.conferir_piso(msec.carregar(self.locais))

    def test_secao_abaixo_do_piso_com_voto_barra_o_build(self):
        dados = msec.carregar(self.locais)
        s = next(s for lc in dados["1200401"]["t"]["1"] for s in lc[9] if s[3] < ms.PISO)
        s[4], s[5] = [5, 7], 0
        with self.assertRaises(ValueError) as cm:
            msec.conferir_piso(dados)
        self.assertIn("1200401", str(cm.exception))

    def test_local_abaixo_do_piso_com_voto_barra_o_build(self):
        dados = msec.carregar(self.locais)
        lc = next(lc for lc in dados["1200401"]["t"]["1"] if lc[6] < ms.PISO)
        lc[7], lc[8] = [10, 8], 0
        with self.assertRaises(ValueError):
            msec.conferir_piso(dados)

    def test_gerar_nao_publica_dados_que_furam_o_piso(self):
        p = self.locais / "1200401.json"
        reg = json.loads(p.read_text(encoding="utf-8"))
        lc = next(lc for lc in reg["t"]["1"] if lc[6] < ms.PISO)
        lc[7] = [10, 8]
        p.write_text(json.dumps(reg), encoding="utf-8")
        with self.assertRaises(ValueError):
            msec.gerar(self.td / "site", self.locais, META)
        self.assertFalse((self.td / "site" / "minha-secao" / "indice.json").exists())


class TestIndice(Base):
    def test_municipios_com_nome_uf_arquivo_e_centro(self):
        idx = msec.indice(msec.carregar(self.locais), META)
        mun = {m[0]: m for m in idx["mun"]}
        self.assertEqual(sorted(mun), ["1200401", "3550308"])
        rb = mun["1200401"]
        self.assertEqual(rb[1:4], ["Rio Branco", "AC", "1200401"])
        # centro = média dos locais com coordenada; COLÉGIO PEQUENO não tem
        self.assertIsNotNone(rb[4])
        self.assertIsNotNone(rb[5])
        # São Paulo da fixture: nenhum local com coordenada
        self.assertEqual(mun["3550308"][4:], [None, None])
        self.assertEqual(idx["part"], {"22": "PL", "13": "PT"})
        self.assertEqual(idx["piso"], ms.PISO)

    def test_ordenado_por_uf_e_nome(self):
        meta = {"mun": {"1200401": ["Rio Branco", "AC"], "3550308": ["Abaeté", "AC"]}, "cand": {}}
        idx = msec.indice(msec.carregar(self.locais), meta)
        self.assertEqual([m[1] for m in idx["mun"]], ["Abaeté", "Rio Branco"])

    def test_municipio_fora_do_meta_usa_o_codigo(self):
        idx = msec.indice(msec.carregar(self.locais), {"mun": {}, "cand": {}})
        self.assertEqual({m[0]: m[1] for m in idx["mun"]}["1200401"], "1200401")


class TestIndiceCep(Base):
    def test_cep5_aponta_os_municipios_em_fatias_de_dois_digitos(self):
        cep = msec.indice_cep(msec.carregar(self.locais))
        self.assertEqual(sorted(cep), ["01", "69"])
        self.assertEqual(cep["69"], {"69900": ["1200401"]})
        self.assertEqual(cep["01"], {"01001": ["3550308"]})

    def test_mesmo_cep_em_dois_municipios(self):
        dados = msec.carregar(self.locais)
        dados["3550308"]["t"]["1"][0][4] = "69900"
        self.assertEqual(msec.indice_cep(dados)["69"], {"69900": ["1200401", "3550308"]})

    def test_local_sem_cep_fica_fora(self):
        dados = msec.carregar(self.locais)
        for lc in dados["3550308"]["t"]["1"] + dados["3550308"]["t"]["2"]:
            lc[4] = None
        self.assertNotIn("01", msec.indice_cep(dados))


class TestGerar(Base):
    def test_com_dados_escreve_indice_cep_e_js(self):
        out = self.td / "site"
        p = msec.gerar(out, self.locais, META)
        self.assertTrue(p["tem"])
        d = out / "minha-secao"
        self.assertEqual(json.loads((d / "indice.json").read_text(encoding="utf-8")), msec.indice(msec.carregar(self.locais), META))
        self.assertEqual(json.loads((d / "cep" / "69.json").read_text(encoding="utf-8")), {"69900": ["1200401"]})
        self.assertEqual((d / "secao.js").read_text(encoding="utf-8"), msec.JS.read_text(encoding="utf-8"))
        self.assertIn('id="ms-app"', p["html"])
        self.assertIn("/minha-secao/secao.js", p["html"])

    def test_sem_dados_em_breve_sem_js_nem_indice(self):
        out = self.td / "site"
        p = msec.gerar(out, self.td / "nada", META)
        self.assertFalse(p["tem"])
        self.assertIn("Em breve", p["html"])
        self.assertNotIn("<script", p["html"])
        self.assertFalse((out / "minha-secao" / "indice.json").exists())

    def test_aviso_fonte_e_privacidade_nos_dois_casos(self):
        for pasta in (self.locais, self.td / "nada"):
            h = msec.gerar(self.td / "site", pasta, META)["html"]
            self.assertIn("Local de votação não é onde a pessoa mora", h)
            self.assertIn('href="https://dadosabertos.tse.jus.br/"', h)
        h = msec.gerar(self.td / "site", self.locais, META)["html"]
        self.assertIn("nunca sai do seu aparelho", h)
        self.assertIn("visível ao servidor", h)


class Requisicoes(HTMLParser):
    """URLs que o navegador busca sozinho ao abrir a página (não conta <a href>, canonical nem og:*)."""
    BUSCA = {"stylesheet", "preload", "modulepreload", "prefetch", "preconnect", "dns-prefetch", "icon", "apple-touch-icon", "manifest"}

    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "img", "iframe", "source", "audio", "video", "embed", "track") and a.get("src"):
            self.urls.append(a["src"])
        if tag == "link" and self.BUSCA & set((a.get("rel") or "").split()):
            self.urls.append(a["href"])
        if tag == "form" and a.get("action"):
            self.urls.append(a["action"])
        if tag == "object" and a.get("data"):
            self.urls.append(a["data"])


def mesmo_dominio(u):
    return u.startswith("/") and not u.startswith("//")


class TestSemRequisicaoExterna(Base):
    def setUp(self):
        super().setUp()
        self.out = self.td / "site"
        with mock.patch.object(B, "LOCAIS", self.locais):
            self.sitemap = B.minha_secao_publicar(self.out, PUB, MOD, meta=META)
        self.html = (self.out / "minha-secao" / "index.html").read_text(encoding="utf-8")
        self.js = (self.out / "minha-secao" / "secao.js").read_text(encoding="utf-8")

    def test_html_so_busca_no_proprio_dominio(self):
        p = Requisicoes()
        p.feed(self.html)
        self.assertIn("/minha-secao/secao.js", p.urls)
        for u in p.urls:
            self.assertTrue(mesmo_dominio(u), u)
        for css in re.findall(r"url\(([^)]*)\)", self.html):
            self.assertTrue(mesmo_dominio(css.strip("'\"")), css)

    def test_sem_contador_de_presenca_nem_medicao(self):
        # o contador "pessoas agora" abre WebSocket no Supabase e a medição carrega GA/Clarity: nenhum dos dois aqui
        self.assertNotIn("topo-pessoas.js", self.html)
        self.assertNotIn("supabase", self.html.lower())
        self.assertNotIn("medicao.js", self.html)

    def test_js_sem_url_absoluta_nem_canal_externo(self):
        self.assertNotRegex(self.js, r"https?:|//[a-z0-9-]+\.[a-z]")
        for proibido in ("WebSocket", "EventSource", "sendBeacon", "XMLHttpRequest", "import(", "importScripts", "new Image", "src="):
            self.assertNotIn(proibido, self.js)
        # um único fetch, dentro de ler(); toda chamada de ler() começa com um caminho do próprio site
        self.assertEqual(len(re.findall(r"\bfetch\(", self.js)), 1)
        chamadas = re.findall(r"\bler\(([^)]*)\)", self.js)
        self.assertTrue(chamadas)
        for alvo in chamadas:
            if alvo == "caminho":  # a própria definição
                continue
            self.assertRegex(alvo.strip(), r'^"/(geo/locais|minha-secao)/', alvo)

    def test_posicao_nao_sai_do_aparelho(self):
        # a posição só serve para calcular distância: nunca vai para URL, storage ou rede
        self.assertIn("getCurrentPosition", self.js)
        for proibido in ("localStorage", "sessionStorage", "document.cookie", "history.", "location.hash", "location.search", "location.href"):
            self.assertNotIn(proibido, self.js)

    def test_sitemap_e_indexa(self):
        self.assertEqual([p for p, _, _ in self.sitemap], ["/minha-secao/"])
        self.assertIn('<meta name="robots" content="index,follow', self.html)


class TestSecoes(unittest.TestCase):
    def test_sem_dados_fica_fora_do_menu_e_sai_em_breve_noindex(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(B, "LOCAIS", Path(td) / "nada"):
                self.assertNotIn("/minha-secao/", [u for u, _ in B.secoes()])
                sm = B.minha_secao_publicar(Path(td) / "site", PUB, MOD, meta=META)
            h = (Path(td) / "site" / "minha-secao" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(sm, [])
        self.assertIn("Em breve", h)
        self.assertIn('<meta name="robots" content="noindex,follow', h)
        self.assertNotIn('href="/minha-secao/"', h.split('id="conteudo"', 1)[0])

    def test_com_dados_entra_no_menu(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(B, "LOCAIS", montar_locais(td)):
                urls = [u for u, _ in B.secoes()]
                self.assertIn("/minha-secao/", urls)
                self.assertEqual(urls.index("/minha-secao/"), urls.index("/analise/") + 1)
                self.assertIn('<a href="/minha-secao/"', B.menu_secoes("/analise/"))
                self.assertEqual(dict(B.secoes())["/minha-secao/"], NAV.MINHA_SECAO)


class TestLayout(Base):
    def test_trilha_unica_e_largura_de_texto(self):
        for pasta in (self.locais, self.td / "nada"):
            h = msec.gerar(self.td / "site", pasta, META)["html"]
            self.assertIn(NAV.trilha((NAV.INICIO, "/"), (NAV.MINHA_SECAO, None)), h)
        self.assertIn("main.ms{max-width:var(--w-texto)", msec.CSS)
        self.assertNotRegex(msec.CSS, r"max-width:(1160|1120|880)px")


@unittest.skipUnless(shutil.which("deno"), "precisa de deno")
class TestBuscaJS(unittest.TestCase):
    """busca por zona e seção, por CEP e por proximidade: municipios/minha_secao_test.js (Deno) sobre a fixture"""

    def test_deno(self):
        with tempfile.TemporaryDirectory() as td:
            locais = montar_locais(td)
            env = {**os.environ, "LOCAIS": str(locais), "NO_COLOR": "1"}
            r = subprocess.run(["deno", "test", "--allow-read", "--allow-env=LOCAIS", str(R / "municipios" / "minha_secao_test.js")],
                               capture_output=True, text=True, timeout=180, env=env)
        saida = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, saida[-4000:])
        self.assertRegex(saida, r"ok \| \d+ passed")


if __name__ == "__main__":
    unittest.main()
