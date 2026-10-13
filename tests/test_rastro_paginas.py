import copy
import hashlib
import html
import json
import re
import tempfile
import unittest
from pathlib import Path

from rastro import indicadores as ind
from rastro import paginas as pg
from tests.test_rastro_indicadores import cpfs_validos

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "rastro" / "paginas"
CFG = json.loads((RAIZ / "rastro" / "config.json").read_text(encoding="utf-8"))
PROIBIDOS = ("fraude", "laranja", "fictícia", "ficticia")


def lj(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


ELEITOS = lj("eleitos.json")
INDS = lj("indicadores.json")
FORN = lj("fornecedores.json")
PUBL = lj("publicados.json")
E = {e["sq"]: e for e in ELEITOS["eleitos"]}
BASES = {"contas": "2026-10-12", "receita": "2026-09-01"}


def texto(h):
    """HTML sem tags, com entidades resolvidas e espaços colapsados."""
    h = re.sub(r"</(p|li|h\d|td|th|dt|dd|tr|div|section|nav|title)>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h)))


def gerar(dest, **kw):
    args = dict(publicados=PUBL, eleitos=ELEITOS, dir_contas=FIX / "contas", indicadores=INDS, fornecedores=FORN, cfg=CFG)
    args.update(kw)
    return pg.gerar(dest, **args)


def arquivos(raiz):
    return {str(p.relative_to(raiz)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(raiz).rglob("*")) if p.is_file()}


def pagina_2001(contas=None, itens=None, forn=None):
    c = contas if contas is not None else json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
    return pg.html_eleito(E["2001"], c, itens if itens is not None else INDS["indicadores"]["2001"],
                          forn if forn is not None else FORN["fornecedores"], CFG, BASES)


class TestCaminho(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(pg.slug("JOSÉ D'ÁVILA"), "jose-davila")
        self.assertEqual(pg.slug("  Ana  Maria / Silva-Jr. "), "ana-maria-silva-jr")

    def test_caminho(self):
        self.assertEqual(pg.caminho(E["2001"]), "rastro/depfed/ma/aluisio-mendes/")
        self.assertEqual(pg.caminho(E["2003"]), "rastro/senador/pi/maria-sem-contas/")

    def test_colisao_recebe_sq(self):
        a = {"sq": "1", "nome_urna": "JOÃO SILVA", "cargo": "depfed", "uf": "SP"}
        b = {"sq": "2", "nome_urna": "Joao Silva", "cargo": "depfed", "uf": "SP"}
        c = {"sq": "3", "nome_urna": "JOAO SILVA", "cargo": "depest", "uf": "SP"}
        cam = pg.caminhos([a, b, c])
        self.assertEqual(cam["1"], "rastro/depfed/sp/joao-silva-1/")
        self.assertEqual(cam["2"], "rastro/depfed/sp/joao-silva-2/")
        self.assertEqual(cam["3"], "rastro/depest/sp/joao-silva/")
        self.assertEqual(len(set(cam.values())), 3)


class TestEleito(unittest.TestCase):
    def test_conteudo_obrigatorio(self):
        h = pagina_2001()
        t = texto(h)
        self.assertIn("12/10/2026", t)
        self.assertIn("01/09/2026", t)
        self.assertIn(pg.AVISO, t)
        self.assertIn('href="/rastro/metodologia/"', h)
        self.assertIn("Contestar este dado", h)
        self.assertIn(f'href="mailto:{CFG["contato_email"]}?', h)
        for i in INDS["indicadores"]["2001"]:
            self.assertIn(f'{i["nome"]}: {i["fato"]}', t)
            self.assertIn(f'<a href="{i["fonte_url"]}"', h)
        self.assertIn("Receitas por origem", h)
        self.assertIn("Despesas por fornecedor", h)
        self.assertIn(ind.brl(400000), t)

    def test_sem_prestacao(self):
        for contas in (None, {"sq": "2002", "prestacao_parcial": False, "receitas": None, "despesas": None}):
            t = texto(pg.html_eleito(E["2002"], contas, [], FORN["fornecedores"], CFG, BASES))
            self.assertIn("sem prestação parcial publicada", t)
            self.assertNotIn("R$ 0", t)
            self.assertNotIn("Receitas por origem", t)
            self.assertNotIn("Nenhum indicador", t)

    def test_homonimo(self):
        itens = [{"nome": n, "fato": "algo", "valor": 1, "fonte_url": "https://x.invalid/"}
                 for n in ("socio_doador", "socio_ligado", "socio_nomeado", "concentracao", "mei_acima_teto")]
        h = pagina_2001(itens=itens)
        com = [m for m in re.findall(r"<li>.*?</li>", h, re.S) if "pode ser homônimo" in m]
        self.assertEqual(len(com), 3)
        for nome in ("socio_doador", "socio_ligado", "socio_nomeado"):
            self.assertTrue(any(f"<code>{nome}</code>" in m for m in com), nome)

    def test_sem_indicadores(self):
        self.assertIn("Nenhum indicador disparado", texto(pagina_2001(itens=[])))


class TestLgpd(unittest.TestCase):
    def test_mei_mascarado(self):
        h = pagina_2001()
        self.assertIn(ind.mascarar_cnpj("11111111000191"), h)
        self.assertNotIn("11111111000191", h)
        self.assertNotIn("NOME DO MEI DONO", h)
        self.assertIn("EMPRESA GRANDE LTDA", h)

    def test_sem_cadastro_tambem_mascara(self):
        h = pagina_2001()
        self.assertNotIn("SEM CADASTRO LTDA", h)
        self.assertNotIn("99999999000191", h)

    def test_pf_so_agregado(self):
        t = texto(pagina_2001())
        self.assertIn("Pessoas físicas: 24 pagas", t)
        self.assertIn("Despesas com pessoal", t)

    def test_cpf_valido_no_nome_levanta(self):
        contas = json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
        contas["despesas"]["fornecedores_pj"][0]["nome"] = "EMPRESA 529.982.247-25 LTDA"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "contas").mkdir()
            (Path(d) / "contas" / "2001.json").write_text(json.dumps(contas), encoding="utf-8")
            with tempfile.TemporaryDirectory() as saida:
                with self.assertRaisesRegex(ValueError, "CPF"):
                    gerar(saida, publicados=["2001"], dir_contas=Path(d) / "contas")
                self.assertEqual(arquivos(saida), {})  # nada foi gravado

    def test_sem_fornecedores_falha(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "MEI"):
                gerar(d, fornecedores=None)

    def test_sem_publicados_nao_exige_fornecedores(self):
        with tempfile.TemporaryDirectory() as d:
            pags = gerar(d, publicados=[], indicadores=None, fornecedores=None)
            self.assertEqual([p["path"] for p in pags], ["/rastro/metodologia/"])

    @unittest.skipUnless((RAIZ / "site" / "rastro").exists(), "site/rastro ainda não gerado")
    def test_site_sem_cpf(self):
        for p in (RAIZ / "site" / "rastro").rglob("*"):
            if p.is_file():
                self.assertEqual(cpfs_validos(p.read_text(encoding="utf-8")), [], str(p))


class TestRedacao(unittest.TestCase):
    def varrer(self, raiz):
        n = 0
        for p in Path(raiz).rglob("*"):
            if p.is_file():
                n += 1
                baixo = p.read_text(encoding="utf-8").lower()
                for termo in PROIBIDOS:
                    self.assertNotIn(termo, baixo, f"{termo} em {p}")
        return n

    def test_gerado(self):
        with tempfile.TemporaryDirectory() as d:
            gerar(d)
            self.assertEqual(self.varrer(d), 4)

    def test_termo_proibido_levanta(self):
        contas = json.loads((FIX / "contas" / "2001.json").read_text(encoding="utf-8"))
        contas["despesas"]["fornecedores_pj"][0]["nome"] = "LARANJA DISTRIBUIDORA LTDA"
        with self.assertRaisesRegex(ValueError, "proibido"):
            pg.varrer("x", pg.html_eleito(E["2001"], contas, [], FORN["fornecedores"], CFG, BASES))

    @unittest.skipUnless((RAIZ / "site" / "rastro").exists(), "site/rastro ainda não gerado")
    def test_site(self):
        self.varrer(RAIZ / "site" / "rastro")


class TestMetodologia(unittest.TestCase):
    CHAVES = {
        "recem_aberta_dias": 411, "multicampanha_min": 14, "concentracao_pct": 63, "endereco_min_fornecedores": 4,
        "percentil_comparacao": 88, "min_campanhas_grupo": 17, "pf_qtd_min": 31, "pf_repetido_min_campanhas": 6,
        "pf_redondo_alto_min_qtd": 9, "tardio_dias": 12,
    }

    def test_lista_todos_os_indicadores(self):
        t = texto(pg.html_metodologia(CFG))
        for nome in ("mei_acima_teto", "empresa_recem_aberta", "atividade_incompativel", "socio_doador", "socio_ligado",
                     "multicampanha", "situacao_irregular", "concentracao", "endereco_compartilhado", "preco_fora_da_curva",
                     "gasto_por_voto", "transferencia_candidato", "pessoal_pf", "saque_especie", "pagamento_tardio"):
            self.assertIn(nome, t)

    def test_limites_fontes_e_aviso(self):
        t = texto(pg.html_metodologia(CFG))
        self.assertIn(pg.AVISO, t)
        self.assertIn("Parentesco não consta em nenhuma base pública", t)
        self.assertIn("fato textual", t)
        self.assertIn("homônimos", t)
        self.assertIn("TSE", t)
        self.assertIn("Receita", t)
        self.assertIn("Contestar este dado", t)

    def test_valores_vem_do_config(self):
        antes = texto(pg.html_metodologia(CFG))
        cfg = copy.deepcopy(CFG)
        cfg.update(self.CHAVES)
        cfg["mei_teto_anual"] = 77777
        cfg["tardio_pct_ultimos_dias"] = 0.37
        cfg["situacoes_irregulares"] = ["XPTO"]
        depois = texto(pg.html_metodologia(cfg))
        for k, v in self.CHAVES.items():
            self.assertNotIn(f" {v} ", antes, k)
            self.assertIn(str(v), depois, k)
        for esperado in (ind.brl(77777), "37%", "XPTO"):
            self.assertIn(esperado, depois)
            self.assertNotIn(esperado, antes)
        self.assertIn(ind.brl(CFG["mei_teto_anual"]), antes)
        self.assertNotIn(ind.brl(CFG["mei_teto_anual"]), depois)


class TestIsolamento(unittest.TestCase):
    PROTEGIDOS = ("relatorio/relatorio.json", "relatorio/historico.json", "painel.html")

    def snapshot(self):
        out = {}
        for rel in self.PROTEGIDOS:
            p = RAIZ / rel
            if p.is_file():
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        for pasta in ("hud", "supabase"):
            for p in sorted((RAIZ / pasta).rglob("*")):
                if p.is_file() and "node_modules" not in p.parts:
                    out[str(p.relative_to(RAIZ))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    def test_gerar_nao_mexe_no_resto(self):
        antes = self.snapshot()
        self.assertTrue(antes)
        with tempfile.TemporaryDirectory() as d:
            gerar(d)
            gravados = set(arquivos(d))
        self.assertEqual(self.snapshot(), antes)
        self.assertEqual(gravados, {
            "rastro/metodologia/index.html",
            "rastro/depfed/ma/aluisio-mendes/index.html",
            "rastro/depest/ma/jose-davila/index.html",
            "rastro/senador/pi/maria-sem-contas/index.html"})

    def test_envolver_recebe_a_pagina(self):
        with tempfile.TemporaryDirectory() as d:
            pags = gerar(d, envolver=lambda p: "<!--moldura-->" + p["html"])
            for p in pags:
                self.assertTrue((Path(d) / p["path"].strip("/") / "index.html").read_text(encoding="utf-8").startswith("<!--moldura-->"))


class TestPublicados(unittest.TestCase):
    def test_vazio_no_repo(self):
        self.assertEqual(json.loads((RAIZ / "rastro" / "publicados.json").read_text(encoding="utf-8")), [])

    def test_config_tem_contato(self):
        self.assertRegex(CFG["contato_email"], r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


if __name__ == "__main__":
    unittest.main()
