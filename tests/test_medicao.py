import functools, http.server, re, unittest.mock, shutil, socketserver, subprocess, sys, tempfile, threading, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B

GA_TESTE, CL_TESTE = "G-TESTE0000", "teste000"
TEM_CHROME = bool(shutil.which(B.CHROME) or Path(B.CHROME).exists())


class SemLiteral(unittest.TestCase):
    def test_nenhum_id_no_codigo_fonte(self):
        arquivos = subprocess.check_output(["git", "-C", str(R), "ls-files"], text=True).splitlines()
        achados = []
        for f in arquivos:
            if f.startswith(("site/", "tests/")) or f == ".env.example":
                continue
            try:
                txt = (R / f).read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            if re.search(r"\bG-[A-Z0-9]{8,}\b", txt) or "tp8n6kanob" in txt:
                achados.append(f)
        self.assertEqual(achados, [], "IDs de medição só na env/.env")


class Config(unittest.TestCase):
    def test_env_tem_prioridade_e_depois_o_arquivo(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("# comentario\nX_TESTE_ID=do-arquivo\nOUTRO='aspas'\n")
            self.assertEqual(B.config("X_TESTE_ID", env), "do-arquivo")
            self.assertEqual(B.config("OUTRO", env), "aspas")
            self.assertEqual(B.config("NAO_EXISTE_ID", env), "")
            with unittest.mock.patch.dict("os.environ", {"X_TESTE_ID": "da-env"}):
                self.assertEqual(B.config("X_TESTE_ID", env), "da-env")


class Gerador(unittest.TestCase):
    def test_sem_ids_nada(self):
        html, js = B.medicao("", "")
        self.assertEqual((html, js), ("", None))

    def test_so_um_dos_dois(self):
        _, js = B.medicao(GA_TESTE, "")
        self.assertIn("googletagmanager", js); self.assertNotIn("clarity.ms", js)
        _, js = B.medicao("", CL_TESTE)
        self.assertIn("clarity.ms", js); self.assertNotIn("googletagmanager", js)

    def test_com_os_dois(self):
        html, js = B.medicao(GA_TESTE, CL_TESTE)
        self.assertIn('<script src="/medicao.js" defer>', html)
        self.assertIn("consent-css", html)
        self.assertNotIn(GA_TESTE, html); self.assertNotIn(CL_TESTE, html)
        self.assertNotIn("googletagmanager", html); self.assertNotIn("clarity.ms", html)
        for x in (GA_TESTE, CL_TESTE, "googletagmanager.com", "clarity.ms"):
            self.assertIn(x, js)
            # só dentro de carregar(): nada disso antes dela
            self.assertGreater(js.index(x), js.index("function carregar()"))
            self.assertLess(js.index(x), js.index("var v=ler()"))

    def test_com_medicao_injeta_so_o_trecho(self):
        if B.MEDICAO_HTML:
            self.assertNotIn(B.GA_ID, B.com_medicao("<body></body>"))
        else:
            self.assertEqual(B.com_medicao("<body></body>"), "<body></body>")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipUnless(TEM_CHROME, "sem Chrome")
class DomReal(unittest.TestCase):
    def pagina(self, ga, cl, cookie=None):
        html, js = B.medicao(ga, cl)
        d = Path(self.tmp.name)
        for f in d.iterdir():
            f.unlink()
        if js:
            (d / "medicao.js").write_text(js)
        pre = f'<script>document.cookie="consent={cookie}; path=/"</script>' if cookie else ""
        (d / "index.html").write_text(
            f'<!doctype html><html><head><meta charset="utf-8"></head><body>{pre}<main>x</main>{html}</body></html>')

    def dom(self):
        p = subprocess.run([B.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--enable-logging=stderr", "--v=0",
                            "--virtual-time-budget=4000", "--dump-dom", f"http://127.0.0.1:{self.porta}/"],
                           capture_output=True, text=True, timeout=90)
        self.assertIn("<html", p.stdout)
        return p.stdout, p.stderr

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=self.tmp.name))
        self.porta = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.srv = srv

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.tmp.cleanup()

    def test_a_sem_consentimento_nao_carrega_nada(self):
        self.pagina(GA_TESTE, CL_TESTE)
        dom, _ = self.dom()
        self.assertNotIn("googletagmanager", dom); self.assertNotIn("clarity.ms", dom)
        self.assertIn('class="consent"', dom)

    def test_b_aceito_carrega_os_dois(self):
        self.pagina(GA_TESTE, CL_TESTE, "accepted")
        dom, _ = self.dom()
        self.assertIn("googletagmanager.com/gtag/js?id=" + GA_TESTE, dom)
        self.assertIn("clarity.ms/tag/" + CL_TESTE, dom)
        self.assertNotIn('class="consent"', dom)

    def test_c_recusado_nao_carrega(self):
        self.pagina(GA_TESTE, CL_TESTE, "rejected")
        dom, _ = self.dom()
        self.assertNotIn("googletagmanager", dom); self.assertNotIn("clarity.ms", dom)
        self.assertNotIn('class="consent"', dom)

    def test_d_sem_ids_sem_banner_e_sem_erro(self):
        self.pagina("", "")
        dom, err = self.dom()
        self.assertNotIn("googletagmanager", dom); self.assertNotIn("clarity.ms", dom)
        self.assertNotIn('class="consent"', dom)
        self.assertNotIn("Uncaught", err)


if __name__ == "__main__":
    unittest.main()
