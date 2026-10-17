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
C1003 = lj("contas/1003.json")
CAND = lj("candidatos.json")
PARTE2 = ("multicampanha_min", "concentracao_pct", "endereco_min_fornecedores", "situacoes_irregulares",
          "sobrenome_particulas", "sobrenomes_comuns")
TODOS = {"mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel", "socio_doador", "socio_ligado",
         "multicampanha", "situacao_irregular", "concentracao", "endereco_compartilhado",
         "preco_fora_da_curva", "gasto_por_voto", "transferencia_candidato",
         "pessoal_pf", "saque_especie", "pagamento_tardio"}
ELEITOS = lj("eleitos.json")["eleitos"]
E1001, E1002 = ELEITOS
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
        self.assertEqual((cfg["percentil_comparacao"], cfg["min_campanhas_grupo"], cfg["quantis_metodo"]),
                         (95, 10, "inclusive"))
        self.assertGreater(cfg["votacao_infima_fracao_eleitorado"], 0)

    def test_config_das_nomeacoes(self):
        cfg = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
        self.assertRegex(cfg["nomeacoes_mes"], r"^\d{4}-(0[1-9]|1[0-2])$")
        for sigla in ("DAS", "FCPE", "CCE", "FCE", "NES"):
            self.assertTrue(cfg["nomeacoes_funcoes"][sigla].strip(), sigla)
        self.assertEqual(set(cfg["nomeacoes_fontes"]), {"siape", "camara", "senado"})
        self.assertIn("{mes}", cfg["nomeacoes_fontes"]["siape"])
        self.assertTrue(cfg["nomeacoes_fontes"]["siape"].startswith("https://"))

    def test_chaves_da_parte_2(self):
        cfg = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
        for k in ("multicampanha_min", "concentracao_pct", "endereco_min_fornecedores"):
            self.assertGreater(cfg[k], 0, k)
        for k in ("situacoes_irregulares", "sobrenome_particulas", "sobrenomes_comuns"):
            self.assertTrue(cfg[k] and all(isinstance(x, str) and x for x in cfg[k]), k)
        for k in PARTE2:  # o fixture diverge de propósito em outras chaves (pf_*, nomeacoes_*), nestas não
            self.assertEqual(cfg[k], CFG[k], k)

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
        self.assertEqual(r[0]["valor"], 725.0)  # 725.000 contratados / 1.000 votos
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
        # NOME · UF · SIGLA; sem a sigla no dado, sai sem partido (não inventa)
        self.assertEqual([i["contraparte"] for i in r], ["CANDIDATO INFIMO · AC · PZ", "CANDIDATO VOTADO · AC"])
        self.assertIn("a CANDIDATO INFIMO · AC · PZ, que usou", r[0]["fato"])
        self.assertEqual([i["valor"] for i in r], [3000.0, 1000.0])
        self.assertIn("teve 20 votos (votação ínfima)", r[0]["fato"])
        self.assertNotIn("ínfima", r[1]["fato"])
        self.assertIn("EMPRESA GRANDE LTDA", r[1]["fato"])
        self.assertTrue(all(i["nome"] == "transferencia_candidato" and i["fonte_url"] == ind.URL_CONTAS for i in r))

    def test_recebedor_sem_partido_completa_pelo_tse_baixado(self):
        """agregados.json antigo, sem `partido` em candidatos: a sigla vem de relatorio/dados (issue #78); a que já veio
        no agregados não é trocada"""
        partidos = ind.ler_partidos(FIX / "relatorio_dados")
        self.assertEqual(partidos, {"2002": ("AC", "PQ"), "2001": ("AC", "PW")})
        agr = ind.completar_recebedores(copy.deepcopy(AGR), partidos)
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            r = self.rodar(agr=agr, forn=FORN)
        self.assertEqual([i["contraparte"] for i in r], ["CANDIDATO INFIMO · AC · PZ", "CANDIDATO VOTADO · AC · PQ"])
        self.assertIn("a CANDIDATO VOTADO · AC · PQ, que usou", r[1]["fato"])

    def test_recebedor_sem_uf_completa_pelo_tse_baixado(self):
        agr = ind.completar_recebedores({"candidatos": {"2002": {"nome": "X"}}}, {"2002": ("AC", "PQ")})
        self.assertEqual(ind.rotulo_recebedor(agr["candidatos"]["2002"]), "X · AC · PQ")
        self.assertEqual(ind.completar_recebedores({"candidatos": {"9": {"nome": "Y"}}}, {})["candidatos"]["9"], {"nome": "Y"})

    def test_recebedor_sem_nome_fica_outro_candidato(self):
        self.assertEqual(ind.rotulo_recebedor({"nome": None, "uf": "AC", "partido": "PZ"}), "outro candidato")

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


class TestSobrenomes(unittest.TestCase):
    def test_particulas_e_comuns_saem(self):
        self.assertEqual(ind.sobrenomes("MARIA DOS SANTOS PEREIRA", CFG), set())
        self.assertEqual(ind.sobrenomes("MARIA DOS SANTOS BRANDAO", CFG), {"BRANDAO"})

    def test_prenome_nao_conta(self):
        self.assertEqual(ind.sobrenomes("BRANDAO MOTA", CFG), {"MOTA"})

    def test_acentos_normalizados(self):
        self.assertEqual(ind.sobrenomes("Carlos Brandão da Mota", CFG), {"BRANDAO", "MOTA"})
        self.assertEqual(ind.sobrenomes("Ana Gonçalves Pires", CFG), {"PIRES"})

    def test_nome_de_uma_palavra(self):
        self.assertEqual(ind.sobrenomes("MADONNA", CFG), set())
        self.assertEqual(ind.sobrenomes("", CFG), set())


class TestSocioLigado(unittest.TestCase):
    def rodar(self, cand=CAND, forn=FORN):
        return ind.socio_ligado("1001", so(C1001, {"99999999000191"}), forn, cand, CFG)

    def socios(self, *socios):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["socios"] = list(socios)
        return forn

    def test_ramo_candidato_dispara(self):
        r = [i for i in self.rodar() if "candidato(a)/suplente" in i["fato"]]
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nome"], "socio_ligado")
        self.assertIn("JOSE DA SILVA", r[0]["fato"])
        self.assertIn("pode ser homônimo", r[0]["fato"])
        self.assertEqual(r[0]["valor"], 15000.0)
        self.assertEqual(r[0]["contraparte"], "SOCIEDADE COM SOCIOS LTDA")

    def test_homonimo_com_cpf_diferente_nao_casa(self):
        forn = self.socios({"nome": "JOSE DA SILVA", "cpf_mascarado": "***654321**"})
        self.assertEqual(self.rodar(forn=forn), [])

    def test_candidato_sem_cpf_nao_casa_so_por_nome(self):
        forn = self.socios({"nome": "MARIA PEREIRA", "cpf_mascarado": "***111111**"})
        self.assertEqual(self.rodar(forn=forn), [])

    def test_socio_sem_cpf_mascarado_nao_casa(self):
        forn = self.socios({"nome": "JOSE DA SILVA", "cpf_mascarado": None})
        self.assertEqual(self.rodar(forn=forn), [])

    def test_o_proprio_pagador_nao_conta(self):
        cand = {"1001": {"nome": "JOSE DA SILVA", "uf": "AC", "cargo": "X", "cpf_meio": "123456"}}
        forn = self.socios({"nome": "JOSE DA SILVA", "cpf_mascarado": "***123456**"})
        self.assertEqual(self.rodar(cand=cand, forn=forn), [])

    def test_ramo_sobrenome_dispara(self):
        r = [i for i in self.rodar() if "sobrenome" in i["fato"]]
        self.assertEqual(len(r), 1)
        self.assertIn("CARLOS BRANDAO MOTA", r[0]["fato"])
        self.assertIn("mesmo sobrenome", r[0]["fato"])
        self.assertNotIn("parente", r[0]["fato"].lower())

    def test_so_sobrenome_comum_nao_dispara(self):
        cand = {"1001": {"nome": "ANA SILVA", "uf": "AC", "cargo": "X", "cpf_meio": None}}
        forn = self.socios({"nome": "JOSE DA SILVA", "cpf_mascarado": "***000000**"})
        self.assertEqual(self.rodar(cand=cand, forn=forn), [])

    def test_so_particula_em_comum_nao_dispara(self):
        cand = {"1001": {"nome": "ANA DA ROSA", "uf": "AC", "cargo": "X", "cpf_meio": None}}
        forn = self.socios({"nome": "CARLOS DA MOTA", "cpf_mascarado": "***000000**"})
        self.assertEqual(self.rodar(cand=cand, forn=forn), [])

    def test_mei_fica_de_fora(self):
        forn = copy.deepcopy(FORN)
        forn["99999999000191"]["mei"] = True
        self.assertEqual(self.rodar(forn=forn), [])

    def test_sem_pagador_no_arquivo_cala_o_ramo_sobrenome(self):
        cand = {k: v for k, v in CAND.items() if k != "1001"}
        self.assertFalse([i for i in self.rodar(cand=cand) if "sobrenome" in i["fato"]])

    def test_um_item_por_socio(self):
        forn = self.socios({"nome": "JOSE DA SILVA", "cpf_mascarado": "***123456**"},
                           {"nome": "JOSE DA SILVA", "cpf_mascarado": "***123456**"})
        self.assertEqual(len(self.rodar(forn=forn)), 1)


class TestMulticampanha(unittest.TestCase):
    def rodar(self, cnpj="10101010000191", cfg=CFG):
        return ind.multicampanha("1003", so(C1003, {cnpj}), FORN, AGR, cfg)

    def test_n_dispara(self):
        r = self.rodar()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["valor"], 5)
        self.assertIn("5 campanhas", r[0]["fato"])
        self.assertEqual(r[0]["contraparte"], "EMPRESA BAIXADA LTDA")

    def test_n_menos_um_nao_dispara(self):
        self.assertEqual(self.rodar("30303030000191"), [])  # 4 campanhas, N=5
        self.assertEqual(len(self.rodar("30303030000191", {**CFG, "multicampanha_min": 4})), 1)

    def test_mei_mascarado(self):
        r = self.rodar("20202020000191")
        self.assertEqual(r[0]["contraparte"], "**.***.***/0001-**")
        self.assertNotIn("20202020", json.dumps(r))

    def test_fora_dos_agregados_nao_dispara(self):
        self.assertEqual(ind.multicampanha("1001", so(C1001, {"44444444000191"}), FORN, AGR, CFG), [])


class TestSituacaoIrregular(unittest.TestCase):
    def rodar(self, situacao, base="2026-09-01"):
        forn = copy.deepcopy(FORN)
        forn["30303030000191"]["situacao"] = situacao
        return ind.situacao_irregular("1003", so(C1003, {"30303030000191"}), forn, CFG, base)

    def test_cada_situacao_da_lista_dispara(self):
        for sit in CFG["situacoes_irregulares"]:
            r = self.rodar(sit)
            self.assertEqual(len(r), 1, sit)
            self.assertEqual(r[0]["fato"], f"Situação cadastral na Receita: {sit} (base de 2026-09-01)")
            self.assertEqual(r[0]["valor"], 100.0)

    def test_ativa_e_nula_nao_disparam(self):
        self.assertEqual(self.rodar("ATIVA"), [])
        self.assertEqual(self.rodar(None), [])

    def test_fornecedor_ausente_nao_dispara(self):
        self.assertEqual(ind.situacao_irregular("1003", so(C1003, {"30303030000191"}), {}, CFG), [])

    def test_sem_data_base_omite_o_parentese(self):
        self.assertNotIn("base de", self.rodar("BAIXADA", None)[0]["fato"])


class TestConcentracao(unittest.TestCase):
    def rodar(self, contas=C1003, cfg=CFG):
        return ind.concentracao("1003", contas, FORN, cfg)

    def test_acima_dispara(self):
        r = self.rodar()
        self.assertEqual(len(r), 1)  # 60% de 1000; o de 30% e o de 10% ficam de fora
        self.assertEqual(r[0]["valor"], 60.0)
        self.assertIn("60,0%", r[0]["fato"])
        self.assertIn("50%", r[0]["fato"])
        self.assertEqual(r[0]["contraparte"], "EMPRESA BAIXADA LTDA")

    def test_exatamente_x_nao_dispara(self):
        self.assertEqual(self.rodar(cfg={**CFG, "concentracao_pct": 60}), [])
        self.assertEqual(len(self.rodar(cfg={**CFG, "concentracao_pct": 59.9})), 1)

    def test_total_zero_ou_nulo_cala(self):
        for total in (0, None):
            c = copy.deepcopy(C1003)
            c["despesas"]["total_contratado"] = total
            self.assertEqual(self.rodar(c), [], total)

    def test_sem_despesas_cala(self):
        self.assertEqual(self.rodar({"sq": "1003", "despesas": None}), [])

    def test_mei_mascarado(self):
        r = self.rodar(cfg={**CFG, "concentracao_pct": 20})
        self.assertIn("**.***.***/0001-**", [i["contraparte"] for i in r])


class TestEndereco(unittest.TestCase):
    def rodar(self, forn=FORN, contas=C1003, cfg=CFG):
        return ind.endereco_compartilhado("1003", contas, forn, cfg)

    def test_dois_fornecedores_disparam_um_item_cada(self):
        r = self.rodar()
        self.assertEqual(len(r), 2)
        por = {i["contraparte"]: i for i in r}
        self.assertEqual(set(por), {"EMPRESA BAIXADA LTDA", "**.***.***/0001-**"})
        self.assertIn("**.***.***/0001-**", por["EMPRESA BAIXADA LTDA"]["fato"])  # cita o MEI mascarado
        self.assertIn("EMPRESA BAIXADA LTDA", por["**.***.***/0001-**"]["fato"])
        self.assertEqual(por["EMPRESA BAIXADA LTDA"]["valor"], 600.0)

    def test_fato_nao_traz_endereco(self):
        txt = json.dumps(self.rodar(), ensure_ascii=False)
        self.assertNotIn("RUA A", txt)
        self.assertNotIn("11111111", txt)

    def test_endereco_nulo_nunca_agrupa(self):
        forn = copy.deepcopy(FORN)
        for c in ("10101010000191", "20202020000191"):
            forn[c]["endereco_chave"] = None
        self.assertEqual(self.rodar(forn), [])

    def test_um_so_fornecedor_nao_dispara(self):
        self.assertEqual(self.rodar(contas=so(C1003, {"10101010000191", "30303030000191"})), [])

    def test_matriz_e_filial_nao_contam_como_dois(self):
        forn = copy.deepcopy(FORN)
        forn["10101010000272"] = {**forn["10101010000191"]}
        contas = copy.deepcopy(so(C1003, {"10101010000191"}))
        contas["despesas"]["fornecedores_pj"].append({**contas["despesas"]["fornecedores_pj"][0], "cnpj": "10101010000272"})
        self.assertEqual(self.rodar(forn, contas), [])

    def test_minimo_vem_do_config(self):
        self.assertEqual(self.rodar(cfg={**CFG, "endereco_min_fornecedores": 3}), [])

    def test_mesmo_endereco_em_campanhas_diferentes_nao_dispara(self):
        self.assertEqual(self.rodar(contas=so(C1003, {"10101010000191"})), [])
        self.assertEqual(self.rodar(contas=so(C1003, {"20202020000191"})), [])


class TestValoresIdenticos(unittest.TestCase):
    CFG_VI = dict(CFG, valores_identicos_min=5000, valores_identicos_ignorar_multiplo=10000)
    FORN_VI = {"22584613000156": {"mei": False, "razao": "FROTA10 LOCACAO DE VEICULOS LTDA"},
               "45587474000110": {"mei": False, "razao": "FROTA VIP LOCACAO DE VEICULOS LTDA"},
               "62159285000165": {"mei": False, "razao": "FV LOCADORA LTDA"},
               "11111111000191": {"mei": True, "razao": "NOME DA PESSOA"}}

    def vi(self, *forns, forn=None):
        contas = {"despesas": {"fornecedores_pj": [{"cnpj": c, "nome": "x", "total": t} for c, t in forns]}}
        return ind.valores_identicos("1", contas, forn or self.FORN_VI, self.CFG_VI)

    def test_tres_locadoras(self):
        out = self.vi(("62159285000165", 32585.0), ("22584613000156", 32585.0), ("45587474000110", 32585.0), ("10000000000191", 999.0))
        self.assertEqual(len(out), 1)
        i = out[0]
        self.assertEqual(i["nome"], "valores_identicos")
        self.assertEqual(i["contrapartes"], ["FROTA VIP LOCACAO DE VEICULOS LTDA", "FROTA10 LOCACAO DE VEICULOS LTDA", "FV LOCADORA LTDA"])
        self.assertEqual(i["contraparte"], i["contrapartes"][0])
        self.assertEqual(i["valor"], 3 * 32585.0)
        self.assertEqual(i["fonte_url"], rcontas.URL_CONTAS)
        self.assertIn("R$ 32.585,00 cada", i["fato"])

    def test_matriz_e_filial_nao_disparam(self):
        self.assertEqual(self.vi(("22584613000156", 32585.0), ("22584613000237", 32585.0)), [])

    def test_abaixo_do_minimo(self):
        self.assertEqual(self.vi(("22584613000156", 4999.0), ("45587474000110", 4999.0)), [])

    def test_multiplo_redondo_ignorado(self):
        self.assertEqual(self.vi(("22584613000156", 30000.0), ("45587474000110", 30000.0)), [])

    def test_mei_so_mascarado(self):
        out = self.vi(("11111111000191", 7777.0), ("22584613000156", 7777.0))
        self.assertIn("**.***.***/0001-**", out[0]["contrapartes"])
        self.assertNotIn("NOME DA PESSOA", json.dumps(out, ensure_ascii=False))

    def test_sem_cadastro_na_receita_so_mascarado(self):  # pode ser MEI: o nome do TSE pode ser o da pessoa
        contas = {"despesas": {"fornecedores_pj": [{"cnpj": "33333333000191", "nome": "FULANA DE TAL", "total": 7777.0},
                                                   {"cnpj": "22584613000156", "nome": "x", "total": 7777.0}]}}
        out = ind.valores_identicos("1", contas, self.FORN_VI, self.CFG_VI)
        self.assertNotIn("FULANA", json.dumps(out, ensure_ascii=False))
        self.assertIn("**.***.***/0001-**", out[0]["contrapartes"])

    def test_lista_um_nome_por_fornecedor(self):  # dois MEIs com a mesma máscara: a lista bate com a contagem
        forn = dict(self.FORN_VI, **{"44444444000191": {"mei": True}})
        out = self.vi(("11111111000191", 7777.0), ("44444444000191", 7777.0), ("22584613000156", 7777.0), forn=forn)
        self.assertEqual(len(out[0]["contrapartes"]), 3)
        self.assertTrue(out[0]["fato"].startswith("3 fornecedores"))

    def test_config_sem_regra_nao_calcula(self):
        contas = {"despesas": {"fornecedores_pj": [{"cnpj": "22584613000156", "total": 7777.0}, {"cnpj": "45587474000110", "total": 7777.0}]}}
        self.assertEqual(ind.valores_identicos("1", contas, self.FORN_VI, CFG), [])

    def test_config_real(self):
        cfg = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["valores_identicos_min"], 5000)
        self.assertEqual(cfg["valores_identicos_ignorar_multiplo"], 10000)


class TestGerar(unittest.TestCase):
    def gerar(self, hash_path=FIX / "doadores_hash.json", pf_path=FIX / "pf_por_campanha.json",
              saques_path=FIX / "extrato_saques.json", nomeados_path=FIX / "nomeados.json",
              eleitos_path=FIX / "eleitos.json", cand_path=FIX / "candidatos.json"):
        tmp = tempfile.mkdtemp()
        saida = Path(tmp) / "indicadores.json"
        ind.gerar(FIX / "contas", FIX / "fornecedores.json", FIX / "agregados.json", hash_path, CFG, saida,
                  cnae_x_tipo=TABELA, pf_path=pf_path, saques_path=saques_path, nomeados_path=nomeados_path,
                  eleitos_path=eleitos_path, candidatos_path=cand_path, relatorio_dados=FIX / "relatorio_dados")
        return saida.read_text(encoding="utf-8"), json.loads(saida.read_text(encoding="utf-8"))

    def test_repasse_gravado_com_sigla_do_tse_baixado(self):
        """o agregados.json da fixture não tem `partido` do 2002: o reprocessamento grava a sigla de relatorio/dados"""
        _, d = self.gerar()
        rep = [i for i in d["indicadores"]["1001"] if i["nome"] == "transferencia_candidato"]
        self.assertEqual([i["contraparte"] for i in rep], ["CANDIDATO INFIMO · AC · PZ", "CANDIDATO VOTADO · AC · PQ"])

    def test_forma_envelope_e_ordem(self):
        txt, d = self.gerar()
        self.assertEqual(set(d), {"fonte", "data_base", "gerado_em", "avisos", "indicadores"})
        self.assertEqual(d["avisos"], [])  # todas as fontes presentes: nada pulado
        self.assertEqual(d["data_base"], "2026-09-01")
        self.assertIn("https://exemplo.invalid/receita", d["fonte"])
        self.assertIn("https://exemplo.invalid/tse", d["fonte"])
        self.assertEqual(list(d["indicadores"]), ["1001", "1003"])
        nomes = [i["nome"] for i in d["indicadores"]["1001"]]
        self.assertEqual(nomes, ["mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel", "socio_doador",
                                 "socio_ligado", "socio_ligado", "socio_ligado", "concentracao",
                                 "preco_fora_da_curva", "gasto_por_voto", "transferencia_candidato",
                                 "transferencia_candidato", "pessoal_pf", "pessoal_pf", "pessoal_pf",
                                 "saque_especie", "pagamento_tardio", "pagamento_tardio"])
        self.assertIn(ind.URL_EXTRATO, d["fonte"])
        self.assertIn("https://exemplo.invalid/portal/202609", d["fonte"])
        nomes = [i["nome"] for i in d["indicadores"]["1003"]]
        self.assertEqual(nomes, ["multicampanha", "multicampanha", "situacao_irregular", "situacao_irregular",
                                 "concentracao", "endereco_compartilhado", "endereco_compartilhado"])
        self.assertIn(ind.URL_CAND, d["fonte"])
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
        for meio in ("123456", "654321", "999999", "777777", "888888", "555555", "666666"):
            self.assertNotIn(meio, txt)
        for cnpj in ("10101010000191", "20202020000191"):
            self.assertNotIn(cnpj, txt)
        self.assertNotIn("RUA A", txt)
        for proibida in ("fraude", "laranja", "fictícia"):
            self.assertNotIn(proibida, txt.lower())
        pessoal = [i for itens in json.loads(txt)["indicadores"].values() for i in itens if i["nome"] == "pessoal_pf"]
        self.assertEqual(len(pessoal), 3)
        for proibido in ("MARIA", "98765432100", "11144477735", "h1", "h2", "BELTRANO", "DA SILVA"):
            self.assertNotIn(proibido, json.dumps(pessoal, ensure_ascii=False))

    def test_sem_extrato_e_sem_pf_pulam_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING") as cm:
            _, d = self.gerar(pf_path=FIX / "nao_existe.json", saques_path=None)
        self.assertTrue(any("saque_especie pulado" in m for m in cm.output))
        self.assertTrue(any("pessoal_pf pulado" in m for m in cm.output))
        # O que foi pulado fica no envelope, para a metodologia dizer.
        self.assertTrue(any(a.startswith("saque_especie") for a in d["avisos"]))
        self.assertTrue(any(a.startswith("repetidos do pessoal_pf") for a in d["avisos"]))
        nomes = [i["nome"] for i in d["indicadores"]["1001"]]
        self.assertNotIn("saque_especie", nomes)
        self.assertEqual(nomes.count("pessoal_pf"), 2)  # sobram contagem e redondos; repetidos precisa do arquivo
        self.assertNotIn(ind.URL_EXTRATO, d["fonte"])

    def test_vocabulario_e_nomes(self):
        txt, d = self.gerar()
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertEqual(nomes, TODOS)
        for palavra in ("fraude", "laranja", "fictícia", "parente"):
            self.assertNotIn(palavra, txt.lower())

    def test_sem_candidatos_pula_so_o_ramo_candidato_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            _, d = self.gerar(cand_path=FIX / "nao_existe.json")
        itens = [i for its in d["indicadores"].values() for i in its]
        self.assertEqual({i["nome"] for i in itens}, TODOS)  # socio_ligado segue pelo ramo nomeações
        self.assertEqual([i for i in itens if i["nome"] == "socio_ligado" and i["fonte_url"] == ind.URL_CAND], [])
        self.assertNotIn(ind.URL_CAND, [i["fonte_url"] for i in itens])

    def test_sem_hash_pula_socio_doador_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            _, d = self.gerar(FIX / "nao_existe.json")
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertEqual(nomes, TODOS - {"socio_doador"})

    def test_eleito_fora_do_eleitos_json_pula_so_os_de_votos(self):
        with self.assertLogs("rastro.indicadores", level="WARNING"):
            _, d = self.gerar(eleitos_path=FIX / "nao_existe.json")
        nomes = {i["nome"] for itens in d["indicadores"].values() for i in itens}
        self.assertNotIn("preco_fora_da_curva", nomes)
        self.assertNotIn("gasto_por_voto", nomes)
        self.assertIn("transferencia_candidato", nomes)

    def test_sem_nomeados_pula_socio_ligado_com_aviso(self):
        with self.assertLogs("rastro.indicadores", level="WARNING") as lg:
            _, d = self.gerar(nomeados_path=FIX / "nao_existe.json")
        self.assertTrue(any("socio_ligado" in m for m in lg.output))
        itens = [i for its in d["indicadores"].values() for i in its]
        siape = "https://exemplo.invalid/portal/202609"
        self.assertEqual([i for i in itens if i["nome"] == "socio_ligado" and i["fonte_url"] == siape], [])
        self.assertIn("socio_ligado", {i["nome"] for i in itens})  # o ramo candidato/sobrenome segue
        self.assertNotIn(siape, d["fonte"])


if __name__ == "__main__":
    unittest.main()
