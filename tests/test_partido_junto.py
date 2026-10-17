"""Partido junto do nome: todo bloco do site que cita um candidato traz a sigla dele no mesmo bloco (issue #69).
O helper blocos_sem_sigla roda sobre o HTML pré-renderizado; os testes de página dependem do Chrome headless."""
import html.parser, json, re, shutil, sys, tempfile, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); sys.path.insert(0, str(R / "relatorio"))
import build_site as B
import pagina as P

FIX = Path(__file__).parent / "fixtures" / "partido"
TEM_CHROME = bool(shutil.which(B.CHROME) or Path(B.CHROME).exists())
BLOCOS = {"li", "tr", "p", "h1", "h2", "h3", "title", "summary", "text", "g"}
CLASSES = {"legend", "ramp", "nm"}
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Blocos(html.parser.HTMLParser):
    """(tag, texto) de cada bloco; o texto inclui o dos filhos. Ignora script e style."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha, self.blocos, self.mudo = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in VAZIOS:
            return
        if tag in ("script", "style"):
            self.mudo += 1
        classes = set((dict(attrs).get("class") or "").split())
        self.handle_data(" ")  # célula colada na outra ("PT36,16") não vira uma palavra só
        self.pilha.append([tag, tag in BLOCOS or bool(classes & CLASSES), []])

    def handle_endtag(self, tag):
        self.handle_data(" ")
        if tag in ("script", "style"):
            self.mudo = max(0, self.mudo - 1)
        for i in range(len(self.pilha) - 1, -1, -1):  # fecha até a tag correspondente (HTML mal fechado)
            if self.pilha[i][0] == tag:
                for t, bloco, partes in self.pilha[i:][::-1]:
                    if bloco:
                        self.blocos.append((t, " ".join("".join(partes).split())))
                del self.pilha[i:]
                return

    def handle_data(self, data):
        if not self.mudo:
            for e in self.pilha:
                e[2].append(data)


def _re(palavra):
    return re.compile(rf"(?<!\w){re.escape(palavra)}(?!\w)")


def blocos_sem_sigla(doc, candidatos):
    """[(bloco, nome)] dos blocos que citam um nome de `candidatos` ({sigla: [nomes e apelidos]}) sem a sigla no bloco.
    Nomes mais longos casam primeiro e saem do texto: "Cadu de Lula" não conta como menção a Lula."""
    p = _Blocos(); p.feed(doc); p.close()
    nomes = sorted(((n, sg) for sg, ns in candidatos.items() for n in ns), key=lambda x: -len(x[0]))
    achados = []
    for _, texto in p.blocos:
        resto, citados = texto, {}
        for n, sg in nomes:
            if _re(n).search(resto):
                citados.setdefault(sg, n)
                resto = _re(n).sub("\0", resto)
        achados += [(texto[:160], n) for sg, n in citados.items() if not _re(sg).search(texto)]
    return achados


def candidatos(rel, meta22=None):
    """{sigla: [nomes]} de quem aparece nas páginas: presidente (com apelidos), governadores, Senado e deputados mais votados.
    `meta22` (municipios/geo/t2022/meta.json) traz Jair Bolsonaro, citado na comparação com 2022."""
    out = {}
    add = lambda sg, *nomes: out.setdefault(sg, []).extend(n for n in nomes if n not in out.get(sg, []))
    for c in rel["nac"]["cand"]:
        exib = B.NOME_EXIBICAO.get(c["nome"], c["nome"])
        add(c["sg"], exib, c["nome"], exib.split()[0], c["nome"].split()[0]) if c in (B.cF, B.cL) else add(c["sg"], c["nome"])
    for g in rel["gov"]:
        for x in (g["a"], g["b"], g.get("subjudice")):
            if x:
                add(x["sg"], x["nome"])
    for s in rel["sen"]:
        for e in s["eleitos"] + [s["proximo"]]:
            add(e["sg"], e["nome"])
    for x in rel["depfed"]["top"][:10] + rel["depest"]["top"][:10]:
        add(x["sg"], x["nome"])
    for c in (meta22 or {}).get("cand", {}).get("presidente-1t", []):
        if c["nome"] == "Jair Bolsonaro":
            add(c["sg"], c["nome"], "Bolsonaro")
    return out


def _rel():
    return json.loads((R / "relatorio" / "relatorio.json").read_text())


def _meta22():
    return json.loads((R / "municipios" / "geo" / "t2022" / "meta.json").read_text())


class Helper(unittest.TestCase):
    CAND = {"PL": ["Flávio Bolsonaro", "Flávio"], "PT": ["Lula"]}

    def test_fixture_com_sigla_passa(self):
        self.assertEqual(blocos_sem_sigla((FIX / "com_sigla.html").read_text(), self.CAND), [])

    def test_fixture_sem_sigla_falha(self):
        achados = blocos_sem_sigla((FIX / "sem_sigla.html").read_text(), self.CAND)
        self.assertEqual([n for _, n in achados], ["Lula"])

    def test_ignora_script_e_palavra_dentro_de_outra(self):
        doc = "<p>Lulalândia</p><script>const x='<p>Lula</p>'</script><p>Flávio · PL</p>"
        self.assertEqual(blocos_sem_sigla(doc, self.CAND), [])

    def test_sigla_tem_que_ser_palavra_inteira(self):
        self.assertEqual(len(blocos_sem_sigla("<li>Flávio no PLANALTO</li>", self.CAND)), 1)

    def test_candidatos_tira_siglas_do_dado(self):
        c = candidatos(_rel(), _meta22())
        self.assertIn("Flávio", c[B.cF["sg"]]); self.assertIn("Lula", c[B.cL["sg"]])
        self.assertIn("Jair Bolsonaro", c["PL"])


class Textos(unittest.TestCase):
    """strings que o build_site.py escreve direto no HTML (sem pré-render)"""

    def test_rotulos(self):
        self.assertEqual(B.rotulo(B.cF), f"Flávio Bolsonaro ({B.cF['sg']})")
        self.assertEqual(B.curto(B.cL), f"Lula ({B.cL['sg']})")

    def test_principal_e_faq(self):
        cand = candidatos(_rel(), _meta22())
        h1, titulo, desc = B.textos_principal()
        vis, _, _ = B.faq()
        doc = f"<title>{titulo}</title><h1>{h1}</h1><p>{desc}</p>{vis}"
        self.assertEqual(blocos_sem_sigla(doc, cand), [])

    def test_leituras_e_indice(self):
        cand = candidatos(_rel())
        for r in B.rodadas:
            h1, titulo, desc = B.textos_leitura(r["d"])
            self.assertEqual(blocos_sem_sigla(f"<title>{titulo}</title><h1>{h1}</h1><p>{desc}</p>", cand), [], r["slug"])
        # no índice, cada leitura é um <a class="rd">: confere cada linha como um bloco
        doc = B.pagina_apuracao("").replace('<a class="rd', '<li><a class="rd').replace("</a>", "</a></li>")
        self.assertEqual(blocos_sem_sigla(doc, cand), [])


    def test_resumo_hud(self):
        self.assertEqual(blocos_sem_sigla(B.resumo_hud(), candidatos(_rel(), _meta22())), [])


class HudFontes(unittest.TestCase):
    """o HUD (hud/*.js) desenha no navegador; aqui a varredura estática: rótulo de candidato sem sigla no mesmo template"""

    TEMPLATE = re.compile(r"`(?:[^`\\]|\\.)*`")
    NOME = re.compile(r"\$\{\s*(?:primeiroNome\(\s*)?[\w.?\[\]]*\.nome\b")
    SWATCH = re.compile(r"<\$\{Sw\}[^>]*>")
    COM_SIGLA = re.compile(r"\bsg\b|comSigla|cartao|<\$\{Nome\}")

    @classmethod
    def sem_sigla(cls, js):
        """interpolações de `x.nome` em template literal sem sigla (sg, comSigla, cartao ou <Nome/>) no mesmo template"""
        achados = []
        for t in cls.TEMPLATE.findall(js):
            texto = cls.SWATCH.sub("", t)  # a amostra de cor <Sw sg=…/> usa a sigla, mas não a mostra
            if cls.NOME.search(texto) and not cls.COM_SIGLA.search(texto):
                achados.append(t[:120])
        return achados

    def test_detecta_rotulo_sem_sigla(self):
        self.assertEqual(len(self.sem_sigla("html`<span>${c.nome}</span>`")), 1)
        self.assertEqual(len(self.sem_sigla("html`<span>${primeiroNome(c.nome)}</span>`")), 1)
        self.assertEqual(len(self.sem_sigla("html`<li><${Sw} sg=${c.sg} /><span>${c.nome}</span></li>`")), 1)  # a amostra de cor não vale
        self.assertEqual(self.sem_sigla("html`<span>${c.nome} <small>${c.sg}</small></span>`"), [])
        self.assertEqual(self.sem_sigla("html`<span>${comSigla(c)}</span> ${cartao(c)} <${Nome} c=${c} />`"), [])

    def test_hud_sem_rotulo_sem_sigla(self):
        for arq in sorted((R / "hud").glob("*.js")):
            if arq.name.endswith("_test.js"):
                continue
            self.assertEqual(self.sem_sigla(arq.read_text(encoding="utf-8")), [], arq.name)


@unittest.skipUnless(TEM_CHROME, "Chrome headless indisponível")
class Paginas(unittest.TestCase):
    """pré-renderiza as páginas montadas a partir dos templates e procura blocos sem sigla"""

    def render(self, doc):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "index.html"; arq.write_text(doc)
            return B.prerender(arq.as_uri())

    def test_resultado_final(self):
        rel = _rel()
        rel["mapa"] = json.loads((R / "relatorio" / "dados" / "mapa.json").read_text())
        doc = self.render(P.html_relatorio((R / "relatorio" / "template_relatorio.html").read_text(), rel, P.siglas_2022()))
        self.assertIn('id="hl"><li', doc)  # o script rodou
        self.assertEqual(blocos_sem_sigla(doc, candidatos(rel, _meta22())), [])

    @unittest.skipUnless((R / "site" / "ao-vivo" / "index.html").exists(), "site/ não construído (python3 build_site.py)")
    def test_ao_vivo(self):
        """o HUD rodando no Chrome com o dado do 1º turno: manchete, placar e listas com a sigla junto do nome"""
        srv = B.serve(R / "site", port=8797)
        try:
            doc = B.prerender("http://127.0.0.1:8797/ao-vivo/")
        finally:
            srv.shutdown(); srv.server_close()
        self.assertIn('class="manchete', doc)  # o app montou
        self.assertEqual(blocos_sem_sigla(doc, candidatos(_rel(), _meta22())), [])

    def test_leitura(self):
        r = next(x for x in B.rodadas if x["slug"] == "84-9")
        doc = self.render(B.html_leitura((R / "template.html").read_text(), r["d"]))
        self.assertIn("Vantagem final de Flávio", doc)  # o script rodou até o fim
        self.assertEqual(blocos_sem_sigla(doc, candidatos(_rel())), [])


if __name__ == "__main__":
    unittest.main()
