"""Lote 1 do Rastro: escolhe uma única vez os `lote_tamanho` primeiros eleitos e grava rastro/publicados.json.

Ordem (a mesma da Issue 9b): cargo (ordem de paginas.CARGOS), votos em ordem decrescente, número de indicadores
em ordem decrescente. Não grava nada (e sai com mensagem) se rastro/dados/fornecedores.json ou indicadores.json
não existirem: sem eles `paginas.gerar` se recusa a publicar. Sem rede.

Uso: python3 rastro/lote1.py
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI.parent) not in sys.path:
    sys.path.insert(0, str(AQUI.parent))

from rastro.fila import ordenar  # noqa: E402


def escolher(eleitos, indicadores, tamanho):
    """Lista de sq (str) dos `tamanho` primeiros, sem repetição."""
    return ordenar(eleitos, indicadores)[:tamanho]


def main(dados=AQUI / "dados", destino=AQUI / "publicados.json", config=AQUI / "config.json"):
    forn, indic, eleitos = dados / "fornecedores.json", dados / "indicadores.json", dados / "eleitos.json"
    faltam = [p.name for p in (eleitos, forn, indic) if not p.exists()]
    if faltam:
        print(f"lote1: faltam {', '.join(faltam)} em {dados}; nada gravado. Rode rastro/cnpj.py --baixar e rastro/indicadores.py antes.")
        return 1
    if Path(destino).exists() and Path(destino).read_text(encoding="utf-8").strip() not in ("", "[]"):
        print(f"lote1: {destino} já tem publicados; uso único, nada gravado (apague o arquivo para refazer).")
        return 1
    cfg = json.loads(Path(config).read_text(encoding="utf-8"))
    sqs = escolher(json.loads(eleitos.read_text(encoding="utf-8")), json.loads(indic.read_text(encoding="utf-8")), cfg["lote_tamanho"])
    Path(destino).write_text(json.dumps(sqs, indent=1) + "\n", encoding="utf-8")
    print(f"lote1: {len(sqs)} sq gravados em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
