"""Navegação do site: o nome de cada seção e a trilha (breadcrumb), num lugar só (issue 145).

O mesmo nome aparece no menu (build_site.secoes), na trilha e no título da seção; build_site, debates/pagina.py e
rastro/paginas.py importam daqui em vez de escrever o rótulo à mão."""
import html

INICIO = "Início"
AO_VIVO = "Ao vivo"
ESTUDO_2T = "A virada do 2º turno"
DEBATES = "Debates"
ANALISE = "Análise"
MINHA_SECAO = "Minha seção"
RASTRO = "Rastro do dinheiro"
APURACAO = "Histórico da apuração"
METODO = "Método e fontes"
RESULTADO_1T = "Resultado do 1º turno"

# Ordem dos candidatos do 2º turno em todo o site (issue 150): a da votação no 1º turno, Flávio Bolsonaro (PL) 47,0%
# e Lula (PT) 45,2%. Home, Debates e Rastro ordenam por aqui; quem não está na lista (ex.: a mediação) vai para o fim.
ORDEM_PARTIDOS = ("PL", "PT")


def ordem_candidatos(itens, partido=lambda c: c.get("partido")):
    """itens na ordem de ORDEM_PARTIDOS (estável: empates e partidos fora da lista mantêm a ordem de entrada)."""
    pos = {p: i for i, p in enumerate(ORDEM_PARTIDOS)}
    return sorted(itens, key=lambda c: pos.get(partido(c), len(pos)))


def trilha(*passos):
    """passos: (rótulo, href|None); o último, sem link. Um componente só para todas as seções (estilo em build_site.SITE_CSS)."""
    return ('<nav class="crumbs" aria-label="Trilha">'
            + " › ".join(f'<a href="{html.escape(h, quote=True)}">{html.escape(r)}</a>' if h else html.escape(r)
                         for r, h in passos) + "</nav>")
