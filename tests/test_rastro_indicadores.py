import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from rastro import contas as rcontas
from rastro import indicadores as ind

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "indicadores"


def lj(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


CFG = lj("config.json")
TABELA = lj("cnae_x_tipo.json")
FORN = lj("fornecedores.json")["fornecedores"]
AGR = lj("agregados.json")
HASH = lj("doadores_hash.json")
C1001 = lj("contas/1001.json")
C1002 = lj("contas/1002.json")
ELEITOS = lj("eleitos.json")["eleitos"]
E1001, E1002 = ELEITOS


def so(contas, cnpjs):
    """Cópia de contas só com os fornecedores pedidos."""
    c = copy.deepcopy(contas)
    desp = c["despesas"]
    desp["fornecedores_pj"] = [f for f in desp["fornecedores_pj"] if f["cnpj"] in cnpjs]
    return c


def cpfs_validos(txt):
    achados = []
    for m in re.finditer(r"\d[\d.\-\s]{9,17}\d", txt):
        d = re.sub(r"\D", "", m.group())
        if rcontas.cpf_valido(d):
            achados.append(d)
    return achados


class TestConfig(unittest.TestCase):
    def test_chaves_e_fontes(self):
        cfg = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
        for k in ("mei_teto_anual", "mei_teto_fonte", "campanha_inicio", "recem_aberta_dias"):
            self.assertIn(k, cfg)
        self.assertTrue(cfg["mei_teto_fonte"].strip())
        self.assertTrue(cfg["mei_teto_url"].startswith("https://"))
        self.assertEqual(cfg["mei_teto_anual"], 81000)
        self.assertEqual((cfg["percentil_comparacao"], cfg["min_campanhas_grupo"], cfg["quantis_metodo"]),
                         (95, 10, "inclusive"))
        self.assertGreater(cfg["votacao_infima_fracao_eleitorado"], 0)

    def test_tabela_tem_nota_e_listas(self):
        tabela = json.loads((RAIZ / "rastro" / "cnae_x_tipo.json").read_text(encoding="utf-8"))
        self.assertIn("revis", tabela["_nota"])
        for k, v in tabela.items():
            if k != "_nota":
                self.assertTrue(v and all(isinstance(p, str) for p in v), k)


class TestMei(unittest.TestCase):
    def rodar(self, cnpj):
        return ind.mei_acima_teto("1001", so(C1001, {cnpj}), FORN, AGR, CFG)

    def test_mei_acima_dispara(self):
        r = self.rodar("11111111000191")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "mei_acima_teto")
        self.assertEqual(r[0]["valor"], 90000.0)
        self.assertIn("2 campanhas", r[0]["fato"])
        self.assertIn("81.000,00", r[0]["fato"])
        self.assertEqual(r[0]["contraparte"], "**.***.***/0001-**")

    def test_mei_abaixo_nao_dispara(self):
        self.assertEqual(self.rodar("22222222000191"), [])

    def test_nao_mei_nao_dispara(self):
        self.assertEqual(self.rodar("33333333000191"), [])

    def test_cnpj_inteiro_nunca_aparece(self):
        txt = json.dumps(self.rodar("11111111000191"), ensure_ascii=False)
        self.assertNotIn("11111111", txt)
        self.assertNotIn("000191", txt)

    def test_mascarar_cnpj(self):
        self.assertEqual(ind.mascarar_cnpj("12.345.678/0002-95"), "**.***.***/0002-**")
        self.assertEqual(ind.mascarar_cnpj("123"), "**.***.***/****-**")


class TestRecemAberta(unittest.TestCase):
    def rodar(self, cnpj, abertura=...):
        forn = copy.deepcopy(FORN)
        if abertura is not ...:
            forn[cnpj]["abertura"] = abertura
        return ind.empresa_recem_aberta("1001", so(C1001, {cnpj}), forn, CFG)

    def test_aberta_em_2026_dispara(self):
        r = self.rodar("44444444000191")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["valor"], 30000.0)
        self.assertIn("10/01/2026", r[0]["fato"])
        self.assertEqual(r[0]["contraparte"], "EMPRESA NOVA LTDA")

    def test_fronteira(self):
        self.assertEqual(self.rodar("55555555000191"), [])  # 2025-08-15
        self.assertEqual(self.rodar("55555555000191", "2025-08-16"), [])
        self.assertEqual(len(self.rodar("55555555000191", "2025-08-17")), 1)

    def test_aberta_depois_do_inicio_dispara(self):
        r = self.rodar("55555555000191", "2026-09-01")
        self.assertEqual(len(r), 1)
        self.assertIn("depois do início", r[0]["fato"])

    def test_abertura_nula_nao_dispara(self):
        self.assertEqual(self.rodar("44444444000191", None), [])


class TestAtividade(unittest.TestCase):
    def rodar(self, cnpj, forn=FORN, contas=C1001):
        return ind.atividade_incompativel("1001", so(contas, {cnpj}), forn, TABELA)

    def test_grafica_paga_como_combustivel_dispara(self):
        r = self.rodar("66666666000191")
        self.assertEqual(len(r), 1)
        self.assertIn("1813001", r[0]["fato"])
        self.assertIn("Combustíveis e lubrificantes", r[0]["fato"])
        self.assertEqual(r[0]["valor"], 20000.0)

    def test_grafica_paga_como_impressos_nao_dispara(self):
        self.assertEqual(self.rodar("77777777000191"), [])

    def test_tipo_fora_da_tabela_nao_dispara(self):
        self.assertEqual(self.rodar("88888888000191"), [])

    def test_um_tipo_compativel_basta_para_calar(self):
        c = so(C1001, {"66666666000191"})
        c["despesas"]["fornecedores_pj"][0]["tipos"] = ["Combustíveis e lubrificantes",
                                                        "Publicidade por materiais impressos"]
        self.assertEqual(ind.atividade_incompativel("1001", c, FORN, TABELA), [])

    def test_tipo_fora_da_tabela_junto_de_incompativel_cala(self):
        c = so(C1001, {"66666666000191"})
        c["despesas"]["fornecedores_pj"][0]["tipos"] = ["Combustíveis e lubrificantes", "Serviços prestados por terceiros"]
        self.assertEqual(ind.atividade_incompativel("1001", c, FORN, TABELA), [])

    def test_cnae_ausente_nao_dispara(self):
        forn = copy.deepcopy(FORN)
        forn["66666666000191"]["cnae"] = None
        c = so(C1001, {"66666666000191"})
        c["despesas"]["fornecedores_pj"][0]["cnae"] = None
        self.assertEqual(ind.atividade_incompativel("1001", c, forn, TABELA), [])

    def test_cnae_da_conta_como_reserva(self):
        forn = copy.deepcopy(FORN)
        forn["66666666000191"]["cnae"] = None
        self.assertEqual(len(self.rodar("66666666000191", forn)), 1)


class TestSocioDoador(unittest.TestCase):
    def rodar(self, forn=FORN, doadores=HASH):
        return ind.socio_doador("1001", so(C1001, {"99999999000191"}), forn, doadores)

    def test_nome_e_trecho_iguais_dispara(self):
        r = self.rodar()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "socio_doador")
        self.assertEqual(r[0]["valor"], 5000.0)
        self.assertIn("JOSE DA SILVA", r[0]["fato"])
        self.assertIn("2 campanhas", r[0]["fato"])
        self.assertTrue(r[0]["fato"].endswith("pode ser homônimo"))
        self.assertEqual(r[0]["contraparte"], "SOCIEDADE COM SOCIOS LTDA")

    def test_homonimos_com_trechos_diferentes_nao_casam(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "JOSE DA SILVA", "cpf_mascarado": "***654321**"},
                                            {"nome": "JOSE DA SILVA", "cpf_mascarado": "***777777**"}]
        self.assertEqual(self.rodar(forn), [])

    def test_mesmo_trecho_nome_diferente_nao_casa(self):
        # MARIA PEREIRA ***111111** x doadora ANA LIMA 111111
        self.assertFalse([i for i in self.rodar() if "MARIA" in i["fato"] or "ANA LIMA" in i["fato"]])

    def test_socio_sem_cpf_mascarado_nao_casa(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "ANA LIMA", "cpf_mascarado": None}]
        self.assertEqual(self.rodar(forn), [])

    def test_so_papel_doador_ou_ambos(self):
        self.assertEqual(self.rodar(), self.rodar(doadores={k: v for k, v in HASH.items() if k != "dddd"}))
        self.assertFalse([i for i in self.rodar() if "PAULO" in i["fato"]])
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "Ana Lima", "cpf_mascarado": "***111111**"}]
        self.assertEqual(len(self.rodar(forn)), 1)  # papel 'ambos'

    def test_lgpd_sem_cpf_nem_trecho(self):
        txt = json.dumps(self.rodar(), ensure_ascii=False)
        self.assertEqual(cpfs_validos(txt), [])
        for meio in ("123456", "654321", "111111", "999999"):
            self.assertNotIn(meio, txt)
        self.assertNotIn("aaaa", txt)


class TestPercentil(unittest.TestCase):
    def test_lista_conhecida(self):
        self.assertAlmostEqual(ind.percentil(list(range(1, 21)), CFG), 19.05)

    def test_menos_de_n_campanhas_nao_calcula(self):
        self.assertIsNone(ind.percentil(list(range(1, 10)), CFG))
        self.assertIsNotNone(ind.percentil(list(range(1, 11)), CFG))

    def test_limiares_vem_do_config(self):
        cfg = {**CFG, "min_campanhas_grupo": 3, "percentil_comparacao": 50}
        self.assertEqual(ind.percentil([1, 2, 3], cfg), 2)


class TestPrecoForaDaCurva(unittest.TestCase):
    def rodar(self, por_tipo, agr=AGR):
        c = copy.deepcopy(C1001)
        c["despesas"]["por_tipo"] = por_tipo
        return ind.preco_fora_da_curva("1001", c, E1001, agr, CFG)

    def test_acima_do_p95_dispara(self):
        r = self.rodar({"Serviços prestados por terceiros": 20000.0})
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "preco_fora_da_curva")
        self.assertEqual(r[0]["valor"], 20000.0)
        self.assertEqual(r[0]["fonte_url"], ind.URL_CONTAS)
        for trecho in ("20.000,00", "11.450,00", "12 campanhas", "33,33 por mil eleitores"):
            self.assertIn(trecho, r[0]["fato"])

    def test_abaixo_cala(self):
        self.assertEqual(self.rodar({"Serviços prestados por terceiros": 5000.0}), [])

    def test_grupo_com_menos_de_n_cala(self):
        self.assertEqual(self.rodar({"Publicidade por materiais impressos": 900000.0}), [])

    def test_tipo_ausente_do_grupo_cala(self):
        self.assertEqual(self.rodar({"Tipo inexistente": 900000.0}), [])

    def test_sem_por_tipo_ou_sem_eleito_cala(self):
        self.assertEqual(ind.preco_fora_da_curva("1001", C1002, E1002, AGR, CFG), [])
        self.assertEqual(ind.preco_fora_da_curva("1001", C1001, {}, AGR, CFG), [])


class TestGastoPorVoto(unittest.TestCase):
    def rodar(self, eleito=E1001, contas=C1001, agr=AGR):
        return ind.gasto_por_voto("1001", contas, eleito, agr, CFG)

    def test_acima_dispara(self):
        r = self.rodar()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "gasto_por_voto")
        self.assertEqual(r[0]["valor"], 20.0)
        self.assertIn("11,45", r[0]["fato"])

    def test_abaixo_cala(self):
        self.assertEqual(self.rodar({**E1001, "votos": 100000}), [])

    def test_grupo_menor_que_n_cala(self):
        c = copy.deepcopy(C1002)
        c["despesas"]["total_contratado"] = 999999.0
        self.assertEqual(self.rodar(E1002, c), [])

    def test_sem_votos_ou_sem_despesas_cala(self):
        self.assertEqual(self.rodar({**E1001, "votos": 0}), [])
        self.assertEqual(self.rodar({**E1001, "votos": None}), [])
        self.assertEqual(self.rodar(contas={**C1001, "despesas": None}), [])
        self.assertEqual(self.rodar(contas={**C1001, "prestacao_parcial": False}), [])


class TestTransferencia(unittest.TestCase):
    def rodar(self, agr=AGR, forn=None, contas=C1001):
        return ind.transferencia_candidato("1001", contas, agr, agr["eleitorado"], CFG, forn)

    def test_dispara_com_fornecedor_em_comum_e_destaca_infima_primeiro(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            r = self.rodar(forn=FORN)
        self.assertEqual([i["contraparte"] for i in r], ["CANDIDATO INFIMO", "CANDIDATO VOTADO"])
        self.assertEqual([i["valor"] for i in r], [3000.0, 1000.0])
        self.assertIn("teve 20 votos (votação ínfima)", r[0]["fato"])
        self.assertNotIn("ínfima", r[1]["fato"])
        self.assertIn("EMPRESA GRANDE LTDA", r[1]["fato"])
        self.assertTrue(all(i["nome"] == "transferencia_candidato" and i["fonte_url"] == ind.URL_CONTAS for i in r))

    def test_mei_em_comum_sai_mascarado(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            r = self.rodar(forn=FORN)
        self.assertIn("**.***.***/0001-**", r[0]["fato"])
        self.assertNotIn("MEI PEQUENO", r[0]["fato"])
        self.assertNotIn("22222222", r[0]["fato"])

    def test_sem_dados_da_receita_mascara_todos(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            r = self.rodar()
        self.assertNotIn("EMPRESA GRANDE", json.dumps(r, ensure_ascii=False))

    def test_sem_fornecedor_em_comum_cala(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            r = self.rodar(forn=FORN)
        self.assertNotIn("CANDIDATO SEM COMUM", json.dumps(r))

    def test_recebedor_sem_dados_cala_com_log(self):
        with self.assertLogs("rastro.indicadores", level="WARNING") as cm:
            self.rodar(forn=FORN)
        self.assertTrue(any("2004" in m for m in cm.output))

    def test_votos_desconhecidos_nao_viram_infima(self):
        agr = copy.deepcopy(AGR)
        agr["candidatos"]["2001"]["votos"] = None
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            r = self.rodar(agr, FORN)
        self.assertNotIn("ínfima", json.dumps(r, ensure_ascii=False))

    def test_sem_repasse_cala(self):
        self.assertEqual(ind.transferencia_candidato("1002", C1002, AGR, AGR["eleitorado"], CFG, FORN), [])


class TestGerar(unittest.TestCase):
    def gerar(self, hash_path=FIX / "doadores_hash.json", eleitos_path=FIX / "eleitos.json"):
        tmp = tempfile.mkdtemp()
        saida = Path(tmp) / "indicadores.json"
        ind.gerar(FIX / "contas", FIX / "fornecedores.json", FIX / "agregados.json", hash_path, CFG, saida,
                  cnae_x_tipo=TABELA, eleitos_path=eleitos_path)
        return saida.read_text(encoding="utf-8"), json.loads(saida.read_text(encoding="utf-8"))

    def test_forma_envelope_e_ordem(self):
        txt, d = self.gerar()
        self.assertEqual(set(d), {"fonte", "data_base", "gerado_em", "indicadores"})
        self.assertEqual(d["data_base"], "2026-09-01")
        self.assertIn("https://exemplo.invalid/receita", d["fonte"])
        self.assertIn("https://exemplo.invalid/tse", d["fonte"])
        self.assertEqual(list(d["indicadores"]), ["1001"])
        nomes = [i["nome"] for i in d["indicadores"]["1001"]]
        self.assertEqual(nomes, ["mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel", "socio_doador",
                                "preco_fora_da_curva", "gasto_por_voto", "transferencia_candidato",
                                "transferencia_candidato"])
        for itens in d["indicadores"].values():
            for i in itens:
                self.assertEqual(set(i) - {"contraparte"}, {"nome", "fato", "valor", "fonte_url"})
        self.assertEqual(self.gerar()[1]["indicadores"], d["indicadores"])

    def test_eleito_sem_indicador_fica_de_fora(self):
        _, d = self.gerar()
        self.assertNotIn("1002", d["indicadores"])  # só a empresa grande, aberta em 2010

    def test_lgpd_no_arquivo_inteiro(self):
        txt, _ = self.gerar()
        self.assertEqual(cpfs_validos(txt), [])
        self.assertNotIn("11111111000191", txt)
        for meio in ("123456", "654321", "999999"):
            self.assertNotIn(meio, txt)
        for proibida in ("fraude", "laranja", "fictícia"):
            self.assertNotIn(proibida, txt.lower())

    def test_sem_hash_pula_socio_doador_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            _, d = self.gerar(FIX / "nao_existe.json")
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertEqual(nomes, {"mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel",
                                 "preco_fora_da_curva", "gasto_por_voto", "transferencia_candidato"})

    def test_eleito_fora_do_eleitos_json_pula_so_os_de_votos(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            _, d = self.gerar(eleitos_path=FIX / "nao_existe.json")
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertNotIn("preco_fora_da_curva", nomes)
        self.assertNotIn("gasto_por_voto", nomes)
        self.assertIn("transferencia_candidato", nomes)


if __name__ == "__main__":
    unittest.main()
