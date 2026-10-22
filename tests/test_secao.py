"""Testes do pipeline de resultado por seção e local de votação (municipios/baixar_secao.py e montar_secao.py)."""
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from municipios import baixar_secao, montar_secao as ms

FX = Path(__file__).resolve().parent / "fixtures" / "secao"


def zipar(dest, membros):
    """ZIP no formato do TSE: CSV ';' em latin-1, um membro por UF (nome -> arquivo de fixture)."""
    with zipfile.ZipFile(dest, "w") as zf:
        for nome, fx in membros.items():
            zf.writestr(nome, (FX / fx).read_text(encoding="utf-8").encode("latin-1"))


class TestBaixar(unittest.TestCase):
    def test_25_10_sai_sem_nenhuma_requisicao(self):
        chamadas = []
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            baixar_secao.baixar(td, opener=lambda *a, **k: chamadas.append(a), hoje=date(2026, 10, 25))
        self.assertEqual(chamadas, [])

    def test_baixa_os_tres_arquivos_em_sequencia(self):
        urls = []

        def opener(req, timeout=None):
            urls.append(req.full_url)
            r = io.BytesIO(b"x")
            r.headers = {}
            return r

        with tempfile.TemporaryDirectory() as td:
            res = baixar_secao.baixar(td, opener=opener, hoje=date(2026, 10, 22))
            self.assertEqual(sorted(p.name for p in Path(td).iterdir()), sorted(res))
        self.assertEqual(urls, baixar_secao.ARQUIVOS)
        self.assertIn("votacao_secao_2026_BR.zip", res)
        self.assertIn("eleitorado_local_votacao_2026.zip", res)


class Base(unittest.TestCase):
    turnos = ("votacao_t1.csv",)

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.br = self.td / "brutos"
        self.br.mkdir()
        membros = {f"votacao_secao_2026_T{i}.csv": fx for i, fx in enumerate(self.turnos, 1)}
        zipar(self.br / ms.ZIP_SECAO, membros)
        zipar(self.br / ms.ZIP_LOCAIS, {"eleitorado_local_votacao_2026.csv": "locais.csv"})
        shutil.copy(FX / "mun-config.json", self.br / ms.CFG)
        self.cfg = json.loads((FX / "mun-config.json").read_text(encoding="utf-8"))

    def juntar(self):
        return ms.juntar(self.br / ms.ZIP_SECAO, self.br / ms.ZIP_LOCAIS, self.cfg)

    def local(self, dados, cdi, nome, t="1"):
        return next(lc for lc in dados[cdi]["t"][t] if lc[2] == nome)


class TestLinhasZip(Base):
    def test_le_em_streaming_latin1_e_pula_brasil(self):
        z = self.td / "a.zip"
        zipar(z, {"x_AC.csv": "votacao_t1.csv", "x_BRASIL.csv": "votacao_t1.csv", "leiame.pdf": "votacao_t1.csv"})
        with mock.patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("extraiu")), \
                mock.patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("leu inteiro")):
            linhas = list(ms.linhas_zip(z))
        self.assertEqual(len(linhas), 22)
        self.assertEqual(linhas[0]["NM_VOTAVEL"], "LULA")
        nomes = [r["NM_LOCAL_VOTACAO"] for r in ms.linhas_zip(self.br / ms.ZIP_LOCAIS)]
        self.assertIn("ESCOLA SÃO JOSÉ", nomes)


class TestJuncao(Base):
    def test_candidatos_em_ordem_fixa_no_topo(self):
        dados, _, _ = self.juntar()
        self.assertEqual(dados["1200401"]["cand"]["1"], [[13, "Lula"], [22, "Jair Bolsonaro"], [15, "Simone Tebet"]])
        self.assertEqual(dados["3550308"]["cand"], dados["1200401"]["cand"])

    def test_local_soma_suas_secoes(self):
        dados, _, _ = self.juntar()
        lc = self.local(dados, "1200401", "ESCOLA SÃO JOSÉ")
        self.assertEqual(lc[:5], [-9.97, -67.81, "ESCOLA SÃO JOSÉ", "CENTRO", "69900"])
        # aptos: 300 + 50 + 20 (seção 3 agregada à 2) + 60; comparecimento: 190 + 12 + 40
        self.assertEqual(lc[5:9], [430, 242, [127, 98], 17])
        self.assertEqual([s[:4] for s in lc[9]], [[9, 1, 300, 190], [9, 2, 70, 12], [9, 7, 60, 40]])
        self.assertEqual(lc[9][0][4:], [[100, 80], 10])

    def test_ignora_outros_cargos(self):
        dados, _, _ = self.juntar()
        sp = dados["3550308"]["t"]["1"]
        self.assertEqual(sp, [[None, None, "EMEF CAMPOS SALLES", "SÉ", "01001", 400, 390, [200, 150, 30], 10,
                               [[1, 5, 400, 390, [200, 150, 30], 10]]]])

    def test_secao_sem_local_vira_orfa(self):
        dados, orfas, _ = self.juntar()
        self.assertEqual(orfas, [("1", "AC", "01120", 9, 4)])
        secoes = [s[1] for lc in dados["1200401"]["t"]["1"] for s in lc[9]]
        self.assertNotIn(4, secoes)

    def test_municipio_sem_cdi_e_reportado(self):
        dados, _, sem_cdi = self.juntar()
        self.assertEqual(sem_cdi, [("AC", "99999")])
        self.assertEqual(sorted(dados), ["1200401", "3550308"])

    def test_coordenada_vazia_ou_menos_um_vira_null(self):
        dados, _, _ = self.juntar()
        self.assertEqual(self.local(dados, "1200401", "COLÉGIO PEQUENO")[:2], [None, None])
        self.assertEqual(dados["3550308"]["t"]["1"][0][:2], [None, None])

    def test_montar_imprime_orfas_e_sem_cdi(self):
        out = io.StringIO()
        with redirect_stdout(out):
            ms.montar(self.br, self.td / "geo")
        self.assertIn("seções sem local de votação: 1", out.getvalue())
        self.assertIn("municípios sem código IBGE no mun-config: 1", out.getvalue())


class TestPiso(Base):
    def test_secao_abaixo_do_piso_so_mostra_aptos_e_comparecimento(self):
        dados, _, _ = self.juntar()
        s2 = self.local(dados, "1200401", "ESCOLA SÃO JOSÉ")[9][1]
        self.assertEqual(s2, [9, 2, 70, 12, None, None])

    def test_local_abaixo_do_piso_perde_voto_por_candidato(self):
        dados, _, _ = self.juntar()
        lc = self.local(dados, "1200401", "COLÉGIO PEQUENO")
        self.assertEqual(lc[2:], ["COLÉGIO PEQUENO", "BOSQUE", "69900", 25, 18, None, None, [[9, 10, 25, 18, None, None]]])

    def test_total_do_local_inclui_secao_suprimida(self):
        dados, _, _ = self.juntar()
        lc = self.local(dados, "1200401", "ESCOLA SÃO JOSÉ")
        visiveis = [s for s in lc[9] if s[4] is not None]
        self.assertEqual(lc[7], [127, 98])
        self.assertNotEqual(lc[7], [sum(x) for x in zip(*(s[4] for s in visiveis))])
        self.assertEqual(lc[6], sum(s[3] for s in lc[9]))

    def test_supressao_complementar_nao_deixa_deduzir_a_secao_oculta(self):
        # só a seção 2 (12) está abaixo do piso: total do local - visíveis revelaria o voto dela.
        # A menor visível (seção 7, 40) também é ocultada, e as ocultas somam 52 >= PISO.
        dados, _, _ = self.juntar()
        lc = self.local(dados, "1200401", "ESCOLA SÃO JOSÉ")
        self.assertEqual(lc[9][2], [9, 7, 60, 40, None, None])
        self.assertEqual(lc[9][0][4:], [[100, 80], 10])
        self.assertGreaterEqual(sum(s[3] for s in lc[9] if s[4] is None), ms.PISO)

    def test_supressao_complementar_entre_locais_do_municipio(self):
        # só o COLÉGIO PEQUENO (18) está abaixo do piso: total do município (geo/t1) - locais visíveis revelaria o voto
        # dele. O menor visível (POSTO RURAL, 32) também perde o voto, inclusive o das seções, e os ocultos somam 50.
        dados, _, _ = self.juntar()
        posto = self.local(dados, "1200401", "POSTO RURAL")
        self.assertEqual(posto[5:9], [50, 32, None, None])
        self.assertEqual(posto[9], [[9, 20, 50, 32, None, None]])
        self.assertEqual(self.local(dados, "1200401", "ESCOLA SÃO JOSÉ")[7], [127, 98])
        ocultos = [lc for lc in dados["1200401"]["t"]["1"] if lc[7] is None]
        self.assertGreaterEqual(sum(lc[6] for lc in ocultos), ms.PISO)

    def test_secoes_orfas_abaixo_do_piso_tambem_disparam_supressao(self):
        # nenhum local abaixo do piso, mas 10 de comparecimento órfão entram no total do município e não saem em local
        # nenhum: o total menos os locais visíveis revelaria as órfãs, então o menor local também perde o voto
        itens = [[90], [40], [50]]
        self.assertEqual(ms._ocultar(itens, 0), set())
        self.assertEqual(ms._ocultar(itens, 0, fora=10), {1})
        self.assertEqual(ms._ocultar(itens, 0, fora=ms.PISO), set())
        # órfãs não diminuem a supressão de um item já abaixo do piso
        self.assertEqual(ms._ocultar([[90], [20], [50]], 0, fora=40), {1, 2})


class TestTurnos(Base):
    def test_so_primeiro_turno(self):
        dados, _, _ = self.juntar()
        for reg in dados.values():
            self.assertEqual(list(reg["t"]), ["1"])
            self.assertEqual(list(reg["cand"]), ["1"])


class TestSegundoTurno(Base):
    turnos = ("votacao_t1.csv", "votacao_t2.csv")

    def test_segundo_turno_entra_sozinho(self):
        dados, orfas, _ = self.juntar()
        sp = dados["3550308"]
        self.assertEqual(sorted(sp["t"]), ["1", "2"])
        self.assertEqual(sp["cand"]["2"], [[13, "Lula"], [22, "Jair Bolsonaro"]])
        # locais sem linha do 2º turno: reaproveita local e aptos do 1º
        self.assertEqual(sp["t"]["2"], [[None, None, "EMEF CAMPOS SALLES", "SÉ", "01001", 400, 394, [210, 180], 4,
                                         [[1, 5, 400, 394, [210, 180], 4]]]])
        self.assertEqual(list(dados["1200401"]["t"]), ["1"])
        self.assertEqual(len(orfas), 1)


class TestSaida(Base):
    def test_um_arquivo_por_municipio(self):
        out = self.td / "geo"
        with redirect_stdout(io.StringIO()):
            n, b = ms.montar(self.br, out)
        arqs = sorted(p.name for p in (out / "locais").iterdir())
        self.assertEqual(arqs, ["1200401.json", "3550308.json"])
        self.assertEqual((n, b), (2, sum((out / "locais" / a).stat().st_size for a in arqs)))
        reg = json.loads((out / "locais" / "3550308.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(reg), ["cand", "t"])
        txt = (out / "locais" / "3550308.json").read_text(encoding="utf-8")
        self.assertNotIn(", ", txt)
        self.assertNotIn(": ", txt)

    def test_por_uf(self):
        out = self.td / "geo"
        with redirect_stdout(io.StringIO()):
            n, _ = ms.montar(self.br, out, por_uf=True)
        self.assertEqual(n, 2)
        self.assertEqual(sorted(p.name for p in (out / "locais").iterdir()), ["AC.json", "SP.json"])
        ac = json.loads((out / "locais" / "AC.json").read_text(encoding="utf-8"))
        self.assertEqual(list(ac), ["1200401"])
        self.assertEqual(sorted(ac["1200401"]), ["cand", "t"])

    def test_acima_do_limite_grava_por_uf_e_limpa_os_antigos(self):
        out = self.td / "geo"
        with redirect_stdout(io.StringIO()):
            ms.montar(self.br, out)
            ms.montar(self.br, out, limite_bytes=10)
        self.assertEqual(sorted(p.name for p in (out / "locais").iterdir()), ["AC.json", "SP.json"])

    def test_sem_brutos_sai_com_aviso(self):
        with self.assertRaises(SystemExit):
            ms.montar(self.td / "nada", self.td / "geo")


if __name__ == "__main__":
    unittest.main()
