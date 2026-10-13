import base64
import json
import re
import tempfile
import threading
import unittest
import zipfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from rastro import cnpj
from tests.test_rastro_cnpj import CONTAS, RAIZ, montar_zips

RAIZ_XML = RAIZ / "tests" / "fixtures" / "cnpj_webdav" / "raiz.xml"
PREFIXO = "/public.php/webdav"


def zips_completos(destino):
    """31 ZIPs: os da fixture mais ZIPs vazios (1 membro, 0 linhas) para o resto."""
    destino = montar_zips(destino)
    for nome in cnpj.nomes_zip():
        if not (destino / nome).exists():
            with zipfile.ZipFile(destino / nome, "w") as zf:
                zf.writestr("vazio.csv", b"")
    return {n: (destino / n).read_bytes() for n in cnpj.nomes_zip()}


class Webdav:
    """Servidor WebDAV mínimo: PROPFIND, GET com Range e registro das chamadas."""

    def __init__(self, meses, raiz_xml=None, token=cnpj.TOKEN, ao_get=None):
        self.meses, self.raiz_xml, self.token, self.ao_get = meses, raiz_xml, token, ao_get
        self.chamadas = []
        self.cortar_proximo = False
        self.ignorar_range = False
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok(self):
                esperado = "Basic " + base64.b64encode(f"{srv.token}:".encode()).decode()
                if self.headers.get("Authorization") != esperado:
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return False
                return True

            def do_PROPFIND(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                srv.chamadas.append(("PROPFIND", self.path, self.headers.get("Depth")))
                if not self._ok():
                    return
                pasta = self.path[len(PREFIXO):].strip("/")
                if not pasta and srv.raiz_xml:
                    corpo = srv.raiz_xml.read_bytes()
                else:
                    itens = [f"<d:response><d:href>{self.path}</d:href></d:response>"]
                    if not pasta:
                        itens += [f"<d:response><d:href>{PREFIXO}/{m}/</d:href></d:response>" for m in srv.meses]
                    for nome, dados in srv.meses.get(pasta, {}).items():
                        itens.append(f"<d:response><d:href>{PREFIXO}/{pasta}/{nome}</d:href><d:propstat><d:prop>"
                                     f"<d:getcontentlength>{len(dados)}</d:getcontentlength></d:prop></d:propstat>"
                                     "</d:response>")
                    corpo = ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(itens)
                             + "</d:multistatus>").encode()
                self.send_response(207)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self):
                rng = self.headers.get("Range")
                srv.chamadas.append(("GET", self.path, rng))
                if srv.ao_get:
                    srv.ao_get(self.path)
                if not self._ok():
                    return
                mes, nome = self.path[len(PREFIXO):].strip("/").split("/")
                dados = srv.meses[mes][nome]
                ini, status = 0, 200
                m = re.fullmatch(r"bytes=(\d+)-", rng or "")
                if m and not srv.ignorar_range:
                    ini, status = int(m.group(1)), 206
                resto = dados[ini:]
                self.send_response(status)
                self.send_header("Content-Length", str(len(resto)))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {ini}-{len(dados) - 1}/{len(dados)}")
                self.end_headers()
                if srv.cortar_proximo:
                    srv.cortar_proximo = False
                    self.wfile.write(resto[: len(resto) // 2])
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.wfile.write(resto)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_port}{PREFIXO}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    def gets(self):
        return [c for c in self.chamadas if c[0] == "GET"]


class TestListar(unittest.TestCase):
    def test_meses_e_arquivos(self):
        with Webdav({"2026-08": {}, "2026-09": {"A.zip": b"PKxxxx"}}) as w:
            self.assertEqual(set(cnpj.listar(w.base, "")), {"2026-08", "2026-09"})
            self.assertEqual(cnpj.listar(w.base, "2026-09"), {"A.zip": 6})
            self.assertEqual(w.chamadas[0][2], "1")

    def test_autenticacao_errada(self):
        with Webdav({"2026-09": {}}, token="outro") as w:
            with self.assertRaises(SystemExit) as c:
                cnpj.listar(w.base, "")
        self.assertIn("401", str(c.exception))

    def test_mes_mais_recente(self):
        with Webdav({}, raiz_xml=RAIZ_XML) as w:
            self.assertEqual(cnpj.mes_mais_recente(w.base), "2026-09")

    def test_sem_mes_valido(self):
        with Webdav({"foo": {}, "2026-13": {}}) as w:
            with self.assertRaises(SystemExit):
                cnpj.mes_mais_recente(w.base)

    def test_faltando_arquivo_diz_quais(self):
        tam = {n: 10 for n in cnpj.nomes_zip()}
        del tam["Socios3.zip"]
        tam["Cnaes.zip"] = 5  # extra é ignorado
        with self.assertRaises(SystemExit) as c:
            cnpj.esperados(tam)
        self.assertIn("Socios3.zip", str(c.exception))
        tam["Socios3.zip"] = 10
        self.assertEqual(set(cnpj.esperados(tam)), set(cnpj.nomes_zip()))


class TestDisco(unittest.TestCase):
    def test_pouco_espaco(self):
        with tempfile.TemporaryDirectory() as td:
            pouco = mock.Mock(return_value=mock.Mock(free=19))
            with self.assertRaises(SystemExit) as c:
                cnpj.checar_disco(td, {"A.zip": 10, "B.zip": 4}, pouco)
            self.assertIn("necessário", str(c.exception))

    def test_espaco_suficiente_e_part_conta(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "A.zip.part").write_bytes(b"x" * 5)
            cnpj.checar_disco(td, {"A.zip": 10}, mock.Mock(return_value=mock.Mock(free=15)))  # 15 + 5 >= 20


class TestBaixarWebdav(unittest.TestCase):
    DADOS = b"PK" + bytes(range(256)) * 40

    def rodar(self, w, dados=None, parte=None, tamanho=None):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        dest = Path(td.name) / "A.zip"
        if parte is not None:
            dest.with_name("A.zip.part").write_bytes(parte)
        tam = len(dados or self.DADOS) if tamanho is None else tamanho
        cnpj.baixar_webdav(f"{w.base}/2026-09/A.zip", dest, tam, espera=lambda s: None)
        return dest

    def test_retoma_do_part(self):
        with Webdav({"2026-09": {"A.zip": self.DADOS}}) as w:
            dest = self.rodar(w, parte=self.DADOS[:1000])
            self.assertEqual(w.gets()[0][2], "bytes=1000-")
        self.assertEqual(dest.read_bytes(), self.DADOS)
        self.assertFalse(dest.with_name("A.zip.part").exists())

    def test_conexao_cortada_retoma(self):
        with Webdav({"2026-09": {"A.zip": self.DADOS}}) as w:
            w.cortar_proximo = True
            dest = self.rodar(w)
            self.assertEqual(len(w.gets()), 2)
            self.assertTrue(w.gets()[1][2].startswith("bytes="))
        self.assertEqual(dest.read_bytes(), self.DADOS)

    def test_range_ignorado_recomeca(self):
        with Webdav({"2026-09": {"A.zip": self.DADOS}}) as w:
            w.ignorar_range = True
            dest = self.rodar(w, parte=self.DADOS[:1000])
        self.assertEqual(dest.read_bytes(), self.DADOS)

    def test_tamanho_diferente(self):
        with Webdav({"2026-09": {"A.zip": self.DADOS}}) as w:
            with self.assertRaises(SystemExit) as c:
                self.rodar(w, tamanho=len(self.DADOS) - 5)
        self.assertIn("tamanho", str(c.exception))

    def test_sem_pk(self):
        html = b"<html>" + b"x" * 500
        with Webdav({"2026-09": {"A.zip": html}}) as w:
            with self.assertRaises(SystemExit) as c:
                self.rodar(w, dados=html)
        self.assertIn("PK", str(c.exception))

    def test_erro_http_nao_e_retentado(self):
        with Webdav({"2026-09": {"A.zip": self.DADOS}}, token="outro") as w:
            with self.assertRaises(SystemExit):
                self.rodar(w)
            self.assertEqual(len(w.gets()), 1)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.tmp = Path(self.td.name)
        for alvo, valor in (("rastro.baixar.OUT", self.tmp / "brutos"), ("rastro.cnpj.SAIDA", self.tmp / "forn.json"),
                            ("rastro.cnpj.SAIDA_CONTAS", CONTAS)):
            p = mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

    def livre(self):
        return mock.Mock(return_value=mock.Mock(free=10**12))

    def test_baixar_ponta_a_ponta(self):
        locais = self.tmp / "locais"
        locais.mkdir()
        zips = zips_completos(locais)
        pasta = self.tmp / "brutos" / "cnpj" / "2026-09"
        simultaneos = []

        def ao_get(path):
            simultaneos.append(len(list(pasta.glob("*.zip"))))

        with Webdav({"2026-08": {}, "2026-09": zips}, ao_get=ao_get) as w:
            with self.assertLogs("rastro.cnpj", level="WARNING"):
                cnpj.main(["--baixar"], base=w.base, hoje=date(2026, 10, 13), disk_usage=self.livre())
            gets = w.gets()
        ordem = [re.sub(r"\d*\.zip", "", c[1].rsplit("/", 1)[-1]) for c in gets]
        self.assertEqual(len(gets), 31)
        self.assertEqual(sorted(set(ordem), key=ordem.index), ["Estabelecimentos", "Empresas", "Socios", "Simples"])
        self.assertEqual(max(simultaneos), 0)  # o anterior já foi apagado antes de cada GET
        self.assertEqual(list(pasta.iterdir()), [])
        esperado = self.tmp / "local.json"
        with self.assertLogs("rastro.cnpj", level="WARNING"):
            cnpj.gerar(locais, CONTAS, esperado, "2026-09")
        a, b = (json.loads(f.read_text(encoding="utf-8")) for f in (self.tmp / "forn.json", esperado))
        a.pop("gerado_em"), b.pop("gerado_em")
        self.assertEqual(a, b)
        self.assertTrue(all(u.startswith(cnpj.WEBDAV + "/2026-09/") for u in a["fonte"]))

    def test_baixar_aborta_sem_disco_antes_de_qualquer_get(self):
        zips = {n: b"PK" + b"0" * 10 for n in cnpj.nomes_zip()}
        with Webdav({"2026-09": zips}) as w:
            pouco = mock.Mock(return_value=mock.Mock(free=5))
            with self.assertRaises(SystemExit):
                cnpj.main(["--baixar", "--mes", "2026-09"], base=w.base, hoje=date(2026, 10, 13), disk_usage=pouco)
            self.assertEqual(w.gets(), [])
            self.assertEqual({c[0] for c in w.chamadas}, {"PROPFIND"})

    def test_modo_local(self):
        pasta = self.tmp / "brutos" / "cnpj" / "2026-09"
        pasta.mkdir(parents=True)
        zips_completos(pasta)
        with self.assertLogs("rastro.cnpj", level="WARNING"):
            cnpj.main(["--mes", "2026-09"])
        self.assertIn(cnpj.WEBDAV, (self.tmp / "forn.json").read_text(encoding="utf-8"))

    def test_sem_baixar_exige_mes(self):
        with self.assertRaises(SystemExit):
            cnpj.main([])

    def test_bloqueia_25_10_sem_nenhuma_rede(self):
        with Webdav({"2026-09": {}}) as w:
            with self.assertRaises(SystemExit):
                cnpj.main(["--baixar"], base=w.base, hoje=date(2026, 10, 25))
            self.assertEqual(w.chamadas, [])

    def test_mes_invalido(self):
        with self.assertRaises(SystemExit):
            cnpj.main(["--mes", "2026-13"])


if __name__ == "__main__":
    unittest.main()
