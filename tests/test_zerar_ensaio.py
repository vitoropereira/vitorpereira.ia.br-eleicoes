import contextlib, io, os, socket, sys, unittest, unittest.mock, urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "supabase"))
import zerar_ensaio as Z

TOKEN_FALSO, REF_FALSO = "sbp_tokenfalso0123456789", "reffalsoabcdefgh"


def sem_rede(*a, **k):
    raise AssertionError("abriu conexão de rede")


def rodar(argv, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        codigo = Z.main(argv, **kw)
    return codigo, out.getvalue()


class ClienteFalso:
    def __init__(self, falhar_apagar=False):
        self.chamadas, self.objetos = [], {
            "_estado.json": b'{"travaAte": 0}', "_parcial.json": b"{}", "agora.json": b"{}", "feed.json": b"[]",
            "config.json": b'{"presenca":true}', "serie/index.json": b"[]", "serie/1930.json": b"{}",
        }
        self.ativo, self.falhar_apagar = True, falhar_apagar

    def sql(self, q):
        self.chamadas.append(("sql", q))
        if "active := false" in q:
            self.ativo = False
        elif "active := true" in q:
            self.ativo = True
        return [{"jobname": Z.JOB, "schedule": "* * * * *", "active": self.ativo}]

    def listar(self, prefixo):
        self.chamadas.append(("listar", prefixo))
        return sorted(k for k in self.objetos if k.startswith(prefixo))

    def ler(self, caminho):
        self.chamadas.append(("ler", caminho))
        return self.objetos.get(caminho)

    def apagar(self, caminhos):
        self.chamadas.append(("apagar", list(caminhos)))
        if self.falhar_apagar:
            raise RuntimeError("Storage respondeu 500")
        for c in caminhos:
            self.objetos.pop(c, None)


class DryRun(unittest.TestCase):
    def setUp(self):
        self.p = [
            unittest.mock.patch.object(urllib.request, "urlopen", sem_rede),
            unittest.mock.patch.object(socket, "create_connection", sem_rede),
            unittest.mock.patch.dict(os.environ, {"SUPABASE_TOKEN": TOKEN_FALSO, "SUPABASE_PROJECT_REF": REF_FALSO}),
        ]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_sem_flags_e_dry_run_sem_rede(self):
        def nao_crie():
            raise AssertionError("criou o cliente no dry-run")
        codigo, saida = rodar([], fabrica=nao_crie)
        self.assertEqual(codigo, 0)
        self.assertIn("dry-run", saida)

    def test_ordem_dos_passos(self):
        _, saida = rodar([])
        marcos = [
            f"jobname = '{Z.JOB}'), active := false",
            "travaAte",
            "_estado.json", "_parcial.json", "agora.json", "feed.json", "serie/",
            "ausente",
            "active := true",
        ]
        pos = [saida.find(m) for m in marcos]
        self.assertNotIn(-1, pos, list(zip(marcos, pos)))
        self.assertLess(pos[0], pos[1])
        remocao = saida.find("apagaria")
        self.assertLess(pos[1], remocao)
        for alvo in marcos[2:7]:
            self.assertGreater(saida.find(alvo, remocao), remocao, alvo)
        self.assertLess(remocao, saida.find("ausente", remocao))
        self.assertLess(saida.find("ausente", remocao), saida.rfind("active := true"))

    def test_config_json_nunca_e_alvo(self):
        self.assertNotIn("config.json", Z.ALVOS)
        _, saida = rodar([])
        for linha in saida.splitlines():
            if "config.json" in linha:
                self.assertNotRegex(linha, r"^\s*-\s")  # nunca listado como alvo

    def test_nao_imprime_credenciais(self):
        _, saida = rodar([])
        self.assertNotIn(TOKEN_FALSO, saida)
        self.assertNotIn(REF_FALSO, saida)


class Executar(unittest.TestCase):
    def setUp(self):
        self.p = unittest.mock.patch.object(urllib.request, "urlopen", sem_rede)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_ordem_pausar_apagar_conferir_reativar(self):
        c = ClienteFalso()
        codigo, saida = rodar(["--executar"], fabrica=lambda: c, dormir=lambda s: None)
        self.assertEqual(codigo, 0, saida)
        tipos = [(t, a) for t, a in c.chamadas]
        i_pausa = next(i for i, (t, a) in enumerate(tipos) if t == "sql" and "active := false" in a)
        i_apaga = next(i for i, (t, _) in enumerate(tipos) if t == "apagar")
        i_confere = max(i for i, (t, _) in enumerate(tipos) if t == "ler")
        i_reativa = next(i for i, (t, a) in enumerate(tipos) if t == "sql" and "active := true" in a)
        self.assertLess(i_pausa, i_apaga)
        self.assertLess(i_apaga, i_confere)
        self.assertLess(i_confere, i_reativa)
        apagados = tipos[i_apaga][1]
        self.assertNotIn("config.json", apagados)
        self.assertEqual(set(apagados), {"_estado.json", "_parcial.json", "agora.json", "feed.json",
                                          "serie/index.json", "serie/1930.json"})
        self.assertEqual(set(c.objetos), {"config.json"})
        self.assertTrue(c.ativo)
        self.assertIn("ELEICAO_FORCADA", saida)

    def test_espera_a_trava(self):
        c = ClienteFalso()
        c.objetos["_estado.json"] = b'{"travaAte": 1000060000}'
        dormiu = []
        codigo, _ = rodar(["--executar"], fabrica=lambda: c, dormir=dormiu.append, agora=lambda: 1000000.0)
        self.assertEqual(codigo, 0)
        self.assertGreaterEqual(sum(dormiu), 60)

    def test_falha_ao_apagar_nao_reativa(self):
        c = ClienteFalso(falhar_apagar=True)
        codigo, saida = rodar(["--executar"], fabrica=lambda: c, dormir=lambda s: None)
        self.assertNotEqual(codigo, 0)
        self.assertFalse(c.ativo)
        self.assertFalse(any(t == "sql" and "active := true" in a for t, a in c.chamadas))
        self.assertIn("agora.json", saida.split("ficou para trás", 1)[-1])
        self.assertIn("pausado", saida)


if __name__ == "__main__":
    unittest.main()
