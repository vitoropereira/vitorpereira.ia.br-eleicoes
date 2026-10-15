import json
import unittest
from pathlib import Path

from rastro import paginas as pg
from rastro.rotulos import ROTULOS, peso

RAIZ = Path(__file__).resolve().parent.parent
CFG = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
PUBLICADO = json.loads((RAIZ / "rastro" / "dados" / "indicadores.json").read_text(encoding="utf-8"))


def nomes():
    out = {n for n, _ in pg.descricoes(CFG)} | {"socio_nomeado"}
    return out | {i["nome"] for itens in PUBLICADO["indicadores"].values() for i in itens}


class TestRotulos(unittest.TestCase):
    def test_todo_indicador_tem_rotulo_e_peso(self):
        for n in nomes():
            self.assertIn(n, ROTULOS, n)
            self.assertIn(n, CFG["destaque_pesos"], n)
            self.assertIn(peso(n, CFG), (1, 2, 3), n)

    def test_redacao_neutra(self):
        for n, r in ROTULOS.items():
            self.assertIsNone(pg.termo_proibido(r), n)
            self.assertNotIn("_", r, n)

    def test_niveis(self):
        self.assertGreater(peso("situacao_irregular", CFG), peso("preco_fora_da_curva", CFG))
        self.assertEqual(peso("valores_identicos", CFG), 3)
        self.assertEqual(peso("multicampanha", CFG), 1)


if __name__ == "__main__":
    unittest.main()
