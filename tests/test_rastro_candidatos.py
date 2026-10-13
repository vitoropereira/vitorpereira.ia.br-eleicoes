import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from rastro import baixar, candidatos
from tests.test_rastro_indicadores import cpfs_validos

RAIZ = Path(__file__).resolve().parent.parent
CSV = RAIZ / "tests" / "fixtures" / "rastro" / "candidatos" / "consulta_cand_2026_BRASIL.csv"


class TestCandidatos(unittest.TestCase):
    def rodar(self):
        tmp = Path(tempfile.mkdtemp())
        zip_path = tmp / "consulta_cand_2026.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("consulta_cand_2026_BRASIL.csv", CSV.read_bytes().decode("utf-8").encode("latin-1"))
        saida = tmp / "candidatos.json"
        res = candidatos.gerar(zip_path, saida)
        return res, saida.read_text(encoding="utf-8")

    def test_titular_e_suplentes(self):
        res, _ = self.rodar()
        self.assertEqual(res["2001"], {"nome": "CARLOS BRANDÃO MOTA", "uf": "AC", "cargo": "SENADOR", "cpf_meio": "982247"})
        self.assertEqual(res["2002"]["cargo"], "1º SUPLENTE")
        self.assertEqual(res["2003"]["cargo"], "2º SUPLENTE")
        self.assertEqual(set(res["2001"]), {"nome", "uf", "cargo", "cpf_meio"})

    def test_cpf_nulo_vira_none(self):
        res, _ = self.rodar()
        self.assertIsNone(res["2004"]["cpf_meio"])

    def test_homonimos_tem_cpf_meio_diferente(self):
        res, _ = self.rodar()
        self.assertEqual(res["2005"]["nome"], res["2006"]["nome"])
        self.assertNotEqual(res["2005"]["cpf_meio"], res["2006"]["cpf_meio"])

    def test_lgpd_sem_cpf_inteiro(self):
        _, txt = self.rodar()
        self.assertEqual(cpfs_validos(txt), [])
        for cpf in ("52998224725", "11144477735", "39053344705", "12345678909"):
            self.assertNotIn(cpf, txt)
        self.assertEqual(len(json.loads(txt)), 6)

    def test_url_no_baixar(self):
        self.assertIn(baixar.URL_CAND, baixar.ARQUIVOS)


if __name__ == "__main__":
    unittest.main()
