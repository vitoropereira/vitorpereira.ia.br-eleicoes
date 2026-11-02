"""horarios/: leitura dos logs de urna e estatísticas do horário dos votos."""
import io, sys, unittest, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "horarios"))
import estatisticas as E  # noqa: E402
import ler_logs as L  # noqa: E402

D = "25/10/2026"


def ln(hora, texto, dia=D):
    return f"{dia} {hora}\tINFO\t1\tVOTA\t{texto}\tX"


LOG = "\n".join([
    ln("08:00:00", "Identificador do eleitor digitado pelo mesário"),
    ln("08:00:05", "Tipo de habilitação do eleitor [biométrica]"),
    ln("08:00:10", "Eleitor foi habilitado"),
    ln("08:00:30", "O voto do eleitor foi computado"),
    ln("08:01:00", "Identificador do eleitor digitado pelo mesário"),
    ln("08:01:40", "Solicitação de dado pessoal do eleitor para habilitação manual"),
    ln("08:02:00", "Eleitor foi habilitado"),
    ln("08:02:12", "O voto do eleitor foi computado"),
    ln("08:03:00", "O voto do eleitor foi computado"),           # sem habilitação registrada
    ln("09:00:00", "O voto do eleitor foi computado", "04/10/2026"),  # 1º turno: fica fora
])


class TestLerLogs(unittest.TestCase):
    def test_votos(self):
        t, mesa, cab, hab = L.votos(LOG)
        self.assertEqual(t, [8 * 3600 + 30, 8 * 3600 + 132, 8 * 3600 + 180])
        self.assertEqual(mesa, [10, 60, -1])
        self.assertEqual(cab, [20, 12, -1])
        self.assertEqual(hab, "bm?")

    def test_latin1_do_tse(self):
        """O logd.dat vem em latin1: a habilitação manual tem que ser achada depois do decode."""
        bruto = LOG.encode("latin1").decode("latin1")
        self.assertEqual(L.votos(bruto)[3], "bm?")

    def test_entrada_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("o03221rr0300000040011-log.jez", b"conteudo" * 100)
        dados = buf.getvalue()
        info = zipfile.ZipFile(io.BytesIO(dados)).infolist()[0]
        orig = L.faixa
        L.faixa = lambda url, a, b: dados[a:b + 1]
        try:
            self.assertEqual(L.entrada("x", info), b"conteudo" * 100)
        finally:
            L.faixa = orig

    def test_nome_da_secao(self):
        m = L.NOME.search("o03221rr0300000040011-log.jez")
        self.assertEqual((m[1], m[2], m[3], m[4]), ("rr", "03000", "0004", "0011"))

class TestRetomar(unittest.TestCase):
    def test_tmp_truncado_fica_com_linhas_completas(self):
        import gzip, json, tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "2t_XX.jsonl.tmp"
            with gzip.open(tmp, "at", encoding="utf-8") as f:
                f.write(json.dumps({"mun": "1", "zona": "2", "secao": "3", "t": [1]}) + "\n")
            inteiro = tmp.read_bytes()
            with gzip.open(tmp, "at", encoding="utf-8") as f:   # 2º lote, que vai ser cortado no meio
                f.write(json.dumps({"mun": "1", "zona": "2", "secao": "4", "t": [2]}) + "\n")
            tmp.write_bytes(tmp.read_bytes()[:len(inteiro) + 15])
            linhas = L.retomar(tmp)
            self.assertEqual([json.loads(x)["secao"] for x in linhas], ["3"])
            self.assertEqual(L.retomar(tmp), linhas)          # o .tmp regravado lê limpo
        self.assertEqual(L.retomar(Path("/nao/existe.tmp")), [])


class TestEstatisticas(unittest.TestCase):
    def test_fuso(self):
        self.assertEqual(E.fuso([8 * 3600 + 60, 8 * 3600 + 200]), 0)
        self.assertEqual(E.fuso([7 * 3600 + 30, 7 * 3600 + 90, 7 * 3600 + 5]), 1)   # RR, AM: 1h atrás
        self.assertEqual(E.fuso([6 * 3600 + 30]), 2)                               # AC

    def test_simpson_detecta_inversao(self):
        """Agregado sobe, mas dentro de cada grupo desce: o 'dentro' tem que sair negativo."""
        g = {"A": [(0, 10, 1), (1, 9, 1), (2, 8, 1)], "B": [(5, 30, 1), (6, 29, 1), (7, 28, 1)]}
        junto = [p for v in g.values() for p in v]
        self.assertGreater(E.inclinacao(junto), 0)
        self.assertAlmostEqual(E.dentro(g), -1.0)

    def test_quantis(self):
        from collections import Counter
        self.assertEqual(E.quantis(Counter({1: 1, 2: 1, 3: 1, 4: 1}), (0.5,)), {"p50": 2})

    def test_calcular_converte_fuso_e_cruza_resultado(self):
        s = lambda mun, sec, ts: dict(mun=mun, zona="0001", secao=sec, t=ts, mesa=[10] * len(ts), cab=[15] * len(ts),
                                      hab="b" * len(ts))
        h = 3600
        secoes = [("RR", s("03000", "0001", [7 * h + 10, 10 * h, 15 * h + 59 * 60 + 30])),   # hora local, +1h
                  ("SP", s("71072", "0002", [8 * h + 5, 13 * h, 17 * h + 2 * 60]))]
        res = {("RR", 3000, 1, 1): [20, 10, 1, 2], ("SP", 71072, 1, 2): [10, 25, 0, 0]}
        est = E.calcular(secoes, res)
        self.assertEqual(est["fusos"], {"+1h": 1, "+0h": 1})
        self.assertEqual(est["depois_das_17h"], 1)               # só o voto de SP às 17:02 (RR 15:59 local = 16:59)
        self.assertEqual(est["cobertura"]["RR"], dict(log=3, oficial=33, pct=9.09))
        self.assertEqual(est["curva_10min"][0]["hora"], "08:00")  # 07:00 local de RR vira 08:00 de Brasília
        self.assertEqual(est["secoes_cruzadas"], 2)


if __name__ == "__main__":
    unittest.main()
