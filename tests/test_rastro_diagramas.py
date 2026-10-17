import copy
import json
import re
import unittest
from pathlib import Path

from rastro import diagramas as dg
from rastro import indicadores as ind
from rastro import paginas as pg

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "paginas"
FORN = json.loads((FIX / "fornecedores.json").read_text(encoding="utf-8"))["fornecedores"]
INDS = json.loads((FIX / "indicadores.json").read_text(encoding="utf-8"))["indicadores"]
RE_COR = re.compile(r"#[0-9a-f]{3,6}|rgb\(", re.I)


def contas(sq):
    return json.loads((FIX / "contas" / f"{sq}.json").read_text(encoding="utf-8"))


C5 = contas("2005")
FORN5 = {ind.digitos(f["cnpj"]): {"razao": f["nome"], "mei": False} for f in C5["despesas"]["fornecedores_pj"]}


def somas(fluxos):
    entra, sai = {}, {}
    for f in fluxos:
        sai[f["de"]] = sai.get(f["de"], 0) + f["valor"]
        entra[f["para"]] = entra.get(f["para"], 0) + f["valor"]
    return entra, sai


def svg_de(d):
    return dg.sankey(d["colunas"], d["fluxos"], {"titulo": "Caminho do dinheiro", "resumo": d["resumo"]})


def nos(d, col):
    return {n["id"]: n for n in d["colunas"][col]}


class TestLayout(unittest.TestCase):
    COLS = [[{"id": "a", "rotulo": "A"}, {"id": "b", "rotulo": "B"}], [{"id": "m", "rotulo": "M"}],
            [{"id": "x", "rotulo": "X"}, {"id": "y", "rotulo": "Y"}, {"id": "z", "rotulo": "Z"}]]
    FLUX = [{"de": "a", "para": "m", "valor": 1000.0}, {"de": "b", "para": "m", "valor": 0.5},
            {"de": "m", "para": "x", "valor": 900.0}, {"de": "m", "para": "y", "valor": 100.0}, {"de": "m", "para": "z", "valor": 0.5}]

    def lay(self):
        return dg.layout_sankey(self.COLS, self.FLUX, 300, 900)

    def test_fecha_no_intermediario(self):
        lay = self.lay()
        entra = sum(f["valor"] for f in lay["faixas"] if f["para"] == "m")
        sai = sum(f["valor"] for f in lay["faixas"] if f["de"] == "m")
        self.assertAlmostEqual(entra, sai, delta=0.01)
        self.assertAlmostEqual(lay["nos"]["m"]["valor"], 1000.5, delta=0.01)

    def test_faixa_positiva_tem_espessura(self):
        for f in self.lay()["faixas"]:
            self.assertGreater(f["espessura"], 0)
        for n in self.lay()["nos"].values():
            self.assertGreater(n["h"], 0)

    def test_proporcao_no_valor(self):
        fx = {(f["de"], f["para"]): f for f in self.lay()["faixas"]}
        self.assertAlmostEqual(fx["m", "x"]["espessura"] / fx["m", "y"]["espessura"], 9, places=6)

    def test_sem_sobreposicao_na_coluna(self):
        lay = self.lay()
        for col in self.COLS:
            gs = sorted((lay["nos"][n["id"]] for n in col), key=lambda g: g["y"])
            for a, b in zip(gs, gs[1:]):
                self.assertLessEqual(a["y"] + a["h"], b["y"])

    def test_tudo_zero_nao_divide_por_zero(self):
        lay = dg.layout_sankey([[{"id": "a", "rotulo": "A"}], [{"id": "b", "rotulo": "B"}]], [{"de": "a", "para": "b", "valor": 0}], 100, 400)
        self.assertEqual(lay["faixas"], [])


class TestFluxos(unittest.TestCase):
    def test_2001_alerta_e_lgpd(self):
        d = dg.fluxos_campanha(contas("2001"), FORN, INDS["2001"], None)
        forn = nos(d, 3)
        grande = [n for n in forn.values() if n["rotulo"] == "EMPRESA GRANDE LTDA"]
        self.assertEqual(len(grande), 1)
        self.assertTrue(grande[0]["alerta"])
        self.assertEqual(grande[0]["href"], "#f-n0")
        mascarados = [n for n in forn.values() if n["rotulo"] == ind.mascarar_cnpj("99999999000191")]
        self.assertTrue(mascarados)
        self.assertFalse(any(n["alerta"] for n in mascarados))  # máscara ambígua na campanha: sem marcador
        s = svg_de(d)
        for proibido in ("NOME DO MEI DONO", "11111111000191", "SEM CADASTRO LTDA", "99999999000191"):
            self.assertNotIn(proibido, s)

    def test_fecha_em_cada_no(self):
        for c, forn, itens in ((contas("2001"), FORN, INDS["2001"]), (C5, FORN5, [])):
            d = dg.fluxos_campanha(c, forn, itens, None)
            entra, sai = somas(d["fluxos"])
            self.assertAlmostEqual(entra["camp"], sai["camp"], delta=0.01)
            self.assertAlmostEqual(entra["camp"], c["receitas"]["total"], delta=0.01)
            for t in nos(d, 2):
                if t in sai:  # tipos de gasto; sumidouros (PF, não gasto) não têm saída
                    self.assertAlmostEqual(entra[t], sai[t], delta=0.01, msg=t)
            self.assertLessEqual(len(d["colunas"][0]), 6)

    def test_limites_outros_doadores_e_mais_fornecedores(self):
        d = dg.fluxos_campanha(C5, FORN5, [], None)
        orig = [n["rotulo"] for n in d["colunas"][0]]
        self.assertEqual(orig, ["Direção Nacional - PX", "Direção Estadual - PX - SP", "Outros doadores", "Pessoas físicas", "Recursos próprios", "Outros"])
        entra, sai = somas(d["fluxos"])
        self.assertAlmostEqual(sai["o-resto"], 10000, delta=0.01)
        rot = [n["rotulo"] for n in d["colunas"][3]]
        self.assertIn("Mais 2 fornecedores", rot)
        self.assertIn("Mais 1 fornecedor", rot)
        self.assertEqual(len([r for r in rot if r.startswith("FORNECEDOR")]), 10)
        tipos = [n["rotulo"] for n in d["colunas"][2]]
        self.assertIn("Pessoas físicas (3 pagas)", tipos)
        self.assertIn("Ainda não gasto / não declarado", tipos)
        self.assertEqual(nos(d, 2)["t-nao"]["tom"], "muted")
        self.assertAlmostEqual(entra["t-nao"], 100000, delta=0.01)
        self.assertIn("50% do partido", d["resumo"])
        self.assertIn("os 3 maiores destinos foram FORNECEDOR 01 LTDA", d["resumo"])

    def test_tipo_principal_inteiro(self):
        d = dg.fluxos_campanha(C5, FORN5, [], None)
        entra, _ = somas(d["fluxos"])
        serv = [n["id"] for n in d["colunas"][2] if n["rotulo"] == "Serviços prestados por terceiros"][0]
        self.assertAlmostEqual(entra[serv], 738000, delta=0.01)  # inclui o FORNECEDOR 13, com dois tipos

    def test_contratado_maior_que_recebido(self):
        c = copy.deepcopy(C5)
        c["receitas"]["total"] = 500000.0
        c["receitas"]["por_origem"] = {"Recursos de partido político": 500000.0}
        c["receitas"]["doadores_pj"] = []
        d = dg.fluxos_campanha(c, FORN5, [], None)
        entra, sai = somas(d["fluxos"])
        self.assertAlmostEqual(sai["o-excesso"], 400000, delta=0.01)
        self.assertAlmostEqual(entra["camp"], sai["camp"], delta=0.01)
        self.assertNotIn("t-nao", entra)


class TestSvg(unittest.TestCase):
    def setUp(self):
        self.d = dg.fluxos_campanha(contas("2001"), FORN, INDS["2001"], {"33333333000191": "33333333000191"})
        self.s = svg_de(self.d)

    def test_acessivel(self):
        s = self.s
        self.assertIn('role="img"', s)
        self.assertIn('aria-labelledby="sk-t sk-d"', s)
        self.assertIn('<title id="sk-t">Caminho do dinheiro</title>', s)
        self.assertRegex(s, r'<desc id="sk-d">R\$ 500\.000,00 entraram \(84% do partido\); os 3 maiores destinos foram EMPRESA GRANDE LTDA')

    def test_title_em_cada_faixa(self):
        paths = re.findall(r"<path [^>]*>(.*?)</path>", self.s)
        self.assertEqual(len(paths), len([f for f in self.d["fluxos"] if f["valor"] > 0]))
        for p in paths:
            self.assertRegex(p, r"<title>.+: R\$ [\d.]+,\d{2}</title>")

    def test_sem_cor_literal_e_sem_tamanho_fixo(self):
        svg = re.search(r"<svg.*</svg>", self.s, re.S).group()
        self.assertIsNone(RE_COR.search(svg))
        self.assertIn("var(--", svg)
        tag = re.match(r"<svg[^>]*>", svg).group()
        self.assertIn("viewBox=", tag)
        self.assertNotRegex(tag, r"\s(width|height)=")

    def test_rotulo_longo_cortado(self):
        c = contas("2001")
        nome = "EMPRESA DE NOME MUITO MAIS LONGO QUE O ESPAÇO DO RÓTULO LTDA"
        c["despesas"]["fornecedores_pj"][0]["nome"] = nome
        s = svg_de(dg.fluxos_campanha(c, FORN, [], None))
        self.assertIn("…", s)
        self.assertIn(f"<title>{nome}</title>", s)
        self.assertNotIn(f">{nome} <tspan", s)

    def test_alerta_com_ancora_ambar(self):
        self.assertIn('<a href="#f-33333333000191">', self.s)
        bloco = self.s.split('<a href="#f-33333333000191">')[1].split("</a>")[0]
        self.assertIn("stroke:var(--amber)", bloco)
        self.assertNotIn("/rastro/fornecedor/", self.s)

    def test_varredura(self):
        pg.varrer("svg", self.s)
        pg.varrer("svg5", svg_de(dg.fluxos_campanha(C5, FORN5, [], None)))


SNAP_2001 = "99ffad68ebf5b0633b24e0c418de0d7fb626ab038d5f29828e632a3a30954da4"  # SVG da issue A, antes da opção rotulo_acima


def camp(i, href=True, total=1000.0, partido="PX", uf="SP"):
    return {"nome_urna": f"ELEITO {i:02d}", "cargo": "depfed", "uf": uf, "partido": partido, "total": total,
            "href": f"/rastro/depfed/sp/e{i}/" if href else None}


class TestSankeyDuasColunas(unittest.TestCase):
    def test_quatro_colunas_identico(self):
        import hashlib
        s = svg_de(dg.fluxos_campanha(contas("2001"), FORN, INDS["2001"], None))
        self.assertEqual(hashlib.sha256(s.encode()).hexdigest(), SNAP_2001)

    def test_rotulo_ao_lado(self):
        cols = [[{"id": "a", "rotulo": "A"}], [{"id": "b", "rotulo": "EMPRESA B"}]]
        s = dg.sankey(cols, [{"de": "a", "para": "b", "valor": 10.0}], {"titulo": "t", "resumo": "r", "xs": dg.XS2, "rotulo_acima": None})
        self.assertNotIn("text-anchor:middle", s)
        x = float(re.search(r'<text x="([\d.]+)"[^>]*>EMPRESA B', s).group(1))
        self.assertEqual(x, dg.XS2[1] + dg.NO_W + 6)


class TestFluxosFornecedor(unittest.TestCase):
    def test_tres_campanhas(self):
        cs = [camp(1), camp(2, total=500.0), camp(3, href=False, total=250.0)]
        d = dg.fluxos_fornecedor("33333333000191", "EMPRESA", cs)
        self.assertEqual(len(d["fluxos"]), 3)
        self.assertAlmostEqual(sum(f["valor"] for f in d["fluxos"]), 1750, delta=0.01)
        self.assertEqual(d["total"], 1750)
        hrefs = [n.get("href") for n in d["colunas"][0]]
        self.assertEqual(hrefs, ["/rastro/depfed/sp/e1/", "/rastro/depfed/sp/e2/", None])
        self.assertEqual(d["colunas"][0][0]["rotulo"], "ELEITO 01 · Deputado(a) federal · SP · PX")

    def test_limite_de_campanhas(self):
        cs = [camp(i, total=1000.0 - i) for i in range(14)]
        d = dg.fluxos_fornecedor("33333333000191", "EMPRESA", cs, max_campanhas=12)
        self.assertEqual(len(d["colunas"][0]), 13)
        self.assertEqual(d["colunas"][0][-1]["rotulo"], "Mais 2 campanhas")
        self.assertAlmostEqual(sum(f["valor"] for f in d["fluxos"]), sum(c["total"] for c in cs), delta=0.01)

    def test_outras_nao_eleitas(self):
        d = dg.fluxos_fornecedor("33333333000191", "EMPRESA", [camp(1), camp(2, partido="PY", uf="RJ")], outras={"n": 4, "valor": 300.0})
        o = d["colunas"][0][-1]
        self.assertEqual(o["rotulo"], "Outras 4 campanhas (não eleitas)")
        self.assertEqual(o["tom"], "muted")
        self.assertNotIn("href", o)
        self.assertEqual(d["resumo"], f"Recebeu {ind.brl(2300)} de 6 campanhas: 2 de eleitos, de 2 partidos em 2 estados, e 4 não eleitas.")

    def test_sem_outras_resumo(self):
        d = dg.fluxos_fornecedor("33333333000191", "EMPRESA", [camp(1), camp(2)])
        self.assertEqual(d["resumo"], f"Recebeu {ind.brl(2000)} de 2 campanhas de 1 partido em 1 estado.")

    def test_mei_mascarado(self):
        d = dg.fluxos_fornecedor("11111111000191", "NOME DO MEI DONO", [camp(1)], mei=True)
        self.assertEqual(d["colunas"][1][0]["rotulo"], ind.mascarar_cnpj("11111111000191"))
        h = dg.diagrama_fornecedor("11111111000191", "NOME DO MEI DONO", [camp(1)], mei=True)
        self.assertNotIn("NOME DO MEI DONO", h)
        self.assertNotIn("11111111000191", h)

    def test_vazio(self):
        self.assertIsNone(dg.fluxos_fornecedor("33333333000191", "E", []))
        self.assertNotIn("<svg", dg.diagrama_fornecedor("33333333000191", "E", []))


class TestRede(unittest.TestCase):
    EMP = [{"cnpj": "A", "rotulo": "EMPRESA A", "href": "/rastro/fornecedor/a/"}, {"cnpj": "B", "rotulo": "EMPRESA B", "href": "/rastro/fornecedor/b/"}]

    def el(self, sq, total):
        return {"sq": sq, "nome_urna": f"ELEITO {sq}", "uf": "SP", "partido": "PX", "total": total, "href": f"/rastro/depfed/sp/{sq}/"}

    def test_eleito_em_duas_empresas_um_no(self):
        d = dg.fluxos_rede(self.EMP, {"A": [self.el("1", 100.0), self.el("2", 50.0)], "B": [self.el("1", 30.0), self.el("3", 10.0)]})
        ids = [n["id"] for n in d["colunas"][0]]
        self.assertEqual(ids.count("e1"), 1)
        self.assertEqual(len([f for f in d["fluxos"] if f["de"] == "e1"]), 2)
        self.assertEqual([n.get("href") for n in d["colunas"][1]], ["/rastro/fornecedor/a/", "/rastro/fornecedor/b/"])

    def test_mais_n_eleitos(self):
        els = {"A": [self.el(str(i), 100.0 - i) for i in range(25)], "B": [self.el("0", 1.0)]}
        d = dg.fluxos_rede(self.EMP, els, max_eleitos=20)
        rot = [n["rotulo"] for n in d["colunas"][0]]
        self.assertIn("Mais 5 eleitos", rot)
        self.assertEqual(len([r for r in rot if r.startswith("ELEITO")]), 20)
        entra, _ = somas(d["fluxos"])
        self.assertAlmostEqual(entra["p0"], sum(e["total"] for e in els["A"]), delta=0.01)

    def test_svg_sem_cor_literal(self):
        h = dg.diagrama_rede(self.EMP, {"A": [self.el("1", 100.0)], "B": [self.el("1", 30.0)]})
        self.assertIsNone(RE_COR.search(h))
        self.assertIn('class="rs-sankey rs-rede"', h)
        self.assertEqual(dg.diagrama_rede(self.EMP, {}), "")


class TestResistencia(unittest.TestCase):
    def test_pf_com_nome_nao_aparece(self):
        c = contas("2001")
        c["despesas"]["fornecedores_pf"]["nome"] = "FULANA PAGA"
        c["despesas"]["fornecedores_pf"]["nomes"] = ["FULANA PAGA"]
        h = dg.diagrama_campanha(c, FORN, INDS["2001"], None)
        self.assertIn("<svg", h)
        self.assertNotIn("FULANA", h)

    def test_sem_prestacao_vira_frase(self):
        base = contas("2001")
        casos = [None, {}, {**base, "receitas": None}, {**base, "despesas": None}, {**base, "receitas": None, "despesas": None},
                 {**base, "receitas": {"total": 0, "por_origem": {}}, "despesas": {"total_contratado": 0, "total_pago": 0}}]
        for c in casos:
            h = dg.diagrama_campanha(c, FORN, [], None)
            self.assertIn(dg.SEM_DIAGRAMA, h)
            self.assertNotIn("<svg", h)

    def test_zeros_e_faltas_nao_quebram(self):
        c = {"receitas": {"total": 0, "por_origem": {"Recursos de pessoas físicas": 0}, "doadores_pj": [{"nome": "X", "total": 0}]},
             "despesas": {"total_contratado": 100.0, "total_pago": 0, "fornecedores_pj": [{"cnpj": "33333333000191", "total": 0}],
                          "fornecedores_pf": {"qtd": 0, "total": 0}}}
        h = dg.diagrama_campanha(c, FORN, [], None)
        self.assertIn("<svg", h)
        self.assertIn("Contratado além do recebido na base", h)



class TestPartidoNosNos(unittest.TestCase):
    """issue #74: todo nó de eleito no Sankey termina com · SIGLA, e o corte do rótulo nunca tira a sigla"""

    def test_fornecedor(self):
        d = dg.fluxos_fornecedor("33333333000191", "EMPRESA", [camp(1, partido="PT"), camp(2, partido="PL")])
        self.assertEqual([n["rotulo"].rsplit(" · ", 1)[1] for n in d["colunas"][0]], ["PT", "PL"])

    def test_rede(self):
        el = lambda sq, sg: {"sq": sq, "nome_urna": f"ELEITO {sq}", "uf": "BA", "partido": sg, "total": 10.0, "href": None}
        d = dg.fluxos_rede([{"cnpj": "A", "rotulo": "EMP A"}], {"A": [el("1", "PT"), el("2", "PSD")]})
        self.assertEqual([n["rotulo"] for n in d["colunas"][0]], ["ELEITO 1 · BA · PT", "ELEITO 2 · BA · PSD"])

    def test_campanha(self):
        d = dg.fluxos_campanha(contas("2001"), FORN, INDS["2001"], None, "RUI COSTA · BA", "PT")
        self.assertEqual(d["colunas"][1][0]["rotulo"], "RUI COSTA · BA · PT")
        self.assertIn(">RUI COSTA · BA · PT</text>", svg_de(d))

    def test_nome_longo_preserva_sigla(self):
        self.assertEqual(dg.cortar("FULANO DE TAL DA SILVA SAURO · SP · REPUBLICANOS", 30, " · REPUBLICANOS"),
                         "FULANO DE TAL… · REPUBLICANOS")
        d = dg.fluxos_fornecedor("33333333000191", "EMPRESA", [{**camp(1, partido="REPUBLICANOS"), "nome_urna": "X" * 80}])
        svg = dg.diagrama_fornecedor("33333333000191", "EMPRESA", [{**camp(1, partido="REPUBLICANOS"), "nome_urna": "X" * 80}])
        self.assertTrue(d["colunas"][0][0]["rotulo"].endswith(" · REPUBLICANOS"))
        self.assertIn("… · REPUBLICANOS <tspan", svg)


if __name__ == "__main__":
    unittest.main()
