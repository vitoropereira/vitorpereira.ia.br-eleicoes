"""A moldura ATUAL (build_site.sitebar, montar_pagina) contra as regras das páginas publicadas do Rastro.
site/rastro/ versionado é gerado com a moldura antiga (o build exige o sal real); aqui as páginas são montadas
com o código de hoje, a fixture de tests/fixtures/rastro/paginas, um sal fictício e um diretório temporário."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_site
from rastro import paginas as pg
from tests.test_rastro_paginas import CFG, ELEITOS, FIX, FORN, INDS, PUBL, SAL
from tests.test_rastro_publicado import RAIZ, faltas_pagina_eleito, problemas, scripts_fora


class TestMolduraAtual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sal_real = RAIZ / "rastro" / ".sal"
        cls.sal_antes = cls.sal_real.stat().st_mtime_ns if cls.sal_real.exists() else None
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        tmp = Path(cls.tmp.name)
        pags = pg.gerar(tmp / "out", PUBL, ELEITOS, FIX / "contas", INDS, FORN, CFG,
                        envolver=build_site.rastro_envolver("2026-10-04", "2026-10-18"), sal=SAL)
        cls.paginas = {p["path"]: (tmp / "out" / p["path"].strip("/") / "index.html").read_text(encoding="utf-8") for p in pags}

    def test_nao_toca_no_sal_real(self):
        depois = self.sal_real.stat().st_mtime_ns if self.sal_real.exists() else None
        self.assertEqual(depois, self.sal_antes)

    def test_cobre_tipos_de_pagina(self):
        paths = list(self.paginas)
        self.assertIn("/rastro/", paths)
        self.assertIn("/rastro/metodologia/", paths)
        forn = [p.rsplit("/", 2)[-2] for p in paths if p.startswith("/rastro/fornecedor/")]
        self.assertTrue([f for f in forn if f.isdigit()], "sem fornecedor PJ (CNPJ)")
        self.assertTrue([f for f in forn if not f.isdigit()], "sem fornecedor MEI (hash)")
        self.assertTrue(self.eleitos(), "sem página de eleito")

    def eleitos(self):
        return {p: h for p, h in self.paginas.items() if p != "/rastro/" and not p.startswith(("/rastro/fornecedor/", "/rastro/metodologia/"))}

    def test_moldura_presente(self):
        for p, h in self.paginas.items():
            self.assertIn('class="sitebar"', h, p)

    def test_isolamento(self):
        for p, h in self.paginas.items():
            self.assertEqual(scripts_fora(h), set(), p)

    def test_sem_cpf_nem_termo_proibido(self):
        for p, h in self.paginas.items():
            self.assertEqual(problemas(h), [], p)

    def test_pagina_eleito(self):
        for p, h in self.eleitos().items():
            self.assertEqual(faltas_pagina_eleito(h), [], p)

    def test_detecta_script_novo_na_moldura(self):
        original = build_site.sitebar
        pagina = {"titulo": "t", "desc": "d", "path": "/rastro/", "crumbs": [], "html": '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>'
                  "<body><main>x</main></body></html>"}
        envolver = build_site.rastro_envolver("2026-10-04", "2026-10-18")
        self.assertEqual(scripts_fora(envolver(pagina)), set())
        with mock.patch.object(build_site, "sitebar", lambda a, f=original: f(a) + '<script src="/x.js"></script>'):
            self.assertEqual(scripts_fora(envolver(pagina)), {"/x.js"})


if __name__ == "__main__":
    unittest.main()
