import json
import re
import tempfile
import unittest
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from rastro import anteriores, baixar
from rastro.contas import RE_CPF, cpf_valido

FIX = Path(__file__).resolve().parent / "fixtures" / "rastro" / "anteriores"
A, B, C = "11222333000181", "33333333000191", "77888999000155"
ALVO = {A, B}


def montar_zip(destino, ano):
    nome = f"despesas_contratadas_candidatos_{ano}_BRASIL.csv"
    zip_path = Path(destino) / f"prestacao_de_contas_eleitorais_candidatos_{ano}.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.write(FIX / nome, nome)
    return zip_path


class TestAgregar(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def test_2022(self):
        inv = Counter()
        with self.assertLogs("rastro.anteriores", level="WARNING"):
            res = anteriores.agregar(montar_zip(self.td.name, 2022), ALVO, inv)
        self.assertEqual(res, {A: {"n_campanhas": 2, "total_contratado": 2234.56},  # D1 repetido conta uma vez
                               B: {"n_campanhas": 1, "total_contratado": 500.0}})  # vazio e #NULO não viram 0
        self.assertEqual(inv[anteriores.ARQUIVO], 2)

    def test_nulo_vai_para_o_log(self):
        with self.assertLogs("rastro.anteriores", level="WARNING") as cm:
            anteriores.agregar(montar_zip(self.td.name, 2022), ALVO)
        self.assertEqual(len(cm.output), 2)

    def test_valor_lixo_conta_invalida_e_loga(self):
        inv = Counter()
        with self.assertLogs("rastro.contas", level="WARNING"):
            res = anteriores.agregar(montar_zip(self.td.name, 2024), ALVO, inv)
        self.assertEqual(res, {A: {"n_campanhas": 1, "total_contratado": 2000.0}})
        self.assertEqual(inv[anteriores.ARQUIVO], 1)

    def test_so_cnpj_do_alvo_e_nunca_cpf(self):
        res = anteriores.agregar(montar_zip(self.td.name, 2022), {A, B, C, "52998224725"})
        self.assertEqual(set(res), {A, B, C})
        self.assertTrue(all(len(k) == 14 for k in res))

    def test_datas(self):
        datas = set()
        anteriores.agregar(montar_zip(self.td.name, 2022), ALVO, datas=datas)
        self.assertEqual(datas, {"20/12/2022", "19/12/2022"})


class TestGerar(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        d = Path(self.td.name)
        self.agg = d / "agregados.json"
        self.agg.write_text(json.dumps({"por_cnpj": {A: {}, B: {}}}), encoding="utf-8")
        self.zips = {2022: montar_zip(d, 2022), 2024: montar_zip(d, 2024)}
        self.saida = d / "dados" / "anteriores.json"

    def gerar(self, anos=(2022, 2024), zips=None):
        with self.assertLogs(level="WARNING"):
            anteriores.gerar(list(anos), zips or self.zips, self.agg, self.saida)
        return json.loads(self.saida.read_text(encoding="utf-8"))

    def test_estrutura(self):
        j = self.gerar()
        self.assertEqual(j["anos"], [2022, 2024])
        self.assertEqual(j["fonte"], [baixar.url_contas(2022), baixar.url_contas(2024)])
        self.assertEqual(j["data_base"], "2025-01-10")  # maior DT_GERACAO lido
        self.assertRegex(j["gerado_em"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(j["por_cnpj"][A], {"2022": {"n_campanhas": 2, "total_contratado": 2234.56},
                                            "2024": {"n_campanhas": 1, "total_contratado": 2000.0}})
        self.assertEqual(j["por_cnpj"][B], {"2022": {"n_campanhas": 1, "total_contratado": 500.0}})
        self.assertNotIn(C, j["por_cnpj"])  # não é fornecedor de 2026

    def test_zip_ausente_vira_aviso(self):
        j = self.gerar(zips={2022: self.zips[2022]})
        self.assertEqual(j["anos"], [2022])
        self.assertEqual(j["fonte"], [baixar.url_contas(2022)])
        self.assertNotIn("2024", j["por_cnpj"][A])

    def test_lgpd_sem_cpf_nem_nome(self):
        texto = self.gerar() and self.saida.read_text(encoding="utf-8")
        for m in re.finditer(RE_CPF, texto):
            self.assertFalse(cpf_valido(re.sub(r"\D", "", m.group())), m.group())
        for nome in ("FULANO", "JOSE", "GRAFICA", "EMPRESA"):
            self.assertNotIn(nome, texto)
        self.assertNotIn("52998224725", texto)


class TestMain(unittest.TestCase):
    def test_dia_da_apuracao_aborta_antes_do_head(self):
        def opener(*a, **k):
            raise AssertionError("não devia pedir nada ao TSE")
        with self.assertRaises(SystemExit):
            anteriores.main(["--baixar"], opener, date(2026, 10, 25))

    def test_config_tem_os_anos(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "rastro" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["anteriores_anos"], [2022, 2024])


if __name__ == "__main__":
    unittest.main()
