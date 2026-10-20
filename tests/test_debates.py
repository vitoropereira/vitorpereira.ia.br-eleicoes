"""Afirmações checáveis extraídas dos debates (debates/<ano>/<slug>/: debate.json, transcricao.md, afirmacoes.json).
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


def debate(**mudar):
    base = {"slug": "presidente-2-turno-band", "ano": 2026, "cargo": "presidente", "turno": 2, "emissora": "Band",
            "data": "2026-10-18", "fonte_transcricao": "youtube-auto",
            "candidatos": [{"id": "fulano-pl", "nome_urna": "Fulano", "partido": "PL"},
                           {"id": "beltrano-pt", "nome_urna": "Beltrano", "partido": "PT", "id_tse": "1"}]}
    base.update(mudar)
    return {k: v for k, v in base.items() if v is not None}


def item(**mudar):
    base = {"id": "seg-01", "bloco": "1", "tema": "seguranca", "quem": "mediacao", "autoria": "certa",
            "timestamp": "4:41", "tipo": "dado", "tese": "mortes-violentas-ano-passado",
            "trecho": "40.775 775 mortes violentas no ano passado",
            "afirmacao": "Houve 40.775 mortes violentas no ano passado."}
    base.update(mudar)
    return {k: v for k, v in base.items() if v is not None}


class TestValidarDebate(unittest.TestCase):
    def test_debate_valido_passa(self):
        self.assertEqual(vd.validar_debate(debate()), [])

    def test_opcionais(self):
        self.assertEqual(vd.validar_debate(debate(mediadores=["Fulana"], url_fonte="https://x", parceiros=["A"])), [])

    def test_falta_campo_obrigatorio(self):
        for campo in ("slug", "ano", "cargo", "turno", "emissora", "data", "candidatos", "fonte_transcricao"):
            with self.subTest(campo=campo):
                self.assertTrue(any(campo in e for e in vd.validar_debate(debate(**{campo: None}))))

    def test_campos_invalidos(self):
        for mudar in ({"fonte_transcricao": "manual"}, {"data": "18/10/2026"}, {"data": "2026-13-40"},
                      {"turno": "2"}, {"turno": True}, {"ano": "2026"}, {"slug": "presidente-2-turno-globo"},
                      {"candidatos": []}, {"candidatos": "fulano"}, {"ano": 2025}):
            with self.subTest(**{k: repr(v) for k, v in mudar.items()}):
                self.assertTrue(vd.validar_debate(debate(**mudar)))

    def test_slug_normaliza_emissora(self):
        self.assertEqual(vd.validar_debate(debate(emissora="TV Gazeta", slug="presidente-2-turno-tv-gazeta")), [])
        self.assertEqual(vd.validar_debate(debate(emissora="Rede Bahia Sertão", slug="presidente-2-turno-rede-bahia-sertao")), [])

    def test_candidato_invalido(self):
        bom = {"id": "fulano-pl", "nome_urna": "Fulano", "partido": "PL"}
        for campo in ("id", "nome_urna", "partido"):
            with self.subTest(campo=campo):
                c = {k: v for k, v in bom.items() if k != campo}
                self.assertTrue(any(campo in e for e in vd.validar_debate(debate(candidatos=[c]))))
        self.assertTrue(vd.validar_debate(debate(candidatos=[{**bom, "id": "Fulano PL"}])))
        self.assertTrue(vd.validar_debate(debate(candidatos=[{**bom, "id": "mediacao"}])))
        self.assertTrue(vd.validar_debate(debate(candidatos=["fulano-pl"])))
        for id_tse in (280002551544, "", "28x"):
            with self.subTest(id_tse=id_tse):
                self.assertTrue(any("id_tse" in e for e in vd.validar_debate(debate(candidatos=[{**bom, "id_tse": id_tse}]))))

    def test_pasta_tem_que_ser_ano_slug(self):
        self.assertEqual(vd.validar_pasta(Path("x/2026/presidente-2-turno-band"), debate()), [])
        self.assertTrue(vd.validar_pasta(Path("x/2025/presidente-2-turno-band"), debate()))
        self.assertTrue(vd.validar_pasta(Path("x/2026-10-18-band"), debate()))

    def test_candidato_repetido(self):
        c = {"id": "fulano-pl", "nome_urna": "Fulano", "partido": "PL"}
        self.assertTrue(any("repetido" in e for e in vd.validar_debate(debate(candidatos=[c, c]))))

    def test_topo_tem_que_ser_objeto(self):
        self.assertTrue(vd.validar_debate([debate()]))


class TestValidar(unittest.TestCase):
    def erros(self, *itens):
        return vd.validar(list(itens), TRANSCRICAO, debate())

    def test_item_valido_passa(self):
        self.assertEqual(self.erros(item()), [])

    def test_trecho_que_atravessa_timestamps_h_mm_ss(self):
        it = item(id="seg-02", bloco="2", quem="fulano-pl", tipo="fato", timestamp="59:53",
                  trecho="a Renata foi assassinada por um marginal que já estava preso")
        self.assertEqual(self.erros(it), [])

    def test_falta_campo_obrigatorio(self):
        for campo in vd.CAMPOS:
            with self.subTest(campo=campo):
                self.assertTrue(any(campo in e for e in self.erros(item(**{campo: None}))))

    def test_enums(self):
        for campo, valor in (("tema", "esporte"), ("tipo", "opiniao"), ("bloco", "4"), ("autoria", "talvez")):
            with self.subTest(campo=campo):
                self.assertTrue(self.erros(item(**{campo: valor})))

    def test_enums_da_issue(self):
        self.assertEqual(self.erros(item(id="cor-01", tema="corrupcao-acusacoes", quem="beltrano-pt")), [])
        self.assertTrue(self.erros(item(id="cor-01", tema="corrupcao")))
        self.assertTrue(self.erros(item(tipo="numero")))
        for t in vd.TIPOS:
            with self.subTest(tipo=t):
                self.assertEqual(self.erros(item(tipo=t)), [])

    def test_quem_vem_do_debate(self):
        for q in ("fulano-pl", "beltrano-pt", "mediacao"):
            with self.subTest(quem=q):
                self.assertEqual(self.erros(item(quem=q)), [])
        for q in ("flavio", "lula", "fulano"):
            with self.subTest(quem=q):
                self.assertTrue(any("quem" in e for e in self.erros(item(quem=q))))

    def test_autoria(self):
        for a in ("certa", "incerta"):
            with self.subTest(autoria=a):
                self.assertEqual(self.erros(item(autoria=a)), [])

    def test_tese(self):
        for t in ("", "Homicidios", "homicidios_2012", "homicidios--2012", "-homicidios", "homicídios-2012"):
            with self.subTest(tese=t):
                self.assertTrue(any("tese" in e for e in self.erros(item(tese=t))))

    def test_tese_repetida_pode(self):
        self.assertEqual(self.erros(item(), item(id="seg-02", timestamp="4:48", trecho="mortes violentas")), [])

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
        it = item(id="eco-01", bloco="2", tema="economia", quem="beltrano-pt", timestamp="5:26",
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
        self.assertTrue(vd.validar({"afirmacoes": [item()]}, TRANSCRICAO, debate()))
        self.assertTrue(vd.validar(["seg-01"], TRANSCRICAO, debate()))

    def test_debate_quebrado_nao_derruba_os_itens(self):
        for deb in ({"candidatos": "x"}, {"candidatos": ["x", {"id": 1}]}, []):
            with self.subTest(debate=repr(deb)):
                self.assertTrue(vd.validar([item(quem="fulano-pl")], TRANSCRICAO, deb))

    def test_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026" / "presidente-2-turno-band"
            self.assertEqual(vd.main([str(d)]), 1)  # pasta sem os arquivos: erro, não traceback
            d.mkdir(parents=True)
            (d / "transcricao.md").write_text(TRANSCRICAO, encoding="utf-8")
            (d / "debate.json").write_text(json.dumps(debate()), encoding="utf-8")
            (d / "afirmacoes.json").write_text(json.dumps([item()]), encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 0)
            (d / "afirmacoes.json").write_text(json.dumps([item(), item()]), encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 1)
            (d / "afirmacoes.json").write_text(json.dumps([item()]), encoding="utf-8")
            (d / "debate.json").write_text(json.dumps(debate(fonte_transcricao="x")), encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 1)


HOJE = vd.date(2026, 10, 20)
AFIRMACOES = [
    {"id": "eco-01", "autoria": "certa", "tipo": "dado"},
    {"id": "eco-02", "autoria": "certa", "tipo": "promessa"},
    {"id": "sau-01", "autoria": "certa", "tipo": "acusacao"},
    {"id": "out-01", "autoria": "incerta", "tipo": "acusacao"},
]


def fonte(**kw):
    f = {"url": "https://sidra.ibge.gov.br/tabela/6784", "titulo": "Tabela 6784", "orgao": "IBGE",
         "data_publicacao": "2026-03-03", "acessado_em": "2026-10-20"}
    f.update(kw)
    return f


def checagem(**kw):
    c = {"id": "eco-01", "veredito": "verdadeiro", "explicacao": "O IBGE registra 7,5%. O número é de 2010.",
         "fontes": [fonte()], "atualizado_em": "2026-10-20"}
    c.update(kw)
    return {k: v for k, v in c.items() if v is not None}


class TestValidarChecagens(unittest.TestCase):
    def erros(self, *chs):
        return vd.validar_checagens(list(chs), AFIRMACOES, HOJE)

    def test_checagem_valida_passa(self):
        self.assertEqual(self.erros(checagem(), checagem(id="eco-02", veredito="viavel"),
                                    checagem(id="sau-01", veredito="ha-investigacao", outro_lado="A defesa nega.")),
                         [])

    def test_topo_tem_que_ser_lista(self):
        self.assertTrue(vd.validar_checagens({"checagens": [checagem()]}, AFIRMACOES, HOJE))
        self.assertTrue(vd.validar_checagens(["eco-01"], AFIRMACOES, HOJE))

    def test_id_duplicado_ou_sem_afirmacao(self):
        self.assertTrue(any("duplicado" in e for e in self.erros(checagem(), checagem())))
        self.assertTrue(any("não há afirmação" in e for e in self.erros(checagem(id="eco-99"))))

    def test_incerta_nao_se_checa(self):
        self.assertTrue(any("incerta" in e for e in self.erros(checagem(id="out-01", veredito="ha-denuncia"))))

    def test_veredito_da_escala_do_tipo(self):
        for id_, v in (("eco-01", "viavel"), ("eco-02", "verdadeiro"), ("sau-01", "falso"), ("eco-01", "x")):
            with self.subTest(id=id_, veredito=v):
                self.assertTrue(any("veredito" in e for e in self.erros(checagem(id=id_, veredito=v))))

    def test_falta_campo(self):
        for c in ("id", "veredito", "explicacao", "atualizado_em", "fontes"):
            with self.subTest(campo=c):
                self.assertTrue(self.erros(checagem(**{c: None})))
        self.assertTrue(self.erros(checagem(outro_lado="")))

    def test_explicacao_de_2_a_4_frases(self):
        for txt in ("", "   ", "Só uma frase.", "Um. Dois. Três. Quatro. Cinco."):
            with self.subTest(explicacao=txt):
                self.assertTrue(self.erros(checagem(explicacao=txt)))
        self.assertEqual(self.erros(checagem(explicacao="O PIB foi de R$ 3,9 tri. Cresceu 7,5% em 2010.")), [])

    def test_fontes_mesmo_sem_evidencia(self):
        for v in ("sem-evidencia", "nao-checavel", "verdadeiro"):
            with self.subTest(veredito=v):
                self.assertTrue(self.erros(checagem(veredito=v, fontes=[])))
        self.assertEqual(self.erros(checagem(veredito="sem-evidencia")), [])

    def test_fonte_incompleta_ou_sem_https(self):
        self.assertTrue(self.erros(checagem(fontes=[fonte(url="http://ibge.gov.br")])))
        self.assertTrue(self.erros(checagem(fontes=["https://ibge.gov.br"])))
        for c in vd.FONTE:
            with self.subTest(campo=c):
                self.assertTrue(self.erros(checagem(fontes=[{k: v for k, v in fonte().items() if k != c}])))

    def test_datas(self):
        for kw in ({"atualizado_em": "20/10/2026"}, {"atualizado_em": "2026-02-30"},
                   {"atualizado_em": "2026-10-21"}, {"fontes": [fonte(acessado_em="2026-10-21")]},
                   {"fontes": [fonte(data_publicacao="2026-3-3")]}):
            with self.subTest(**{k: repr(v) for k, v in kw.items()}):
                self.assertTrue(self.erros(checagem(**kw)))

    def test_main_valida_checagens_quando_existem(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026" / "presidente-2-turno-band"
            d.mkdir(parents=True)
            (d / "transcricao.md").write_text(TRANSCRICAO, encoding="utf-8")
            (d / "debate.json").write_text(json.dumps(debate()), encoding="utf-8")
            (d / "afirmacoes.json").write_text(json.dumps([item()]), encoding="utf-8")
            (d / "checagens.json").write_text(json.dumps([checagem(id="seg-99")]), encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 1)
            (d / "checagens.json").write_text("[", encoding="utf-8")
            self.assertEqual(vd.main([str(d)]), 1)


TEMAS_CHECADOS = {"economia", "social", "saude", "outros"}  # a #88 acrescenta seguranca, internacional, corrupcao


class TestDebatesPublicados(unittest.TestCase):
    def test_checagens_reais(self):
        for pasta in sorted((RAIZ / "debates").glob("*/*/checagens.json")):
            with self.subTest(debate=f"{pasta.parent.parent.name}/{pasta.parent.name}"):
                itens = json.loads((pasta.parent / "afirmacoes.json").read_text(encoding="utf-8"))
                chs = json.loads(pasta.read_text(encoding="utf-8"))
                self.assertEqual(vd.validar_checagens(chs, itens), [])
                ids = {c["id"] for c in chs}
                faltam = [i["id"] for i in itens
                          if i["autoria"] == "certa" and i["tema"] in TEMAS_CHECADOS and i["id"] not in ids]
                self.assertEqual(faltam, [], "afirmação certa sem checagem")
                self.assertEqual([i["id"] for i in itens if i["autoria"] == "incerta" and i["id"] in ids], [])

    def test_ha_checagens_do_debate_da_band(self):
        self.assertTrue((RAIZ / "debates/2026/presidente-2-turno-band/checagens.json").exists())

    def test_afirmacoes_reais(self):
        anos = [p for p in (RAIZ / "debates").iterdir() if p.is_dir() and not p.name.startswith(("_", "."))]
        for p in anos:
            self.assertRegex(p.name, r"^\d{4}$", "debates/ só tem pastas <ano>/<slug>")
        pastas = sorted(p for a in anos for p in a.iterdir() if p.is_dir())
        self.assertTrue(pastas, "nenhum debates/<ano>/<slug>/")
        for pasta in pastas:
            with self.subTest(debate=f"{pasta.parent.name}/{pasta.name}"):
                deb = json.loads((pasta / "debate.json").read_text(encoding="utf-8"))
                itens = json.loads((pasta / "afirmacoes.json").read_text(encoding="utf-8"))
                transcricao = (pasta / "transcricao.md").read_text(encoding="utf-8")
                self.assertEqual(vd.validar_debate(deb), [])
                self.assertEqual(vd.validar_pasta(pasta, deb), [])
                self.assertEqual(vd.validar(itens, transcricao, deb), [])
                quem = Counter(i["quem"] for i in itens)
                for q in [c["id"] for c in deb["candidatos"]] + ["mediacao"]:
                    self.assertGreater(quem[q], 0, q)
                self.assertEqual({i["bloco"] for i in itens}, set(vd.BLOCOS))


if __name__ == "__main__":
    unittest.main()
