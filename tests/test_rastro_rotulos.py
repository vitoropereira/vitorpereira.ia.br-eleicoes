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

    def test_niveis_da_issue(self):  # issue #63: alto, médio e baixo por indicador
        alto = ["situacao_irregular", "mei_acima_teto", "empresa_recem_aberta", "socio_doador", "socio_ligado", "socio_nomeado",
                "valores_identicos", "endereco_compartilhado", "atividade_incompativel", "concentracao"]
        medio = ["preco_fora_da_curva", "gasto_por_voto", "pessoal_pf"]
        for n in alto:
            self.assertEqual(peso(n, CFG), 3, n)
        for n in medio:
            self.assertEqual(peso(n, CFG), 2, n)
        self.assertEqual([n for n, p in CFG["destaque_pesos"].items() if p == 1], ["multicampanha"])


if __name__ == "__main__":
    unittest.main()
