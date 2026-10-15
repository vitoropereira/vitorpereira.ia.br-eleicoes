"""Lote diário do Rastro: publica os próximos N eleitos da fila e abre o PR "Rastro: lote AAAA-MM-DD".

Fluxo: trava de data (config.json: trava_inicio..trava_fim, inclusive) -> árvore limpa e branch do dia inexistente ->
branch rastro/lote-AAAA-MM-DD a partir de origin/main -> regenera fila.json -> move os próximos `lote_diario_tamanho` sq
(que não estão em publicados.json) para publicados.json -> build_site.py -> commit só de publicados.json, fila.json e
site/ (o build também muda sitemap.xml e llms.txt) -> python3 -m pytest -q (sobre o conteúdo exato do lote) -> push ->
gh pr create -> gh pr merge --squash se o pytest passou, ou label `bloqueado` (sem merge) se falhou. O merge é a publicação:
é automático, mas só com os testes (LGPD, redação, isolamento) verdes. Sem rede além de `git`, `gh` e do build. `--dry-run` imprime o lote e os comandos sem gravar nada.

Uso: python3 rastro/lote.py [--dry-run]
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI.parent) not in sys.path:
    sys.path.insert(0, str(AQUI.parent))

from rastro import fila as fila_mod  # noqa: E402

# O build reescreve fora de site/rastro/ (sitemap.xml, llms.txt, og/...): tudo em site/ entra no lote,
# senão o PR sai sem as páginas novas no sitemap e a árvore fica suja no dia seguinte.
CAMINHOS_GIT = ["rastro/publicados.json", "rastro/fila.json", "site/"]
TESTES = ["python3", "-m", "pytest", "-q"]
ROTULO_BLOQUEADO = "bloqueado"


def travado(hoje, cfg=None):
    cfg = cfg or json.loads((AQUI / "config.json").read_text(encoding="utf-8"))
    return date.fromisoformat(cfg["trava_inicio"]) <= hoje <= date.fromisoformat(cfg["trava_fim"])


def proximos(fila, publicados, n):
    """Os `n` primeiros da fila que ainda não foram publicados (comparação sempre como string)."""
    ja = {str(s) for s in publicados}
    return [s for s in dict.fromkeys(str(s) for s in fila) if s not in ja][:n]


def aplicar(publicados, novos):
    """Publicados anteriores na mesma ordem, com os novos no fim, sem repetição."""
    return list(dict.fromkeys([str(s) for s in publicados] + [str(s) for s in novos]))


def corpo_pr(novos, eleitos, dia):
    lista = eleitos["eleitos"] if isinstance(eleitos, dict) else eleitos
    por_sq = {str(e["sq"]): e for e in lista}
    linhas = [f"Lote diário do Rastro de {dia}: {len(novos)} eleitos.",
              "A publicação é automática, condicionada aos testes: o merge só acontece se `python3 -m pytest -q` passar; "
              "se falhar, o PR fica aberto com o label `bloqueado` e nada é publicado.", ""]
    for sq in novos:
        e = por_sq.get(sq, {})
        linhas.append(f"- {sq}: {e.get('nome_urna', '?')} ({e.get('cargo', '?')}, {e.get('uf', '?')})")
    return "\n".join(linhas) + "\n"


def main(hoje=None, raiz=AQUI.parent, executar=subprocess.run, dry_run=False):
    hoje = hoje or date.today()
    raiz = Path(raiz)
    cfg_arq = raiz / "rastro" / "config.json"
    if not cfg_arq.exists():
        cfg_arq = AQUI / "config.json"
    cfg = json.loads(cfg_arq.read_text(encoding="utf-8"))
    if travado(hoje, cfg):
        print(f"lote: {hoje} está na trava ({cfg['trava_inicio']} a {cfg['trava_fim']}); nada feito.")
        return 2

    dados, pub_arq, fila_arq = raiz / "rastro" / "dados", raiz / "rastro" / "publicados.json", raiz / "rastro" / "fila.json"
    dia = hoje.isoformat()
    branch, titulo = f"rastro/lote-{dia}", f"Rastro: lote {dia}"

    def rodar(cmd):
        return executar(cmd, cwd=str(raiz), capture_output=True, text=True)

    def desfazer():
        # Volta ao main e descarta a branch do dia (nada foi publicado: o push ou o PR é que publicam).
        rodar(["git", "reset", "--hard"])
        rodar(["git", "clean", "-fd", "--", *CAMINHOS_GIT])  # arquivos novos do build não são desfeitos pelo reset
        rodar(["git", "checkout", "main"])
        rodar(["git", "branch", "-D", branch])

    if not dry_run:
        suja = rodar(["git", "status", "--porcelain"])
        if suja.returncode != 0 or (suja.stdout or "").strip():
            print("lote: árvore de trabalho suja (ou git falhou); nada feito.")
            return 1
        if rodar(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode == 0:
            print(f"lote: a branch {branch} já existe; nada feito.")
            return 1
        # Lote reprovado (label bloqueado) pede conserto humano: não empilha nem duplica PR.
        aberto = rodar(["gh", "pr", "list", "--state", "open", "--label", ROTULO_BLOQUEADO, "--search", "Rastro: lote in:title",
                        "--json", "number", "--jq", "length"])
        if aberto.returncode != 0 or (aberto.stdout or "").strip() not in ("", "0"):
            print(f"lote: há PR de lote aberto com o label {ROTULO_BLOQUEADO} (ou o gh falhou); conserte ou feche antes. Nada feito.")
            return 1
        # A base é o origin/main atualizado, e o lote é calculado sobre ela.
        for c in (["git", "fetch", "origin", "main"], ["git", "checkout", "-b", branch, "origin/main"]):
            if rodar(c).returncode != 0:
                print(f"lote: falhou: {' '.join(c)}")
                return 1

    eleitos_arq, indic_arq = dados / "eleitos.json", dados / "indicadores.json"
    faltam = [p.name for p in (eleitos_arq, indic_arq) if not p.exists()]
    if faltam:
        print(f"lote: faltam {', '.join(faltam)} em {dados}; nada feito.")
        if not dry_run:
            desfazer()
        return 1
    eleitos = json.loads(eleitos_arq.read_text(encoding="utf-8"))
    fila = fila_mod.ordenar(eleitos, json.loads(indic_arq.read_text(encoding="utf-8")))
    publicados = json.loads(pub_arq.read_text(encoding="utf-8")) if pub_arq.exists() else []
    novos = proximos(fila, publicados, cfg["lote_diario_tamanho"])
    if not novos:
        print("lote: nada a publicar (fila esgotada).")
        if not dry_run:
            desfazer()
        return 0

    corpo = corpo_pr(novos, eleitos, dia)
    depois = [
        ["python3", "build_site.py"],
        ["git", "add", *CAMINHOS_GIT],
        ["git", "commit", "-m", titulo],
    ]
    publicar = [
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", titulo, "--body", corpo],
    ]
    merge = ["gh", "pr", "merge", branch, "--squash", "--delete-branch"]
    bloquear = ["gh", "pr", "edit", branch, "--add-label", ROTULO_BLOQUEADO]
    if dry_run:
        print(f"lote (dry-run): {len(novos)} sq: {', '.join(novos)}")
        print(f"  $ git fetch origin main && git checkout -b {branch} origin/main")
        for c in depois + [TESTES, publicar[0]]:
            print("  $ " + " ".join(c))
        print(f"  $ gh pr create --title '{titulo}'")
        print(f"  $ {' '.join(merge)}  # só se o pytest passar; senão: {' '.join(bloquear)}")
        return 0

    if fila_mod.main(dados, fila_arq) != 0:
        desfazer()
        return 1
    pub_arq.write_text(json.dumps(aplicar(publicados, novos), indent=1) + "\n", encoding="utf-8")
    print(f"lote: {len(novos)} sq em {pub_arq}")
    for c in depois:
        r = rodar(c)
        if r.returncode != 0:
            print(f"lote: falhou: {' '.join(c[:4])}\n{(r.stderr or '').strip()}")
            desfazer()
            return 1
    testes = rodar(TESTES)
    aprovado = testes.returncode == 0
    if not aprovado:
        print(f"lote: testes falharam; o PR sai com o label {ROTULO_BLOQUEADO}, sem merge.\n{(testes.stdout or '')[-2000:]}")
    for c in publicar:
        r = rodar(c)
        if r.returncode != 0:
            print(f"lote: falhou: {' '.join(c[:4])}\n{(r.stderr or '').strip()}")
            desfazer()
            return 1
    final = merge if aprovado else bloquear
    r = rodar(final)
    if r.returncode != 0:
        print(f"lote: falhou: {' '.join(final[:4])}\n{(r.stderr or '').strip()}")
        if aprovado:  # merge falhou: marca o PR para a trava do próximo dia não reabrir o mesmo lote
            rodar(bloquear)
        return 1
    if not aprovado:
        return 1
    print(f"lote: {titulo} publicado (testes verdes, merge automático).")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
