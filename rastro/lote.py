"""Lote diário do Rastro: publica os próximos N eleitos da fila e abre o PR "Rastro: lote AAAA-MM-DD".

Fluxo: trava de data (config.json: trava_inicio..trava_fim, inclusive) -> árvore limpa e branch do dia inexistente ->
branch rastro/lote-AAAA-MM-DD a partir de origin/main -> regenera fila.json -> move os próximos `lote_diario_tamanho` sq
(que não estão em publicados.json) para publicados.json -> build_site.py -> commit só de publicados.json, fila.json e
site/rastro/ -> push -> gh pr create. Nunca faz merge nem deploy: o merge do PR pelo Vitor é a publicação.
Sem rede além de `git push` e `gh`. `--dry-run` imprime o lote e os comandos sem gravar nada.

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

CAMINHOS_GIT = ["rastro/publicados.json", "rastro/fila.json", "site/rastro/"]


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
    linhas = [f"Lote diário do Rastro de {dia}: {len(novos)} eleitos. O merge deste PR é a publicação.", ""]
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
    eleitos_arq, indic_arq = dados / "eleitos.json", dados / "indicadores.json"
    faltam = [p.name for p in (eleitos_arq, indic_arq) if not p.exists()]
    if faltam:
        print(f"lote: faltam {', '.join(faltam)} em {dados}; nada feito.")
        return 1
    eleitos = json.loads(eleitos_arq.read_text(encoding="utf-8"))
    fila = fila_mod.ordenar(eleitos, json.loads(indic_arq.read_text(encoding="utf-8")))
    publicados = json.loads(pub_arq.read_text(encoding="utf-8")) if pub_arq.exists() else []
    novos = proximos(fila, publicados, cfg["lote_diario_tamanho"])
    if not novos:
        print("lote: nada a publicar (fila esgotada).")
        return 0

    dia = hoje.isoformat()
    branch, titulo = f"rastro/lote-{dia}", f"Rastro: lote {dia}"
    corpo = corpo_pr(novos, eleitos, dia)
    comandos = [
        ["git", "fetch", "origin", "main"],
        ["git", "checkout", "-b", branch, "origin/main"],
        ["python3", "build_site.py"],
        ["git", "add", *CAMINHOS_GIT],
        ["git", "commit", "-m", titulo],
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", titulo, "--body", corpo],
    ]
    if dry_run:
        print(f"lote (dry-run): {len(novos)} sq: {', '.join(novos)}")
        for c in comandos:
            print("  $ " + " ".join(c[:8] if c[0] != "gh" else c[:7]))
        return 0

    def rodar(cmd):
        return executar(cmd, cwd=str(raiz), capture_output=True, text=True)

    suja = rodar(["git", "status", "--porcelain"])
    if suja.returncode != 0 or (suja.stdout or "").strip():
        print("lote: árvore de trabalho suja (ou git falhou); nada feito.")
        return 1
    if rodar(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode == 0:
        print(f"lote: a branch {branch} já existe; nada feito.")
        return 1

    # Os dois primeiros comandos antes de gravar: a base é o origin/main atualizado.
    for c in comandos[:2]:
        if rodar(c).returncode != 0:
            print(f"lote: falhou: {' '.join(c)}")
            return 1
    if fila_mod.main(dados, fila_arq) != 0:
        return 1
    pub_arq.write_text(json.dumps(aplicar(publicados, novos), indent=1) + "\n", encoding="utf-8")
    print(f"lote: {len(novos)} sq em {pub_arq}")
    for c in comandos[2:]:
        r = rodar(c)
        if r.returncode != 0:
            print(f"lote: falhou: {' '.join(c[:6])}\n{(r.stderr or '').strip()}")
            return 1
    print(f"lote: PR aberto ({titulo}). Merge fica com o Vitor.")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
