import json
import os
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from rastro import extrato

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "extrato"
CSV = FIX / "extrato_bancario_candidato_2026_BRASIL.csv"
TERMOS = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))["saque_termos"]
CPF_CONTRAPARTE = "11144477735"


def zipar(destino, nome=CSV.name):
    z = Path(destino) / "extrato.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(CSV, nome)
        zf.writestr("leiame.txt", "ignorar")
    return z


class TestLerExtrato(unittest.TestCase):
    def ler(self, **kw):
        inval = Counter()
        with tempfile.TemporaryDirectory() as td:
            z = zipar(td, **kw)
            with self.assertLogs("rastro.extrato", level="WARNING") as cm:
                res = extrato.ler_extrato(z, TERMOS, inval)
            self.assertEqual(os.listdir(td), ["extrato.zip"])  # nada extraído para o disco
        return res, inval, cm.output

    def test_so_saque_e_especie(self):
        res, _, _ = self.ler()
        self.assertEqual(set(res), {"12345678000195", "22345678000195"})
        l = res["12345678000195"]
        self.assertEqual([(x["data"], x["valor"]) for x in l], [("2026-09-20", 1500.0), ("2026-10-05", 800.0)])
        self.assertEqual(res["22345678000195"][0]["valor"], 300.0)
        self.assertNotIn("TED", json.dumps(res))

    def test_valor_nulo_conta_loga_e_nao_vira_zero(self):
        res, inval, log = self.ler()
        self.assertEqual(inval["extrato_bancario"], 1)
        self.assertIn("ausente ou inválido", log[0])
        self.assertNotIn(0.0, [x["valor"] for v in res.values() for x in v])
        self.assertEqual(len(res["12345678000195"]), 2)

    def test_contraparte_nunca_e_guardada(self):
        res, _, _ = self.ler()
        txt = json.dumps(res, ensure_ascii=False)
        for proibido in (CPF_CONTRAPARTE, "98765432100", "BELTRANO", "MARIA", "GRAFICA"):
            self.assertNotIn(proibido, txt)
        for itens in res.values():
            for x in itens:
                self.assertEqual(set(x), {"data", "ds", "tp", "valor"})

    def test_unico_csv_sem_sufixo_brasil(self):
        res, _, _ = self.ler(nome="qualquer_nome.csv")
        self.assertEqual(len(res["12345678000195"]), 2)

    def test_zip_sem_csv_levanta(self):
        with tempfile.TemporaryDirectory() as td:
            z = Path(td) / "vazio.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("leiame.txt", "x")
            with self.assertRaises(FileNotFoundError):
                extrato.ler_extrato(z, TERMOS)


if __name__ == "__main__":
    unittest.main()
