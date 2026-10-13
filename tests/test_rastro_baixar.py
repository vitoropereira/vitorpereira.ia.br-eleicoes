import io
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path

from rastro import baixar
from municipios import baixar as mun_baixar


class Resp(io.BytesIO):
    def __init__(self, corpo, last_modified=None):
        super().__init__(corpo)
        self.headers = {"Last-Modified": last_modified} if last_modified else {}


class Opener:
    """urlopen falso: registra as requisições e devolve as respostas na ordem."""
    def __init__(self, *respostas):
        self.respostas, self.reqs = list(respostas), []

    def __call__(self, req, timeout=None):
        self.reqs.append(req)
        r = self.respostas.pop(0)
        if isinstance(r, int):
            raise urllib.error.HTTPError(req.full_url, r, "x", {}, None)
        return r


HOJE = date(2026, 10, 13)
URL = "https://exemplo.test/a.zip"


class TestBaixar(unittest.TestCase):
    def test_primeira_vez_grava_e_guarda_lastmod(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "a.zip"
            op = Opener(Resp(b"zip1", "Mon, 12 Oct 2026 10:00:00 GMT"))
            self.assertEqual(baixar.baixar(URL, dest, op, HOJE), "baixado")
            self.assertEqual(dest.read_bytes(), b"zip1")
            self.assertEqual((Path(td) / "a.zip.lastmod").read_text().strip(), "Mon, 12 Oct 2026 10:00:00 GMT")
            self.assertEqual(sorted(p.name for p in Path(td).iterdir()), ["a.zip", "a.zip.lastmod"])  # sem .tmp
            self.assertNotIn("If-modified-since", op.reqs[0].headers)
            self.assertEqual(op.reqs[0].headers["User-agent"], mun_baixar.UA)

    def test_304_nao_toca_no_arquivo(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "a.zip"
            dest.write_bytes(b"velho")
            (Path(td) / "a.zip.lastmod").write_text("Mon, 12 Oct 2026 10:00:00 GMT\n")
            op = Opener(304)
            self.assertEqual(baixar.baixar(URL, dest, op, HOJE), "em cache")
            self.assertEqual(dest.read_bytes(), b"velho")
            self.assertEqual(op.reqs[0].headers["If-modified-since"], "Mon, 12 Oct 2026 10:00:00 GMT")

    def test_200_substitui_e_atualiza_lastmod(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "a.zip"
            dest.write_bytes(b"velho")
            (Path(td) / "a.zip.lastmod").write_text("antigo\n")
            baixar.baixar(URL, dest, Opener(Resp(b"novo", "novo-lm")), HOJE)
            self.assertEqual(dest.read_bytes(), b"novo")
            self.assertEqual((Path(td) / "a.zip.lastmod").read_text().strip(), "novo-lm")

    def test_erro_http_preserva_o_arquivo(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "a.zip"
            dest.write_bytes(b"velho")
            with self.assertRaises(urllib.error.HTTPError):
                baixar.baixar(URL, dest, Opener(500), HOJE)
            self.assertEqual(dest.read_bytes(), b"velho")

    def test_dia_da_apuracao_aborta_antes_de_pedir(self):
        with tempfile.TemporaryDirectory() as td:
            op = Opener()
            with self.assertRaises(SystemExit):
                baixar.baixar(URL, Path(td) / "a.zip", op, date(2026, 10, 25))
            self.assertEqual(op.reqs, [])

    def test_extrato_na_lista(self):
        self.assertIn(baixar.URL_EXTRATO, baixar.ARQUIVOS)
        self.assertTrue(baixar.URL_EXTRATO.endswith("/extrato_bancario_candidato_2026.zip"))

    def test_404_do_extrato_e_aviso_e_nao_derruba_os_outros(self):
        with tempfile.TemporaryDirectory() as td:
            urls = ["https://exemplo.test/a.zip", "https://exemplo.test/extrato.zip", "https://exemplo.test/c.zip"]
            op = Opener(Resp(b"a"), 404, Resp(b"c"))
            with self.assertLogs("rastro.baixar", level="WARNING") as cm:
                res = baixar.baixar_todos(urls, td, op, HOJE)
            self.assertEqual(res, {"a.zip": "baixado", "extrato.zip": "não encontrado", "c.zip": "baixado"})
            self.assertIn("404", cm.output[0])
            self.assertEqual((Path(td) / "c.zip").read_bytes(), b"c")

    def test_500_continua_derrubando(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(urllib.error.HTTPError):
                baixar.baixar_todos(["https://exemplo.test/a.zip"], td, Opener(500), HOJE)

    def test_urls(self):
        for u in baixar.ARQUIVOS:
            self.assertTrue(u.startswith("https://cdn.tse.jus.br/estatistica/sead/odsele/"))

    def test_url_contas_por_ano(self):
        for ano in (2022, 2024):
            self.assertEqual(baixar.url_contas(ano), f"https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip")
        self.assertEqual(baixar.ARQUIVOS_ANTERIORES, [baixar.url_contas(2022), baixar.url_contas(2024)])
        self.assertTrue(set(baixar.ARQUIVOS_ANTERIORES).isdisjoint(baixar.ARQUIVOS))  # o padrão continua só 2026

    def test_anos_anteriores_respeitam_o_dia_da_apuracao(self):
        with tempfile.TemporaryDirectory() as td:
            op = Opener()
            with self.assertRaises(SystemExit):
                baixar.baixar_todos(baixar.ARQUIVOS_ANTERIORES, td, op, date(2026, 10, 25))
            self.assertEqual(op.reqs, [])


if __name__ == "__main__":
    unittest.main()
