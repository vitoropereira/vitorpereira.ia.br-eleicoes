import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from rastro import baixar, nomeacoes

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "nomeacoes"
CFG = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
FUNCOES = CFG["nomeacoes_funcoes"]


def montar_zip(pasta, csv_texto=None, nome="202609_Cadastro.csv", zip_nome="202609_Servidores.zip"):
    """ZIP em pasta com o CSV da fixture em latin-1, como o Portal publica."""
    if csv_texto is None:
        csv_texto = (FIX / "202609_Cadastro.csv").read_text(encoding="utf-8")
    caminho = Path(pasta) / zip_nome
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(nome, csv_texto.encode("latin-1"))
    return caminho


class TestLerSiape(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.zip = montar_zip(self.td.name)

    def test_so_funcao_comissionada(self):
        r = nomeacoes.ler_siape(self.zip, FUNCOES)
        self.assertEqual(set(r), {("JOSE DA SILVA", "123456"), ("JOSE DA SILVA", "654321")})
        self.assertEqual(r[("JOSE DA SILVA", "123456")],
                         {"funcao": "FCPE", "orgao": "MINISTERIO TESTE", "base": "siape"})

    def test_homonimos_ficam_separados_pelo_trecho(self):
        r = nomeacoes.ler_siape(self.zip, FUNCOES)
        self.assertEqual(r[("JOSE DA SILVA", "654321")]["funcao"], "DAS")

    def test_efetivo_sem_funcao_fora(self):
        nomes = {n for n, _ in nomeacoes.ler_siape(self.zip, FUNCOES)}
        self.assertNotIn("ANA EFETIVA", nomes)
        self.assertNotIn("CARLOS VAZIO", nomes)

    def test_prefixos_vem_do_config(self):
        self.assertEqual(nomeacoes.ler_siape(self.zip, {"XYZ": "n"}), {})

    def test_cpf_inteiro_descartado_com_aviso_e_nunca_na_saida(self):
        with self.assertLogs("rastro.nomeacoes", level="WARNING") as lg:
            r = nomeacoes.ler_siape(self.zip, FUNCOES)
        self.assertTrue(any("CPF inteiro" in m for m in lg.output))
        self.assertNotIn("PEDRO INTEIRO", {n for n, _ in r})
        self.assertNotIn("11144477735", json.dumps([list(k) + [v] for k, v in r.items()]))

    def test_cpf_vazio_descartado_e_contado(self):
        with self.assertLogs("rastro.nomeacoes", level="INFO") as lg:
            r = nomeacoes.ler_siape(self.zip, FUNCOES)
        self.assertNotIn("LUIZ SEM CPF", {n for n, _ in r})
        self.assertTrue(any("1 linha(s) comissionada(s) sem CPF" in m for m in lg.output))

    def test_cpf_meio(self):
        av = {"vazio": 0, "inteiro": 0, "formato": 0}
        self.assertEqual(nomeacoes.cpf_meio("***.123.456-**", av), "123456")
        self.assertEqual(nomeacoes.cpf_meio("***123456**", av), "123456")
        self.assertIsNone(nomeacoes.cpf_meio("123.456.789-09", av))
        self.assertEqual(av["inteiro"], 1)

    def test_cabecalho_renomeado_aborta(self):
        z = montar_zip(self.td.name, '"Nome";"Documento";"SIGLA_FUNCAO"\n"A";"***.123.456-**";"FCPE"\n',
                       zip_nome="y.zip")
        with self.assertRaises(ValueError):
            nomeacoes.ler_siape(z, FUNCOES)

    def test_membro_inesperado_aborta(self):
        z = montar_zip(self.td.name, nome="outro.csv", zip_nome="x.zip")
        with self.assertRaises(FileNotFoundError):
            nomeacoes.ler_siape(z, FUNCOES)


class TestLerExterna(unittest.TestCase):
    COLUNAS = {"nome": "Nome", "cpf": "CPF", "funcao": None, "orgao": "Lotacao"}

    def zip(self, td, texto):
        return montar_zip(td, texto, nome="secretarios.csv", zip_nome="camara.zip")

    def test_le_quando_ha_cpf_mascarado(self):
        with tempfile.TemporaryDirectory() as td:
            z = self.zip(td, '"Nome";"CPF";"Lotacao"\n"MARIA PEREIRA";"***.111.111-**";"GABINETE X"\n')
            r = nomeacoes.ler_externa(z, self.COLUNAS, "camara")
        self.assertEqual(r, {("MARIA PEREIRA", "111111"): {"funcao": None, "orgao": "GABINETE X", "base": "camara"}})

    def test_ignora_base_sem_coluna_de_cpf(self):
        with tempfile.TemporaryDirectory() as td:
            z = self.zip(td, '"Nome";"Cargo";"Lotacao"\n"MARIA PEREIRA";"SECRETARIO";"GABINETE X"\n')
            with self.assertLogs("rastro.nomeacoes", level="WARNING") as lg:
                r = nomeacoes.ler_externa(z, self.COLUNAS, "camara")
        self.assertEqual(r, {})
        self.assertIn("ignorada", lg.output[0])

    def test_ignora_mapeamento_sem_cpf(self):
        with tempfile.TemporaryDirectory() as td:
            z = self.zip(td, '"Nome";"Lotacao"\n"MARIA PEREIRA";"GABINETE X"\n')
            with self.assertLogs("rastro.nomeacoes", level="WARNING"):
                r = nomeacoes.ler_externa(z, {"nome": "Nome", "cpf": None, "orgao": "Lotacao"}, "senado")
        self.assertEqual(r, {})


class FalsaResp:
    headers = {}

    def __init__(self, corpo):
        self.corpo = corpo

    def read(self, n=-1):
        corpo, self.corpo = self.corpo, b""
        return corpo

    def close(self):
        pass


class TestMain(unittest.TestCase):
    def rodar(self, td, opener, hoje=date(2026, 10, 13)):
        antigo = baixar.OUT
        baixar.OUT = Path(td)
        try:
            nomeacoes.main(opener=opener, hoje=hoje, cfg=CFG)
        finally:
            baixar.OUT = antigo

    def test_baixa_do_config_e_grava_nomeados(self):
        pedidos = []
        with tempfile.TemporaryDirectory() as td:
            origem = montar_zip(td, zip_nome="origem.zip")
            corpo = origem.read_bytes()

            def opener(req, timeout=None):
                pedidos.append(req)
                return FalsaResp(corpo)

            self.rodar(td, opener)
            saida = json.loads((Path(td) / "nomeados.json").read_text(encoding="utf-8"))
            self.assertTrue((Path(td) / "nomeacoes" / "202609_Servidores.zip").exists())
        self.assertEqual(pedidos[0].full_url, "https://portaldatransparencia.gov.br/download-de-dados/servidores/202609")
        self.assertEqual(pedidos[0].get_header("User-agent"), baixar.UA)
        self.assertEqual(saida["data_base"], "2026-09-01")
        self.assertEqual(saida["fonte"], [pedidos[0].full_url])
        self.assertEqual(len(saida["nomeados"]), 2)
        self.assertEqual(set(saida["nomeados"][0]), {"nome", "cpf_meio", "funcao", "orgao", "base"})
        self.assertNotIn("11144477735", json.dumps(saida))

    def test_bloqueia_25_10(self):
        def opener(*a, **k):
            raise AssertionError("não pode baixar em 25/10")

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                self.rodar(td, opener, hoje=date(2026, 10, 25))


if __name__ == "__main__":
    unittest.main()
