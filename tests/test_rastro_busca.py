"""Busca do Rastro (Revisão 4C): índice estático site/rastro/busca.json, caixa nas páginas e LGPD do índice."""
import copy
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from rastro import busca
from rastro import paginas as pg
from tests.test_rastro_paginas import CFG, ELEITOS, FIX, FORN, gerar, texto

RAIZ = Path(__file__).resolve().parent.parent
CPF = "52998224725"
PH = "Busque um eleito, uma empresa, um CNPJ ou um sócio"


def indice(d, **kw):
    pags = gerar(d, **kw)
    return pags, json.loads((Path(d) / "rastro" / "busca.json").read_text(encoding="utf-8"))["itens"]


class TestIndice(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as d:
            self.pags, self.itens = indice(d)
            self.js = (Path(d) / "rastro" / "busca.js").read_text(encoding="utf-8")
        self.por_nome = {(i["t"], i["n"]): i for i in self.itens}

    def test_eleito_publicado_com_url(self):
        i = self.por_nome[("e", "ALUISIO MENDES")]
        self.assertEqual(i["u"], "/rastro/depfed/ma/aluisio-mendes/")
        self.assertEqual(i["p"], 1)
        self.assertTrue(i["c"].startswith("Deputado(a) federal · MA · PSD · "))
        self.assertRegex(i["c"], r"\d+ indicador")

    def test_nao_publicado_com_ancora(self):
        i = self.por_nome[("e", "NAO PUBLICADO")]
        self.assertEqual((i["u"], i["p"]), ("/rastro/#e-7d4", 0))
        home = {p["path"]: p["html"] for p in self.pags}["/rastro/"]
        self.assertIn('<tr id="e-7d4">', home)

    def test_fornecedor_e_socio(self):
        f = self.por_nome[("f", "EMPRESA GRANDE LTDA")]
        self.assertEqual(f["u"], "/rastro/fornecedor/33333333000191/")
        self.assertIn("33333333000191", f["k"])
        self.assertRegex(f["c"], r"^recebeu R\$ [\d.]+,\d{2} de 2 campanhas$")
        s = self.por_nome[("s", "BELTRANO SOCIO")]
        self.assertEqual((s["u"], s["c"]), (f["u"], "sócio(a) de EMPRESA GRANDE LTDA"))

    def test_chaves_curtas(self):
        for i in self.itens:
            self.assertLessEqual(set(i), {"t", "n", "c", "u", "k", "p"})
            self.assertEqual(i["k"], busca.normalizar(i["k"]))

    def test_toda_url_existe(self):
        paths = {p["path"] for p in self.pags}
        for i in self.itens:
            self.assertIn(i["u"].split("#")[0], paths, i)

    def test_js_copiado(self):
        self.assertEqual(self.js, (RAIZ / "rastro" / "busca.js").read_text(encoding="utf-8"))
        self.assertNotRegex(self.js, r"https?://")


class TestAncora(unittest.TestCase):
    def test_sq_nunca_vira_cpf(self):
        # sq reais de 11 dígitos que passam no dígito verificador de CPF
        for sq in ("80002542390", "10002544296", "250002542390", "2004"):
            a = busca.ancora_eleito(sq)
            self.assertNotRegex(a, r"\d{11}")
            self.assertEqual(int(a[2:], 16), int(sq))


class TestNormalizar(unittest.TestCase):
    def test_acento_e_caixa(self):
        self.assertEqual(busca.normalizar("JOÃO"), busca.normalizar("joao"))
        self.assertEqual(busca.normalizar("  José   D'Ávila "), "jose d'avila")

    def test_cnpj_com_e_sem_pontuacao(self):
        with tempfile.TemporaryDirectory() as d:
            _, itens = indice(d)
        k = next(i["k"] for i in itens if i["t"] == "f")
        self.assertIn(re.sub(r"\D", "", "33.333.333/0001-91"), k)

    def test_js_tem_os_mesmos_passos(self):
        js = (RAIZ / "rastro" / "busca.js").read_text(encoding="utf-8")
        self.assertIn('.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().replace(/\\s+/g, " ").trim()', js)
        self.assertEqual(busca.RE_DIACRITICO.pattern, "[\\u0300-\\u036f]")
        for a, b in (("JOÃO", "joao"), ("Ñandú  ÇA", "nandu ca"), ("D'ÁVILA", "d'avila")):
            self.assertEqual(busca.normalizar(a), b)


def contas_lgpd(dest):
    """Cópia das contas das fixtures com nome em pessoa física paga e em doador PF (o gerador nunca deve lê-los)."""
    shutil.copytree(FIX / "contas", dest)
    arq = Path(dest) / "2001.json"
    c = json.loads(arq.read_text(encoding="utf-8"))
    c["despesas"]["fornecedores_pf"] = {"qtd": 1, "total": 10.0, "por_tipo": {}, "valores": [], "nomes": ["FULANA PAGA PF"]}
    c["receitas"]["doadores_pf"] = {"qtd": 1, "total": 10.0, "nomes": ["CICLANO DOADOR PF"], "cpfs": [CPF]}
    arq.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


class TestLgpd(unittest.TestCase):
    def test_indice_sem_dado_pessoal(self):
        with tempfile.TemporaryDirectory() as d:
            contas_lgpd(Path(d) / "contas")
            gerar(Path(d) / "out", dir_contas=Path(d) / "contas")
            txt = (Path(d) / "out" / "rastro" / "busca.json").read_text(encoding="utf-8")
        self.assertEqual([m.group() for m in pg.RE_CPF_CANDIDATO.finditer(txt) if pg.cpf_valido(re.sub(r"\D", "", m.group()))], [])
        for proibido in ("cpf_mascarado", "***", "11111111000191", "**.***.***", "NOME DO MEI DONO", "SOCIO DO MEI", "FULANA PAGA PF",
                         "CICLANO DOADOR PF", CPF, "99999999000191", "RUA SECRETA"):
            self.assertNotIn(proibido, txt)
        self.assertIsNone(pg.PROIBIDOS.search(txt))

    def test_cpf_no_indice_derruba(self):
        txt = busca.serializar([{"t": "s", "n": f"FULANO {CPF[:3]}.{CPF[3:6]}.{CPF[6:9]}-{CPF[9:]}", "c": "", "u": "/", "k": ""}])
        with self.assertRaises(ValueError):
            pg.varrer("busca.json", txt["busca.json"])

    def test_cpf_em_socio_nao_grava_nada(self):
        forn = copy.deepcopy(FORN)
        forn["fornecedores"]["33333333000191"]["socios"].append({"nome": f"SOCIO {CPF}", "cpf_mascarado": None})
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                gerar(d, fornecedores=forn)
            self.assertEqual(list(Path(d).rglob("*")), [])

    def test_cpf_em_nome_de_pendente_nao_grava_nada(self):
        el = copy.deepcopy(ELEITOS)
        el["eleitos"][3]["nome_urna"] = f"NAO {CPF}"
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                gerar(d, eleitos=el)
            self.assertEqual(list(Path(d).rglob("*")), [])


class TestSerializar(unittest.TestCase):
    ITENS = [{"t": "e", "n": f"NOME {i}", "c": "x", "u": f"/rastro/#e-{i}", "k": f"nome {i}", "p": 0} for i in range(50)]

    def test_compacto_e_utf8(self):
        out = busca.serializar([{"t": "s", "n": "JOÃO", "c": "", "u": "/", "k": "joao"}])
        self.assertEqual(list(out), ["busca.json"])
        self.assertIn('"n":"JOÃO"', out["busca.json"])
        self.assertNotIn(", ", out["busca.json"])

    def test_divide_acima_do_limite(self):
        out = busca.serializar(self.ITENS, limite=600)
        man = json.loads(out.pop("busca.json"))
        self.assertGreater(len(man["partes"]), 1)
        self.assertEqual([f"/rastro/{n}" for n in out], man["partes"])
        juntos = [i for t in out.values() for i in json.loads(t)["itens"]]
        self.assertEqual(juntos, self.ITENS)
        self.assertTrue(all(len(t.encode()) <= 600 for t in out.values()))


class TestCaixa(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as d:
            self.pags = {p["path"]: p["html"] for p in gerar(d)}

    def test_home_caixa_grande_abaixo_do_h1(self):
        h = self.pags["/rastro/"]
        self.assertRegex(h, r'<h1>Rastro do dinheiro</h1><div class="rs-busca rs-busca-g"')
        self.assertNotIn('<div class="rs-topo">', h)
        self.assertIn('<h2 id="eleitos">', h)
        self.assertIn('<tr id="e-7d1">', h)

    def test_toda_pagina_tem_caixa_e_script(self):
        for path, h in self.pags.items():
            self.assertEqual(h.count("data-rs-busca"), 1, path)
            self.assertIn(f'placeholder="{PH}"', h, path)
            self.assertIn('<script src="/rastro/busca.js" defer></script>', h, path)
            self.assertRegex(h, r'<input id="rs-busca-q" type="search" role="combobox" aria-controls="rs-busca-l"', path)
            self.assertIn('<ul id="rs-busca-l" role="listbox"', h, path)
            if path != "/rastro/":
                self.assertIn('<div class="rs-topo"><nav class="rs-crumbs"', h, path)

    def test_sem_js_link_para_a_lista(self):
        h = self.pags["/rastro/depfed/ma/aluisio-mendes/"]
        self.assertIn('<a class="rs-busca-sem" href="/rastro/#eleitos">Ver a lista completa de eleitos</a>', h)
        self.assertIn('<div class="rs-busca-cx" hidden>', h)

    def test_css_so_por_token(self):
        regras = [linha for linha in pg.CSS.splitlines() if "rs-busca" in linha or "rs-topo" in linha or "rs-sr" in linha]
        self.assertTrue(regras)
        for r in regras:
            self.assertNotRegex(r, r"#[0-9a-fA-F]{3,8}\b|rgba?\(", r)
        self.assertIn("max-width:100%", "".join(regras))

    def test_nome_com_aspas_e_sinais(self):
        el = copy.deepcopy(ELEITOS)
        el["eleitos"][3]["nome_urna"] = 'ZÉ "<B>" & CIA'
        with tempfile.TemporaryDirectory() as d:
            pags, itens = indice(d, eleitos=el)
        home = {p["path"]: p["html"] for p in pags}["/rastro/"]
        self.assertIn("ZÉ \"&lt;B&gt;\" &amp; CIA", home)
        self.assertIn('ZÉ "<B>" & CIA', texto(home))
        ze = next(i for i in itens if i["n"].startswith("ZÉ"))
        self.assertEqual((ze["n"], ze["k"]), ('ZÉ "<B>" & CIA', 'ze "<b>" & cia'))  # o JSON guarda cru; busca.js escapa


if __name__ == "__main__":
    unittest.main()
