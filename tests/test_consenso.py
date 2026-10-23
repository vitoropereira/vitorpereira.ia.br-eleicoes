"""Consenso entre classificadores (debates/consenso.py): votos, divergência, juiz, regra e o CLI."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from debates import consenso as C
from debates import validar as V

TESTE = R / "tests" / "fixtures" / "debates" / "2026" / "presidente-2-turno-teste"
ESC = C.ESCALAS["retorica"]
VER = C.ESCALAS["checagem"]
CEGO = [{"id": f"r-000{n}", "anterior": "", "frase": f"frase {n}", "seguinte": ""} for n in (1, 2, 3)]


class Normalizar(unittest.TestCase):
    def test_lista_e_dict(self):
        lista = [{"id": "r-0001", "etiqueta": "dado", "confianca": 0.9, "motivo": "x"},
                 {"id": "r-0002", "categoria": "fora"}]
        self.assertEqual(C.normalizar_votos(lista, ESC), {"r-0001": "dado", "r-0002": "fora"})
        self.assertEqual(C.normalizar_votos({"r-0001": "apelo"}, ESC), {"r-0001": "apelo"})

    def test_fora_da_escala(self):
        with self.assertRaisesRegex(ValueError, "r-0001.*'xis'"):
            C.normalizar_votos({"r-0001": "xis"}, ESC)
        with self.assertRaises(ValueError):
            C.normalizar_votos([{"id": "a", "categoria": "dado"}], VER)


class Decidir(unittest.TestCase):
    def test_unanime(self):
        d, como, div = C.decidir([{"a": "dado"}] * 3, ESC)
        self.assertEqual((d, como, div), ({"a": "dado"}, {"a": "unanime"}, {}))

    def test_maioria_com_os_dois_primeiros_iguais(self):
        d, como, div = C.decidir([{"a": "dado"}, {"a": "dado"}, {"a": "apelo"}], ESC)
        self.assertEqual((d, como, div), ({"a": "dado"}, {"a": "maioria"}, {}))

    def test_dois_a_um_com_os_primeiros_diferentes_diverge(self):
        d, como, div = C.decidir([{"a": "dado"}, {"a": "apelo"}, {"a": "dado"}], ESC)
        self.assertEqual((d, como, div), ({}, {}, {"a": ["dado", "apelo", "dado"]}))

    def test_maioria_simples_com_parametro(self):
        d, como, _ = C.decidir([{"a": "dado"}, {"a": "apelo"}, {"a": "dado"}], ESC, primeiros_iguais=False)
        self.assertEqual((d, como), ({"a": "dado"}, {"a": "maioria"}))

    def test_tres_diferentes_diverge(self):
        _, _, div = C.decidir([{"a": "dado"}, {"a": "apelo"}, {"a": "proposta"}], ESC)
        self.assertEqual(set(div), {"a"})

    def test_id_faltando_num_voto_diverge(self):
        d, _, div = C.decidir([{"a": "dado", "b": "dado"}, {"a": "dado"}, {"a": "dado", "b": "dado"}], ESC)
        self.assertEqual((d, div), ({"a": "dado"}, {"b": ["dado", "dado"]}))

    def test_id_fora_da_referencia(self):
        with self.assertRaisesRegex(ValueError, "zzz"):
            C.decidir([{"a": "dado", "zzz": "dado"}], ESC, ids=["a"])

    def test_id_da_referencia_sem_voto_diverge(self):
        _, _, div = C.decidir([{"a": "dado"}] * 3, ESC, ids=["a", "b"])
        self.assertEqual(div, {"b": []})


class Refazer(unittest.TestCase):
    def test_checou_coisa_certa_false(self):
        brutos = [[{"id": "a", "categoria": "verdadeiro", "checou_coisa_certa": True},
                   {"id": "b", "categoria": "verdadeiro", "checou_coisa_certa": False}],
                  [{"id": "a", "categoria": "verdadeiro"}, {"id": "b", "categoria": "verdadeiro"}],
                  {"a": "verdadeiro"}]
        self.assertEqual(C.refazer(brutos), ["b"])

    def test_decidido_e_refazer_ao_mesmo_tempo(self):
        votos = [[{"id": "b", "categoria": "verdadeiro", "checou_coisa_certa": False}],
                 [{"id": "b", "categoria": "verdadeiro"}], [{"id": "b", "categoria": "verdadeiro"}]]
        d, como, _ = C.decidir([C.normalizar_votos(v, VER) for v in votos], ids=["b"])
        self.assertEqual((d, como, C.refazer(votos)), ({"b": "verdadeiro"}, {"b": "unanime"}, ["b"]))


class Retorica(unittest.TestCase):
    def test_divergencias_no_formato_cego(self):
        self.assertEqual(C.divergencias_retorica({"r-0003", "r-0001"}, CEGO), [CEGO[0], CEGO[2]])

    def saida(self, **mais):
        base = {"modo": "retorica", "decididos": {"r-0001": "dado"}, "como": {"r-0001": "unanime"},
                "divergencias": [CEGO[1], CEGO[2]], "votos": {"r-0002": ["apelo", "proposta", "dado"],
                                                              "r-0003": ["apelo", "fora"]}}
        return {**base, **mais}

    def test_juizes_de_acordo(self):
        final, como = C.aplicar(self.saida(), [{"r-0002": "apelo", "r-0003": "fora"}] * 2)
        self.assertEqual(final["r-0002"], "apelo")
        self.assertEqual(como["r-0002"], "juiz")

    def test_juizes_divergentes_ou_ausentes_caem_na_regra(self):
        final, como = C.aplicar(self.saida(), [{"r-0002": "apelo"}, {"r-0002": "proposta"}])
        # regra: primeiro de dado, proposta, ataque-critica, apelo entre os votados (inclui os votos dos etiquetadores)
        self.assertEqual((final["r-0002"], como["r-0002"]), ("dado", "regra"))
        self.assertEqual((final["r-0003"], como["r-0003"]), ("apelo", "regra"))  # ausente; `fora` só se for o único
        self.assertEqual(final["r-0001"], "dado")

    def test_fora_so_ganha_sozinho(self):
        s = self.saida(votos={"r-0002": ["fora", "fora"], "r-0003": ["fora"]})
        final, _ = C.aplicar(s, [])
        self.assertEqual((final["r-0002"], final["r-0003"]), ("fora", "fora"))

    def test_checagem_cai_em_nao_comprovado(self):
        s = {"modo": "checagem", "decididos": {}, "como": {}, "divergencias": [{"id": "a"}],
             "votos": {"a": ["verdadeiro", "falso-ou-exagerado"]}}
        final, como = C.aplicar(s, [{"a": "verdadeiro"}, {"a": "falso-ou-exagerado"}])
        self.assertEqual((final, como), ({"a": "nao-comprovado"}, {"a": "regra"}))

    def test_juiz_em_id_sem_divergencia(self):
        with self.assertRaisesRegex(ValueError, "r-0001"):
            C.aplicar(self.saida(), [{"r-0001": "dado"}])

    def test_juiz_com_rotulo_invalido(self):
        with self.assertRaises(ValueError):
            C.aplicar(self.saida(), [{"r-0002": "verdadeiro"}])


class Concordancia(unittest.TestCase):
    def test_pares_e_contagens(self):
        votos = [{"a": "dado", "b": "dado"}, {"a": "dado", "b": "apelo"}, {"a": "dado", "b": "apelo"}]
        total, ok, pct = C.concordancia(votos)
        self.assertEqual((total, ok), (6, 4))
        self.assertAlmostEqual(pct, 100 * 4 / 6)
        linhas = C.relatorio({"a": "unanime", "b": "maioria", "c": "juiz", "d": "regra", "e": "regra"}, votos)
        self.assertEqual(linhas[1], "unanime: 1; maioria: 1; juiz: 1; regra: 2")
        self.assertIn("4/6", linhas[0])


class CegoChecagem(unittest.TestCase):
    def test_itens_sem_quem_nem_veredito(self):
        itens = C.cego_checagem(TESTE)
        self.assertEqual([i["id"] for i in itens], ["seg-01", "eco-01", "out-01", "soc-01"])  # sem mediação nem incerta
        for i in itens:
            self.assertEqual(set(i), {"id", "tipo", "afirmacao", "trecho", "contexto", "explicacao", "fontes"})
        seg = itens[0]
        self.assertEqual(seg["contexto"], "Boa noite. A taxa de roubos caiu pela metade em dez anos. "
                                          "O salário mínimo subiu cinco por cento no ano.")
        self.assertIn("anuário", seg["explicacao"])
        self.assertEqual(seg["fontes"][0]["orgao"], "Órgão A")

    def test_nada_que_revele_quem_ou_o_veredito(self):
        itens = C.cego_checagem(TESTE)
        texto = json.dumps(itens, ensure_ascii=False)
        debate = json.loads((TESTE / "debate.json").read_text(encoding="utf-8"))
        for c in debate["candidatos"]:
            for k in ("id", "nome_urna", "partido"):
                self.assertNotIn(c[k], texto)
        self.assertNotIn('"quem"', texto)
        for k in ("veredito", "veredito_sugerido"):
            self.assertNotIn(k, texto)

    def test_de_uma_pasta_de_pesquisa(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "a.json").write_text(json.dumps([{"id": "eco-01", "explicacao": "do pesquisador", "fontes": [],
                                                         "veredito_sugerido": "verdadeiro"}]), encoding="utf-8")
            itens = {i["id"]: i for i in C.cego_checagem(TESTE, t)}
        self.assertEqual(itens["eco-01"]["explicacao"], "do pesquisador")
        self.assertEqual(itens["seg-01"]["explicacao"], "")
        self.assertNotIn("veredito", json.dumps(itens))


class Cli(unittest.TestCase):
    def rodar(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = C.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def test_checagem_e_aplicar_ponta_a_ponta(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)

            def v(nome, dados):
                (t / nome).write_text(json.dumps(dados), encoding="utf-8")
                return t / nome

            cego = v("cego.json", [{"id": "seg-01"}, {"id": "eco-01"}, {"id": "out-01"}, {"id": "soc-01"}])
            a = v("a.json", [{"id": "seg-01", "categoria": "verdadeiro", "checou_coisa_certa": False},
                             {"id": "eco-01", "categoria": "falso-ou-exagerado"}, {"id": "out-01", "categoria": "verdadeiro"},
                             {"id": "soc-01", "categoria": "pendente-ou-condicionado"}])
            b = v("b.json", {"seg-01": "verdadeiro", "eco-01": "falso-ou-exagerado", "out-01": "falso-ou-exagerado",
                             "soc-01": "pendente-ou-condicionado"})
            c = v("c.json", {"seg-01": "verdadeiro", "eco-01": "nao-comprovado", "out-01": "verdadeiro",
                             "soc-01": "pendente-ou-condicionado"})
            code, out, err = self.rodar("checagem", a, b, c, "--cego", cego)
            self.assertEqual(code, 0, err)
            saida = json.loads(out)
            self.assertEqual(saida["modo"], "checagem")
            self.assertEqual(saida["decididos"], {"seg-01": "verdadeiro", "eco-01": "falso-ou-exagerado",
                                                  "soc-01": "pendente-ou-condicionado"})
            self.assertEqual(saida["como"]["eco-01"], "maioria")
            self.assertEqual([d["id"] for d in saida["divergencias"]], ["out-01"])
            self.assertEqual(saida["refazer"], ["seg-01"])
            self.assertIn("concordância: 8/12", err)
            self.assertIn("unanime: 2; maioria: 1; juiz: 0; regra: 0", err)
            dec = v("dec.json", saida)
            juiz = v("juiz.json", {"out-01": "falso-ou-exagerado"})
            code, out, err = self.rodar("aplicar", dec, juiz, "--pasta", TESTE)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["out-01"], "falso-ou-exagerado")
            self.assertIn("unanime: 2; maioria: 1; juiz: 1; regra: 0", err)
            self.assertIn("refazer: seg-01", err)
            self.assertIn("divergências por quem: ana-silva-pa: 1", err)

    def test_retorica_manda_divergencias_no_formato_cego(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "cego.json").write_text(json.dumps(CEGO), encoding="utf-8")
            for nome, voto in (("a", "dado"), ("b", "apelo"), ("c", "dado")):
                (t / f"{nome}.json").write_text(json.dumps({c["id"]: voto for c in CEGO}), encoding="utf-8")
            code, out, _ = self.rodar("retorica", t / "a.json", t / "b.json", t / "c.json", "--cego", t / "cego.json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["divergencias"], CEGO)

    def test_uso_errado_devolve_2(self):
        for argv in ([], ["nada"], ["checagem"], ["retorica", "x.json"], ["aplicar", "x.json"], ["cego-checagem"]):
            code, _, err = self.rodar(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("python3 debates/consenso.py", err)

    def test_voto_invalido_devolve_2(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "a.json"
            f.write_text(json.dumps({"a": "xis"}), encoding="utf-8")
            code, _, err = self.rodar("checagem", f)
        self.assertEqual(code, 2)
        self.assertIn("xis", err)


if __name__ == "__main__":
    unittest.main()
