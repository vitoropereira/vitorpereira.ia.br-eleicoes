"""Projeção do 2º turno (gerar_2turno.py): UF sem apuração entra pela base do 1º turno deslocada pelas pesquisas;
UF com pouca apuração mistura o % atual com essa base; UF com apuração alta segue só o % atual."""
import sys, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import gerar_2turno as G


def uf(nome, pst, f, l, vv=None):
    vv = f + l if vv is None else vv
    return dict(uf=nome, ht="17:00:00", pst=pst, ts=100, st=int(pst), te=1000, vv=vv, cand={G.F: f, G.L: l}, sg={})


class Projecao(unittest.TestCase):
    # 1º turno: Flávio 60% entre os dois em AA, 40% em BB; nacional 50%
    U1 = {"AA": uf("AA", 100, 600, 400), "BB": uf("BB", 100, 400, 600)}
    POLLS = [("X", "", 48, 52)]  # Flávio 52% → desloca +2 pt

    def test_uf_sem_apuracao_usa_a_base_deslocada(self):
        base, desloc, f1n, pol_f = G.projetar([uf("AA", 0, 0, 0), uf("BB", 0, 0, 0)], self.U1, self.POLLS)
        self.assertAlmostEqual(desloc, 0.02)
        self.assertAlmostEqual(base[0]["fr"], 0.62)
        self.assertAlmostEqual(base[1]["fr"], 0.42)
        self.assertEqual(base[0]["tot"], 1000)  # válidos dos dois no 1º turno
        f, l = G.proj(base)
        self.assertAlmostEqual(f, 52.0)
        self.assertAlmostEqual(f + l, 100.0)

    def test_pouca_apuracao_mistura_com_a_base(self):
        # 15% apurado, Flávio 30% ali: peso 15/30 = 0,5 → 0,5·0,30 + 0,5·0,62 = 0,46
        base, *_ = G.projetar([uf("AA", 15, 30, 70), uf("BB", 0, 0, 0)], self.U1, self.POLLS, mistura=30)
        self.assertAlmostEqual(base[0]["fr"], 0.46)

    def test_apuracao_alta_segue_so_o_atual(self):
        base, *_ = G.projetar([uf("AA", 60, 300, 300), uf("BB", 0, 0, 0)], self.U1, self.POLLS, mistura=30)
        self.assertAlmostEqual(base[0]["fr"], 0.5)
        self.assertAlmostEqual(base[0]["tot"], 1000)  # 600 válidos com 60% → 1000

    def test_shift_vai_para_lula(self):
        base, *_ = G.projetar([uf("AA", 0, 0, 0), uf("BB", 0, 0, 0)], self.U1, self.POLLS)
        f0, _ = G.proj(base)
        f1, _ = G.proj(base, 0.01)
        self.assertAlmostEqual(f0 - f1, 1.0)


if __name__ == "__main__":
    unittest.main()
