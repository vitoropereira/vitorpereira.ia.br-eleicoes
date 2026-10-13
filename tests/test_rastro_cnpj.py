import json
import os
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

from rastro import baixar, cnpj, contas

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "cnpj"
CONTAS = FIX / "contas"
MEI, BAIXADO, SOCIOS, ISCA, AUSENTE = ("11111111000191", "22222222000100", "33333333000100",
                                       "44444444000144", "55555555000155")


def montar_zips(destino):
    """Zipa cada CSV da fixture (Empresas0.csv -> Empresas0.zip, com 1 membro) em destino."""
    for csv_ in FIX.glob("*.csv"):
        with zipfile.ZipFile(Path(destino) / f"{csv_.stem}.zip", "w") as zf:
            zf.write(csv_, csv_.name)
    return Path(destino)


class TestAlvo(unittest.TestCase):
    def test_repetido_uma_vez_e_tamanho_errado_ignorado(self):
        with self.assertLogs("rastro.cnpj", level="WARNING"):
            alvo = cnpj.cnpjs_alvo(CONTAS)
        self.assertEqual(alvo, {MEI, BAIXADO, SOCIOS, AUSENTE})


class TestNormalizadores(unittest.TestCase):
    def test_situacao(self):
        self.assertEqual(cnpj.situacao("08"), "BAIXADA")
        self.assertEqual(cnpj.situacao("02"), "ATIVA")
        with self.assertLogs("rastro.cnpj", level="WARNING"):
            self.assertEqual(cnpj.situacao("99"), "99")

    def test_data_iso(self):
        self.assertEqual(cnpj.data_iso("20250310"), "2025-03-10")
        self.assertIsNone(cnpj.data_iso(""))
        self.assertIsNone(cnpj.data_iso("00000000"))

    def test_endereco_chave(self):
        self.assertEqual(cnpj.endereco_chave("RUA", "DAS FLORES", "123", "01234567"), "RUA DAS FLORES|123|01234567")
        a = cnpj.endereco_chave("Rua", "  das  Flôres ", "123", "01234-567")
        self.assertEqual(a, "RUA DAS FLORES|123|01234567")
        for sn in ("S/N", "sn", "", None):
            self.assertEqual(cnpj.endereco_chave("RUA", "A", sn, "01234567"), "RUA A|SN|01234567")
        self.assertIsNone(cnpj.endereco_chave("RUA", "", "1", "01234567"))
        self.assertIsNone(cnpj.endereco_chave("RUA", "A", "1", ""))


class TestCpfMascarado(unittest.TestCase):
    def test_mascara_mantida(self):
        self.assertEqual(cnpj.cpf_mascarado("2", "***123456**"), "***123456**")

    def test_cpf_inteiro_nunca_gravado(self):
        with self.assertLogs("rastro.cnpj", level="WARNING"):
            self.assertIsNone(cnpj.cpf_mascarado("2", "12345678909"))

    def test_socio_pj_sem_cpf(self):
        self.assertIsNone(cnpj.cpf_mascarado("1", "99999999000199"))
        self.assertIsNone(cnpj.cpf_mascarado("1", "***123456**"))


class TestLerZip(unittest.TestCase):
    def test_streaming_latin1_sem_extrair(self):
        with tempfile.TemporaryDirectory() as td:
            z = Path(td) / "Empresas0.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("K.EMPRECSV", "1;AÇAÍ LTDA;x\n".encode("latin-1"))
            self.assertEqual(list(cnpj.ler_zip(z)), [["1", "AÇAÍ LTDA", "x"]])
            self.assertEqual(os.listdir(td), ["Empresas0.zip"])


class TestGerar(unittest.TestCase):
    def gerar(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        zips = montar_zips(td.name)
        saida = Path(td.name) / "out" / "fornecedores.json"
        with self.assertLogs("rastro.cnpj", level="WARNING"):
            n = cnpj.gerar(zips, CONTAS, saida, "2026-09")
        self.assertEqual(n, (4, 3))
        self.texto = saida.read_text(encoding="utf-8")
        return json.loads(self.texto)

    def test_saida(self):
        obj = self.gerar()
        self.assertEqual(obj["data_base"], "2026-09-01")
        self.assertTrue(obj["gerado_em"])
        self.assertTrue(all(u.startswith("https://") for u in obj["fonte"]))
        f = obj["fornecedores"]
        self.assertEqual(set(f), {MEI, BAIXADO, SOCIOS, AUSENTE})  # isca fora
        self.assertTrue(f[MEI]["mei"])
        self.assertTrue(f[MEI]["simples"])
        self.assertEqual(f[MEI]["razao"], "JOAO DA SILVA")
        self.assertEqual(f[MEI]["abertura"], "2020-03-10")
        self.assertEqual(f[MEI]["cnae"], "9602501")
        self.assertEqual(f[MEI]["endereco_chave"], "RUA DAS FLORES|123|01234567")
        self.assertEqual(f[BAIXADO]["situacao"], "BAIXADA")
        self.assertFalse(f[BAIXADO]["mei"])
        self.assertEqual(f[BAIXADO]["endereco_chave"], "AVENIDA BRASIL|SN|20000000")
        self.assertEqual(f[SOCIOS]["endereco_chave"], f[MEI]["endereco_chave"])
        self.assertEqual(len(f[SOCIOS]["socios"]), 3)
        self.assertEqual(f[SOCIOS]["socios"][0], {"nome": "MARIA SOUZA", "cpf_mascarado": "***123456**"})
        self.assertIsNone(f[SOCIOS]["socios"][1]["cpf_mascarado"])
        self.assertIsNone(f[SOCIOS]["socios"][2]["cpf_mascarado"])
        self.assertIsNone(f[AUSENTE]["situacao"])
        self.assertEqual(f[AUSENTE]["socios"], [])

    def test_lgpd_nenhum_cpf_valido(self):
        self.gerar()
        achados = [m.group() for m in contas.RE_CPF.finditer(self.texto)
                   if contas.cpf_valido(contas.digitos(m.group()))]
        self.assertEqual(achados, [])
        for cpf in ("11144477735", "98765432100", "12345678909"):
            self.assertNotIn(cpf, self.texto)


class TestMain(unittest.TestCase):
    class Resp:
        headers = {}

        def read(self, n=-1):
            return b""

        def close(self):
            pass

    def test_urls_por_mes(self):
        urls = []

        def opener(req, timeout=None):
            urls.append(req.full_url)
            raise HTTPError(req.full_url, 404, "x", {}, None)

        with tempfile.TemporaryDirectory() as td:
            antigo = baixar.OUT
            baixar.OUT = Path(td)
            try:
                with self.assertRaises(HTTPError):
                    cnpj.main(["--mes", "2026-08"], opener=opener, hoje=date(2026, 10, 13))
            finally:
                baixar.OUT = antigo
        self.assertEqual(urls, [cnpj.url_zip("2026-08", "Empresas0.zip")])
        self.assertIn("path=/2026-08&files=Empresas0.zip", urls[0])

    def test_bloqueia_25_10(self):
        def opener(*a, **k):
            raise AssertionError("não pode baixar em 25/10")

        with self.assertRaises(SystemExit):
            cnpj.main([], opener=opener, hoje=date(2026, 10, 25))

    def test_mes_invalido(self):
        with self.assertRaises(SystemExit):
            cnpj.main(["--mes", "2026-13"])


if __name__ == "__main__":
    unittest.main()
