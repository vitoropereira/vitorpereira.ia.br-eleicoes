import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WF = RAIZ / ".github" / "workflows" / "ci.yml"
WF_LOTE = RAIZ / ".github" / "workflows" / "rastro-lote.yml"


def _sem_comentarios(texto):
    return "\n".join(linha for linha in texto.splitlines() if not linha.lstrip().startswith("#"))


class TestWorkflowCI(unittest.TestCase):
    """O YAML é lido como texto (sem PyYAML): o que importa é o que ele chama e com que permissão."""

    def setUp(self):
        self.y = WF.read_text(encoding="utf-8")
        self.passos = _sem_comentarios(self.y)

    def test_dispara_em_pr_e_job_gate(self):
        self.assertIn("pull_request:", self.passos)
        self.assertRegex(self.passos, r"(?m)^name: ci\s*$")
        self.assertRegex(self.passos, r"(?m)^\s+name: gate\s*$")

    def test_mesma_versao_de_python_do_lote(self):
        versao = re.search(r'python-version: "([^"]+)"', self.passos)
        lote = re.search(r'python-version: "([^"]+)"', _sem_comentarios(WF_LOTE.read_text(encoding="utf-8")))
        self.assertIsNotNone(versao)
        self.assertIsNotNone(lote)
        self.assertEqual(versao.group(1), lote.group(1))

    def test_roda_o_gate(self):
        self.assertRegex(self.passos, r"pip install\b.*\bpytest\b")
        self.assertRegex(self.passos, r"pip install\b.*\bruff\b")
        self.assertIn("ruff check .", self.passos)
        self.assertIn("python3 -m pytest -q", self.passos)

    def test_sem_segredo_nem_escrita(self):
        self.assertRegex(self.passos, r"permissions:\s*\n\s+contents: read\s*\n")
        self.assertNotIn("secrets.", self.passos)
        self.assertNotIn("pull_request_target", self.passos)
        self.assertNotIn("write", self.passos)


if __name__ == "__main__":
    unittest.main()
