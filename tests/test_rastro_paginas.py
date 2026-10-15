import copy
import hashlib
import html
import json
import re
import tempfile
import unittest
from pathlib import Path

from rastro import indicadores as ind
from rastro import paginas as pg
from rastro.rotulos import rotulo
from tests.test_rastro_indicadores import cpfs_validos

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "paginas"
CFG = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
PROIBIDOS = ("fraude", "laranja", "fictícia", "ficticia")


def lj(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


ELEITOS = lj("eleitos.json")
INDS = lj("indicadores.json")
FORN = lj("fornecedores.json")
PUBL = lj("publicados.json")
CORR = lj("correcoes.json")
SAL = "sal-de-teste"
E = {e["sq"]: e for e in ELEITOS["eleitos"]}
BASES = {"contas": "2026-10-12", "receita": "2026-09-01"}


def texto(h):
    """HTML sem tags, com entidades resolvidas e espaços colapsados."""
    h = re.sub(r"</(p|li|h\d|td|th|dt|dd|tr|div|section|nav|title)>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h)))


def gerar(dest, **kw):
    args = dict(publicados=PUBL, eleitos=ELEITOS, dir_contas=FIX / "contas", indicadores=INDS, fornecedores=FORN, cfg=CFG, sal=SAL)
    args.update(kw)
    return pg.gerar(dest, **args)


def arquivos(raiz):
    return {str(p.relative_to(raiz)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(raiz).rglob("*")) if p.is_file()}


def pagina_2001(contas=None, itens=None, forn=None):
    c = contas if contas is not None else json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
    return pg.html_eleito(E["2001"], c, itens if itens is not None else INDS["indicadores"]["2001"],
                          forn if forn is not None else FORN["fornecedores"], CFG, BASES)


ID_PJ = "33333333000191"
ID_MEI = pg.id_fornecedor("11111111000191", True, SAL)
ID_SEM = pg.id_fornecedor("99999999000191", True, SAL)


def agregado(cnpj):
    """campanhas (2001 e 2002) que pagaram `cnpj`, no formato de html_fornecedor."""
    out = []
    for sq in ("2001", "2002"):
        c = json.loads((FIX / "contas" / f"{sq}.json").read_text(encoding="utf-8"))
        for f in c["despesas"]["fornecedores_pj"]:
            if f["cnpj"] == cnpj:
                out.append({"eleito": E[sq], "caminho": pg.caminho(E[sq]), "cnpj": cnpj, "nome": f["nome"], "total": f["total"], "tipos": f["tipos"]})
    return out


def pagina_forn(cnpj, mei, itens=()):
    return pg.html_fornecedor(pg.id_fornecedor(cnpj, mei, SAL), FORN["fornecedores"].get(cnpj), agregado(cnpj), list(itens), CFG, BASES)


class TestIdFornecedor(unittest.TestCase):
    def test_pj_e_o_cnpj(self):
        self.assertEqual(pg.id_fornecedor("33.333.333/0001-91", False, None), "33333333000191")

    def test_mei_estavel_com_o_mesmo_sal(self):
        a = pg.id_fornecedor("11111111000191", True, "s1")
        self.assertEqual(a, pg.id_fornecedor("11.111.111/0001-91", True, "s1"))
        self.assertNotEqual(a, pg.id_fornecedor("11111111000191", True, "s2"))
        self.assertRegex(a, r"^[0-9a-f]{16}$")

    def test_mei_nao_contem_cnpj(self):
        self.assertNotIn("11111111", pg.id_fornecedor("11111111000191", True, SAL))

    def test_mei_sem_sal_levanta(self):
        for sal in (None, ""):
            with self.assertRaises(ValueError):
                pg.id_fornecedor("11111111000191", True, sal)

    def test_ler_sal_nao_cria(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                pg.ler_sal(Path(d) / ".sal")
            self.assertEqual(list(Path(d).iterdir()), [])


class TestFornecedor(unittest.TestCase):
    def test_mei_sem_nome_nem_cnpj_nem_socio(self):
        h = pagina_forn("11111111000191", True)
        for proibido in ("NOME DO MEI DONO", "11111111000191", "SOCIO DO MEI", "654321"):
            self.assertNotIn(proibido, h)
        self.assertIn(ind.mascarar_cnpj("11111111000191"), h)

    def test_pj_com_duas_campanhas(self):
        h = pagina_forn("33333333000191", False)
        t = texto(h)
        self.assertIn("EMPRESA GRANDE LTDA", t)
        self.assertIn("2 campanha(s)", t)
        self.assertIn(ind.brl(330000), t)
        for sq in ("2001", "2002"):
            self.assertIn(f'href="/{pg.caminho(E[sq])}"', h)
        self.assertIn("BELTRANO SOCIO", t)
        self.assertIn("Situação cadastral", t)

    def test_nunca_endereco_nem_cpf_mascarado(self):
        h = pagina_forn("33333333000191", False)
        self.assertNotIn("RUA SECRETA", h)
        self.assertNotIn("123456", h)

    def test_obrigatorios(self):
        for cnpj, mei in (("33333333000191", False), ("11111111000191", True)):
            h = pagina_forn(cnpj, mei)
            t = texto(h)
            self.assertIn("01/09/2026", t)
            self.assertIn("12/10/2026", t)
            self.assertIn(pg.AVISO, t)
            self.assertIn('href="/rastro/metodologia/"', h)
            self.assertIn("Contestar este dado", h)

    def test_homonimo_so_no_pj(self):
        it = [{"eleito": E["2001"], "caminho": pg.caminho(E["2001"]), "nome": "socio_doador", "fato": "x", "valor": 1, "fonte_url": "https://x.invalid/"}]
        self.assertIn("pode ser homônimo", texto(pagina_forn("33333333000191", False, it)))
        self.assertNotIn("socio_doador", pagina_forn("11111111000191", True, it))

    def test_sem_cadastro_vira_mascara(self):
        h = pg.html_fornecedor("abc", None, agregado("11111111000191"), [], CFG, BASES)
        self.assertNotIn("NOME DO MEI DONO", h)
        self.assertIn("não localizado", h)


ANT = {"fonte": [], "data_base": "2025-01-10", "gerado_em": "2026-10-13T00:00:00+00:00", "anos": [2022, 2024],
       "por_cnpj": {"33333333000191": {"2022": {"n_campanhas": 4, "total_contratado": 12345.5},
                                       "2024": {"n_campanhas": 2, "total_contratado": 800.0}},
                    "11111111000191": {"2022": {"n_campanhas": 1, "total_contratado": 50.0}}}}


def pagina_ant(cnpj, mei, ant=ANT):
    return pg.html_fornecedor(pg.id_fornecedor(cnpj, mei, SAL), FORN["fornecedores"].get(cnpj), agregado(cnpj), [], CFG, BASES, anteriores=ant)


class TestFornecedorAnteriores(unittest.TestCase):
    def test_sem_anteriores_html_identico(self):
        h = pagina_forn("33333333000191", False)
        self.assertNotIn("eleições anteriores", h)
        self.assertEqual(h, pagina_ant("33333333000191", False, None))

    def test_secao_com_linha_por_ano_e_fonte(self):
        h = pagina_ant("33333333000191", False)
        t = texto(h)
        self.assertIn("Em eleições anteriores", t)
        self.assertIn("4 campanha(s) " + ind.brl(12345.5), t)
        self.assertIn("2 campanha(s) " + ind.brl(800), t)
        for ano in (2022, 2024):
            self.assertIn(f'href="https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip"', h)
        self.assertIn("contratado por campanhas em 2022, 2024 e 2026", t.lower())
        self.assertIn("mesmo CNPJ não garante", t)

    def test_parcial_diz_o_ano_sem_registro(self):
        t = texto(pagina_ant("11111111000191", True))
        self.assertNotIn("contratado por campanhas em", t.lower())
        self.assertIn("Sem registro nas eleições de 2024 da base do TSE", t)

    def test_sem_dado_nenhum(self):
        t = texto(pagina_ant("33333333000191", False, {**ANT, "por_cnpj": {}}))
        self.assertIn("Sem registro nas eleições de 2022 e 2024 da base do TSE", t)

    def test_mei_mascarado_e_varredura(self):
        h = pagina_ant("11111111000191", True)
        self.assertNotIn("11111111000191", h)
        self.assertIn(ind.mascarar_cnpj("11111111000191"), h)
        pg.varrer("mei", h)
        pg.varrer("pj", pagina_ant("33333333000191", False))
        for p in PROIBIDOS:
            self.assertNotIn(p, h.lower())

    def test_ano_nao_lido_nao_vira_sem_registro(self):
        t = texto(pagina_ant("33333333000191", False, {**ANT, "anos": [2022]}))
        self.assertNotIn("2024", t.replace("2024.zip", ""))

    def test_gerar_repassa(self):
        with tempfile.TemporaryDirectory() as d:
            gerar(d, anteriores=ANT)
            arqs = [p.read_text(encoding="utf-8") for p in Path(d).rglob("index.html") if "fornecedor" in str(p)]
            self.assertTrue(any("Em eleições anteriores" in a for a in arqs))
        with tempfile.TemporaryDirectory() as d:
            gerar(d)
            self.assertFalse(any("Em eleições anteriores" in p.read_text(encoding="utf-8") for p in Path(d).rglob("index.html")))


AGR = {"por_cnpj": {"33333333000191": {"total_recebido": 400000.0, "n_campanhas": 3, "campanhas": ["2001", "2002", "9001"]},
                    "11111111000191": {"total_recebido": 110000.0, "n_campanhas": 2, "campanhas": ["2001", "2002"]}}}


def diagrama(h):
    return h.split('<section class="rs-diagrama">')[1].split("</section>")[0]


def faixas(svg):
    """valores (R$) das faixas do Sankey, lidos do <title> de cada <path>."""
    return [float(v.replace(".", "").replace(",", ".")) for v in re.findall(r"<path [^>]*><title>[^<]*: R\$ ([\d.,]+)</title></path>", svg)]


class TestRedeFornecedor(unittest.TestCase):
    def paginas(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            return {p["path"]: p["html"] for p in gerar(d, **kw)}

    def test_duas_publicadas_e_uma_nao_eleita(self):
        pags = self.paginas(agregados=AGR)
        svg = diagrama(pags[f"/rastro/fornecedor/{ID_PJ}/"])
        fx = faixas(svg)
        self.assertEqual(len(fx), 3)
        self.assertAlmostEqual(sum(fx), 400000, delta=0.01)
        links = re.findall(r'<a href="(/rastro/[^"]+)">', svg)
        self.assertEqual(sorted(links), sorted("/" + pg.caminho(E[sq]) for sq in ("2001", "2002")))
        self.assertIn("Outra campanha (não eleita)", svg)
        for a in re.findall(r"<a .*?</a>", svg):
            self.assertNotIn("não eleita", a)
        self.assertIn(f"Recebeu {ind.brl(400000)} de 3 campanhas: 2 de eleitos, de 2 partidos em 1 estado, e 1 não eleita.", texto(svg))
        self.assertFalse(any("9001" in p for p in pags))
        self.assertNotIn("9001", "".join(pags.values()))

    def test_sem_agregados_so_eleitos(self):
        fx = faixas(diagrama(self.paginas()[f"/rastro/fornecedor/{ID_PJ}/"]))
        self.assertEqual(len(fx), 2)
        self.assertAlmostEqual(sum(fx), 330000, delta=0.01)

    def test_diagrama_acima_da_tabela(self):
        h = self.paginas()[f"/rastro/fornecedor/{ID_PJ}/"]
        self.assertLess(h.index("Caminho do dinheiro"), h.index("Campanhas publicadas que o contrataram"))

    def test_pendente_sem_link(self):
        pend = [{"eleito": E["2004"], "total": 5000.0}]
        h = pg.html_fornecedor(ID_PJ, FORN["fornecedores"]["33333333000191"], agregado("33333333000191"), [], CFG, BASES, pendentes=pend)
        svg = diagrama(h)
        self.assertIn("NAO PUBLICADO", svg)
        self.assertEqual(len(re.findall(r"<a ", svg)), 2)
        self.assertNotIn("/rastro/depfed/ma/nao-publicado/", h)

    def test_mei_mascarado_no_svg(self):
        h = self.paginas(agregados=AGR)[f"/rastro/fornecedor/{ID_MEI}/"]
        svg = diagrama(h)
        self.assertIn(ind.mascarar_cnpj("11111111000191"), svg)
        self.assertNotIn("NOME DO MEI DONO", h)
        self.assertNotIn("11111111000191", h)

    def test_faixa_anteriores(self):
        com = diagrama(self.paginas(anteriores=ANT)[f"/rastro/fornecedor/{ID_PJ}/"])
        self.assertIn("Também recebeu em 2022 (4 campanhas) e 2024 (2 campanhas)", texto(com))
        self.assertIn('href="#anteriores"', com)
        self.assertNotIn("Também recebeu", self.paginas()[f"/rastro/fornecedor/{ID_PJ}/"])


class TestRedeHome(unittest.TestCase):
    def home(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            h = {p["path"]: p["html"] for p in gerar(d, **kw)}["/rastro/"]
        return h.split('<section id="rede">')[1].split("</section>")[0]

    def linhas(self, sec):
        tab = sec.split("<tbody>")[1].split("</tbody>")[0] if "<tbody>" in sec else ""
        return re.findall(r'<tr><td><a href="/rastro/fornecedor/([^/]+)/">', tab)

    def test_ordem_por_eleitos_e_total(self):
        sec = self.home()
        self.assertEqual(self.linhas(sec), [ID_PJ, ID_MEI])  # os dois atendem 2 eleitos; o PJ tem mais valor
        self.assertNotIn(ID_SEM, self.linhas(sec))  # 1 eleito só: fora
        self.assertIn("não um ranking de risco", texto(sec))
        self.assertIn("2 partido(s)", texto(sec))

    def test_desempate_e_top_n(self):
        cfg = copy.deepcopy(CFG)
        cfg["rede_top_n"] = 1
        self.assertEqual(self.linhas(self.home(cfg=cfg)), [ID_PJ])

    def test_exclui_plataforma(self):
        cfg = copy.deepcopy(CFG)
        cfg["rede_excluir_cnpj_raiz"] = [{"raiz": "33333333", "nome": "PLATAFORMA X"}]
        sec = self.home(cfg=cfg)
        self.assertEqual(self.linhas(sec), [ID_MEI])
        self.assertNotIn("EMPRESA GRANDE", sec)
        self.assertIn('Não listadas: plataformas de pagamento e anúncio (lista na <a href="/rastro/metodologia/#rede">metodologia</a>)', sec)

    def test_mei_mascarado(self):
        sec = self.home()
        self.assertIn(ind.mascarar_cnpj("11111111000191"), sec)
        self.assertNotIn("11111111000191", sec)
        self.assertNotIn("NOME DO MEI DONO", sec)

    def test_mini_diagrama(self):
        sec = self.home()
        self.assertIn('<div class="rs-sankey rs-rede">', sec)
        self.assertIn("veja a tabela acima", sec)
        self.assertIn(".rs-rede{display:none}", pg.CSS)

    def test_maiores_fornecedores_continua(self):
        with tempfile.TemporaryDirectory() as d:
            h = {p["path"]: p["html"] for p in gerar(d)}["/rastro/"]
        self.assertLess(h.index("Maiores fornecedores"), h.index("Empresas que atendem mais eleitos"))


class TestRedeEleito(unittest.TestCase):
    def paginas(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            return {p["path"]: p["html"] for p in gerar(d, **kw)}

    def secao(self, h):
        return h.split('<section id="rede">')[1].split("</section>")[0] if '<section id="rede">' in h else ""

    def test_a_lista_b_e_b_lista_a(self):
        pags = self.paginas()
        a, b = (self.secao(pags["/" + pg.caminho(E[sq])]) for sq in ("2001", "2002"))
        self.assertIn(f'href="/{pg.caminho(E["2002"])}"', a)
        self.assertIn(f'href="/{pg.caminho(E["2001"])}"', b)
        self.assertNotIn(f'href="/{pg.caminho(E["2001"])}"', a)
        self.assertIn(f'href="/rastro/fornecedor/{ID_PJ}/"', a)
        self.assertNotIn(ID_SEM, a)  # só a 2001 pagou: sem cruzamento
        self.assertLess(pags["/" + pg.caminho(E["2001"])].index("<h2>Tabelas</h2>"), pags["/" + pg.caminho(E["2001"])].index('<section id="rede">'))

    def test_mei_mascarado_e_sem_cnpj(self):
        a = self.secao(self.paginas()["/" + pg.caminho(E["2001"])])
        self.assertIn(f'<a href="/rastro/fornecedor/{ID_MEI}/">{ind.mascarar_cnpj("11111111000191")}</a>', a)
        self.assertNotIn("11111111000191", a)
        self.assertNotIn("NOME DO MEI DONO", a)

    def test_plataforma_fora(self):
        cfg = copy.deepcopy(CFG)
        cfg["rede_excluir_cnpj_raiz"] = [{"raiz": "33333333", "nome": "PLATAFORMA X"}]
        a = self.secao(self.paginas(cfg=cfg)["/" + pg.caminho(E["2001"])])
        self.assertNotIn(ID_PJ, a)
        self.assertIn(ID_MEI, a)

    def test_sem_cruzamento_sem_secao(self):
        h = self.paginas(publicados=["2001"])["/" + pg.caminho(E["2001"])]
        self.assertNotIn("Fornecedores que também atendem outros eleitos", h)

    def test_limite_de_dez(self):
        outros = [{"nome_urna": f"ELEITO {i:02d}", "caminho": f"rastro/depfed/sp/e{i}/"} for i in range(13)]
        t = texto(pg.secao_cruzada([{"id": "x", "rotulo": "EMPRESA", "outros": outros}]))
        self.assertIn("ELEITO 09 e mais 3", t)
        self.assertNotIn("ELEITO 10", t)


class TestRedeMetodologia(unittest.TestCase):
    def test_plataformas_e_contagem(self):
        h = pg.html_metodologia(CFG)
        t = texto(h)
        self.assertIn('<h2 id="rede">Rede de fornecedores</h2>', h)
        self.assertIn("não um ranking de risco", t)
        for p in CFG["rede_excluir_cnpj_raiz"]:
            self.assertIn(p["nome"], t)
            self.assertIn(p["raiz"], t)

    def test_config_raizes(self):
        forn = RAIZ / "rastro" / "dados" / "fornecedores.json"
        cnpjs = set(json.loads(forn.read_text(encoding="utf-8"))["fornecedores"]) if forn.exists() else set()
        self.assertTrue(CFG["rede_excluir_cnpj_raiz"])
        for p in CFG["rede_excluir_cnpj_raiz"]:
            self.assertRegex(p["raiz"], r"^\d{8}$")
            if cnpjs:
                self.assertTrue(any(c.startswith(p["raiz"]) for c in cnpjs), p)


class TestRedeResistencia(unittest.TestCase):
    def test_varredura_e_lgpd_com_agregados(self):
        with tempfile.TemporaryDirectory() as d:
            pags = gerar(d, agregados=AGR, anteriores=ANT)
            tudo = "".join(p["html"] for p in pags)
            self.assertEqual(TestRedacao.varrer(self, d), 8)
        for p in pags:
            pg.varrer(p["path"], p["html"])
        self.assertEqual(cpfs_validos(tudo), [])
        for proibido in ("11111111000191", "NOME DO MEI DONO", "SOCIO DO MEI", "99999999000191", "SEM CADASTRO LTDA", "RUA SECRETA"):
            self.assertNotIn(proibido, tudo)
        for termo in ("esquema", "suspeit"):
            self.assertNotIn(termo, tudo.lower())


class TestGerarFornecedores(unittest.TestCase):
    def test_so_quem_aparece_em_publicado(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {p["path"] for p in gerar(d)}
        self.assertIn(f"/rastro/fornecedor/{ID_PJ}/", paths)
        self.assertIn(f"/rastro/fornecedor/{ID_MEI}/", paths)
        self.assertNotIn("/rastro/fornecedor/44444444000191/", paths)
        self.assertEqual(len([p for p in paths if "/fornecedor/" in p]), 3)  # PJ, MEI e o sem cadastro (tratado como MEI)

    def test_eleito_linka_fornecedor(self):
        with tempfile.TemporaryDirectory() as d:
            pags = {p["path"]: p["html"] for p in gerar(d)}
        h = pags["/" + pg.caminho(E["2001"])]
        self.assertIn(f'href="/rastro/fornecedor/{ID_PJ}/"', h)
        self.assertIn(f'href="/rastro/fornecedor/{ID_MEI}/"', h)
        self.assertNotIn("11111111000191", "".join(pags.values()))

    def test_mei_sem_sal_nao_grava(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                gerar(d, sal=None)
            self.assertEqual(arquivos(d), {})

    def test_cpf_valido_em_nome_de_fornecedor_pj(self):
        forn = copy.deepcopy(FORN)
        forn["fornecedores"]["33333333000191"]["razao"] = "EMPRESA 529.982.247-25 LTDA"
        with tempfile.TemporaryDirectory() as saida:
            with self.assertRaisesRegex(ValueError, "CPF"):
                gerar(saida, fornecedores=forn)
            self.assertEqual(arquivos(saida), {})


class TestHome(unittest.TestCase):
    def home(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            return {p["path"]: p["html"] for p in gerar(d, **kw)}["/rastro/"]

    def test_conteudo(self):
        h = self.home()
        t = texto(h)
        self.assertIn(pg.AVISO, t)
        self.assertIn("12/10/2026", t)
        self.assertIn('href="/rastro/metodologia/"', h)
        self.assertIn("Contestar este dado", h)
        self.assertIn("Total contratado por cargo", t)
        self.assertIn(ind.brl(480000), t)  # depfed (2001)
        self.assertIn(ind.brl(50000), t)  # depest (2002)
        self.assertIn("Maiores fornecedores", t)
        self.assertIn("Indícios mais frequentes entre os publicados", t)
        # O não publicado só aparece na tabela "ainda sem página", sem link e sem os fornecedores dele.
        self.assertNotIn("NAO PUBLICADO", t.split("Eleitos ainda sem página")[0])
        self.assertNotIn("SO DO NAO PUBLICADO LTDA", t)
        self.assertNotIn("NOME DO MEI DONO", t)

    def test_eleitos_ainda_sem_pagina(self):
        h = self.home()
        t = texto(h)
        self.assertIn("Eleitos ainda sem página", t)
        sec = h.split("Eleitos ainda sem página")[1].split('<section id="contestar">')[0]
        self.assertIn("NAO PUBLICADO", sec)
        self.assertIn(pg.CARGOS[E["2004"]["cargo"]], texto(sec))
        self.assertNotIn("<a ", sec)
        for pub in PUBL:
            self.assertNotIn(E[pub]["nome_urna"], sec)
        self.assertEqual(cpfs_validos(h), [])
        self.assertIsNone(pg.termo_proibido(h))

    def test_sem_pendentes_sem_tabela(self):
        h = self.home(publicados=[e["sq"] for e in ELEITOS["eleitos"]])
        self.assertNotIn("Eleitos ainda sem página", h)

    def test_vazia_lista_pendentes(self):
        with tempfile.TemporaryDirectory() as d:
            h = gerar(d, publicados=[], indicadores=None, fornecedores=None)[0]["html"]
        self.assertIn("Eleitos ainda sem página", h)
        self.assertNotIn('href="/rastro/depfed/', h)

    def test_eleito_sem_contas_sem_r0(self):
        t = texto(self.home())
        self.assertIn("MARIA SEM CONTAS", t)
        self.assertIn("sem prestação parcial publicada", t)
        self.assertNotIn("R$ 0", t)

    def test_top_n_vem_do_config(self):
        cfg = copy.deepcopy(CFG)
        cfg["home_top_n"] = 1
        h = self.home(cfg=cfg).split("Maiores fornecedores")[1].split('<section id="rede">')[0]
        self.assertEqual(h.count('href="/rastro/fornecedor/'), 1)
        self.assertIn(f'href="/rastro/fornecedor/{ID_PJ}/"', h)  # o de maior valor

    def test_mei_mascarado(self):
        h = self.home()
        self.assertIn(ind.mascarar_cnpj("11111111000191"), h)
        self.assertNotIn("11111111000191", h)

    def test_vazia(self):
        with tempfile.TemporaryDirectory() as d:
            h = gerar(d, publicados=[], indicadores=None, fornecedores=None)[0]["html"]
        t = texto(h).lower()
        self.assertIn("nenhuma página publicada ainda", t)
        self.assertIn(pg.AVISO.lower(), t)
        self.assertIn("contestar este dado", t)


class TestCorrecoes(unittest.TestCase):
    def paginas(self):
        return [{"path": "/rastro/a/", "html": '<main><section id="contestar">x</section></main>'},
                {"path": "/rastro/b/", "html": '<main><section id="contestar">y</section></main>'}]

    def test_aplica_so_na_pagina_certa(self):
        pags = self.paginas()
        antes_b = pags[1]["html"]
        pg.aplicar_correcoes(pags, [{"path": "/rastro/a/", "data": "2026-10-13", "o_que_mudou": "Valor ajustado.", "fonte_url": "https://x.invalid/f"}])
        t = texto(pags[0]["html"])
        self.assertIn("Correções", t)
        self.assertIn("13/10/2026", t)
        self.assertIn("Valor ajustado.", t)
        self.assertIn('href="https://x.invalid/f"', pags[0]["html"])
        self.assertEqual(pags[1]["html"], antes_b)

    def test_path_inexistente_levanta(self):
        with self.assertRaisesRegex(ValueError, "inexistente"):
            pg.aplicar_correcoes(self.paginas(), [{"path": "/rastro/zzz/", "data": "2026-10-13", "o_que_mudou": "x"}])

    def test_varre_o_texto(self):
        for txt, esperado in (("CPF 529.982.247-25 informado por engano.", "CPF"), ("Era laranja, na verdade.", "proibido")):
            with self.assertRaisesRegex(ValueError, esperado):
                pg.aplicar_correcoes(self.paginas(), [{"path": "/rastro/a/", "data": "2026-10-13", "o_que_mudou": txt}])

    def test_envelope_do_repo_e_valido(self):
        pg.aplicar_correcoes(self.paginas(), json.loads((RAIZ / "rastro" / "correcoes.json").read_text(encoding="utf-8")))

    def test_gerar_aplica(self):
        with tempfile.TemporaryDirectory() as d:
            pags = {p["path"]: p["html"] for p in gerar(d, correcoes=CORR)}
        self.assertIn("Valor do fornecedor corrigido", pags["/" + pg.caminho(E["2001"])])
        self.assertNotIn("Valor do fornecedor corrigido", pags["/" + pg.caminho(E["2002"])])

    def test_gerar_path_errado_nao_grava(self):
        errada = {"correcoes": [{"path": "/rastro/nao-existe/", "data": "2026-10-13", "o_que_mudou": "x"}]}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                gerar(d, correcoes=errada)
            self.assertEqual(arquivos(d), {})

    def test_metodologia_explica(self):
        self.assertIn("Correções", texto(pg.html_metodologia(CFG)))


class TestLote1(unittest.TestCase):
    def test_ordem_e_tamanho(self):
        from rastro import lote1
        self.assertEqual(lote1.escolher(ELEITOS, INDS, 3), ["2003", "2001", "2004"])  # senador, depfed (votos), depfed
        self.assertEqual(len(lote1.escolher(ELEITOS, INDS, 2)), 2)

    def test_sem_dados_nao_grava(self):
        from rastro import lote1
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "publicados.json"
            self.assertEqual(lote1.main(Path(d), dest, RAIZ / "rastro" / "config.json"), 1)
            self.assertFalse(dest.exists())

    def test_grava_com_fixtures(self):
        from rastro import lote1
        with tempfile.TemporaryDirectory() as d:
            for n in ("eleitos.json", "fornecedores.json", "indicadores.json"):
                (Path(d) / n).write_text((FIX / n).read_text(encoding="utf-8"), encoding="utf-8")
            dest = Path(d) / "publicados.json"
            self.assertEqual(lote1.main(Path(d), dest, RAIZ / "rastro" / "config.json"), 0)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), ["2003", "2001", "2004", "2002"])


class TestCaminho(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(pg.slug("JOSÉ D'ÁVILA"), "jose-davila")
        self.assertEqual(pg.slug("  Ana  Maria / Silva-Jr. "), "ana-maria-silva-jr")

    def test_caminho(self):
        self.assertEqual(pg.caminho(E["2001"]), "rastro/depfed/ma/aluisio-mendes/")
        self.assertEqual(pg.caminho(E["2003"]), "rastro/senador/pi/maria-sem-contas/")

    def test_colisao_recebe_sq(self):
        a = {"sq": "1", "nome_urna": "JOÃO SILVA", "cargo": "depfed", "uf": "SP"}
        b = {"sq": "2", "nome_urna": "Joao Silva", "cargo": "depfed", "uf": "SP"}
        c = {"sq": "3", "nome_urna": "JOAO SILVA", "cargo": "depest", "uf": "SP"}
        cam = pg.caminhos([a, b, c])
        self.assertEqual(cam["1"], "rastro/depfed/sp/joao-silva-1/")
        self.assertEqual(cam["2"], "rastro/depfed/sp/joao-silva-2/")
        self.assertEqual(cam["3"], "rastro/depest/sp/joao-silva/")
        self.assertEqual(len(set(cam.values())), 3)


class TestEleito(unittest.TestCase):
    def test_conteudo_obrigatorio(self):
        h = pagina_2001()
        t = texto(h)
        self.assertIn("12/10/2026", t)
        self.assertIn("01/09/2026", t)
        self.assertIn(pg.AVISO, t)
        self.assertIn('href="/rastro/metodologia/"', h)
        self.assertIn("Contestar este dado", h)
        self.assertIn(f'href="mailto:{CFG["contato_email"]}?', h)
        for i in INDS["indicadores"]["2001"]:
            self.assertIn(f'{rotulo(i["nome"])}: {i["fato"]}', t)
            self.assertIn(f'<a href="{i["fonte_url"]}"', h)
        self.assertIn("Receitas por origem", h)
        self.assertIn("Despesas por fornecedor", h)
        self.assertIn(ind.brl(400000), t)

    def test_sem_prestacao(self):
        for contas in (None, {"sq": "2002", "prestacao_parcial": False, "receitas": None, "despesas": None}):
            t = texto(pg.html_eleito(E["2002"], contas, [], FORN["fornecedores"], CFG, BASES))
            self.assertIn("sem prestação parcial publicada", t)
            self.assertNotIn("R$ 0", t)
            self.assertNotIn("Receitas por origem", t)
            self.assertNotIn("Nenhum indicador", t)

    def test_homonimo(self):
        itens = [{"nome": n, "fato": "algo", "valor": 1, "fonte_url": "https://x.invalid/"}
                 for n in ("socio_doador", "socio_ligado", "socio_nomeado", "concentracao", "mei_acima_teto")]
        h = pagina_2001(itens=itens).split('id="indicadores"')[1]  # lista completa (os cartões repetem a nota)
        com =[m for m in re.findall(r"<li>.*?</li>", h, re.S) if "pode ser homônimo" in m]
        self.assertEqual(len(com), 3)
        for nome in ("socio_doador", "socio_ligado", "socio_nomeado"):
            self.assertTrue(any(f'<b class="rs-rot">{rotulo(nome)}</b>' in m for m in com), nome)

    def test_sem_indicadores(self):
        self.assertIn("Nenhum indicador disparado", texto(pagina_2001(itens=[])))


class TestEleitoEnxuto(unittest.TestCase):
    def test_diagrama_entre_h1_e_tabelas(self):
        h = pagina_2001()
        self.assertLess(h.index("<h1>"), h.index("<svg"))
        self.assertLess(h.index("<svg"), h.index("<table"))

    def test_linha_de_resumo(self):
        t = texto(pagina_2001())
        self.assertIn(f"Recebeu {ind.brl(500000)} · Contratou {ind.brl(480000)} · 3 fornecedores · 4 indicadores", t)

    def test_aviso_curto_e_rodape_unico(self):
        h = pagina_2001()
        self.assertRegex(h, r'<p class="rs-aviso rs-aviso-curto"><b>' + re.escape(pg.AVISO) + r'</b> <a href="/rastro/metodologia/">')
        self.assertEqual(h.count("<footer"), 1)
        rod = h.split('<footer class="rs-rodape">')[1].split("</footer>")[0]
        self.assertIn("Base de dados: contas do TSE até 12/10/2026", texto(rod))
        self.assertIn("Fontes:", rod)
        self.assertIn("Contestar este dado", rod)
        self.assertIn(f'href="mailto:{CFG["contato_email"]}?', rod)
        self.assertEqual(h.count("Contestar este dado"), 1)

    def test_tabelas_em_details(self):
        h = pagina_2001()
        for titulo in ("Receitas por origem", "Despesas por fornecedor"):
            self.assertRegex(h, r'<details class="rs-det"><summary><b>' + titulo + r"</b> · [^<]*R\$")
        for tab in re.finditer(r"<table", h):
            antes = h[:tab.start()]
            self.assertGreater(antes.count("<details"), antes.count("</details>"))

    def test_limitacao_e_ancoras(self):
        h = pagina_2001()
        self.assertIn("A base não liga cada receita a cada despesa; o diagrama não mostra que fonte pagou qual fornecedor.", h)
        self.assertGreater(h.index("A base não liga"), h.index("</svg>"))
        self.assertEqual(re.findall(r'<tr id="(f-[^"]+)"', h), ["f-n0", "f-n1", "f-n2"])
        self.assertIn('<a href="#f-n0">', h)  # EMPRESA GRANDE, alertada

    def test_ancora_com_id_de_fornecedor(self):
        with tempfile.TemporaryDirectory() as d:
            h = {p["path"]: p["html"] for p in gerar(d)}["/" + pg.caminho(E["2001"])]
        self.assertRegex(h, f'<tr id="f-{ID_PJ}"[ >]')
        self.assertRegex(h, f'<tr id="f-{ID_MEI}"[ >]')
        self.assertIn(f'<a href="#f-{ID_PJ}">', h)

    def test_correcao_entra_antes_do_rodape(self):
        with tempfile.TemporaryDirectory() as d:
            h = {p["path"]: p["html"] for p in gerar(d, correcoes=CORR)}["/" + pg.caminho(E["2001"])]
        self.assertLess(h.index('<section id="correcoes">'), h.index('<footer class="rs-rodape">'))

    def test_prestacao_vazia_frase_no_lugar_do_diagrama(self):
        c = json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
        c["receitas"] = c["despesas"] = None
        h = pagina_2001(contas=c)
        self.assertIn("Sem prestação na base para o diagrama.", h)
        self.assertNotIn("<svg", h)

    def test_metodologia_mantem_aviso_completo(self):
        h = pg.html_metodologia(CFG)
        self.assertIn("Cada item abaixo é um fato público", h)
        self.assertIn("A base não liga cada receita a cada despesa", h)


class TestLgpd(unittest.TestCase):
    def test_mei_mascarado(self):
        h = pagina_2001()
        self.assertIn(ind.mascarar_cnpj("11111111000191"), h)
        self.assertNotIn("11111111000191", h)
        self.assertNotIn("NOME DO MEI DONO", h)
        self.assertIn("EMPRESA GRANDE LTDA", h)

    def test_sem_cadastro_tambem_mascara(self):
        h = pagina_2001()
        self.assertNotIn("SEM CADASTRO LTDA", h)
        self.assertNotIn("99999999000191", h)

    def test_pf_so_agregado(self):
        t = texto(pagina_2001())
        self.assertIn("Pessoas físicas: 24 pagas", t)
        self.assertIn("Despesas com pessoal", t)

    def test_cpf_valido_no_nome_levanta(self):
        contas = json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
        contas["despesas"]["fornecedores_pj"][0]["nome"] = "EMPRESA 529.982.247-25 LTDA"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "contas").mkdir()
            (Path(d) / "contas" / "2001.json").write_text(json.dumps(contas), encoding="utf-8")
            with tempfile.TemporaryDirectory() as saida:
                with self.assertRaisesRegex(ValueError, "CPF"):
                    gerar(saida, publicados=["2001"], dir_contas=Path(d) / "contas")
                self.assertEqual(arquivos(saida), {})  # nada foi gravado

    def test_sem_fornecedores_falha(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "MEI"):
                gerar(d, fornecedores=None)

    def test_sem_publicados_nao_exige_fornecedores(self):
        with tempfile.TemporaryDirectory() as d:
            pags = gerar(d, publicados=[], indicadores=None, fornecedores=None)
            self.assertEqual([p["path"] for p in pags], ["/rastro/", "/rastro/metodologia/"])

    @unittest.skipUnless((RAIZ / "site" / "rastro").exists(), "site/rastro ainda não gerado")
    def test_site_sem_cpf(self):
        for p in (RAIZ / "site" / "rastro").rglob("*"):
            if p.is_file():
                self.assertEqual(cpfs_validos(p.read_text(encoding="utf-8")), [], str(p))


class TestRedacao(unittest.TestCase):
    def varrer(self, raiz):
        n = 0
        for p in Path(raiz).rglob("*"):
            if p.is_file():
                n += 1
                baixo = p.read_text(encoding="utf-8").lower()
                for termo in PROIBIDOS:
                    self.assertNotIn(termo, baixo, f"{termo} em {p}")
        return n

    def test_gerado(self):
        with tempfile.TemporaryDirectory() as d:
            gerar(d)
            self.assertEqual(self.varrer(d), 8)

    def test_termo_proibido_levanta(self):
        contas = json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
        contas["despesas"]["fornecedores_pj"][0]["nome"] = "LARANJA DISTRIBUIDORA LTDA"
        with self.assertRaisesRegex(ValueError, "proibido"):
            pg.varrer("x", pg.html_eleito(E["2001"], contas, [], FORN["fornecedores"], CFG, BASES))

    @unittest.skipUnless((RAIZ / "site" / "rastro").exists(), "site/rastro ainda não gerado")
    def test_site(self):
        self.varrer(RAIZ / "site" / "rastro")


class TestMetodologia(unittest.TestCase):
    CHAVES = {
        "recem_aberta_dias": 411, "multicampanha_min": 14, "concentracao_pct": 63, "endereco_min_fornecedores": 4,
        "percentil_comparacao": 88, "min_campanhas_grupo": 17, "pf_qtd_min": 31, "pf_repetido_min_campanhas": 6,
        "pf_redondo_alto_min_qtd": 9, "tardio_dias": 12,
    }

    def test_lista_todos_os_indicadores(self):
        t = texto(pg.html_metodologia(CFG))
        for nome in ("mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel", "socio_doador", "socio_ligado",
                     "multicampanha", "situacao_irregular", "concentracao", "endereco_compartilhado", "preco_fora_da_curva",
                     "gasto_por_voto", "transferencia_candidato", "pessoal_pf", "saque_especie", "pagamento_tardio"):
            self.assertIn(nome, t)

    def test_limites_fontes_e_aviso(self):
        t = texto(pg.html_metodologia(CFG))
        self.assertIn(pg.AVISO, t)
        self.assertIn("Parentesco não consta em nenhuma base pública", t)
        self.assertIn("fato textual", t)
        self.assertIn("homônimos", t)
        self.assertIn("TSE", t)
        self.assertIn("Receita", t)
        self.assertIn("Contestar este dado", t)

    def test_avisos_de_indicador_pulado(self):
        self.assertNotIn("não calculados", texto(pg.html_metodologia(CFG)))
        t = texto(pg.html_metodologia(CFG, ["socio_doador: pulado (fonte indisponível)"]))
        self.assertIn("Indicadores não calculados nesta base", t)
        self.assertIn("socio_doador: pulado", t)
        with tempfile.TemporaryDirectory() as d:
            inds = dict(INDS, avisos=["saque_especie: pulado (fonte indisponível)"])
            met = {p["path"]: p["html"] for p in gerar(d, indicadores=inds)}["/rastro/metodologia/"]
        self.assertIn("saque_especie: pulado", texto(met))

    def test_valores_vem_do_config(self):
        antes = texto(pg.html_metodologia(CFG))
        cfg = copy.deepcopy(CFG)
        cfg.update(self.CHAVES)
        cfg["mei_teto_anual"] = 77777
        cfg["tardio_pct_ultimos_dias"] = 0.37
        cfg["situacoes_irregulares"] = ["XPTO"]
        depois = texto(pg.html_metodologia(cfg))
        for k, v in self.CHAVES.items():
            self.assertNotIn(f" {v} ", antes, k)
            self.assertIn(str(v), depois, k)
        for esperado in (ind.brl(77777), "37%", "XPTO"):
            self.assertIn(esperado, depois)
            self.assertNotIn(esperado, antes)
        self.assertIn(ind.brl(CFG["mei_teto_anual"]), antes)
        self.assertNotIn(ind.brl(CFG["mei_teto_anual"]), depois)


class TestIsolamento(unittest.TestCase):
    PROTEGIDOS = ("relatorio/relatorio.json", "relatorio/historico.json", "painel.html")

    def snapshot(self):
        out = {}
        for rel in self.PROTEGIDOS:
            p = RAIZ / rel
            if p.is_file():
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        for pasta in ("hud", "supabase"):
            for p in sorted((RAIZ / pasta).rglob("*")):
                if p.is_file() and "node_modules" not in p.parts:
                    out[str(p.relative_to(RAIZ))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    def test_gerar_nao_mexe_no_resto(self):
        antes = self.snapshot()
        self.assertTrue(antes)
        with tempfile.TemporaryDirectory() as d:
            gerar(d)
            gravados = set(arquivos(d))
        self.assertEqual(self.snapshot(), antes)
        self.assertEqual(gravados, {
            "rastro/index.html", f"rastro/fornecedor/{ID_PJ}/index.html", f"rastro/fornecedor/{ID_MEI}/index.html", f"rastro/fornecedor/{ID_SEM}/index.html",
            "rastro/metodologia/index.html",
            "rastro/depfed/ma/aluisio-mendes/index.html",
            "rastro/depest/ma/jose-davila/index.html",
            "rastro/senador/pi/maria-sem-contas/index.html"})

    def test_envolver_recebe_a_pagina(self):
        with tempfile.TemporaryDirectory() as d:
            pags = gerar(d, envolver=lambda p: "<!--moldura-->" + p["html"])
            for p in pags:
                self.assertTrue((Path(d) / p["path"].strip("/") / "index.html").read_text(encoding="utf-8").startswith("<!--moldura-->"))


class TestPublicados(unittest.TestCase):
    def publicados(self):
        return json.loads((RAIZ / "rastro" / "publicados.json").read_text(encoding="utf-8"))

    def test_tamanho_sem_repeticao_e_em_eleitos(self):
        pub = self.publicados()
        self.assertEqual(len(pub), len(set(pub)))
        if pub:
            arq = RAIZ / "rastro" / "dados" / "eleitos.json"
            sqs = {str(e["sq"]) for e in json.loads(arq.read_text(encoding="utf-8"))["eleitos"]}
            self.assertLessEqual(set(map(str, pub)), sqs)

    def test_com_contas_ou_sem_prestacao(self):
        for sq in self.publicados():
            if (RAIZ / "rastro" / "dados" / "contas" / f"{sq}.json").exists():
                continue
            h = pg.html_eleito({"sq": sq, "nome_urna": "X", "cargo": "depfed", "uf": "SP", "partido": "P"}, None, [], {}, CFG, BASES)
            self.assertIn("sem prestação parcial publicada", texto(h))

    def test_config_tem_contato(self):
        self.assertRegex(CFG["contato_email"], r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _it(nome, valor=1000.0, contraparte=None, fato="fato público", **kw):
    i = {"nome": nome, "fato": fato, "valor": valor, "fonte_url": "https://x.invalid/"}
    if contraparte:
        i["contraparte"] = contraparte
    i.update(kw)
    return i


def _contas(*forns):
    return {"despesas": {"fornecedores_pj": [{"cnpj": c, "nome": n, "total": t, "tipos": []} for c, n, t in forns]}}


PJ_REC = {"mei": False, "razao": None}
FORN_D = {"10000000000191": dict(PJ_REC, razao="ALFA LTDA"), "20000000000191": dict(PJ_REC, razao="BETA LTDA"),
          "30000000000191": dict(PJ_REC, razao="GAMA LTDA")}
CONTAS_D = _contas(("10000000000191", "ALFA LTDA", 1000.0), ("20000000000191", "BETA LTDA", 500000.0),
                   ("30000000000191", "GAMA LTDA", 900000.0))


class TestDestaques(unittest.TestCase):
    def d(self, itens, contas=CONTAS_D, ids=None):
        return pg.destaques(itens, contas, FORN_D, CFG, ids)

    def test_peso_antes_do_valor(self):
        c = self.d([_it("preco_fora_da_curva", 1_000_000.0), _it("situacao_irregular", contraparte="ALFA LTDA")])
        self.assertEqual([x["itens"][0]["nome"] for x in c], ["situacao_irregular", "preco_fora_da_curva"])

    def test_mesmo_peso_maior_valor_primeiro(self):
        c = self.d([_it("empresa_recem_aberta", contraparte="BETA LTDA"), _it("empresa_recem_aberta", contraparte="GAMA LTDA")])
        self.assertEqual([x["titulo"] for x in c], ["GAMA LTDA", "BETA LTDA"])
        self.assertEqual(c[0]["valor"], 900000.0)  # total do fornecedor, não o valor do item

    def test_empate_por_nome(self):
        contas = _contas(("10000000000191", "ALFA LTDA", 5.0), ("20000000000191", "BETA LTDA", 5.0))
        c = self.d([_it("socio_doador", contraparte="BETA LTDA"), _it("socio_doador", contraparte="ALFA LTDA")], contas)
        self.assertEqual([x["titulo"] for x in c], ["ALFA LTDA", "BETA LTDA"])

    def test_multicampanha_nunca_vira_cartao(self):
        self.assertEqual(self.d([_it("multicampanha", 7, contraparte="ALFA LTDA")]), [])
        c = self.d([_it("multicampanha", 7, contraparte="ALFA LTDA"), _it("concentracao", 60, contraparte="ALFA LTDA")])
        self.assertEqual([i["nome"] for i in c[0]["itens"]], ["concentracao"])

    def test_agrupa_por_fornecedor(self):
        c = self.d([_it("concentracao", 60, contraparte="GAMA LTDA"), _it("atividade_incompativel", contraparte="GAMA LTDA")])
        self.assertEqual(len(c), 1)
        h = pg.bloco_destaques(c, "12/10/2026", CFG)
        self.assertEqual(h.count('class="rs-tag"'), 2)
        self.assertIn(rotulo("concentracao"), h)
        self.assertIn(rotulo("atividade_incompativel"), h)

    def test_no_maximo_cinco(self):
        itens = [_it("pagamento_tardio", float(v)) for v in range(1, 9)]
        self.assertEqual(len(self.d(itens)), pg.MAX_DESTAQUES)

    def test_homonimo_mantem_nota(self):
        h = pg.bloco_destaques(self.d([_it("socio_doador", contraparte="ALFA LTDA")]), "12/10/2026", CFG)
        self.assertIn("pode ser homônimo", h)

    def test_pessoal_pf_so_contagem_e_total(self):
        c = self.d([_it("pessoal_pf", 30000.0, fato="Pagou 25 pessoas físicas, num total de R$ 30.000,00")])
        self.assertEqual(c[0]["titulo"], rotulo("pessoal_pf"))
        h = pg.bloco_destaques(c, "12/10/2026", CFG)
        self.assertIn("25 pessoas físicas", h)
        self.assertEqual(cpfs_validos(h), [])

    def test_gasto_por_voto_sem_reais(self):
        c = self.d([_it("gasto_por_voto", 12.5), _it("pagamento_tardio", 1.0)])
        self.assertEqual(c[0]["itens"][0]["nome"], "pagamento_tardio")  # peso médio antes do baixo
        self.assertIsNone(next(x for x in c if x["itens"][0]["nome"] == "gasto_por_voto")["valor"])

    def test_valores_identicos_um_cartao_do_grupo(self):
        vi = _it("valores_identicos", 3000.0, contraparte="ALFA LTDA", contrapartes=["ALFA LTDA", "BETA LTDA"])
        c = self.d([vi])
        self.assertEqual(c[0]["titulo"], "ALFA LTDA; BETA LTDA")
        self.assertEqual(c[0]["valor"], 501000.0)

    def test_link_ver_fornecedor(self):
        c = self.d([_it("situacao_irregular", contraparte="BETA LTDA")])
        self.assertEqual(c[0]["href"], "#f-n1")
        c = self.d([_it("situacao_irregular", contraparte="BETA LTDA")], ids={"20000000000191": "20000000000191"})
        self.assertEqual(c[0]["href"], "/rastro/fornecedor/20000000000191/")

    def test_vazio(self):
        for itens in ([], [_it("multicampanha", 7, contraparte="ALFA LTDA")]):
            h = pg.bloco_destaques(self.d(itens), "12/10/2026", CFG)
            self.assertIn("Nenhum indicador disparado nesta base (12/10/2026)", texto(h))

    def test_bloco_no_topo_da_pagina(self):
        h = pagina_2001()
        self.assertLess(h.index("rs-aviso-curto"), h.index('id="destaques"'))
        self.assertLess(h.index('id="destaques"'), h.index("<svg"))


class TestSeloEFiltro(unittest.TestCase):
    def test_selo_e_filtro(self):
        h = pagina_2001()
        self.assertIn('<label hidden class="rs-filtro"><input type="checkbox"> Só com indício</label>', h)
        self.assertIn('<script defer src="/rastro/rastro.js"></script>', h)
        self.assertRegex(h, r'<tr id="f-n0" data-indicio="\d+"><td>[^\n]*?<span class="rs-selo" title="[^"]+">\d+</span>')

    def test_multicampanha_conta_no_selo(self):
        linha = pg._linha_fornecedor({"cnpj": "10000000000191", "nome": "ALFA LTDA", "total": 1.0}, FORN_D, None, 0,
                                     [_it("multicampanha", 7, contraparte="ALFA LTDA")])
        self.assertIn('data-indicio="1"', linha)
        self.assertIn(f'title="{rotulo("multicampanha")}"', linha)

    def test_sem_indicio_sem_selo(self):
        linha = pg._linha_fornecedor({"cnpj": "10000000000191", "nome": "ALFA LTDA", "total": 1.0}, FORN_D, None, 0, [])
        self.assertNotIn("data-indicio", linha)
        self.assertNotIn("rs-selo", linha)

    def test_script_so_na_pagina_do_eleito(self):
        with tempfile.TemporaryDirectory() as d:
            for p in gerar(d):
                eleito = not (p["path"] in ("/rastro/", "/rastro/metodologia/") or p["path"].startswith("/rastro/fornecedor/"))
                if not eleito:
                    self.assertNotIn("rastro.js", p["html"], p["path"])

    def test_contrapartes_casam_fornecedor(self):
        vi = _it("valores_identicos", contraparte="ALFA LTDA", contrapartes=["ALFA LTDA", "BETA LTDA"])
        f = {"cnpj": "20000000000191", "nome": "BETA LTDA"}
        self.assertEqual(pg._itens_do_fornecedor(f, FORN_D["20000000000191"], False, [f], [vi]), [vi])


class TestRotulosNasPaginas(unittest.TestCase):
    def test_sem_code_com_nome_tecnico(self):
        nomes = [n for n, _ in pg.descricoes(CFG)] + ["socio_nomeado"]
        with tempfile.TemporaryDirectory() as d:
            for p in gerar(d):
                if p["path"] == "/rastro/metodologia/":
                    continue
                for n in nomes:
                    self.assertNotIn(f"<code>{n}</code>", p["html"], p["path"])

    def test_metodologia_rotulo_e_ancora(self):
        h = pg.html_metodologia(CFG)
        self.assertIn(f'{rotulo("valores_identicos")} <code id="ind-valores_identicos">valores_identicos</code>', h)
        self.assertIn(ind.brl(CFG["valores_identicos_min"]), h)
        self.assertIn("nunca aparece como número", h)
        pg.varrer("metodologia", h)

    def test_home_sem_multicampanha(self):
        itens = {"2001": [_it("multicampanha", 7, contraparte="X"), _it("concentracao", 60, contraparte="X")]}
        with tempfile.TemporaryDirectory() as d:
            h = gerar(d, indicadores=dict(INDS, indicadores=dict(INDS["indicadores"], **itens)))[0]["html"]
        sec = h.split("Indícios mais frequentes entre os publicados")[1]
        self.assertNotIn(rotulo("multicampanha"), sec.split("</ul>")[0])
        self.assertIn(rotulo("concentracao"), sec)


class TestRedacaoNova(unittest.TestCase):
    def test_termos_novos_barrados(self):
        for termo in ("suspeito", "suspeita", "desvio", "esquema", "irregular"):
            with self.assertRaises(ValueError, msg=termo):
                pg.varrer("x", f"<li>Fornecedor {termo}</li>")

    def test_fato_suspeito_derruba_a_pagina(self):
        itens = [_it("concentracao", 60, contraparte="EMPRESA GRANDE LTDA", fato="pagamento suspeito")]
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            gerar(d, indicadores=dict(INDS, indicadores=dict(INDS["indicadores"], **{"2001": itens})))

    def test_excecoes_permitidas(self):
        pg.varrer("x", pg.AVISO + " Não afirmamos que houve irregularidade. <code>situacao_irregular</code>")
        with self.assertRaises(ValueError):
            pg.varrer("x", "houve irregularidade grave")


if __name__ == "__main__":
    unittest.main()
