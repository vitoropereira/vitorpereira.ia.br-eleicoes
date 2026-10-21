"""Retórica dos debates (retorica.json): validador, etiquetagem cega (debates/retorica.py) e placar na página."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
import build_site as B
from debates import pagina as dp
from debates import retorica as rt
from debates import validar as V

TESTE = R / "tests" / "fixtures" / "debates" / "2026" / "presidente-2-turno-teste"
FICT = R / "tests" / "fixtures" / "debates" / "2030" / "governador-1-turno-fict"
PROIBIDAS = re.compile(r"\b(venceu|vencedor|ganhou|perdeu|mentiu|mentiros[oa]|destruiu|humilhou|arrasou|massacrou)\b", re.I)
FALAS = [{"inicio": "0:10", "fim": "0:20", "quem": "ana-silva-pa", "autoria": "certa"},
         {"inicio": "0:30", "fim": "0:30", "quem": "bruno-lima-pb", "autoria": "certa"},
         {"inicio": "0:40", "fim": "0:40", "quem": "ana-silva-pa", "autoria": "incerta"},
         {"inicio": "0:01", "fim": "0:01", "quem": "mediacao", "autoria": "certa"}]


def ler(nome, pasta=TESTE):
    return json.loads((pasta / nome).read_text(encoding="utf-8")) if nome.endswith(".json") \
        else (pasta / nome).read_text(encoding="utf-8")


def frase(**mudar):
    base = {"id": "r-0001", "timestamp": "0:10", "quem": "ana-silva-pa",
            "frase": "A taxa de roubos caiu pela metade em dez anos.", "etiqueta": "dado"}
    base.update(mudar)
    return {k: v for k, v in base.items() if v is not None}


def erros(*itens):
    return V.validar_retorica(list(itens), ler("transcricao.md"), ler("debate.json"))


class Validar(unittest.TestCase):
    def test_valido_e_fixture(self):
        self.assertEqual(erros(frase()), [])
        self.assertEqual(V.validar_retorica(ler("retorica.json"), ler("transcricao.md"), ler("debate.json")), [])

    def test_frase_que_atravessa_marcacoes(self):
        self.assertEqual(erros(frase(frase="dez anos. O salário mínimo subiu")), [])

    def test_topo_tem_que_ser_lista(self):
        self.assertIn("lista", V.validar_retorica({}, ler("transcricao.md"), ler("debate.json"))[0])

    def test_campo_faltando_ou_nao_string(self):
        self.assertRegex(" ".join(erros(frase(etiqueta=None))), "etiqueta")
        self.assertRegex(" ".join(erros(frase(quem=3))), "quem")
        self.assertRegex(" ".join(erros("x")), "não é objeto")

    def test_id(self):
        self.assertRegex(" ".join(erros(frase(id="r-1"))), "r-NNNN")
        self.assertRegex(" ".join(erros(frase(), frase())), "duplicado")

    def test_timestamp(self):
        self.assertRegex(" ".join(erros(frase(timestamp="0:11"))), "marcação")
        self.assertRegex(" ".join(erros(frase(timestamp="0:1"))), "marcação")

    def test_quem(self):
        self.assertRegex(" ".join(erros(frase(quem="mediacao"))), "quem")
        self.assertRegex(" ".join(erros(frase(quem="carla-souza-pc"))), "quem")

    def test_etiqueta(self):
        self.assertRegex(" ".join(erros(frase(etiqueta="mentira"))), "etiqueta")
        for e in V.ETIQUETAS:
            self.assertEqual(erros(frase(etiqueta=e)), [])

    def test_frase_vazia_inventada_ou_longe(self):
        self.assertRegex(" ".join(erros(frase(frase="  "))), "vazia")
        self.assertRegex(" ".join(erros(frase(frase="Inventei."))), "não está")
        self.assertRegex(" ".join(erros(frase(frase="Vou criar um programa"))), "não está")

    def test_chave_a_mais(self):
        for c in ("autoria", "veredito", "nome"):
            self.assertRegex(" ".join(erros(frase(**{c: "x"}))), c)

    def test_main_com_e_sem_retorica(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026" / "presidente-2-turno-teste"
            shutil.copytree(TESTE, d)
            (d / "checagens.json").unlink()  # a checagem de incerta da fixture é de propósito (pagina filtra)
            self.assertEqual(V.main([str(d)]), 0)
            (d / "retorica.json").write_text(json.dumps([frase(etiqueta="x")]), encoding="utf-8")
            self.assertEqual(V.main([str(d)]), 1)
            (d / "retorica.json").unlink()
            self.assertEqual(V.main([str(d)]), 0)


class Cego(unittest.TestCase):
    def test_frases_so_de_candidato_certa(self):
        fs = rt.frases(TESTE, FALAS)
        self.assertEqual([(f["id"], f["timestamp"], f["quem"]) for f in fs],
                         [("r-0001", "0:10", "ana-silva-pa"), ("r-0002", "0:20", "ana-silva-pa"),
                          ("r-0003", "0:30", "bruno-lima-pb")])
        self.assertEqual(fs[1]["frase"], "O salário mínimo subiu cinco por cento no ano.")

    def test_sem_pontuacao_corta_na_janela(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            shutil.copy(TESTE / "debate.json", d)
            marcas = "".join(f"**0:{s:02d}** — palavra {s} sem ponto\n\n" for s in range(10, 20))
            (d / "transcricao.md").write_text(f"## Bloco 1 — x\n\n{marcas}", encoding="utf-8")
            fs = rt.frases(d, [{"inicio": "0:10", "fim": "0:19", "quem": "ana-silva-pa", "autoria": "certa"}])
            self.assertEqual([f["timestamp"] for f in fs], ["0:10", "0:14", "0:18"])
            self.assertEqual(V.validar_retorica([{**f, "etiqueta": "dado"} for f in fs],
                                                (d / "transcricao.md").read_text(encoding="utf-8"), ler("debate.json")), [])

    def test_trecho_fora_da_transcricao(self):
        with self.assertRaises(ValueError):
            rt.frases(TESTE, [{"inicio": "0:11", "fim": "0:20", "quem": "ana-silva-pa", "autoria": "certa"}])

    def test_cego_nao_diz_quem_falou(self):
        fs = rt.frases(TESTE, FALAS)
        cego = rt.cego(fs)
        self.assertTrue(all(set(c) == {"id", "frase"} for c in cego))
        texto = json.dumps(cego, ensure_ascii=False)
        for c in ler("debate.json")["candidatos"]:
            for k in ("id", "nome_urna", "partido"):
                fora_das_frases = texto
                for f in fs:
                    fora_das_frases = fora_das_frases.replace(f["frase"], "")
                self.assertNotIn(c[k], fora_das_frases)

    def test_juntar(self):
        fs = rt.frases(TESTE, FALAS)
        out = rt.juntar(fs, {"r-0001": "dado", "r-0002": "fora", "r-0003": "proposta"})
        self.assertEqual([(r["id"], r["etiqueta"]) for r in out], [("r-0001", "dado"), ("r-0003", "proposta")])
        self.assertEqual(set(out[0]), set(V.CAMPOS_RETORICA))
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            rt.juntar(fs, {"r-0001": "dado", "r-0002": "dado", "r-0003": "dado", "r-0009": "dado"})
        with self.assertRaisesRegex(ValueError, "falta"):
            rt.juntar(fs, {"r-0001": "dado", "r-0002": "dado"})
        with self.assertRaisesRegex(ValueError, "fora de"):
            rt.juntar(fs, {"r-0001": "dado", "r-0002": "dado", "r-0003": "mentira"})


class Placar(unittest.TestCase):
    def test_soma_bate_com_o_arquivo(self):
        m = dp.carregar(TESTE)
        esperado = Counter((r["quem"], r["etiqueta"]) for r in ler("retorica.json"))
        conta = dp.placar_retorica(m)
        for q, c in conta.items():
            self.assertEqual(list(c), list(V.ETIQUETAS))
            for e, n in c.items():
                self.assertEqual(n, esperado[(q, e)])
        self.assertEqual(sum(sum(c.values()) for c in conta.values()), len(m["retorica"]))

    def test_pct_100(self):
        for conta in ({"a": 1, "b": 1, "c": 1}, {"a": 2, "b": 1, "c": 0}, {"a": 1, "b": 5, "c": 7, "d": 0}):
            self.assertEqual(sum(dp.pct_100(conta).values()), 100, conta)
        self.assertEqual(dp.pct_100({"a": 1, "b": 1, "c": 1}), {"a": 34, "b": 33, "c": 33})
        self.assertEqual(dp.pct_100({"a": 0}), {"a": 0})
        conta = dp.placar_retorica(dp.carregar(TESTE))
        for c in conta.values():
            self.assertEqual(sum(dp.pct_100(c).values()), 100)

    def test_sem_arquivo(self):
        m = dp.carregar(FICT)
        self.assertIsNone(m["retorica"])
        self.assertEqual(dp.placar_retorica(m), {})

    def test_arquivo_quebrado_levanta(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026" / "presidente-2-turno-teste"
            shutil.copytree(TESTE, d)
            (d / "retorica.json").write_text(json.dumps([frase(etiqueta="x")]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "etiqueta"):
                dp.carregar(d)


class Pagina(unittest.TestCase):
    def test_secao_so_com_arquivo(self):
        h = dp.gerar(dp.carregar(TESTE), B.BASE, B.PESSOA)["html"]
        sec = re.search(r'<section aria-labelledby="retorica">.*?</section>', h, re.S).group(0)
        self.assertEqual(sec.count("<li id=\"r-"), len(ler("retorica.json")))
        self.assertIn('class="db-rt-filtro"', sec)
        self.assertRegex(sec, r'<form class="db-rt-filtro"[^>]*hidden>')
        self.assertIn("var(--flavio)", sec)
        self.assertNotIn("cyan", sec)
        self.assertNotRegex(h, PROIBIDAS)
        self.assertLess(h.index('aria-labelledby="placar"'), h.index('aria-labelledby="retorica"'))
        for c in ("Ana Silva (PA)", "Bruno Lima (PB)"):
            self.assertIn(c, sec)
        sem = dp.gerar(dp.carregar(FICT), B.BASE, B.PESSOA)
        self.assertNotIn('aria-labelledby="retorica"', sem["html"])
        self.assertEqual(sem["retorica"], {})

    def test_percentuais_da_barra_somam_100(self):
        h = dp.gerar(dp.carregar(TESTE), B.BASE, B.PESSOA)["html"]
        sec = re.search(r'<section aria-labelledby="retorica">.*?</section>', h, re.S).group(0)
        blocos = re.findall(r'<div class="db-pc".*?</div>', sec)
        self.assertEqual(len(blocos), 2)
        for b in blocos:
            self.assertEqual(sum(int(p) for p in re.findall(r"\((\d+)%\)", b)), 100)

    def test_indice_soma(self):
        gs = [dp.gerar(m, B.BASE, B.PESSOA) for m in dp.listar(TESTE.parent.parent)]
        idx = dp.indice(gs, B.BASE, B.PESSOA)
        esperado = Counter((r["quem"], r["etiqueta"]) for r in ler("retorica.json"))
        self.assertEqual({(q, e): n for q, c in idx["retorica"].items() for e, n in c.items() if n}, dict(esperado))
        sec = re.search(r'<section aria-labelledby="retorica">.*?</section>', idx["html"], re.S).group(0)
        self.assertIn("1 debate,", sec)
        for b in re.findall(r'<div class="db-pc".*?</div>', sec):
            self.assertEqual(sum(int(p) for p in re.findall(r"\((\d+)%\)", b)), 100)
        sem = dp.indice([dp.gerar(dp.carregar(FICT), B.BASE, B.PESSOA)], B.BASE, B.PESSOA)
        self.assertNotIn('aria-labelledby="retorica"', sem["html"])


if __name__ == "__main__":
    unittest.main()
