"""Partido junto do nome: todo bloco do site que cita um candidato traz a sigla dele no mesmo bloco (issues #69 e #74).
O helper blocos_sem_sigla roda sobre o HTML pré-renderizado; rotulos_canvas pega o que o Chart.js desenha no canvas
(que não vira HTML); os testes de página dependem do Chrome headless."""
import functools, html, html.parser, json, re, shutil, sys, tempfile, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); sys.path.insert(0, str(R / "relatorio"))
import build_site as B
import pagina as P

FIX = Path(__file__).parent / "fixtures" / "partido"
TEM_CHROME = bool(shutil.which(B.CHROME) or Path(B.CHROME).exists())
BLOCOS = {"li", "tr", "p", "h1", "h2", "h3", "title", "summary", "text", "g"}
CLASSES = {"legend", "ramp", "nm"}
# título de matéria citado como prova (<cite>) é da fonte, não é rótulo nosso: fica fora, como script e style
MUDOS = {"script", "style", "cite"}
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Blocos(html.parser.HTMLParser):
    """(tag, texto) de cada bloco; o texto inclui o dos filhos. Ignora script, style e cite."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha, self.blocos, self.mudo = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in VAZIOS:
            return
        if tag in MUDOS:
            self.mudo += 1
        classes = set((dict(attrs).get("class") or "").split())
        self.handle_data(" ")  # célula colada na outra ("PT36,16") não vira uma palavra só
        self.pilha.append([tag, tag in BLOCOS or bool(classes & CLASSES), []])

    def handle_endtag(self, tag):
        self.handle_data(" ")
        if tag in MUDOS:
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


@functools.cache
def _re(palavra):
    return re.compile(rf"(?<!\w){re.escape(palavra)}(?!\w)")


PALAVRA = re.compile(r"\w+")


@functools.cache
def _indice(chave):
    """(nomes, por_palavra, sempre) de um dicionário de candidatos congelado em `chave`. `nomes` vem do mais longo ao
    mais curto; `por_palavra` leva a 1ª palavra do nome aos índices dele em `nomes`; `sempre` são os nomes que não
    começam com letra ou dígito, conferidos em todo bloco."""
    nomes = sorted(((n, sg) for sg, ns in chave for n in ns), key=lambda x: -len(x[0]))
    por_palavra, sempre = {}, []
    for i, (n, _) in enumerate(nomes):
        m = PALAVRA.match(n)
        (por_palavra.setdefault(m.group(0), []) if m else sempre).append(i)
    return nomes, por_palavra, sempre


def blocos_sem_sigla(doc, candidatos, corte=160):
    """[(bloco, nome)] dos blocos que citam um nome de `candidatos` ({sigla: [nomes e apelidos]}) sem a sigla no bloco.
    Nomes mais longos casam primeiro e saem do texto: "Cadu de Lula" não conta como menção a Lula."""
    p = _Blocos(); p.feed(doc); p.close()
    nomes, por_palavra, sempre = _indice(tuple((sg, tuple(ns)) for sg, ns in candidatos.items()))
    achados = []
    for _, texto in p.blocos:
        resto, citados = texto, {}
        # filtro barato (a varredura do site/ usa ~1.700 nomes): um nome que casa como palavra inteira começa numa
        # palavra do bloco igual à 1ª palavra dele; a ordem do mais longo ao mais curto fica
        idx = set(sempre).union(*(por_palavra.get(w, ()) for w in set(PALAVRA.findall(texto))))
        for n, sg in (nomes[i] for i in sorted(idx)):
            if _re(n).search(resto):
                citados.setdefault(sg, n)
                resto = _re(n).sub("\0", resto)
        achados += [(texto[:corte], n) for sg, n in citados.items() if not _re(sg).search(texto)]
    return achados


LITERAL = re.compile(r"`(?:[^`\\]|\\.)*`|'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"")
SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)


def rotulos_canvas(js, siglas):
    """literais de string e template do JS (label dos datasets, title.text dos eixos, fillText, tooltips), com
    ${SG.f}/${SG.l} trocados pela sigla de `siglas` ({"f": "PL", "l": "PT"}). O que vai para o canvas não vira HTML:
    cada literal é um bloco para blocos_sem_sigla (ver blocos_canvas)."""
    out = []
    for m in LITERAL.finditer(js):
        t = m.group(0)[1:-1]
        for k, v in siglas.items():
            t = t.replace("${SG.%s}" % k, v)
        out.append(t)
    return out


def blocos_canvas(js, siglas):
    return "".join(f"<p>{html.escape(t)}</p>" for t in rotulos_canvas(js, siglas))


CALC_ANALISE = R / "analise" / "js" / "calc.js"
LADO_JS = re.compile(r"\$\{(?:CAND|SIGLA|LADO_NOME|LADO_MIN|LADO_CURTO)\.([LCF])\}")


def analise_js(js):
    """JS da Análise com ${CAND.L}, ${SIGLA.F}, ${LADO_NOME.L}… trocados pelo texto que o calc.js monta (a sigla vem
    de SIGLA, conferida com relatorio.json em test_sigla_da_analise_vem_do_dado)"""
    calc = CALC_ANALISE.read_text(encoding="utf-8")
    sg = dict(zip("LF", re.search(r'export const SIGLA = \{ L: "(\w+)", F: "(\w+)" \}', calc).groups()))
    cand = {"L": f"Lula ({sg['L']})", "F": f"Flávio ({sg['F']})"}
    tab = {"CAND": cand, "SIGLA": sg, "LADO_CURTO": {**cand, "C": "Centro"},
           "LADO_NOME": {"L": f"Lado de {cand['L']}", "F": f"Lado de {cand['F']}", "C": "Centro/sem lado"},
           "LADO_MIN": {"L": f"lado de {cand['L']}", "F": f"lado de {cand['F']}", "C": "centro"}}
    return LADO_JS.sub(lambda m: tab[m.group(0)[2:].split(".")[0]][m.group(1)], js)


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

    def test_cite_de_fonte_fica_fora(self):
        self.assertEqual(blocos_sem_sigla("<tr><td><cite>Lula x Flávio</cite></td></tr>", self.CAND), [])
        self.assertEqual(len(blocos_sem_sigla("<tr><td><cite>fonte</cite> Lula</td></tr>", self.CAND)), 1)

    def test_sigla_tem_que_ser_palavra_inteira(self):
        self.assertEqual(len(blocos_sem_sigla("<li>Flávio no PLANALTO</li>", self.CAND)), 1)

    def test_svg_sem_sigla_no_no_falha(self):
        """caso negativo da #74: o nó do Sankey sem a sigla dá achado mesmo com a sigla no <title> do SVG"""
        cand = {"PT": ["RUI COSTA"]}
        self.assertEqual(blocos_sem_sigla((FIX / "com_sigla.svg").read_text(), cand), [])
        self.assertEqual([n for _, n in blocos_sem_sigla((FIX / "sem_sigla.svg").read_text(), cand)], ["RUI COSTA", "RUI COSTA"])

    def test_canvas_sem_sigla_falha(self):
        sg = {"f": "PL", "l": "PT"}
        self.assertEqual(blocos_sem_sigla(blocos_canvas((FIX / "com_sigla_canvas.js").read_text(), sg), self.CAND), [])
        achados = blocos_sem_sigla(blocos_canvas((FIX / "sem_sigla_canvas.js").read_text(), sg), self.CAND)
        self.assertEqual(achados, [("Lula (projeção mediana)", "Lula")])

    def test_resultado_exato_da_varredura(self):
        """trava a saída de blocos_sem_sigla e achados_rastro (issue #148: a otimização não pode mudar o que acham):
        nome dentro de nome maior, nomes que se sobrepõem (o mais longo vence), cite, script, nome de urna dentro de
        nome maior e nome que não começa com letra"""
        cand = {"PT": ["Lula", "Cadu de Lula", "LUIZ DA SILVA"], "PL": ["Flávio Bolsonaro", "Flávio", "B C D"],
                "MDB": ["A B", "CASTRO NETO"], "NOVO": ["-Zé"]}
        doc = ("<p>Cadu de Lula disse</p><li>Lula (PT) e Flávio</li><p>Flávio Bolsonaro · PL</p>"
               "<tr><td><cite>Lula fala</cite> sem nome</td></tr><script>var x='<p>Lula</p>'</script>"
               "<p>A B C D</p><p>JOSE DIAS DE CASTRO NETO</p><p>CASTRO NETO · MDB</p><p>LUIZ DA SILVA, Lulalândia</p>"
               "<p>o -Zé foi</p>")
        comuns = [("Cadu de Lula disse", "Cadu de Lula"), ("Lula (PT) e Flávio", "Flávio"), ("A B C D", "B C D")]
        fim = [("LUIZ DA SILVA, Lulalândia", "LUIZ DA SILVA"), ("o -Zé foi", "-Zé")]
        self.assertEqual(blocos_sem_sigla(doc, cand), comuns + [("JOSE DIAS DE CASTRO NETO", "CASTRO NETO")] + fim)
        self.assertEqual(achados_rastro(doc, cand), comuns + fim)
        cand["PSOL"] = ["Lulalândia"]  # o índice de nomes não pode ficar velho quando o dicionário muda
        self.assertIn(("LUIZ DA SILVA, Lulalândia", "Lulalândia"), blocos_sem_sigla(doc, cand))

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


    def test_canvas_do_resultado_final(self):
        """o que o template.html desenha no canvas (séries, rótulo de fim de linha, eixos e tooltips) traz a sigla"""
        js = "".join(SCRIPT.findall((R / "template.html").read_text()))
        sg = {"f": B.cF["sg"], "l": B.cL["sg"]}
        self.assertIn(f"Lula ({B.cL['sg']}) projeção mediana", rotulos_canvas(js, sg))
        self.assertEqual(blocos_sem_sigla(blocos_canvas(js, sg), candidatos(_rel())), [])

    def test_sigla_da_analise_vem_do_dado(self):
        """analise/js/calc.js fixa a sigla de Lula e de Flávio (SIGLA): tem que bater com relatorio.json"""
        js = (R / "analise" / "js" / "calc.js").read_text(encoding="utf-8")
        m = re.search(r'export const SIGLA = \{ L: "(\w+)", F: "(\w+)" \}', js)
        self.assertEqual(m.groups(), (B.cL["sg"], B.cF["sg"]))

    def test_og_da_analise(self):
        """os cartões OG da Análise viram PNG: o texto deles não passa pelo pré-render, só pelo JS"""
        js = (R / "analise" / "js" / "og.js").read_text(encoding="utf-8")
        self.assertIn("`${CAND.L} precisa`", js)
        self.assertEqual(blocos_sem_sigla(blocos_canvas(js, {}), candidatos(_rel(), _meta22())), [])
        self.assertNotEqual(blocos_sem_sigla(blocos_canvas(js.replace("`${CAND.L} precisa`", '"Lula precisa"'), {}), candidatos(_rel())), [])

    def test_rotulos_js_da_analise(self):
        """o que app.js, calc.js, textos.js e graficos.js escrevem (canvas, título, tabela, dica) traz a sigla, com
        ${CAND.L}, ${SIGLA.F}, ${LADO_NOME.L}… resolvidos pelo calc.js (issue #78)"""
        cand = candidatos(_rel(), _meta22())
        for nome in ("app.js", "calc.js", "textos.js", "graficos.js", "og.js"):
            js = analise_js((R / "analise" / "js" / nome).read_text(encoding="utf-8"))
            self.assertEqual(blocos_sem_sigla(blocos_canvas(js, {}), cand), [], nome)
        app = (R / "analise" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("`${CAND.L} precisa`", app)
        self.assertNotEqual(blocos_sem_sigla(blocos_canvas(analise_js(app.replace("`${CAND.L} precisa`", "`Lula precisa`")), {}), cand), [])
        self.assertNotEqual(blocos_sem_sigla(blocos_canvas(analise_js(app.replace("Bolsonaro (${SIGLA.F})", "Bolsonaro")), {}), cand), [])

    def test_resumo_hud(self):
        self.assertEqual(blocos_sem_sigla(B.resumo_hud(), candidatos(_rel(), _meta22())), [])


def _textos(x, chaves=None):
    """strings de `x` (todas, ou só as que ficam sob uma chave de `chaves`); "refs" (de onde vem cada número) fica fora"""
    if isinstance(x, str):
        if chaves is None:
            yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            if k != "refs":
                yield from _textos(v, None if chaves is None or k in chaves else chaves)
    elif isinstance(x, list):
        for v in x:
            yield from _textos(v, chaves)


class AnaliseTextos(unittest.TestCase):
    """os textos que analise/calcular.py grava em analise/dados/ (destaques, FAQ, títulos, notas e rótulos de linha e
    coluna) citam Lula, Flávio e Jair Bolsonaro com a sigla no mesmo texto (issue #78). Fica fora o que é dado de fonte:
    nome de candidato com `partido` ao lado (eliminados, puxadores) e a cópia de lados-*.json e fontes/cenarios.json
    (título de matéria e fato checado), que a página não mostra como rótulo nosso."""

    TEXTO = {"titulo", "texto", "nota", "metodo", "criterio", "ranking_criterio", "linhas", "colunas", "gap_depfed", "rotulo"}
    DADOS = R / "analise" / "dados"

    def doc(self, arq, troca=None):
        d = json.loads((self.DADOS / arq).read_text(encoding="utf-8"))
        if arq in ("destaques.json", "faq.json"):
            textos = list(_textos(d))
        else:
            textos = list(_textos({k: v for k, v in d.items() if k != "fontes_2022"}, self.TEXTO))
            textos += [c["nome"] for c in d.get("cenarios", []) if isinstance(c, dict)]
        if troca:
            textos = [t.replace(*troca) for t in textos]
        return "".join(f"<p>{html.escape(t)}</p>" for t in textos)

    def test_sigla_do_calcular_vem_do_dado(self):
        sys.path.insert(0, str(R / "analise"))
        import calcular as C
        self.assertEqual(C.SIGLA, {"L": B.cL["sg"], "F": B.cF["sg"]})
        self.assertEqual(C.rot("F", "Jair Bolsonaro"), f"Jair Bolsonaro ({B.cF['sg']})")

    def test_nenhum_texto_sem_sigla(self):
        self.maxDiff = None
        cand = candidatos(_rel(), _meta22())
        arqs = sorted(a.name for a in self.DADOS.glob("*.json") if a.name != "lados.json")
        self.assertIn("destaques.json", arqs)
        self.assertEqual({a: x[:3] for a in arqs if (x := blocos_sem_sigla(self.doc(a), cand))}, {})

    def test_texto_sem_sigla_falha(self):
        """caso negativo: tirar a sigla de Lula de um destaque e dos rótulos do voto dividido dá achado"""
        cand = candidatos(_rel(), _meta22())
        self.assertNotEqual(blocos_sem_sigla(self.doc("destaques.json", ("Lula (PT)", "Lula")), cand), [])
        self.assertNotEqual(blocos_sem_sigla(self.doc("dividido.json", ("Lula (PT)", "Lula")), cand), [])
        self.assertNotEqual(blocos_sem_sigla(self.doc("comparacao2022.json", ("Bolsonaro (PL)", "Bolsonaro")), cand), [])


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


class AoVivoPublicado(unittest.TestCase):
    """o site/ commitado é o que a Vercel publica: o /ao-vivo/ precisa sair com a moldura de consentimento e medição"""

    def test_moldura_de_medicao(self):
        html_ = (R / "site" / "ao-vivo" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="/medicao.js" defer>', html_)
        self.assertIn('<style id="consent-css">', html_)


def candidatos_site():
    """candidatos(rel, meta22) mais os eleitos do Rastro pelo nome de urna completo, de duas palavras ou mais (nome com
    mais de um partido fica de fora). SiteGerado e SitePublicado dividem uma leitura só (issue #148); cada um recebe
    sua cópia"""
    return {sg: list(ns) for sg, ns in _candidatos_site().items()}


@functools.cache
def _candidatos_site():
    out = candidatos(_rel(), _meta22())
    ja = {n for ns in out.values() for n in ns}
    por_nome = {}
    for e in json.loads((R / "rastro" / "dados" / "eleitos.json").read_text())["eleitos"]:
        por_nome.setdefault(e["nome_urna"], set()).add(e["partido"])
    for n, sgs in sorted(por_nome.items()):
        if len(sgs) == 1 and n not in ja and " " in n:  # nome de uma palavra (LEANDRO, BECK) casa dentro de razão social
            out.setdefault(next(iter(sgs)), []).append(n)
    return out


MAIUSC = "A-ZÀ-Ý"


def achados_rastro(doc, cand):
    """blocos_sem_sigla, sem o caso que não é rótulo nosso: o nome de urna dentro de um nome maior (JOSE DIAS DE CASTRO
    NETO não é CASTRO NETO; ORLANDO DE PAULA E SILVA NETO não é SILVA NETO; CARLOS HENRIQUE S. PAJARES; a razão social
    "ELEICAO 2026 FULANO DEPUTADO" é do fornecedor)"""
    out = []
    for b, n in blocos_sem_sigla(doc, cand, corte=None):
        if re.search(rf"(?:[{MAIUSC}0-9]{{2,}}\.?|(?<!\w)E) {re.escape(n)}(?!\w)"
                     rf"|(?<!\w){re.escape(n)} (?:[{MAIUSC}]{{2,}}|[{MAIUSC}]\.? [{MAIUSC}]{{2,}})", b):
            continue
        out.append((b, n))
    return out


REPASSE = re.compile(r"Repassou R\$ [\d.,]+ a ([^,<]+?), que usou")
TIRA_SIGLA = re.compile(r"(Repassou R\$ [\d.,]+ a [^,<]+? · [A-Z]{2}) · [^,<]+,")


class SiteGerado(unittest.TestCase):
    """varredura do Rastro inteiro, gerado agora com o dado de rastro/dados (o site/ commitado só muda com o build, que
    exige o sal do MEI): nenhum bloco de nenhuma página cita eleito sem a sigla (issue #74). O sal aqui é de teste: só
    muda o id do fornecedor MEI, não os rótulos."""

    @classmethod
    def setUpClass(cls):
        from rastro import paginas as rp
        cls.cand = candidatos_site()
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        sal = d / "sal"; sal.write_text("sal-de-teste")
        antes, ler = rp.SAL, rp.ler_sal
        rp.SAL, rp.ler_sal = sal, lambda caminho=sal: ler(caminho)
        try:
            B.rastro_publicar(d / "site", "2026-10-17", "2026-10-17")
        finally:
            rp.SAL, rp.ler_sal = antes, ler
        cls.paginas = {str(a.relative_to(d / "site")): a.read_text(encoding="utf-8") for a in sorted((d / "site").rglob("*.html"))}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_nenhum_rotulo_sem_sigla(self):
        self.maxDiff = None
        self.assertGreater(len(self.paginas), 10)
        achados = {k: a[:3] for k, doc in self.paginas.items() if (a := achados_rastro(doc, self.cand))}
        self.assertEqual(achados, {})

    def test_titulos_indexaveis_unicos(self):
        """issue #149: com o dado real, nenhum <title> se repete entre as páginas do Rastro que indexam (MEI vai de noindex)."""
        titulos = [re.search(r"<title>(.*?)</title>", h).group(1) for h in self.paginas.values()
                   if 'content="noindex,follow' not in h]
        self.assertGreater(len(titulos), 10)
        self.assertEqual(sorted({t for t in titulos if titulos.count(t) > 1}), [])

    def test_no_sem_sigla_falha(self):
        """caso negativo: tirar a sigla do nó da campanha num HTML do Rastro dá achado"""
        no = re.compile(r'(<text [^>]*font-weight:600[^>]*>[^<]+?) · ([A-Z]+)(</text>)')
        doc = next((d for d in self.paginas.values() if no.search(d)), None)
        if doc is None:
            self.skipTest("nenhuma página de eleito com diagrama")
        self.assertEqual(achados_rastro(doc, self.cand), [])
        self.assertNotEqual(achados_rastro(no.sub(r"\1\3", doc, count=1), self.cand), [])

    def test_repasse_com_sigla_do_recebedor(self):
        """issue #78: todo repasse publicado sai "a NOME · UF · SIGLA" (quem recebeu, eleito ou não)"""
        sem = sorted({q for d in self.paginas.values() for q in REPASSE.findall(d) if q.count(" · ") < 2})
        self.assertEqual(sem, [])
        self.assertGreater(sum(len(REPASSE.findall(d)) for d in self.paginas.values()), 100)

    def test_repasse_sem_sigla_falha(self):
        """caso negativo: tirar a sigla do recebedor de um repasse dá achado"""
        doc = next(d for d in self.paginas.values() if TIRA_SIGLA.search(d))
        self.assertNotEqual([q for q in REPASSE.findall(TIRA_SIGLA.sub(r"\1,", doc, count=1)) if q.count(" · ") < 2], [])


@unittest.skipUnless((R / "site" / "index.html").exists(), "site/ não construído (python3 build_site.py)")
class SitePublicado(unittest.TestCase):
    """o site/ commitado é o que a Vercel publica: nenhuma página dele (Resultado final, apuração, Análise, Rastro e
    o resto) cita candidato ou eleito sem a sigla. Pega o site/ que ficou para trás do código (build não rodado)."""

    def test_nenhum_rotulo_sem_sigla(self):
        self.maxDiff = None
        cand = candidatos_site()
        # /debates/ fica de fora: lá o nome vem em fala citada, manchete de fonte e explicação, que não levam sigla
        paginas = sorted(p for p in (R / "site").rglob("*.html") if p.relative_to(R / "site").parts[0] != "debates")
        self.assertGreater(len(paginas), 1000)
        achados = {str(a.relative_to(R / "site")): x[:3] for a in paginas if (x := achados_rastro(a.read_text(encoding="utf-8"), cand))}
        self.assertEqual(achados, {})


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

    def test_analise(self):
        """a Análise montada agora (analise/js e analise/dados do código, não do site/) rodando no Chrome"""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for x in ("vendor", "hud", "geo"):
                (d / x).symlink_to(R / "site" / x)
            B.copiar_analise(d)
            (d / "analise" / "index.html").write_text(B.html_analise(B.analise_dados(), B.ANALISE_GERADA, B.ANALISE_GERADA))
            srv = B.serve(d, port=8796)
            try:
                doc = B.prerender("http://127.0.0.1:8796/analise/")
            finally:
                srv.shutdown(); srv.server_close()
        self.assertIn('id="metodo"', doc)  # o app montou até a última seção
        self.assertEqual(blocos_sem_sigla(doc, candidatos(_rel(), _meta22())), [])

    def test_leitura(self):
        r = next(x for x in B.rodadas if x["slug"] == "84-9")
        doc = self.render(B.html_leitura((R / "template.html").read_text(), r["d"]))
        self.assertIn("Vantagem final de Flávio", doc)  # o script rodou até o fim
        self.assertEqual(blocos_sem_sigla(doc, candidatos(_rel())), [])


if __name__ == "__main__":
    unittest.main()
