import json
import os
import re
import tempfile
import unittest
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

from rastro import contas

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "contas"
RELATORIO = RAIZ / "tests" / "fixtures" / "rastro" / "relatorio_dados"
REAL = RAIZ / "rastro" / "dados"
CPF_PF_FORN, CPF_DOADOR, CPF_MEI = "98765432100", "11144477735", "12345678909"


def montar_zip(destino):
    """Zipa todos os CSVs da fixture (BRASIL, por UF e doador originário) em destino/contas.zip."""
    z = Path(destino) / "contas.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in sorted(FIX.glob("*.csv")):
            zf.write(f, f.name)
    return z


class TestParseValor(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(contas.parse_valor("1.234,56"), Decimal("1234.56"))
        self.assertEqual(contas.parse_valor("900,00"), Decimal("900.00"))
        self.assertEqual(contas.parse_valor("1234,5"), Decimal("1234.5"))
        self.assertEqual(contas.parse_valor("-10,00"), Decimal("-10.00"))

    def test_vazio_e_nulo_nao_viram_zero(self):
        for txt in ("", "  ", "#NULO", "#nulo", None):
            self.assertIsNone(contas.parse_valor(txt))

    def test_lixo_levanta(self):
        for txt in ("abc", "NaN", "Infinity", "1,2,3", "1.2"):
            with self.assertRaises(ValueError):
                contas.parse_valor(txt)

    def test_linha_invalida_conta_e_loga(self):
        inval = Counter()
        with self.assertLogs("rastro.contas", level="WARNING") as cm:
            v = contas.valor_linha({"VR": "abc", "SQ_CANDIDATO": "1"}, "VR", "arq", inval)
        self.assertIsNone(v)
        self.assertEqual(inval["arq"], 1)
        self.assertIn("abc", cm.output[0])


class TestLerCsv(unittest.TestCase):
    def test_streaming_so_brasil(self):
        with tempfile.TemporaryDirectory() as td:
            z = montar_zip(td)
            gen = contas.ler_csv(z, "receitas_candidatos")
            linhas = list(gen)
            self.assertEqual(os.listdir(td), ["contas.zip"])  # nada extraído
        self.assertEqual(len(linhas), 7)  # o _AC e o doador_originario repetem linhas e ficam de fora
        self.assertEqual(linhas[0]["NM_DOADOR"], "EMPRESA DOADORA SA")
        con = [l for l in self._ler("despesas_contratadas_candidatos") if l["SQ_DESPESA"] == "D1"]
        self.assertEqual(con[0]["NM_FORNECEDOR"], "GRÁFICA ALFA LTDA")  # latin-1 decodificado

    def _ler(self, prefixo):
        with tempfile.TemporaryDirectory() as td:
            return list(contas.ler_csv(montar_zip(td), prefixo))

    def test_membro_ausente(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                list(contas.ler_csv(montar_zip(td), "inexistente"))


class TestLimpar(unittest.TestCase):
    def test_remove_cpf_valido_inclusive_sufixo_mei(self):
        self.assertEqual(contas.limpar_texto("FULANO MEI 12345678909"), "FULANO MEI")
        self.assertEqual(contas.limpar_texto("MARIA 111.444.777-35 LTDA"), "MARIA LTDA")

    def test_mantem_o_que_nao_e_cpf(self):
        self.assertEqual(contas.limpar_texto("EMPRESA 12345678900"), "EMPRESA 12345678900")  # DV inválido
        self.assertEqual(contas.limpar_texto("11222333000181"), "11222333000181")  # CNPJ
        self.assertEqual(contas.limpar_texto(None), "")

    def test_texto_codigos_nulos_do_tse(self):
        for v in ("-1", "#NULO", "#NULO#", ""):
            self.assertIsNone(contas.texto({"C": v}, "C"))
        self.assertEqual(contas.texto({"C": " 1813099 "}, "C"), "1813099")

    def test_cpf_valido(self):
        self.assertTrue(contas.cpf_valido(CPF_DOADOR))
        self.assertTrue(contas.cpf_valido(CPF_MEI))
        self.assertTrue(contas.cpf_valido(CPF_PF_FORN))
        self.assertFalse(contas.cpf_valido("11111111111"))


class TestGerar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        t = Path(cls.td.name)
        z = montar_zip(t)
        cls.sal = "sal-de-teste"
        cls.contas_dir, cls.agr, cls.hash = t / "contas", t / "base" / "agregados.json", t / "hash.json"
        cls.pf = t / "brutos" / "pf_por_campanha.json"
        cls.invalidas = contas.gerar(z, FIX / "eleitos.json", RELATORIO, ["ac"], cls.sal,
                                     cls.contas_dir, cls.agr, cls.hash, cls.pf)
        cls.c = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in cls.contas_dir.glob("*.json")}
        cls.a = json.loads(cls.agr.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_um_arquivo_por_eleito(self):
        self.assertEqual(set(self.c), {"1021", "1023", "1031"})  # o não eleito (1022) só entra nos agregados

    def test_campos_do_contrato(self):
        c = self.c["1021"]
        self.assertEqual(set(c), {"sq", "nome_urna", "cargo", "uf", "partido", "cnpj_prestador", "prestacao_parcial",
                                  "receitas", "despesas", "fonte", "data_base", "gerado_em"})
        self.assertEqual(set(c["receitas"]), {"total", "por_origem", "por_fonte", "doadores_pj", "doadores_pf"})
        self.assertEqual(set(c["despesas"]), {"total_contratado", "total_pago", "fornecedores_pj", "fornecedores_pf",
                                             "por_tipo", "pago_por_dia"})
        self.assertEqual(sum(c["despesas"]["por_tipo"].values()), c["despesas"]["total_contratado"])
        self.assertEqual(c["despesas"]["por_tipo"]["Publicidade por materiais impressos"], 900.0)
        self.assertEqual(c["data_base"], "2026-10-12")  # maior DT_GERACAO (há linhas de 10/10)
        self.assertEqual(c["fonte"], [contas.URL_CONTAS])
        self.assertTrue(c["prestacao_parcial"])

    def test_parcelas_nao_somam_em_dobro(self):
        d = self.c["1021"]["despesas"]
        # D1 (R$ 900 em 3 parcelas, linha contratada repetida 3x) + D2 1234,56 + D3 100; vazio/#NULO/inválido fora
        self.assertEqual(d["total_contratado"], 2234.56)
        self.assertEqual(d["total_pago"], 2134.56)  # 3 x 300 + 1234,56
        graf = next(f for f in d["fornecedores_pj"] if f["cnpj"] == "11222333000181")
        self.assertEqual((graf["total"], graf["n_despesas"]), (900.0, 1))

    def test_invalidas_por_arquivo(self):
        self.assertEqual(self.invalidas["despesas_contratadas_candidatos"], 1)
        self.assertEqual(self.invalidas["receitas_candidatos"], 0)

    def test_receitas(self):
        r = self.c["1021"]["receitas"]
        self.assertEqual(r["total"], 6250.0)
        self.assertEqual(r["por_origem"], {"Recursos de partido político": 6000.0, "Recursos de pessoas físicas": 250.0})
        self.assertEqual(r["por_fonte"]["Fundo Especial (FEFC)"], 5000.0)
        self.assertEqual([d["cnpj"] for d in r["doadores_pj"]], ["33444555000166", "55666777000122"])
        self.assertEqual(r["doadores_pj"][0], {"cnpj": "33444555000166", "nome": "EMPRESA DOADORA SA", "total": 5000.0})
        self.assertEqual(r["doadores_pf"], {"qtd": 1, "total": 250.0})

    def test_fornecedores(self):
        d = self.c["1021"]["despesas"]
        self.assertEqual([f["cnpj"] for f in d["fornecedores_pj"]], ["22333444000155", "11222333000181"])
        mei = d["fornecedores_pj"][0]
        self.assertEqual(mei["nome"], "FULANO MEI")
        self.assertEqual(mei["cnae"], "7319002")
        self.assertEqual(mei["tipos"], ["Serviços prestados por terceiros"])
        self.assertEqual(d["fornecedores_pf"],
                         {"qtd": 1, "total": 100.0, "por_tipo": {"Atividades de militância": 100.0}, "valores": [100.0]})

    def test_cnpj_prestador(self):
        self.assertEqual(self.c["1021"]["cnpj_prestador"], "12345678000195")
        self.assertEqual(self.c["1023"]["cnpj_prestador"], "32345678000195")
        self.assertIsNone(self.c["1031"]["cnpj_prestador"])
        for c in self.c.values():
            self.assertTrue(c["cnpj_prestador"] is None or re.fullmatch(r"\d{14}", c["cnpj_prestador"]))

    def test_pago_por_dia_sem_duplicar_parcela(self):
        # D1 em 3 parcelas (05/10, 27/09, 03/10), D2 com data #NULO: soma no total, mas não vira dia
        d = self.c["1021"]["despesas"]
        self.assertEqual(d["pago_por_dia"], {"2026-09-27": 300.0, "2026-10-03": 300.0, "2026-10-05": 300.0})
        self.assertEqual(d["total_pago"], 2134.56)
        self.assertEqual(self.invalidas["despesas_pagas_candidatos (data)"], 1)
        self.assertIsNone(self.c["1031"]["despesas"])

    def test_pf_anonimo_e_hash_fora_do_contas(self):
        self.assertEqual(self.c["1021"]["despesas"]["fornecedores_pf"]["valores"], [100.0])
        bruto = "".join(p.read_text(encoding="utf-8") for p in self.contas_dir.glob("*.json"))
        h_forn = contas.hashlib.sha256((self.sal + CPF_PF_FORN).encode()).hexdigest()
        self.assertNotIn(h_forn, bruto)
        self.assertNotIn("cpfs_hash", bruto)
        pf = json.loads(self.pf.read_text(encoding="utf-8"))
        self.assertEqual(pf["1021"], [h_forn])
        self.assertNotIn(CPF_PF_FORN, self.pf.read_text(encoding="utf-8"))

    def test_eleito_sem_prestacao(self):
        c = self.c["1031"]
        self.assertFalse(c["prestacao_parcial"])
        self.assertIsNone(c["receitas"])
        self.assertIsNone(c["despesas"])
        self.assertNotIn('"total', json.dumps(c).replace('"total_', ""))  # nenhum total 0 inventado

    def test_agregados(self):
        a = self.a
        self.assertEqual(a["por_cnpj"]["11222333000181"],
                         {"total_recebido": 1150.0, "n_campanhas": 2, "campanhas": ["1021", "1022"]})
        self.assertEqual(a["por_tipo_cargo_uf"]["Publicidade por materiais impressos|depfed|AC"], [250.0, 900.0])
        self.assertEqual(a["custo_por_voto"]["depfed|AC"], [0.07, 5.0, 7.45])  # 1023, 1022 (não eleito), 1021
        self.assertNotIn("depest|AC", a["custo_por_voto"])  # 1031 sem despesas
        self.assertEqual(a["eleitorado"], {"AC": 613742})
        self.assertEqual(a["data_base"], "2026-10-12")
        self.assertEqual(a["fonte"], [contas.URL_CONTAS])
        self.assertIn("gerado_em", a)

    def test_repasses_entre_candidatos(self):
        self.assertEqual(self.a["repasses"], {"1021": {"1022": 400.0}})
        self.assertEqual(self.a["candidatos"], {"1022": {"nome": "FED NAO ELEITO", "cargo": "depfed", "uf": "AC",
                                                         "votos": self.a["candidatos"]["1022"]["votos"]}})
        self.assertGreater(self.a["candidatos"]["1022"]["votos"], 0)

    def test_hash_sem_cpf_inteiro(self):
        bruto = self.hash.read_text(encoding="utf-8")
        for cpf in (CPF_PF_FORN, CPF_DOADOR, CPF_MEI):
            self.assertNotIn(cpf, bruto)
        h = json.loads(bruto)
        chave = contas.hashlib.sha256((self.sal + CPF_DOADOR).encode()).hexdigest()
        self.assertEqual(h[chave], {"nome": "BELTRANO", "cpf_meio": "444777", "campanhas": ["1021", "1023"],
                                    "total": 260.0, "papel": "doador"})
        forn = h[contas.hashlib.sha256((self.sal + CPF_PF_FORN).encode()).hexdigest()]
        self.assertEqual(forn["papel"], "fornecedor")

    def test_lgpd_nenhum_cpf_nas_saidas(self):
        achados = varrer_cpf(self.contas_dir, self.agr)
        self.assertEqual(achados, [])
        texto = "".join(p.read_text(encoding="utf-8") for p in [*self.contas_dir.glob("*.json"), self.agr])
        self.assertNotIn("MARIA", texto)  # nome de fornecedor PF nunca sai
        self.assertNotIn("Apoio de", texto)  # DS_DESPESA nunca sai


class TestSal(unittest.TestCase):
    def test_cria_com_0600_e_reaproveita(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / ".sal"
            s1 = contas.carregar_sal(p)
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            self.assertEqual(contas.carregar_sal(p), s1)
            self.assertGreaterEqual(len(s1), 32)


def varrer_cpf(*caminhos, ignorar=frozenset()):
    """CPFs de DV válido no texto dos JSONs. `ignorar`: números que sabidamente não são CPF (SQ_CANDIDATO
    tem 11 dígitos em alguns estados e ~1% deles bate o DV por acaso)."""
    achados = []
    arquivos = []
    for c in caminhos:
        c = Path(c)
        arquivos += sorted(c.glob("*.json")) if c.is_dir() else [c]
    for arq in arquivos:
        for m in contas.RE_CPF.finditer(arq.read_text(encoding="utf-8")):
            dig = re.sub(r"\D", "", m.group())
            if contas.cpf_valido(dig) and dig not in ignorar:
                achados.append((arq.name, m.group()))
    return achados


def sqs_conhecidos(agregados, eleitos):
    sqs = {e["sq"] for e in json.loads(Path(eleitos).read_text(encoding="utf-8"))["eleitos"]}
    agr = json.loads(Path(agregados).read_text(encoding="utf-8"))
    for a in agr["por_cnpj"].values():
        sqs.update(a["campanhas"])
    # SQ_CANDIDATO (id do TSE, não CPF) também é chave de `candidatos` e de `repasses` (origem -> destino)
    sqs.update(agr.get("candidatos") or {})
    for origem, destinos in (agr.get("repasses") or {}).items():
        sqs.add(origem)
        sqs.update(destinos)
    return sqs


@unittest.skipUnless((REAL / "contas").exists() and (REAL / "base" / "agregados.json").exists(),
                     "saída real não gerada")
class TestLgpdReal(unittest.TestCase):
    def test_nenhum_cpf_valido_na_saida_real(self):
        agr = REAL / "base" / "agregados.json"
        self.assertEqual(varrer_cpf(REAL / "contas", agr, ignorar=sqs_conhecidos(agr, REAL / "eleitos.json")), [])


if __name__ == "__main__":
    unittest.main()
