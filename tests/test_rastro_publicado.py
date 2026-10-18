"""LGPD, redação e isolamento sobre as páginas reais do Rastro versionadas em site/rastro/ (o que o lote diário publica).
O lote só faz merge se estes testes passarem."""
import json
import re
import unittest
from pathlib import Path

from rastro import paginas as pg
from rastro.contas import cpf_valido

RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "site"
PUB = json.loads((RAIZ / "rastro" / "publicados.json").read_text(encoding="utf-8"))
ELEITOS = json.loads((RAIZ / "rastro" / "dados" / "eleitos.json").read_text(encoding="utf-8"))
RE_HREF_ELEITO = re.compile(r'href="/(rastro/(?!fornecedor/|metodologia/)[^"]+/)"')
RE_HREF_FORN = re.compile(r'href="/rastro/fornecedor/([^"/]+)/"')
RE_SCRIPT_SRC = re.compile(r'<script[^>]*\ssrc="([^"]+)"', re.I)
SCRIPTS_PERMITIDOS = {"/medicao.js",  # moldura de medição do site (consentimento antes de GA4/Clarity)
                      "/rastro/rastro.js",  # filtro "Só com indício" da tabela de fornecedores
                      "/rastro/busca.js",  # busca do Rastro
                      "/hud/topo-pessoas.js"}  # "pessoas no site agora" do cabeçalho: só presença (id aleatório), não lê a página


def cpfs(texto):
    return [m.group() for m in pg.RE_CPF_CANDIDATO.finditer(texto) if cpf_valido(re.sub(r"\D", "", m.group()))]


def problemas(texto):
    """CPF válido ou termo proibido: o que derruba o lote."""
    out = [f"CPF {c[:3]}…" for c in cpfs(texto)]
    m = pg.termo_proibido(texto)
    return out + ([f"termo {m.group()!r}"] if m else [])


def caminhos_publicados():
    por_sq = {str(e["sq"]): e for e in ELEITOS["eleitos"]}
    cam = pg.caminhos([por_sq[str(s)] for s in PUB])
    return {str(s): cam[por_sq[str(s)]["sq"]] for s in PUB}


class TestPaginasPublicadas(unittest.TestCase):
    def setUp(self):
        self.paginas = {p: p.read_text(encoding="utf-8") for p in sorted((SITE / "rastro").rglob("*.html"))}
        self.assertTrue(self.paginas, "site/rastro/ sem páginas: rode build_site.py")

    def test_nenhum_cpf_nem_termo_proibido(self):
        for p, h in self.paginas.items():
            self.assertEqual(problemas(h), [], p.relative_to(RAIZ))

    def test_detector_pega_cpf_injetado(self):
        # prova de que o teste acima morde: um CPF válido injetado numa página real é detectado
        h = next(iter(self.paginas.values()))
        self.assertTrue(problemas(h.replace("</main>", "<p>529.982.247-25</p></main>", 1) + "<p>52998224725</p>"))
        self.assertTrue(problemas(h + "<p>laranja</p>"))

    def test_pagina_de_cada_eleito(self):
        for sq, cam in caminhos_publicados().items():
            arq = SITE / cam / "index.html"
            self.assertTrue(arq.exists(), f"{sq}: {arq.relative_to(RAIZ)} não existe")
            h = arq.read_text(encoding="utf-8")
            self.assertIn(pg.AVISO, h, sq)
            self.assertRegex(h, r'class="rs-base">Base de dados: [^<]*\d{2}/\d{2}/\d{4}', sq)
            self.assertIn('href="/rastro/metodologia/"', h, sq)
            self.assertIn('<section id="contestar">', h, sq)

    def test_home_linka_exatamente_os_publicados(self):
        h = (SITE / "rastro" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("Nenhuma página publicada", h)
        linkados = set(RE_HREF_ELEITO.findall(h))
        self.assertEqual(linkados, set(caminhos_publicados().values()))

    def test_fornecedor_linkado_existe(self):
        ids = set()
        for h in self.paginas.values():
            ids |= set(RE_HREF_FORN.findall(h))
        if any(cam for cam in caminhos_publicados()):
            self.assertTrue(ids, "nenhum fornecedor linkado nas páginas publicadas")
        for id_ in ids:
            self.assertTrue((SITE / "rastro" / "fornecedor" / id_ / "index.html").exists(), id_)

    def test_isolamento_sem_script_externo(self):
        for p, h in self.paginas.items():
            fora = set(RE_SCRIPT_SRC.findall(h)) - SCRIPTS_PERMITIDOS
            self.assertEqual(fora, set(), p.relative_to(RAIZ))


def cnpjs_mei():
    forn = json.loads((RAIZ / "rastro" / "dados" / "fornecedores.json").read_text(encoding="utf-8"))["fornecedores"]
    return {c for c, r in forn.items() if pg.eh_mei(r)}


def problemas_indice(texto, meis):
    """problemas() mais o que só o índice da busca pode vazar: CNPJ de MEI, máscara ou cpf_mascarado."""
    out = problemas(texto)
    out += [f"MEI {c[:4]}…" for c in meis if c in texto]
    return out + (["cpf_mascarado/máscara"] if "cpf_mascarado" in texto or "***" in texto else [])


class TestBuscaPublicada(unittest.TestCase):
    def setUp(self):
        self.indices = {p: p.read_text(encoding="utf-8") for p in sorted((SITE / "rastro").glob("busca*.json"))}
        self.assertIn(SITE / "rastro" / "busca.json", self.indices, "site/rastro/busca.json não existe: rode build_site.py")
        self.meis = cnpjs_mei()

    def test_indice_sem_dado_pessoal(self):
        for p, t in self.indices.items():
            self.assertEqual(problemas_indice(t, self.meis), [], p.relative_to(RAIZ))

    def test_detector_pega_cpf_injetado(self):
        t = self.indices[SITE / "rastro" / "busca.json"]
        self.assertTrue(problemas_indice(t.replace('"n":"', '"n":"529.982.247-25 ', 1), self.meis))
        self.assertTrue(problemas_indice(t + next(iter(self.meis)), self.meis))

    def test_js_publicado_e_o_do_repo(self):
        self.assertEqual((SITE / "rastro" / "busca.js").read_text(encoding="utf-8"),
                         (RAIZ / "rastro" / "busca.js").read_text(encoding="utf-8"))

    def test_todo_eleito_esta_no_indice(self):
        dados = json.loads(self.indices[SITE / "rastro" / "busca.json"])
        itens = dados.get("itens") or [i for parte in dados["partes"]
                                         for i in json.loads((SITE / parte.lstrip("/")).read_text(encoding="utf-8"))["itens"]]
        eleitos = {i["u"] for i in itens if i["t"] == "e" and i["p"] == 1}
        self.assertEqual(eleitos, {"/" + c for c in caminhos_publicados().values()})
        self.assertEqual(sum(1 for i in itens if i["t"] == "e"), len(ELEITOS["eleitos"]))


if __name__ == "__main__":
    unittest.main()
