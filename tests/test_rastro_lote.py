import json
import re
import shutil
import tempfile
import unittest
from unittest import mock
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from rastro import fila, lote
from rastro.contas import RE_CPF, cpf_valido

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "paginas"
ELEITOS = json.loads((FIX / "eleitos.json").read_text(encoding="utf-8"))
INDS = json.loads((FIX / "indicadores.json").read_text(encoding="utf-8"))
CFG = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))


def cpfs(texto):
    return [m.group() for m in RE_CPF.finditer(texto) if cpf_valido(re.sub(r"\D", "", m.group()))]


class TestFila(unittest.TestCase):
    def test_ordem_das_fixtures(self):
        self.assertEqual(fila.ordenar(ELEITOS, INDS), ["2003", "2001", "2004", "2002"])

    def test_sem_duplicado_sq_string_e_cargo_desconhecido_no_fim(self):
        eleitos = [{"sq": 1, "cargo": "xyz", "votos": 999}, {"sq": 2, "cargo": "depfed", "votos": 1},
                   {"sq": 2, "cargo": "depfed", "votos": 1}]
        self.assertEqual(fila.ordenar(eleitos, None), ["2", "1"])

    def test_main_grava_lista_pura_e_nao_grava_sem_dados(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            dest = d / "fila.json"
            self.assertEqual(fila.main(d, dest), 1)
            self.assertFalse(dest.exists())
            shutil.copy(FIX / "eleitos.json", d)
            shutil.copy(FIX / "indicadores.json", d)
            self.assertEqual(fila.main(d, dest), 0)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), ["2003", "2001", "2004", "2002"])


class TestTrava(unittest.TestCase):
    TRAVA = {"trava_inicio": "2026-10-23", "trava_fim": "2026-10-26"}

    def test_datas(self):
        for dia in (23, 24, 25, 26):
            self.assertTrue(lote.travado(date(2026, 10, dia), self.TRAVA), dia)
        for dia in (22, 27):
            self.assertFalse(lote.travado(date(2026, 10, dia), self.TRAVA), dia)

    def test_sem_trava_no_config(self):
        """Vitor tirou a trava em 21/10/2026 (o site publica os debates na semana da eleição): null = sem trava"""
        self.assertIsNone(CFG["trava_inicio"])
        self.assertIsNone(CFG["trava_fim"])
        for dia in range(20, 28):
            self.assertFalse(lote.travado(date(2026, 10, dia), CFG), dia)
        self.assertFalse(lote.travado(date(2026, 10, 25), {"trava_inicio": None, "trava_fim": None}))

    def test_main_na_trava_nao_chama_nada(self):
        chamadas = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lote, "travado", return_value=True):
            rc = lote.main(hoje=date(2026, 10, 25), raiz=d, executar=lambda *a, **k: chamadas.append(a))
        self.assertNotEqual(rc, 0)
        self.assertEqual(chamadas, [])


class TestProximos(unittest.TestCase):
    def test_sem_repeticao_e_tipos_mistos(self):
        f = ["1", "2", "3", "4"]
        self.assertEqual(lote.proximos(f, [1, "2"], 5), ["3", "4"])
        self.assertEqual(lote.proximos(f, [2], 1), ["1"])
        self.assertEqual(set(lote.proximos(f, ["1", 3], 9)) & {"1", "3"}, set())

    def test_esgotada(self):
        self.assertEqual(lote.proximos(["1"], ["1"], 3), [])

    def test_aplicar_preserva_ordem(self):
        r = lote.aplicar(["9", "1"], ["2", "1", "3"])
        self.assertEqual(r, ["9", "1", "2", "3"])
        self.assertEqual(len(r), len(set(r)))


class Falso:
    def __init__(self, branch_existe=False, suja=False, pytest_rc=0, mergeados=(), gh_merged_rc=0):
        self.cmds, self.branch_existe, self.suja, self.pytest_rc = [], branch_existe, suja, pytest_rc
        self.mergeados, self.gh_merged_rc = list(mergeados), gh_merged_rc

    def __call__(self, cmd, **kw):
        self.cmds.append(list(cmd))
        saida = ""
        rc = 0
        if cmd[:3] == ["gh", "pr", "list"] and "merged" in cmd:
            saida = json.dumps([{"title": t} for t in self.mergeados])
            rc = self.gh_merged_rc
        if cmd[:2] == ["git", "status"]:
            saida = " M x\n" if self.suja else ""
        if cmd[:2] == ["git", "rev-parse"]:
            rc = 0 if self.branch_existe else 1
        if cmd[:4] == ["python3", "-m", "pytest", "-q"]:
            rc = self.pytest_rc
        return SimpleNamespace(returncode=rc, stdout=saida, stderr="")


class TestLote(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        r = self.raiz / "rastro"
        (r / "dados").mkdir(parents=True)
        shutil.copy(FIX / "eleitos.json", r / "dados")
        shutil.copy(FIX / "indicadores.json", r / "dados")
        cfg = dict(CFG, lote_diario_tamanho=2)
        (r / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.pub = r / "publicados.json"
        self.pub.write_text(json.dumps(["2003"]), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_fluxo(self):
        ex = Falso()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 0)
        self.assertEqual(json.loads(self.pub.read_text(encoding="utf-8")), ["2003", "2001", "2004"])
        cmds = ex.cmds
        self.assertIn(["python3", "build_site.py"], cmds)
        self.assertIn(["git", "checkout", "-b", "rastro/lote-2026-10-14", "origin/main"], cmds)
        self.assertIn(["git", "add", *lote.CAMINHOS_GIT], cmds)
        self.assertFalse(any("-A" in c or "." in c for c in cmds if c[:2] == ["git", "add"]))
        # O build muda site/sitemap.xml e site/llms.txt: precisam ir no commit, senão a árvore fica suja.
        add = next(c for c in cmds if c[:2] == ["git", "add"])
        self.assertIn("site/", add)
        self.assertLess(cmds.index(["python3", "build_site.py"]), cmds.index(add))
        pr = next(c for c in cmds if c[:3] == ["gh", "pr", "create"])
        self.assertEqual(pr[pr.index("--title") + 1], "Rastro: lote 2026-10-14")
        corpo = pr[pr.index("--body") + 1]
        self.assertIn("2001", corpo)
        self.assertNotIn("2003", corpo)
        self.assertEqual(cpfs(corpo), [])
        self.assertEqual(cpfs((self.raiz / "rastro" / "fila.json").read_text(encoding="utf-8")), [])

    def test_sem_testes_mergeia_sem_rodar_o_pytest(self):
        """RODAR_TESTES = False (25/10): publica direto, sem pytest; o corpo do PR diz isso."""
        ex = Falso(pytest_rc=1)  # mesmo que o pytest fosse falhar, ele não roda
        with mock.patch.object(lote, "RODAR_TESTES", False):
            self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 0)
        self.assertNotIn(["python3", "-m", "pytest", "-q"], ex.cmds)
        self.assertEqual(ex.cmds[-1], ["gh", "pr", "merge", "rastro/lote-2026-10-14", "--squash", "--delete-branch"])
        pr = next(c for c in ex.cmds if c[:3] == ["gh", "pr", "create"])
        self.assertIn("sem os testes", pr[pr.index("--body") + 1])

    @mock.patch.object(lote, "RODAR_TESTES", True)
    def test_funciona_testes_passam_e_mergeia(self):
        ex = Falso()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 0)
        cmds = ex.cmds
        teste = ["python3", "-m", "pytest", "-q"]
        commit = next(c for c in cmds if c[:2] == ["git", "commit"])
        push = next(c for c in cmds if c[:2] == ["git", "push"])
        # O pytest roda sobre o conteúdo exato do lote: depois do commit, antes do push.
        self.assertLess(cmds.index(commit), cmds.index(teste))
        self.assertLess(cmds.index(teste), cmds.index(push))
        self.assertEqual(cmds[-1], ["gh", "pr", "merge", "rastro/lote-2026-10-14", "--squash", "--delete-branch"])
        self.assertFalse(any("--add-label" in c for c in cmds))
        pr = next(c for c in cmds if c[:3] == ["gh", "pr", "create"])
        corpo = pr[pr.index("--body") + 1]
        self.assertNotIn("merge do Vitor", corpo)
        self.assertIn("automática", corpo)
        self.assertIn("testes", corpo)

    @mock.patch.object(lote, "RODAR_TESTES", True)
    def test_resiste_teste_de_lgpd_falha_e_nao_mergeia(self):
        ex = Falso(pytest_rc=1)
        rc = lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex)
        self.assertNotEqual(rc, 0)
        self.assertFalse(any(c[:3] == ["gh", "pr", "merge"] or "merge" in c[:3] for c in ex.cmds))
        self.assertIn(["gh", "pr", "edit", "rastro/lote-2026-10-14", "--add-label", "bloqueado"], ex.cmds)

    def test_nunca_mergeia_na_trava_no_dry_run_ou_sem_sal(self):
        ex = Falso()
        with mock.patch.object(lote, "travado", return_value=True):  # o mecanismo continua, mesmo sem data no config
            lote.main(hoje=date(2026, 10, 25), raiz=self.raiz, executar=ex)
        lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex, dry_run=True)
        self.assertEqual(ex.cmds, [])

        class FalhaBuild(Falso):  # sem rastro/.sal e com MEI publicado, o build falha
            def __call__(self, cmd, **kw):
                r = super().__call__(cmd, **kw)
                if cmd == ["python3", "build_site.py"]:
                    r.returncode = 1
                return r

        ex = FalhaBuild()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 1)
        self.assertFalse(any(c[:3] == ["gh", "pr", "merge"] for c in ex.cmds))
        self.assertFalse(any(c[:2] == ["git", "push"] for c in ex.cmds))

    def test_dry_run_nao_altera(self):
        antes = self.pub.read_text(encoding="utf-8")
        ex = Falso()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex, dry_run=True), 0)
        self.assertEqual(self.pub.read_text(encoding="utf-8"), antes)
        self.assertFalse((self.raiz / "rastro" / "fila.json").exists())
        self.assertEqual(ex.cmds, [])

    def test_recusa_arvore_suja_e_branch_existente(self):
        antes = self.pub.read_text(encoding="utf-8")
        for ex in (Falso(suja=True), Falso(branch_existe=True)):
            self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 1)
            self.assertEqual(self.pub.read_text(encoding="utf-8"), antes)
            self.assertFalse(any(c[0] == "python3" or c[:2] == ["git", "push"] for c in ex.cmds))

    def test_fila_esgotada(self):
        self.pub.write_text(json.dumps(["2001", "2002", "2003", "2004"]), encoding="utf-8")
        ex = Falso()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 0)
        self.assertFalse(any(c[0] == "python3" or c[:2] in (["git", "push"], ["gh", "pr"]) and c[2] == "create" for c in ex.cmds))
        self.assertIn(["git", "branch", "-D", "rastro/lote-2026-10-14"], ex.cmds)

    def test_pr_de_lote_bloqueado_aberto_bloqueia(self):
        class ComPrAberto(Falso):
            def __call__(self, cmd, **kw):
                r = super().__call__(cmd, **kw)
                if cmd[:3] == ["gh", "pr", "list"] and "--label" in cmd:
                    r.stdout = "1\n"
                return r

        ex = ComPrAberto()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 1)
        self.assertFalse(any(c[:2] == ["git", "checkout"] for c in ex.cmds))
        lista = next(c for c in ex.cmds if c[:3] == ["gh", "pr", "list"] and "--label" in c)
        self.assertIn("bloqueado", lista[lista.index("--label") + 1])

    def test_ja_publicado_hoje_sai_sem_pr(self):
        antes = self.pub.read_text(encoding="utf-8")
        ex = Falso(mergeados=["Rastro: lote 2026-10-14"])
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex, evento="schedule"), 0)
        self.assertEqual(self.pub.read_text(encoding="utf-8"), antes)
        proibidos = (["git", "checkout"], ["git", "push"], ["gh", "pr", "create"], ["gh", "pr", "merge"])
        self.assertFalse(any(c[0] == "python3" or c[:2] in proibidos or c[:3] in proibidos for c in ex.cmds))

    def test_push_e_dispatch_publicam_mesmo_com_lote_do_dia(self):
        """publicação contínua (22/10/2026): a trava do dia é só do cron; push e disparo manual sempre rodam"""
        for evento in ("push", "workflow_dispatch"):
            ex = Falso(mergeados=["Rastro: lote 2026-10-14"])
            self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex, evento=evento), 0, evento)
            self.assertEqual(ex.cmds[-1], ["gh", "pr", "merge", "rastro/lote-2026-10-14", "--squash", "--delete-branch"], evento)
            self.assertFalse(any(c[:3] == ["gh", "pr", "list"] and "merged" in c for c in ex.cmds), evento)
            self.setUp()

    def test_lote_de_outro_dia_nao_trava(self):
        ex = Falso(mergeados=["Rastro: lote 2026-10-13"])
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex, evento="schedule"), 0)
        self.assertEqual(ex.cmds[-1], ["gh", "pr", "merge", "rastro/lote-2026-10-14", "--squash", "--delete-branch"])
        consulta = next(c for c in ex.cmds if c[:3] == ["gh", "pr", "list"] and "merged" in c)
        self.assertIn('"Rastro: lote 2026-10-14" in:title', consulta)

    def test_gh_falhou_na_consulta_nao_publica(self):
        ex = Falso(gh_merged_rc=1)
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex, evento="schedule"), 1)
        self.assertFalse(any(c[:2] == ["git", "checkout"] or c[:2] == ["git", "push"] for c in ex.cmds))

    def test_conferir(self):
        dia = date(2026, 10, 14)
        ex = Falso(mergeados=["Rastro: lote 2026-10-14"])
        self.assertEqual(lote.conferir(dia, self.raiz, ex), 0)
        ex = Falso()
        self.assertEqual(lote.conferir(dia, self.raiz, ex), 1)
        ex = Falso(gh_merged_rc=1)
        self.assertEqual(lote.conferir(dia, self.raiz, ex), 1)
        self.pub.write_text(json.dumps(["2001", "2002", "2003", "2004"]), encoding="utf-8")
        ex = Falso()
        self.assertEqual(lote.conferir(dia, self.raiz, ex), 0)
        escrita = ("checkout", "push", "commit", "add", "branch", "reset", "clean")
        self.assertFalse(any(c[0] == "git" and c[1] in escrita for c in ex.cmds))

    def test_falha_no_push_desfaz_a_branch(self):
        class FalhaPush(Falso):
            def __call__(self, cmd, **kw):
                r = super().__call__(cmd, **kw)
                if cmd[:2] == ["git", "push"]:
                    r.returncode = 1
                return r

        ex = FalhaPush()
        self.assertEqual(lote.main(hoje=date(2026, 10, 14), raiz=self.raiz, executar=ex), 1)
        self.assertIn(["git", "branch", "-D", "rastro/lote-2026-10-14"], ex.cmds)
        self.assertFalse(any(c[:3] == ["gh", "pr", "create"] for c in ex.cmds))


if __name__ == "__main__":
    unittest.main()
