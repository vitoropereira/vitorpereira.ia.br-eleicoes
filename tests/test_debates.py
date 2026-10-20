"""Afirmações checáveis extraídas dos debates (debates/<debate>/afirmacoes.json) contra a transcrição irmã.
Só extração: nenhum veredito aqui (a checagem é outra issue)."""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from debates import validar as vd

RAIZ = Path(__file__).resolve().parent.parent

TRANSCRICAO = """# Debate de teste

## Abertura e regras

**0:08** — Boa noite.

## Bloco 1 — Pergunta 1: segurança pública

**4:41** — Atingiram o menor patamar desde 2012, mas o número é alarmante. 40.775 775

**4:48** — mortes violentas no ano passado, segundo o anuário.

## Intervalo 1 — Sala digital Google

**48:41** — Você está acompanhando o debate.

## Bloco 2 — Pergunta: saúde / SUS

**59:53** — 24 de dezembro de 2023, véspera de Natal, a Renata foi assassinada

**1:00:01** — por um marginal que já estava preso.

**1:05:26** — a inflação de alimento estava 56.17%.

## Considerações finais

**1:44:21** — Eu deixei o país com quase 270 bilhões de reserva.
"""


def item(**mudar):
    base = {"id": "seg-01", "bloco": "1", "tema": "seguranca", "quem": "mediacao", "timestamp": "4:41",
            "trecho": "40.775 775 mortes violentas no ano passado",
            "afirmacao": "Houve 40.775 mortes violentas no ano passado.", "tipo": "numero"}
    base.update(mudar)
    return {k: v for k, v in base.items() if v is not None}


class TestValidar(unittest.TestCase):
    def erros(self, *itens):
        return vd.validar(list(itens), TRANSCRICAO)

    def test_item_valido_passa(self):
        self.assertEqual(self.erros(item()), [])

    def test_trecho_que_atravessa_timestamps_h_mm_ss(self):
        it = item(id="seg-02", bloco="2", quem="flavio", tipo="fato", timestamp="59:53",
                  trecho="a Renata foi assassinada por um marginal que já estava preso")
        self.assertEqual(self.erros(it), [])

    def test_falta_campo_obrigatorio(self):
        for campo in ("id", "bloco", "tema", "quem", "timestamp", "trecho", "afirmacao", "tipo"):
            with self.subTest(campo=campo):
                self.assertTrue(any(campo in e for e in self.erros(item(**{campo: None}))))

    def test_enums(self):
        for campo, valor in (("tema", "esporte"), ("quem", "bolsonaro"), ("tipo", "opiniao"), ("bloco", "4")):
            with self.subTest(campo=campo):
                self.assertTrue(self.erros(item(**{campo: valor})))

    def test_id_fora_do_padrao_ou_do_tema(self):
        for i in ("seg-1", "SEG-01", "seg01", "eco-01"):
            with self.subTest(id=i):
                self.assertTrue(self.erros(item(id=i)))

    def test_id_duplicado(self):
        self.assertTrue(any("duplicado" in e for e in self.erros(item(), item())))

    def test_timestamp_inexistente(self):
        self.assertTrue(self.erros(item(timestamp="4:40")))

    def test_timestamp_nao_casa_dentro_de_outro(self):
        # "5:26" está dentro de "1:05:26", mas não é marcação da transcrição
        it = item(id="eco-01", bloco="2", tema="economia", quem="lula", timestamp="5:26",
                  trecho="a inflação de alimento estava 56.17%")
        self.assertTrue(self.erros(it))
        self.assertEqual(self.erros({**it, "timestamp": "1:05:26"}), [])

    def test_trecho_vazio_ou_inventado(self):
        for t in ("", "   ", "40.775 mortes violentas no ano passado"):
            with self.subTest(trecho=t):
                self.assertTrue(self.erros(item(trecho=t)))

    def test_trecho_longe_do_timestamp(self):
        self.assertTrue(self.erros(item(timestamp="1:44:21")))

    def test_bloco_errado_ou_fora_de_bloco(self):
        self.assertTrue(self.erros(item(bloco="2")))
        fora = item(timestamp="48:41", trecho="Você está acompanhando o debate.")
        self.assertTrue(self.erros(fora))

    def test_sem_veredito(self):
        for chave in ("veredito", "selo", "checagem", "verdadeiro", "falso"):
            with self.subTest(chave=chave):
                self.assertTrue(any(chave in e for e in self.erros(item(**{chave: "x"}))))

    def test_topo_tem_que_ser_lista(self):
        self.assertTrue(vd.validar({"afirmacoes": [item()]}, TRANSCRICAO))
        self.assertTrue(vd.validar(["seg-01"], TRANSCRICAO))

    def test_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "transcricao.md").write_text(TRANSCRICAO, encoding="utf-8")
            (d / "afirmacoes.json").write_text(json.dumps([item()]), encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 0)
            (d / "afirmacoes.json").write_text(json.dumps([item(), item()]), encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 1)


class TestDebatesPublicados(unittest.TestCase):
    def test_afirmacoes_reais(self):
        pastas = sorted(p.parent for p in (RAIZ / "debates").glob("*/afirmacoes.json"))
        self.assertTrue(pastas, "nenhum debates/*/afirmacoes.json")
        for pasta in pastas:
            with self.subTest(debate=pasta.name):
                itens = json.loads((pasta / "afirmacoes.json").read_text(encoding="utf-8"))
                transcricao = (pasta / "transcricao.md").read_text(encoding="utf-8")
                self.assertEqual(vd.validar(itens, transcricao), [])
                quem = Counter(i["quem"] for i in itens)
                for q in ("flavio", "lula", "mediacao"):
                    self.assertGreater(quem[q], 0, q)
                blocos = {i["bloco"] for i in itens}
                self.assertEqual(blocos, set(vd.BLOCOS))


if __name__ == "__main__":
    unittest.main()
