"""Navegação do site: o nome de cada seção e a trilha (breadcrumb), num lugar só (issue 145).

O mesmo nome aparece no menu (build_site.secoes), na trilha e no título da seção; build_site, debates/pagina.py e
rastro/paginas.py importam daqui em vez de escrever o rótulo à mão."""
import html

INICIO = "Início"
AO_VIVO = "Ao vivo"
DEBATES = "Debates"
ANALISE = "Análise"
MINHA_SECAO = "Minha seção"
RASTRO = "Rastro do dinheiro"
APURACAO = "Histórico da apuração"
METODO = "Método e fontes"


def trilha(*passos):
    """passos: (rótulo, href|None); o último, sem link. Um componente só para todas as seções (estilo em build_site.SITE_CSS)."""
    return ('<nav class="crumbs" aria-label="Trilha">'
            + " › ".join(f'<a href="{html.escape(h, quote=True)}">{html.escape(r)}</a>' if h else html.escape(r)
                         for r, h in passos) + "</nav>")
