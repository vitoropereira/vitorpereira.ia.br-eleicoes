"""Testes das análises (analise/calcular.py -> analise/dados/*.json). Lêem os arquivos versionados.
Rodar a comparação completa (200 reamostragens, ~minutos): ANALISE_COMPLETO=1."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
AN = R / "analise"
DADOS = AN / "dados"
T1 = R / "municipios" / "geo" / "t1"
sys.path.insert(0, str(AN))
import calcular as CALC  # noqa: E402
import inferencia as EI  # noqa: E402

UFS = CALC.UFS
ARQS = ["lados", "campos", "dividido", "cadeiras", "divergencias", "brancos", "fragmentacao", "legenda", "puxadores",
        "comparacao2022", "cenarios", "destaques", "faq"]
_c = {}


def dado(nome):
    if nome not in _c: _c[nome] = json.loads((DADOS / f"{nome}.json").read_text())
    return _c[nome]


def t1(nome):
    k = "t1/" + nome
    if k not in _c: _c[k] = json.loads((T1 / f"{nome}.json").read_text())
    return _c[k]


class TestArquivos(unittest.TestCase):
    def test_existem_e_cabem(self):
        for n in ARQS:
            p = DADOS / f"{n}.json"
            self.assertTrue(p.exists(), n)
            self.assertLessEqual(p.stat().st_size, int(2.5 * 1024 * 1024), n)


class TestCampos(unittest.TestCase):
    def test_presidente_bate_com_tse(self):
        cand = t1("meta")["cand"]["presidente"]
        br = t1("presidente")["br"]
        i_l = next(i for i, c in enumerate(cand) if c["nome"] == "Lula")
        i_f = next(i for i, c in enumerate(cand) if c["nome"] == "Flávio Bolsonaro")
        c = dado("campos")["BR"]["presidente"]
        self.assertEqual(c["L"], br[5][i_l])
        self.assertEqual(c["F"], br[5][i_f])
        # o lado F para presidente é o PL (Flávio): mesmo número na tabela por partido
        pp = t1("partidos-presidente")
        self.assertEqual(c["F"], pp["br"][1][pp["partidos"].index("PL")])
        self.assertEqual(c["L"], pp["br"][1][pp["partidos"].index("PT")])

    def test_soma_lados_igual_validos(self):
        cam = dado("campos")
        for g in ["BR"] + UFS:
            for cargo, x in cam[g].items():
                self.assertEqual(x["L"] + x["F"] + x["C"], x["validos"], (g, cargo))
                if cargo in ("depfed", "depest"):
                    for k in "LFC": self.assertLessEqual(x["legenda"][k], x[k], (g, cargo, k))

    def test_br_soma_das_ufs(self):
        cam = dado("campos")
        for cargo in ("governador", "senador", "depfed", "depest"):
            for k in ("L", "F", "C", "validos"):
                self.assertEqual(cam["BR"][cargo][k], sum(cam[u][cargo][k] for u in UFS), (cargo, k))

    def test_senado_dois_votos(self):
        self.assertEqual(dado("campos")["BR"]["senador"]["votos_por_eleitor"], 2)


class TestCadeiras(unittest.TestCase):
    def test_totais(self):
        c = dado("cadeiras")["BR"]
        self.assertEqual(c["depfed"]["total"], 513)
        self.assertEqual(sum(c["depfed"]["cadeiras"].values()), 513)
        self.assertEqual(c["senador"]["total"], 54)
        self.assertEqual(sum(c["senador"]["cadeiras"].values()), 54)

    def test_uf_soma_br(self):
        c = dado("cadeiras")
        for cargo in ("depfed", "depest", "senador"):
            for k in "LFC":
                self.assertEqual(c["BR"][cargo]["cadeiras"][k], sum(c[u][cargo]["cadeiras"][k] for u in UFS))


class TestDividido(unittest.TestCase):
    def celulas(self):
        d = dado("dividido")
        for g in ["BR"] + UFS:
            for cargo in ("depfed", "depest", "senador", "governador"):
                yield g, cargo, d[g][cargo]

    def test_formato(self):
        d = dado("dividido")
        self.assertLessEqual(len(d["metodo"].split()), 120)
        for k in ("lula_para_F", "lula_para_C", "lula_para_L", "flavio_para_L", "flavio_para_C", "flavio_para_F"):
            self.assertIn(k, d["BR"]["depfed"])
        self.assertIs(d["BR"]["depfed"]["est"], True)

    def test_linhas_somam_1(self):
        for g, cargo, x in self.celulas():
            for r in CALC.LINHAS:
                s = sum(x[f"{r}_para_{c}"]["pct"] for c in CALC.COLS)
                self.assertAlmostEqual(s, 1.0, delta=1e-6, msg=(g, cargo, r))

    def test_dentro_dos_limites_e_intervalo(self):
        for g, cargo, x in self.celulas():
            for r in CALC.LINHAS:
                for c in CALC.COLS:
                    k = f"{r}_para_{c}"
                    p, (lo, hi), (dlo, dhi) = x[k]["pct"], x[k]["int"], x["limites"][k]
                    self.assertTrue(dlo <= p <= dhi, (g, cargo, k, p, dlo, dhi))
                    self.assertTrue(lo <= p <= hi, (g, cargo, k, p, lo, hi))
                    self.assertTrue(dlo <= lo and hi <= dhi, (g, cargo, k))

    def test_contagens_batem_com_oficiais(self):
        """Soma das linhas e colunas reconciliadas = votos oficiais nos municípios (Brasil, deputado federal)."""
        x = dado("dividido")["BR"]["depfed"]
        cam = dado("campos")["BR"]["depfed"]
        for c in "LF":
            soma = sum(x[f"{r}_para_{c}"]["v"] for r in CALC.LINHAS)
            self.assertLess(abs(soma - cam[c]) / cam[c], 1e-4, c)


class TestSintetico(unittest.TestCase):
    """O estimador recupera uma matriz conhecida em dados simulados com heterogeneidade entre municípios."""

    def test_recupera_matriz(self):
        import random
        un, ver = EI.simula(random.Random("um"), 300)
        for r, c, v, p, lo, hi, _ in EI.avalia(un, ver, 100, "um"):
            if r < 2: self.assertLess(abs(p - v), 0.03, (r, c, v, p))

    def test_cobertura(self):
        res = EI.cobertura(reps=5, n_mun=250, n_boot=150, semente="teste")
        self.assertGreaterEqual(res["cobertura"], 0.85, res)
        self.assertLess(res["erro_max"], 0.06, res)
        self.assertIn("ponto_fora", res)  # ponto fora da faixa é relatado, não escondido

    def test_avalia_nao_forca_o_ponto_na_faixa(self):
        import random
        un, ver = EI.simula(random.Random("dois"), 200)
        for r, c, v, p, lo, hi, dentro in EI.avalia(un, ver, 60, "dois"):
            self.assertEqual(dentro, lo <= p <= hi)

    def test_bootstrap_deterministico(self):
        import random
        un, _ = EI.simula(random.Random("tres"), 80)
        B, _ = EI.estima(un)
        a = EI.bootstrap(un, B, 0.0, 15, "mesma")
        b = EI.bootstrap(un, B, 0.0, 15, "mesma")
        c = EI.bootstrap(un, B, 0.0, 15, "outra")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_duncan_davis(self):
        un = [(100.0, [60.0, 30.0, 10.0], [50.0, 30.0, 15.0, 5.0])]
        self.assertEqual(EI.duncan_davis(un, 0, 1), (0.0, 30.0))
        self.assertEqual(EI.duncan_davis(un, 0, 0), (10.0, 50.0))

    def test_simplex(self):
        for v in ([0.5, 0.9, -0.2, 0.1], [2.0, 0.0, 0.0, 0.0], [0.25] * 4):
            x = EI.projeta_simplex(v)
            self.assertAlmostEqual(sum(x), 1.0, places=12)
            self.assertTrue(all(0 <= y <= 1 for y in x))


class TestTextos(unittest.TestCase):
    """Todo número de destaque/FAQ vem dos dados calculados (nenhum número digitado à mão)."""

    def dados(self):
        return {f"{n}.json": dado(n) for n in ARQS}

    def confere(self, itens, campos):
        D = self.dados()
        for it in itens:
            tokens_ok = set(CALC.LIVRES)
            for ref in it["refs"]:
                v = CALC.pega(D, ref["arq"], ref["caminho"])
                self.assertEqual(CALC.fmt(v, ref["fmt"]), ref["texto"], ref)
                tokens_ok |= set(CALC.NUM.findall(ref["texto"]))
            for campo in campos:
                for tok in CALC.NUM.findall(it.get(campo, "")):
                    self.assertIn(tok, tokens_ok, f"{it.get('id', it.get('q'))}: número '{tok}' sem fonte")

    def test_destaques(self):
        d = dado("destaques")
        self.assertTrue(6 <= len(d) <= 8)
        for x in d:
            for k in ("id", "titulo", "numero", "texto", "est", "ancora"): self.assertIn(k, x)
            self.assertTrue(x["ancora"].startswith("#"))
        self.confere(d, ("titulo", "numero", "texto"))

    def test_faq(self):
        f = dado("faq")
        self.assertTrue(8 <= len(f) <= 12)
        self.confere(f, ("q", "a"))

    def test_pl_2022(self):
        pl = dado("comparacao2022")["BR"]["pl_depfed"]
        self.assertEqual(pl["2022_tse_atual"], 98)
        self.assertEqual(pl["eleitos_2022"], 99)


class TestContrato(unittest.TestCase):
    def test_int_em_proporcao(self):
        for g, x in dado("dividido").items():
            if g not in ["BR"] + UFS: continue
            for cargo, y in x.items():
                for k, cel in y.items():
                    if isinstance(cel, dict) and "int" in cel:
                        self.assertTrue(0 <= cel["int"][0] <= cel["int"][1] <= 1, (g, cargo, k))
                        self.assertIsInstance(cel["v"], int)

    def test_comparacao_forma_mu(self):
        c = dado("comparacao2022")
        chaves = set(next(iter(c["mu"].values())))
        for g in ["BR"] + UFS: self.assertTrue(chaves <= set(c[g]), g)
        self.assertIsInstance(c["ranking"], list)
        # principal = 1º turno x 1º turno; 2º turno de 2022 só como campo secundário
        self.assertEqual(c["BR"]["pres22_pct_lula"], round(57_259_504 / (57_259_504 + 51_072_345), 4))
        self.assertEqual(c["BR"]["pres22_2t_pct_lula"], round(60_345_999 / (60_345_999 + 58_206_354), 4))
        self.assertIn("viradas_vs_2t_2022", c)
        for x in c["ranking"]:
            for k in ("cd", "nome", "uf", "pres22", "pres26", "pres22_pct_lula", "pres26_pct_lula", "eleitores"):
                self.assertIn(k, x)


class TestBaseDaDispersao(unittest.TestCase):
    """Dispersão do voto dividido: x tem de ser Lula / válidos (mesma base do y), não a fatia de 2 candidatos."""

    def test_pontao_rs(self):
        c = dado("comparacao2022")
        mun = CALC.Base().mun if hasattr(CALC, "Base") else None
        self.assertIsNotNone(mun)
        cd = next(k for k, v in mun.items() if v[0].upper() == "PONTÃO" and v[1] == "RS")
        m = c["mu"][cd]
        self.assertAlmostEqual(m["pres26_validos_lula"], 0.389, delta=0.001)
        self.assertAlmostEqual(m["pres26_pct_lula"], 0.412, delta=0.001)
        self.assertLess(m["pres26_validos_lula"], m["pres26_pct_lula"])
        for g in ["BR"] + UFS:
            self.assertIn("pres26_validos_lula", c[g]); self.assertIn("pres22_validos_lula", c[g])
            self.assertLess(c[g]["pres26_validos_lula"], c[g]["pres26_pct_lula"])

    def test_scatter_usa_validos(self):
        js = (AN / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("x[i] = m.pres26_validos_lula", js)
        self.assertNotIn("x[i] = m.pres26_pct_lula", js)
        self.assertIn("% de ${CAND.L} nos votos válidos (presidente)", js)


class TestDivergencias(unittest.TestCase):
    """Uma definição só: divergente = presidente com vencedor L ou F e o cargo com outro lado (L, F ou C); empate
    para presidente fica fora. A mesma regra do HUD (hud/calc.js) e da página (analise/js/calc.js)."""

    def test_quatro_direcoes_e_regra_do_hud(self):
        d = dado("divergencias")
        for c in CALC.LEG:
            x = d["uf"]["BR"][c]
            self.assertEqual(x["divergentes"], x["lula_e_F"] + x["flavio_e_L"] + x["lula_e_C"] + x["flavio_e_C"], c)
            hud = sum(1 for m in d["mu"].values() if c in m and m["pres"] in ("L", "F") and m[c] != m["pres"])
            self.assertEqual(x["divergentes"], hud, c)
            for g in UFS:
                y = d["uf"][g][c]
                self.assertEqual(y["divergentes"], y["lula_e_F"] + y["flavio_e_L"] + y["lula_e_C"] + y["flavio_e_C"], (g, c))

    def test_brasil_depfed(self):
        x = dado("divergencias")["uf"]["BR"]["depfed"]
        # 2.280 com os lados de antes; 2.283 depois de sair as exceções PSD-SC e PSDB-RS (sem prova verificável)
        self.assertEqual((x["divergentes"], x["total"]), (2283, 5571))

    def test_empate_presidente_fora(self):
        d = dado("divergencias")
        for cd in ("1706258", "3554755"):
            self.assertEqual(d["mu"][cd]["pres"], "C")
        self.assertIn("centro", d["criterio"])
        self.assertIn("empate", d["criterio"])


class TestViradas(unittest.TestCase):
    EMPATES_2026 = ("1706258", "3554755")

    def test_empate_vira_E_e_fica_fora(self):
        c = dado("comparacao2022")
        for cd in self.EMPATES_2026:
            self.assertEqual(c["mu"][cd]["pres26"], "E", cd)
        v = c["viradas"]
        self.assertEqual(v["lula_para_flavio"], 711)
        self.assertEqual(v["mantem_direita"], 2191)
        self.assertEqual(v["mantem_lula"], 2663)
        n_e = sum(1 for m in c["mu"].values() if "E" in (m["pres22"], m["pres26"]))
        self.assertEqual(sum(v.values()) + n_e, len(c["mu"]))
        self.assertEqual(sum(c[u]["viradas"]["lula_para_flavio"] for u in UFS), v["lula_para_flavio"])

    def test_empate_sintetico(self):
        self.assertIsNone(CALC.chave_virada("L", "E"))
        self.assertIsNone(CALC.chave_virada("E", "F"))
        self.assertEqual(CALC.chave_virada("L", "F"), "lula_para_flavio")
        self.assertEqual(CALC.lado_pres(10, 10, "F"), "E")
        self.assertEqual(CALC.lado_pres(11, 10, "F"), "L")
        self.assertEqual(CALC.lado_pres(9, 10, "B"), "B")


class TestCenarios(unittest.TestCase):
    PROP = {"lula", "flavio", "lula_validos", "flavio_validos", "flavio_pct_eliminados", "flavio_pct_dos_eliminados",
            "lula_pct_dos_eliminados", "lula_1t", "bolsonaro_1t", "lula_2t", "bolsonaro_2t", "eliminados_pct"}

    def test_proporcoes_0_1(self):
        achou = []

        def anda(o, cam):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in self.PROP and isinstance(v, (int, float)):
                        achou.append(k)
                        self.assertTrue(0 <= v <= 1, (cam + [k], v))
                    anda(v, cam + [k])
            elif isinstance(o, list):
                for i, v in enumerate(o): anda(v, cam + [i])
        anda(dado("cenarios"), [])
        self.assertGreaterEqual(len(achou), 20)

    def test_texto_em_porcentagem(self):
        txt = json.dumps(dado("faq"), ensure_ascii=False) + json.dumps(dado("destaques"), ensure_ascii=False)
        self.assertIn("61,94%", txt)
        self.assertNotIn("6.194%", txt)
        self.assertNotIn("0,62%", txt)

    def test_eliminados_seguem_lados_2026(self):
        l26 = dado("lados")["2026"]
        for e in dado("cenarios")["eliminados"]:
            self.assertIn("apoio_candidato", e)
            if e["partido"] in l26: self.assertEqual(e["lado_partido"], l26[e["partido"]]["lado"], e["nome"])
        el = {e["nome"]: e for e in dado("cenarios")["eliminados"]}
        self.assertEqual(el["Ronaldo Caiado"]["lado_partido"], "C")
        for n in ("Ronaldo Caiado", "Zema"):
            self.assertEqual(el[n]["apoio_candidato"], "F")
            self.assertTrue(el[n]["fonte_url"].startswith("https://") and el[n]["fonte_data"], n)


class TestTextosNeutros(unittest.TestCase):
    def test_sem_frases_vetadas(self):
        txt = json.dumps([dado("faq"), dado("destaques"), dado("comparacao2022")["BR"]["pl_depfed"]], ensure_ascii=False)
        self.assertNotIn("sobras de 2024", txt)
        self.assertIn("recálculo das sobras determinado pelo STF", txt)
        q = next(x for x in dado("faq") if x["q"].startswith("Por que Lula (PT) tem tantos votos"))
        self.assertTrue(q["a"].startswith("Pela estimativa, "), q["a"])


class TestCenariosAntigo(unittest.TestCase):
    def test_pesquisas(self):
        c = dado("cenarios")
        inst = [(p["instituto"], p["campo"]) for p in c["pesquisas"]]
        self.assertNotIn("PoderData", [i for i, _ in inst])
        self.assertIn(("Datafolha", "06–08/10/2026"), inst)
        for p in c["pesquisas"]:
            self.assertIn("antes_1t", p)
            self.assertTrue(p.get("url_alt") or p["criterio"] == "registro conferido no TSE", p)

    def test_precisa(self):
        p = dado("cenarios")["precisa"]
        self.assertAlmostEqual(p["lula_pct_dos_eliminados"] + p["flavio_pct_dos_eliminados"], 1.0, places=3)
        self.assertEqual(p["minimo_para_vencer"], p["votos_validos"] // 2 + 1)


class TestLados(unittest.TestCase):
    def test_psd_ba_lado_nacional(self):
        self.assertNotIn("BA", dado("lados")["2026"]["PSD"]["uf"])


class TestDeterminismo(unittest.TestCase):
    @staticmethod
    def dispara(pasta, boot, proc=8, hashseed=None):
        env = dict(os.environ, **({"PYTHONHASHSEED": str(hashseed)} if hashseed is not None else {}))
        return subprocess.Popen([sys.executable, str(AN / "calcular.py"), "--saida", pasta, "--boot", str(boot),
                                 "--proc", str(proc)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @staticmethod
    def colhe(proc, pasta):
        out, err = proc.communicate()
        if proc.returncode:
            raise AssertionError(f"calcular.py saiu com {proc.returncode}: {err.decode()[-2000:]}")
        return {n: (Path(pasta) / f"{n}.json").read_bytes() for n in ARQS}

    def roda(self, pasta, boot):
        return self.colhe(self.dispara(pasta, boot), pasta)

    def test_duas_rodadas_iguais(self):
        """as duas rodadas correm juntas (issue #148: antes era uma depois da outra, com 20 reamostragens), uma em
        série e outra com Pool de 4, cada uma com PYTHONHASHSEED diferente: a saída não pode depender da ordem de set/dict
        por hash nem da ordem em que o Pool devolve. Com 3 reamostragens (eram 20) roda o mesmo código de semente e
        percentil; a rodada inteira, com as 200, é a de test_igual_ao_versionado"""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            pa, pb = self.dispara(a, 3, proc=1, hashseed=1), self.dispara(b, 3, proc=4, hashseed=2)
            ra, rb = self.colhe(pa, a), self.colhe(pb, b)
        self.assertEqual(ra, rb)

    @unittest.skipUnless(os.environ.get("ANALISE_COMPLETO"), "rodada completa: ANALISE_COMPLETO=1")
    def test_igual_ao_versionado(self):
        with tempfile.TemporaryDirectory() as a:
            novo = self.roda(a, CALC.N_BOOT)
        for n in ARQS:
            self.assertEqual(novo[n], (DADOS / f"{n}.json").read_bytes(), n)


if __name__ == "__main__":
    unittest.main()
