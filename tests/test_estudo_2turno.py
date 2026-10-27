"""Estudo do 2º turno (/estudo-2-turno/): a conta dos votos novos fecha com as contagens do TSE e a página traz as
seções e o aviso sobre a estimativa. Usa o analise/estudo2t/estudo.json gerado por analise/estudo_2turno.py."""
import json, re, sys, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B

EST = json.loads(B.ESTUDO2T_ARQ.read_text())


class Conta(unittest.TestCase):
    def test_votos_novos_vem_de_outros_brancos_nulos_e_comparecimento(self):
        f = EST["fatos"]; t1, t2, b = f["t1"], f["t2"], f["bolo"]
        self.assertEqual(b["total"], (t2["L"] + t2["F"]) - (t1["L"] + t1["F"]))
        self.assertEqual(b["total"], b["outros"] + b["bn"] + b["comparecimento"])

    def test_virada_bate_com_os_saldos(self):
        f = EST["fatos"]
        self.assertEqual(f["virada"], f["saldo2"] - f["saldo1"])
        # a soma das UFs (municípios, sem o exterior) fica a menos de 1% da virada do Brasil
        self.assertLess(abs(sum(u["virada"] for u in EST["ufs"]) - f["virada"]) / f["virada"], 0.01)

    def test_transferencia_reconcilia_com_os_totais_do_1o_turno(self):
        tot = {x["de"]: x["total"] for x in EST["transferencia"]}
        t1 = EST["fatos"]["t1"]
        # só municípios (sem exterior): fica abaixo do Brasil, mas perto
        self.assertLess(abs(tot["Lula"] - t1["L"]) / t1["L"], 0.01)
        for x in EST["transferencia"]:
            self.assertAlmostEqual(sum(c["pct"] for c in x["para"]), 100, delta=0.3)


class Pagina(unittest.TestCase):
    html = B.pagina_estudo2t("<style></style>", EST)

    def test_secoes(self):
        for h in ["A conta que fecha", "Onde a diferença mudou", "Onde houve mais branco e nulo, Lula cresceu mais",
                  "Abstenção, brancos e nulos desde 2002", "Votos depois das 17h",
                  "10 milhões de votos em 3 semanas: o volume é comum, a virada não"]:
            self.assertIn(f"<h2>{h}</h2>", self.html)

    def test_padrao_avisa_que_nao_prova_e_nao_mostra_a_estimativa_como_resultado(self):
        visivel = re.sub(r"<details>.*?</details>", "", self.html, flags=re.S)
        self.assertIn("Não prova que foram os mesmos eleitores", visivel)
        self.assertNotIn("No 1º turno votou em", self.html)  # a tabela de transferência saiu da página
        self.assertIn("<svg", visivel)

    def test_faixas_de_brancos_e_nulos(self):
        fx = EST["faixas_bn"]
        self.assertEqual(len(fx), 10)
        self.assertEqual(sum(f["municipios"] for f in fx), EST["gerado_com"]["municipios"])
        self.assertEqual([f["bn"] for f in fx], sorted(f["bn"] for f in fx))  # do grupo com menos ao com mais
        t1, t2 = EST["fatos"]["t1"], EST["fatos"]["t2"]
        ganho = sum(f["lula"] * f["eleitores"] / 100 for f in fx)
        self.assertLess(abs(ganho - (t2["L"] - t1["L"])) / (t2["L"] - t1["L"]), 0.02)  # sem o exterior

    def test_serie_tem_2002_a_2026(self):
        anos = sorted({s["ano"] for s in EST["serie"]})
        self.assertEqual(anos, [2002, 2006, 2010, 2014, 2018, 2022, 2026])
        for a in anos:
            self.assertIn(f"<td>{a}</td>", self.html)


class Finalistas(unittest.TestCase):
    F = {x["ano"]: x for x in EST["finalistas"]}

    def test_fatias_somam_100_e_2026_bate_com_o_tse(self):
        for x in EST["finalistas"]:
            self.assertAlmostEqual(x["fatia1"] + x["fatia2"], 100, delta=0.15)
        f = EST["fatos"]
        self.assertEqual((self.F[2026]["ganho1"], self.F[2026]["ganho2"]), (f["ganho"]["F"], f["ganho"]["L"]))

    def test_padrao_o_2o_colocado_leva_a_maior_fatia_menos_em_2006(self):
        fora = [a for a, x in self.F.items() if x["fatia2"] <= x["fatia1"]]
        self.assertEqual(fora, [2006])

    def test_2026_e_a_unica_virada(self):
        self.assertEqual([a for a, x in self.F.items() if x["venceu"] == x["segundo"]], [2026])

    def test_municipios_e_regioes_fecham(self):
        m = EST["municipios"]
        self.assertEqual(m["lula1"] + m["flavio1"], EST["gerado_com"]["municipios"])
        self.assertEqual(m["lula2"] - m["lula1"], m["f_para_l"] - m["l_para_f"])
        self.assertEqual(sum(r["virada"] for r in EST["regioes"]), sum(u["virada"] for u in EST["ufs"]))


if __name__ == "__main__":
    unittest.main()
