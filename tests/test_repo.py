import subprocess, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent


class Repo(unittest.TestCase):
    def ignorado(self, nome):
        return subprocess.run(["git", "-C", str(R), "check-ignore", "-q", nome]).returncode == 0

    def test_env_ignorado(self):
        for nome in (".env", ".env.local", ".env.development.local"):
            self.assertTrue(self.ignorado(nome), f"{nome} precisa estar no .gitignore")

    def test_env_example_versionado_e_sem_valores(self):
        self.assertFalse(self.ignorado(".env.example"))
        for linha in (R / ".env.example").read_text().splitlines():
            if linha and not linha.startswith("#"):
                nome, _, valor = linha.partition("=")
                self.assertEqual(valor, "", f"{nome} não pode ter valor no .env.example")

    def test_agents_md_sem_segredo(self):
        texto = (R / "AGENTS.md").read_text()
        self.assertNotIn("sbp_", texto)
        self.assertNotIn("eyJhbGci", texto)
        self.assertNotRegex(texto, r"[\w.+-]+@[\w-]+\.\w+")
        self.assertNotIn("service_role\":", texto)
        self.assertIn("qzczyicspbizosjogmlq", texto)

    def test_link_do_repo_atualizado(self):
        velho = "github.com/vitoropereira/" + "eleicoes"  # prefixo dos nomes antigos (eleicoes2026, eleicoes-2026); concatenado para o teste não casar consigo mesmo
        arquivos = subprocess.run(["git", "-C", str(R), "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
        com_velho = []
        for nome in arquivos:
            try:
                if velho in (R / nome).read_text(encoding="utf-8"):
                    com_velho.append(nome)
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                pass
        self.assertEqual(com_velho, [], "link do repo antigo ainda presente")
        textos = (R / "analise/js/textos.js").read_text()
        self.assertIn("/analise/codigo/", textos)
        self.assertNotIn("github.com/vitoropereira/" + "vitorpereira.ia.br-eleicoes", textos)


if __name__ == "__main__":
    unittest.main()
