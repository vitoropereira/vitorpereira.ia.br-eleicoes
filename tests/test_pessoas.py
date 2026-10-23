"""Modo "Pessoas" do HUD (#152): posições pré-calculadas dos círculos (municipios/pessoas.py). Sem rede."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from municipios import pessoas as P  # noqa: E402

GEO = R / "municipios" / "geo"


def quadrado(x0, y0, l=1):
    """anel fechado de um quadrado, em graus (lon, lat)"""
    return [[x0, y0], [x0 + l, y0], [x0 + l, y0 + l], [x0, y0 + l], [x0, y0]]


def topo_sintetico(quadrados):
    """topojson sem transform, um arco por município (anel inteiro). quadrados = {cod: (lon, lat, lado)}"""
    arcs, geoms = [], []
    for cod, (x, y, l) in quadrados.items():
        arcs.append(quadrado(x, y, l))
        geoms.append({"type": "Polygon", "properties": {"codarea": cod}, "arcs": [[len(arcs) - 1]]})
    return {"type": "Topology", "arcs": arcs, "objects": {"BRMU": {"type": "GeometryCollection", "geometries": geoms}}}


def pres(te):
    return {"mu": {cod: [n, 0, 0, 0, 0, [], 0] for cod, n in te.items()}}


# dois deles (A e B) com o mesmo centroide
QUAD = {"1": (0, 0, 1), "2": (0, 0, 1), "3": (1.2, 0, 0.5), "4": (0, 1.2, 0.5), "5": (3, 3, 1)}
TE = {"1": 40000, "2": 10000, "3": 90000, "4": 2500, "5": 160000}


class TestPessoas(unittest.TestCase):
    def test_area_proporcional_ao_eleitorado(self):
        r = P.calcular(topo_sintetico(QUAD), pres(TE))
        k = r["k"]
        for cod, (_, _, te) in r["mu"].items():
            self.assertEqual(te, TE[cod])
        razoes = {round((k * math.sqrt(te)) ** 2 / te, 12) for _, _, te in r["mu"].values()}
        self.assertEqual(len(razoes), 1)  # r²/te constante

    def test_sem_sobreposicao_e_mesmo_centroide_separa(self):
        r = P.calcular(topo_sintetico(QUAD), pres(TE))
        pos = {c: (x, y) for c, (x, y, _) in r["mu"].items()}
        raios = {c: r["k"] * math.sqrt(te) for c, (_, _, te) in r["mu"].items()}
        cods = sorted(pos)
        self.assertLessEqual(P.sobreposicao_maxima([pos[c] for c in cods], [raios[c] for c in cods]), 1e-6)
        d = math.dist(pos["1"], pos["2"])
        self.assertGreaterEqual(d, raios["1"] + raios["2"])

    def test_so_entra_quem_tem_centroide_e_eleitorado(self):
        te = dict(TE, **{"9": 5000, "3": 0})  # 9 sem polígono; 3 sem eleitorado
        r = P.calcular(topo_sintetico(QUAD), pres(te))
        self.assertNotIn("9", r["mu"])
        self.assertNotIn("3", r["mu"])
        self.assertIn("1", r["mu"])

    def test_sobreposicao_maxima(self):
        self.assertAlmostEqual(P.sobreposicao_maxima([(0, 0), (1, 0)], [0.75, 0.75]), 0.5)
        self.assertEqual(P.sobreposicao_maxima([(0, 0), (5, 0)], [1, 1]), 0.0)

    def test_garantir_so_regera_quando_a_entrada_muda(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t1").mkdir()
            topo, pr = d / "municipios.topo.json", d / "t1" / "presidente.json"
            saida = d / "pessoas.json"
            self.assertIsNone(P.garantir(topo, pr, saida))  # sem entradas
            self.assertFalse(saida.exists())
            topo.write_text(json.dumps(topo_sintetico(QUAD)))
            pr.write_text(json.dumps(pres(TE)))
            self.assertEqual(P.garantir(topo, pr, saida), saida)
            antes = saida.stat().st_mtime_ns
            with mock.patch.object(P, "calcular", side_effect=AssertionError("regerou sem mudança")):
                self.assertEqual(P.garantir(topo, pr, saida), saida)
            self.assertEqual(saida.stat().st_mtime_ns, antes)
            pr.write_text(json.dumps(pres(dict(TE, **{"5": 250000}))))
            P.garantir(topo, pr, saida)
            self.assertNotEqual(json.loads(saida.read_text())["fonte"], P.assinatura(topo_sintetico(QUAD), pres(TE)))


class TestPessoasReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = json.loads((GEO / "municipios.topo.json").read_text())
        cls.pres = json.loads((GEO / "t1" / "presidente.json").read_text())
        cls.arq = json.loads((GEO / "pessoas.json").read_text())

    def test_fonte_confere_com_as_entradas(self):
        self.assertEqual(self.arq["fonte"], P.assinatura(self.topo, self.pres))
        self.assertEqual(self.arq["campo"], "te")

    def test_todo_cod_elegivel_presente(self):
        cods = {g["properties"]["codarea"] for g in self.topo["objects"]["BRMU"]["geometries"]}
        elegiveis = {c for c, l in self.pres["mu"].items() if c in cods and l[0] > 0}
        self.assertEqual(set(self.arq["mu"]), elegiveis)
        for cod, (_, _, te) in self.arq["mu"].items():
            self.assertEqual(te, self.pres["mu"][cod][0])

    def test_sem_sobreposicao_relevante(self):
        k, mu = self.arq["k"], self.arq["mu"]
        cods = sorted(mu)
        pos = [(mu[c][0], mu[c][1]) for c in cods]
        raios = [k * math.sqrt(mu[c][2]) for c in cods]
        self.assertLessEqual(P.sobreposicao_maxima(pos, raios), 0.01 * P.FOLGA)

    def test_deslocamento_mediano_pequeno(self):
        cen = P.centroides(self.topo)
        d = sorted(math.dist((x, y), cen[c][:2]) for c, (x, y, _) in self.arq["mu"].items())
        self.assertLess(d[len(d) // 2], 1.0)


class TestBuild(unittest.TestCase):
    def test_copiar_hud_publica_pessoas_json(self):
        import build_site
        with tempfile.TemporaryDirectory() as t:
            build_site.copiar_hud(Path(t))
            self.assertTrue((Path(t) / "geo" / "pessoas.json").exists())


if __name__ == "__main__":
    unittest.main()
