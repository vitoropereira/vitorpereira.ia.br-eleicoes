import json, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "relatorio"


class SenadoPct(unittest.TestCase):
    """Senado: % = votos / (válidos + anulados sub judice), como o TSE (e como o governador oficial)."""

    @classmethod
    def setUpClass(cls):
        cls.rel = json.load(open(R / "relatorio.json"))

    def bruto(self, uf):
        d = json.load(open(R / "dados" / f"{uf.lower()}-c0005.json"))
        return int(d["v"]["vv"]) + int(d["v"]["vansj"])

    def test_p_dos_eleitos_e_do_proximo_sobre_validos_mais_sj(self):
        for s in self.rel["sen"]:
            den = self.bruto(s["uf"])
            for e in s["eleitos"] + [s["proximo"]]:
                self.assertEqual(e["p"], round(100 * e["votos"] / den, 2), f'{s["uf"]} {e["nome"]}')

    def test_ac_bittar_25_59(self):
        ac = next(s for s in self.rel["sen"] if s["uf"] == "AC")
        bittar = next(e for e in ac["eleitos"] if "Bittar" in e["nome"])
        self.assertEqual(bittar["p"], 25.59)

    # o site/ commitado só ganha /1-turno/ quando o lote regenera (a home antiga era o relatório)
    @unittest.skipUnless((R.parent / "site" / "1-turno" / "index.html").exists(), "site/1-turno/ ainda não gerado pelo lote")
    def test_rodape_lidos_em_usa_data_do_tse_nao_a_de_geracao(self):
        html = (R.parent / "site" / "1-turno" / "index.html").read_text()
        nac = self.rel["nac"]
        self.assertIn(f'lidos em {nac["dg"]} {nac["ht"]}', html)
        self.assertIn("lidos em 05/10/2026", html)
        self.assertNotIn("lidos em 08/10", html)


if __name__ == "__main__":
    unittest.main()
