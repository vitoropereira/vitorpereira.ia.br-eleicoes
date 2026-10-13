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
NOMEADOS = lj("nomeados.json")
IDX_NOM = ind.indice_nomeados(NOMEADOS)
C1001 = lj("contas/1001.json")
C1002 = lj("contas/1002.json")
PF = lj("pf_por_campanha.json")
SAQUES = lj("extrato_saques.json")


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
        for k in ("dia_eleicao", "tardio_dias", "tardio_pct_ultimos_dias", "pf_qtd_min", "pf_repetido_min_campanhas",
                  "pf_valor_alto", "pf_redondo_multiplo", "pf_redondo_alto_min_qtd", "saque_termos"):
            self.assertIn(k, cfg)
        self.assertEqual(cfg["dia_eleicao"], "2026-10-04")
        self.assertTrue(cfg["saque_termos"])
        self.assertTrue(cfg["mei_teto_fonte"].strip())
        self.assertTrue(cfg["mei_teto_url"].startswith("https://"))
        self.assertEqual(cfg["mei_teto_anual"], 81000)

    def test_config_das_nomeacoes(self):
        cfg = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
        self.assertRegex(cfg["nomeacoes_mes"], r"^\d{4}-(0[1-9]|1[0-2])$")
        for sigla in ("DAS", "FCPE", "CCE", "FCE", "NES"):
            self.assertTrue(cfg["nomeacoes_funcoes"][sigla].strip(), sigla)
        self.assertEqual(set(cfg["nomeacoes_fontes"]), {"siape", "camara", "senado"})
        self.assertIn("{mes}", cfg["nomeacoes_fontes"]["siape"])
        self.assertTrue(cfg["nomeacoes_fontes"]["siape"].startswith("https://"))

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


def com_pf(**kw):
    """Cópia de C1001 com fornecedores_pf alterado."""
    c = copy.deepcopy(C1001)
    c["despesas"]["fornecedores_pf"].update(kw)
    return c


def com_dias(dias):
    c = copy.deepcopy(C1001)
    c["despesas"]["pago_por_dia"] = dias
    return c


class TestPessoalPf(unittest.TestCase):
    def rodar(self, contas=C1001, pf=PF, **cfg):
        return ind.pessoal_pf("1001", contas, pf, {**CFG, **cfg})

    def por_fato(self, itens, trecho):
        return [i for i in itens if trecho in i["fato"]]

    def test_tres_gatilhos(self):
        r = self.rodar()
        self.assertEqual([i["nome"] for i in r], ["pessoal_pf"] * 3)
        self.assertTrue(all("contraparte" not in i and i["fonte_url"] == ind.URL_CONTAS for i in r))
        cont, rep, red = r
        self.assertIn("5 pessoas físicas", cont["fato"])
        self.assertEqual(cont["valor"], 20800.75)
        self.assertIn("2 pessoas pagas também receberam de outras campanhas", rep["fato"])  # h1 (3) e h2 (2)
        self.assertIn("2 pessoas físicas receberam valores redondos", red["fato"])
        self.assertEqual(red["valor"], 17000.0)

    def test_contagem_abaixo_do_limiar_cala(self):
        self.assertFalse(self.por_fato(self.rodar(pf_qtd_min=6), "pagou 5 pessoas"))
        self.assertTrue(self.por_fato(self.rodar(pf_qtd_min=5), "pagou 5 pessoas"))

    def test_repetidos_abaixo_do_limiar_cala(self):
        self.assertFalse(self.por_fato(self.rodar(pf_repetido_min_campanhas=4), "outras campanhas"))
        r = self.por_fato(self.rodar(pf_repetido_min_campanhas=3), "outras campanhas")
        self.assertIn("1 pessoa paga também recebeu", r[0]["fato"])  # só h1 tem 3 campanhas

    def test_repetidos_sem_arquivo_ou_sem_a_campanha_cala(self):
        self.assertFalse(self.por_fato(self.rodar(pf=None), "outras campanhas"))
        self.assertFalse(self.por_fato(self.rodar(pf={"1001": ["x1", "x2"]}), "outras campanhas"))

    def test_redondos_altos_abaixo_do_limiar_cala(self):
        self.assertFalse(self.por_fato(self.rodar(pf_redondo_alto_min_qtd=3), "redondos"))
        self.assertFalse(self.por_fato(self.rodar(pf_valor_alto=12001), "redondos"))  # nenhum valor chega lá
        self.assertFalse(self.por_fato(self.rodar(pf_redondo_multiplo=7000), "redondos"))

    def test_redondos_fronteira_do_valor_alto(self):
        c = com_pf(valores=[5000.0, 4999.0, 5000.0, 6000.0])
        self.assertEqual(len(self.por_fato(self.rodar(c), "3 pessoas físicas receberam valores redondos")), 1)

    def test_sem_despesas_ou_sem_pf_cala(self):
        sem = copy.deepcopy(C1001)
        sem["despesas"] = None
        self.assertEqual(self.rodar(sem), [])  # mesmo com hashes da campanha no arquivo
        self.assertEqual(self.rodar(C1002, pf={}), [])

    def test_lgpd_sem_nome_nem_cpf(self):
        hash_pf = {"1001": ["h1", "h2"], "1002": ["h1", "h2"]}
        contas = com_pf(valores=[5000.0, 12000.0])
        contas["despesas"]["fornecedores_pf"]["nome"] = "MARIA PF"  # não deve vazar mesmo se vier por engano
        txt = json.dumps(self.rodar(contas, pf=hash_pf), ensure_ascii=False)
        self.assertEqual(cpfs_validos(txt), [])
        for proibido in ("MARIA", "98765432100", "11144477735", "BELTRANO", "h1", "h2"):
            self.assertNotIn(proibido, txt)
        for h in HASH:
            self.assertNotIn(h, txt)
        for d in HASH.values():
            self.assertNotIn(d["nome"], txt)


class TestSaqueEspecie(unittest.TestCase):
    def test_casa_pelo_cnpj_da_campanha(self):
        r = ind.saque_especie("1001", C1001, SAQUES, CFG)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "saque_especie")
        self.assertEqual(r[0]["valor"], 2300.0)
        self.assertEqual(r[0]["fonte_url"], ind.URL_EXTRATO)
        self.assertIn("2 lançamentos", r[0]["fato"])
        self.assertIn("R$ 2.300,00", r[0]["fato"])
        self.assertIn("20/09/2026, 05/10/2026", r[0]["fato"])
        self.assertNotIn("contraparte", r[0])

    def test_extrato_de_outra_campanha_nao_casa(self):
        c = copy.deepcopy(C1001)
        c["cnpj_prestador"] = "11111111000191"
        self.assertEqual(ind.saque_especie("1001", c, SAQUES, CFG), [])

    def test_campanha_sem_cnpj_cala(self):
        c = copy.deepcopy(C1001)
        for v in (None, "", "123"):
            c["cnpj_prestador"] = v
            self.assertEqual(ind.saque_especie("1001", c, SAQUES, CFG), [])
        del c["cnpj_prestador"]
        self.assertEqual(ind.saque_especie("1001", c, SAQUES, CFG), [])

    def test_lgpd(self):
        self.assertEqual(cpfs_validos(json.dumps(ind.saque_especie("1001", C1001, SAQUES, CFG))), [])


class TestPagamentoTardio(unittest.TestCase):
    def rodar(self, dias, **cfg):
        return ind.pagamento_tardio("1001", com_dias(dias), {**CFG, **cfg})

    def test_dois_gatilhos_no_fixture(self):
        r = ind.pagamento_tardio("1001", C1001, CFG)
        self.assertEqual([i["nome"] for i in r], ["pagamento_tardio"] * 2)
        self.assertEqual(r[0]["valor"], 1500.0)
        self.assertIn("depois do dia da eleição (04/10/2026)", r[0]["fato"])
        self.assertEqual(r[1]["valor"], 3500.0)  # 28/09 + 04/10
        self.assertIn("58%", r[1]["fato"])
        self.assertIn("27/09/2026 e 04/10/2026", r[1]["fato"])

    def test_dia_da_eleicao_nao_e_depois(self):
        r = self.rodar({"2026-10-04": 1000.0})
        self.assertEqual([i for i in r if "depois" in i["fato"]], [])

    def test_dia_seguinte_e_depois(self):
        r = self.rodar({"2026-10-05": 1000.0, "2026-08-20": 9000.0})
        self.assertEqual([i["valor"] for i in r], [1000.0])

    def test_fronteira_27_09_dentro_da_janela_e_26_fora(self):
        self.assertEqual(len(self.rodar({"2026-09-27": 600.0, "2026-08-01": 400.0})), 1)
        self.assertEqual(self.rodar({"2026-09-26": 600.0, "2026-08-01": 400.0}), [])

    def test_fracao_exatamente_no_limiar_cala(self):
        self.assertEqual(self.rodar({"2026-09-30": 500.0, "2026-08-01": 500.0}), [])

    def test_sem_despesas_ou_sem_datas_cala_sem_dividir_por_zero(self):
        c = copy.deepcopy(C1001)
        c["despesas"] = None
        self.assertEqual(ind.pagamento_tardio("1001", c, CFG), [])
        self.assertEqual(self.rodar(None), [])
        self.assertEqual(self.rodar({}), [])

    def test_total_pago_zero_cala(self):
        self.assertEqual(self.rodar({"2026-10-05": 0.0, "2026-09-30": 0.0}), [])


class TestSocioNomeado(unittest.TestCase):
    def rodar(self, forn=FORN, idx=IDX_NOM, cnpj="99999999000191"):
        return ind.socio_nomeado("1001", so(C1001, {cnpj}), forn, idx, CFG)

    def test_nome_e_trecho_iguais_dispara(self):
        r = self.rodar()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "socio_ligado")
        self.assertEqual(r[0]["valor"], 15000.0)
        self.assertIn("JOSE DA SILVA", r[0]["fato"])
        self.assertIn("(Portal da Transparência, 09/2026)", r[0]["fato"])
        self.assertIn("função FCPE em MINISTERIO TESTE", r[0]["fato"])
        self.assertTrue(r[0]["fato"].endswith("pode ser homônimo"))
        self.assertEqual(r[0]["fonte_url"], "https://exemplo.invalid/portal/202609")
        self.assertEqual(r[0]["contraparte"], "SOCIEDADE COM SOCIOS LTDA")

    def test_homonimos_com_trechos_diferentes_nao_casam(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "JOSE DA SILVA", "cpf_mascarado": "***654321**"},
                                            {"nome": "JOSE DA SILVA", "cpf_mascarado": "***777777**"}]
        self.assertEqual(self.rodar(forn), [])

    def test_mesmo_trecho_nome_diferente_nao_casa(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "MARIA PEREIRA", "cpf_mascarado": "***123456**"}]
        self.assertEqual(self.rodar(forn), [])

    def test_socio_sem_cpf_mascarado_nao_casa(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "JOSE DA SILVA", "cpf_mascarado": None}]
        self.assertEqual(self.rodar(forn), [])

    def test_fornecedor_mei_fica_de_fora(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["mei"] = True
        self.assertEqual(self.rodar(forn), [])

    def test_mesmo_socio_repetido_gera_um_item(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = [{"nome": "José da Silva", "cpf_mascarado": "***123456**"},
                                            {"nome": "JOSE DA SILVA", "cpf_mascarado": "***123456**"}]
        self.assertEqual(len(self.rodar(forn)), 1)

    def test_fato_sem_acusacao(self):
        fato = self.rodar()[0]["fato"].lower()
        for palavra in ("parente", "fraude", "laranja"):
            self.assertNotIn(palavra, fato)

    def test_lgpd_sem_cpf_nem_trecho(self):
        txt = json.dumps(self.rodar(), ensure_ascii=False)
        self.assertEqual(cpfs_validos(txt), [])
        for meio in ("123456", "654321", "999999"):
            self.assertNotIn(meio, txt)


class TestGerar(unittest.TestCase):
    def gerar(self, hash_path=FIX / "doadores_hash.json", pf_path=FIX / "pf_por_campanha.json",
              saques_path=FIX / "extrato_saques.json", nomeados_path=FIX / "nomeados.json"):
        tmp = tempfile.mkdtemp()
        saida = Path(tmp) / "indicadores.json"
        ind.gerar(FIX / "contas", FIX / "fornecedores.json", FIX / "agregados.json", hash_path, CFG, saida,
                  cnae_x_tipo=TABELA, pf_path=pf_path, saques_path=saques_path, nomeados_path=nomeados_path)
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
                                 "socio_ligado", "pessoal_pf", "pessoal_pf", "pessoal_pf", "saque_especie",
                                 "pagamento_tardio", "pagamento_tardio"])
        self.assertIn(ind.URL_EXTRATO, d["fonte"])
        self.assertIn("https://exemplo.invalid/portal/202609", d["fonte"])
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
        pessoal = [i for itens in json.loads(txt)["indicadores"].values() for i in itens if i["nome"] == "pessoal_pf"]
        self.assertEqual(len(pessoal), 3)
        for proibido in ("MARIA", "98765432100", "11144477735", "h1", "h2", "BELTRANO", "DA SILVA"):
            self.assertNotIn(proibido, json.dumps(pessoal, ensure_ascii=False))

    def test_sem_extrato_e_sem_pf_pulam_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING") as cm:
            _, d = self.gerar(pf_path=FIX / "nao_existe.json", saques_path=None)
        self.assertTrue(any("saque_especie pulado" in m for m in cm.output))
        self.assertTrue(any("pessoal_pf pulado" in m for m in cm.output))
        nomes = [i["nome"] for i in d["indicadores"]["1001"]]
        self.assertNotIn("saque_especie", nomes)
        self.assertEqual(nomes.count("pessoal_pf"), 2)  # sobram contagem e redondos; repetidos precisa do arquivo
        self.assertNotIn(ind.URL_EXTRATO, d["fonte"])

    def test_sem_hash_pula_socio_doador_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            _, d = self.gerar(FIX / "nao_existe.json")
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertEqual(nomes, {"mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel", "socio_ligado",
                                 "pessoal_pf", "saque_especie", "pagamento_tardio"})

    def test_sem_nomeados_pula_socio_ligado_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING") as lg:
            _, d = self.gerar(nomeados_path=FIX / "nao_existe.json")
        self.assertTrue(any("socio_ligado" in m for m in lg.output))
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertNotIn("socio_ligado", nomes)
        self.assertNotIn("https://exemplo.invalid/portal/202609", d["fonte"])


if __name__ == "__main__":
    unittest.main()
