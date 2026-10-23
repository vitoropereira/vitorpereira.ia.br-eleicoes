"""Regras dos classificadores e RUNBOOK de debates (debates/regras/*.md, debates/RUNBOOK.md): têm que existir e
ficar em sincronia com as escalas do validador."""
import re
import unittest
from pathlib import Path

from debates import validar as vd

RAIZ = Path(__file__).resolve().parent.parent
DEBATES = RAIZ / "debates"
REGRAS = ("pesquisa", "checagem", "retorica", "auditoria", "juiz")

# escala antiga de vereditos: não pode voltar a aparecer em pesquisa.md
ESCALA_ANTIGA = (
    "verdadeiro-com-ressalva", "exagerado", "sem-evidencia", "nao-checavel", "ja-existe", "viavel",
    "depende-do-congresso", "sem-custo-estimado", "inviavel", "ha-investigacao", "ha-denuncia",
    "ha-condenacao", "sem-registro-publico",
)

LINHA_CATEGORIA = re.compile(r"^- `([a-z-]+)` —", re.M)


def categorias(nome):
    return set(LINHA_CATEGORIA.findall((DEBATES / "regras" / f"{nome}.md").read_text(encoding="utf-8")))


class RegrasDebates(unittest.TestCase):
    def test_arquivos_existem(self):
        for p in [DEBATES / "regras" / f"{n}.md" for n in REGRAS] + [DEBATES / "RUNBOOK.md"]:
            self.assertTrue(p.is_file(), f"falta {p}")
            self.assertTrue(p.read_text(encoding="utf-8").strip(), f"{p} está vazio")

    def test_readme_aponta(self):
        readme = (DEBATES / "README.md").read_text(encoding="utf-8")
        self.assertIn("RUNBOOK.md", readme)
        self.assertIn("regras/", readme)

    def test_checagem_cita_vereditos(self):
        self.assertEqual(categorias("checagem"), set(vd.VEREDITO))

    def test_retorica_cita_etiquetas(self):
        self.assertEqual(categorias("retorica"), set(vd.ETIQUETAS) | {"fora"})

    def test_pesquisa_sem_escala_antiga(self):
        texto = (DEBATES / "regras" / "pesquisa.md").read_text(encoding="utf-8")
        for id_ in ESCALA_ANTIGA:
            self.assertIsNone(re.search(rf"(?<![a-z-]){re.escape(id_)}(?![a-z-])", texto), f"{id_} em pesquisa.md")

    def test_runbook_cita_regras(self):
        runbook = (DEBATES / "RUNBOOK.md").read_text(encoding="utf-8")
        for n in REGRAS:
            self.assertIn(f"regras/{n}.md", runbook)


if __name__ == "__main__":
    unittest.main()
