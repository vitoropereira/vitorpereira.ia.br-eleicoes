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

    def test_urls(self):
        for u in baixar.ARQUIVOS:
            self.assertTrue(u.startswith("https://cdn.tse.jus.br/estatistica/sead/odsele/"))


if __name__ == "__main__":
    unittest.main()
