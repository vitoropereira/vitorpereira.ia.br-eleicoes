import hashlib
import json
import re
import unittest
from pathlib import Path

from rastro import eleitos

RAIZ = Path(__file__).resolve().parent.parent
FIXTURE = RAIZ / "tests" / "fixtures" / "rastro" / "relatorio_dados"
REAL = RAIZ / "relatorio" / "dados"


class TestFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = eleitos.montar(FIXTURE, ["ac", "df"])
        cls.por_sq = {e["sq"]: e for e in cls.out["eleitos"]}

    def test_so_os_eleitos_certos(self):
        esperado = {"1001", "1011", "1013", "1021", "1023", "1031", "2011", "2021", "2031", "2032"}
        self.assertEqual(set(self.por_sq), esperado)
        self.assertEqual(len(self.out["eleitos"]), len(esperado))

    def test_cargos(self):
        self.assertEqual({e["cargo"] for e in self.out["eleitos"]},
                         {"governador", "senador", "depfed", "depest", "distrital"})
        self.assertEqual(self.por_sq["2031"]["cargo"], "distrital")
        self.assertEqual(self.por_sq["1031"]["cargo"], "depest")

    def test_tipos_e_campos(self):
        e = self.por_sq["1023"]
        self.assertIsInstance(e["sq"], str)
        self.assertIsInstance(e["votos"], int)
        self.assertEqual(e["votos"], 700)
        self.assertEqual(e["partido"], "PSD")
        self.assertEqual(e["uf"], "AC")
        self.assertEqual(e["situacao"], "Eleito por média")
        self.assertEqual(e["nome_urna"], "FED MEDIA")

    def test_metadados(self):
        self.assertEqual(self.out["data_base"], "2026-10-05")
        self.assertRegex(self.out["gerado_em"], r"^\d{4}-\d\d-\d\dT")
        self.assertIn("https://resultados.tse.jus.br/oficial/ele2026/6259/dados/df/df-c0008-e006259-u.json",
                      self.out["fonte"])
        self.assertNotIn("df-c0007", " ".join(self.out["fonte"]))

    def test_ordem_estavel(self):
        ordem = ["governador", "senador", "depfed", "depest", "distrital"]
        chaves = [(ordem.index(e["cargo"]), e["uf"], -e["votos"]) for e in self.out["eleitos"]]
        self.assertEqual(chaves, sorted(chaves))

    def test_aborta_se_nao_totalizado(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            shutil.copytree(FIXTURE, t, dirs_exist_ok=True)
            p = Path(t) / "ac-c0003.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            d["tf"] = "n"
            p.write_text(json.dumps(d), encoding="utf-8")
            with self.assertRaises(SystemExit):
                eleitos.montar(t, ["ac"])


class TestContagemReal(unittest.TestCase):
    def test_contagens(self):
        out = eleitos.montar(REAL, eleitos.UFS)
        cont = {}
        for e in out["eleitos"]:
            cont[e["cargo"]] = cont.get(e["cargo"], 0) + 1
        nv = {}
        for uf in eleitos.UFS:
            for c in eleitos.codigos(uf):
                d = json.loads((REAL / f"{uf}-c{c:04d}.json").read_text(encoding="utf-8"))
                cargo = eleitos.CARGOS[c]
                nv[cargo] = nv.get(cargo, 0) + int(d["carg"][0]["nv"])
        for cargo in ("senador", "depfed", "depest", "distrital"):
            self.assertEqual(cont[cargo], nv[cargo], cargo)
        self.assertEqual(cont["depfed"], 513)
        self.assertEqual(cont["senador"], 54)
        self.assertEqual(cont["depest"] + cont["distrital"], 1059)
        com_eleito = sum(1 for uf in eleitos.UFS
                         if '"st" : "Eleito"' in (REAL / f"{uf}-c0003.json").read_text(encoding="utf-8"))
        self.assertEqual(cont["governador"], com_eleito)
        self.assertTrue(all(isinstance(e["sq"], str) and isinstance(e["votos"], int) for e in out["eleitos"]))


class TestHigiene(unittest.TestCase):
    def test_config_json(self):
        json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))

    def test_gitignore(self):
        linhas = (RAIZ / ".gitignore").read_text(encoding="utf-8").split("\n")
        self.assertIn("rastro/brutos/", linhas)
        self.assertIn("rastro/.sal", linhas)

    def test_relatorio_intocado(self):
        def h():
            return [hashlib.sha256((RAIZ / "relatorio" / n).read_bytes()).hexdigest()
                    for n in ("relatorio.json",) if (RAIZ / "relatorio" / n).exists()] + \
                   [hashlib.sha256(p.read_bytes()).hexdigest() for p in RAIZ.glob("**/historico.json")
                    if ".git" not in p.parts]
        antes = h()
        eleitos.montar(FIXTURE, ["ac", "df"])
        self.assertEqual(antes, h())
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", antes[0]))


if __name__ == "__main__":
    unittest.main()
