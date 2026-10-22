import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WF = RAIZ / ".github" / "workflows" / "rastro-lote.yml"


class TestWorkflowLote(unittest.TestCase):
    """O YAML é lido como texto (sem PyYAML): o que importa é o que ele chama e com que permissão."""

    def setUp(self):
        self.y = WF.read_text(encoding="utf-8")
        self.passos = "\n".join(linha for linha in self.y.splitlines() if not linha.lstrip().startswith("#"))

    def test_agenda_e_disparo_manual(self):
        crons = re.findall(r'cron: "([^"]+)"', self.y)
        self.assertEqual(crons, ["17 11 * * *", "17 13 * * *", "7 15 * * *"])  # principal, reserva, alerta
        self.assertTrue(all(len(c.split()) == 5 and not c.startswith("0 ") for c in crons))  # fora do minuto cheio
        self.assertIn("github.event.schedule == '7 15 * * *'", self.passos)
        self.assertIn("python3 rastro/lote.py --conferir", self.passos)
        self.assertIn("workflow_dispatch:", self.y)
        self.assertIn("dry_run:", self.y)

    def test_roda_o_lote(self):
        self.assertIn("python3 rastro/lote.py --dry-run", self.passos)
        self.assertRegex(self.passos, r"python3 rastro/lote\.py\s*\n")
        self.assertIn("pip install pytest", self.passos)
        self.assertIn("fetch-depth: 0", self.passos)

    def test_sal_vem_do_secret_e_falha_se_vazio(self):
        self.assertIn("${{ secrets.RASTRO_SAL }}", self.passos)
        self.assertIn("rastro/.sal", self.passos)
        self.assertIn('if [ -z "$RASTRO_SAL" ]', self.passos)
        sal = self.passos.index("rastro/.sal")
        self.assertLess(sal, self.passos.index("python3 rastro/lote.py"))

    def test_permissoes_e_ids_de_medicao(self):
        self.assertRegex(self.y, r"permissions:\s*\n\s+contents: write\s*\n\s+pull-requests: write")
        self.assertIn("${{ vars.GA_ID }}", self.passos)
        self.assertIn("${{ vars.CLARITY_ID }}", self.passos)
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.passos)

    def test_merge_so_no_lote_py(self):
        self.assertIsNone(re.search(r"gh\s+pr\s+merge", self.passos))
        self.assertIsNone(re.search(r"gh\s+pr\s+merge", self.y))

    def test_cron_antigo_foi_apagado(self):
        self.assertFalse((RAIZ / "rastro" / "cron_lote.sh").exists())


if __name__ == "__main__":
    unittest.main()
