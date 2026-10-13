"""Fila do Rastro: grava rastro/fila.json, lista JSON pura de sq (str) na ordem de publicação.

Ordem (a mesma do lote 1): cargo (ordem de paginas.CARGOS), votos em ordem decrescente, número de indicadores em ordem
decrescente. A fila inclui os já publicados; quem filtra é rastro/lote.py, por publicados.json. Sem rede.
Sai com 1, sem gravar, se faltar rastro/dados/eleitos.json ou indicadores.json.

Uso: python3 rastro/fila.py
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI.parent) not in sys.path:
    sys.path.insert(0, str(AQUI.parent))

from rastro.paginas import CARGOS  # noqa: E402


def chave_prioridade(indicadores):
    """Chave de ordenação para `sorted` sobre eleitos."""
    por_ind = (indicadores or {}).get("indicadores") or {}
    ordem = list(CARGOS)

    def chave(e):
        return (ordem.index(e["cargo"]) if e["cargo"] in ordem else len(ordem), -(e.get("votos") or 0),
                -len(por_ind.get(str(e["sq"])) or []), str(e["sq"]))

    return chave


def ordenar(eleitos, indicadores):
    """Lista de sq (str) em ordem de prioridade, sem repetição."""
    lista = eleitos["eleitos"] if isinstance(eleitos, dict) else eleitos
    return list(dict.fromkeys(str(e["sq"]) for e in sorted(lista, key=chave_prioridade(indicadores))))


def main(dados=AQUI / "dados", destino=AQUI / "fila.json"):
    eleitos, indic = Path(dados) / "eleitos.json", Path(dados) / "indicadores.json"
    faltam = [p.name for p in (eleitos, indic) if not p.exists()]
    if faltam:
        print(f"fila: faltam {', '.join(faltam)} em {dados}; nada gravado.")
        return 1
    sqs = ordenar(json.loads(eleitos.read_text(encoding="utf-8")), json.loads(indic.read_text(encoding="utf-8")))
    Path(destino).write_text(json.dumps(sqs, indent=1) + "\n", encoding="utf-8")
    print(f"fila: {len(sqs)} sq gravados em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
