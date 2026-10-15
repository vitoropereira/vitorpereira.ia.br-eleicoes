"""HTML do relatório final: template_relatorio.html + dados (usado por montar.py e pelos testes)."""
import json
from pathlib import Path
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand

META_2022 = Path(__file__).resolve().parent.parent / "municipios" / "geo" / "t2022" / "meta.json"


def siglas_2022():
    """{nome: sigla} dos candidatos a presidente no 1º turno de 2022 (dado do TSE)"""
    return {c["nome"]: c["sg"] for c in json.loads(META_2022.read_text())["cand"]["presidente-1t"]}


def html_relatorio(tpl, data, sg22):
    """`sg22` vai só para o HTML (chave sg22 em D), nunca para o relatorio.json"""
    return brand.aplicar(tpl.replace("/*__DATA__*/null", json.dumps({**data, "sg22": sg22}, ensure_ascii=False)))
