"""Etiquetagem cega da retórica de um debate (retorica.json), só biblioteca padrão. Formato e regra: debates/README.md, seção 8.

Uso:
  python3 debates/retorica.py cego <pasta> <falas.json>                  → lista cega [{id, anterior, frase, seguinte}] na saída padrão
  python3 debates/retorica.py juntar <pasta> <falas.json> <etiquetas.json> → grava <pasta>/retorica.json

falas.json diz quem fala em cada trecho: [{"inicio": "H:MM:SS", "fim": "H:MM:SS", "quem": id, "autoria": "certa"}],
com início e fim sendo marcações da transcrição (fim incluído). Trecho `incerta` e a mediação ficam de fora.
etiquetas.json é {id: etiqueta ou "fora"} sobre a lista cega; "fora" (cumprimento, "obrigado", pergunta de regra) sai.
Quem etiqueta só vê a lista cega: nem `quem`, nem o debate.json."""
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from debates import validar as V

FORA = "fora"
RE_FIM = re.compile(r"[.!?…][\"”)]*$")


def _ler(pasta):
    pasta = Path(pasta)
    debate = json.loads((pasta / "debate.json").read_text(encoding="utf-8"))
    return debate, (pasta / "transcricao.md").read_text(encoding="utf-8")


def frases(pasta, autoria):
    """[{id, timestamp, quem, frase}] dos trechos `certa` de candidato, quebrados em sentenças. A frase termina na
    pontuação ou antes de passar de JANELA marcações (legenda sem pontuação), para caber na checagem do validador."""
    debate, transcricao = _ler(pasta)
    marcas = V.marcacoes(transcricao)
    pos = {}
    for i, (ts, _, _) in enumerate(marcas):
        pos.setdefault(ts, i)
    cands = V._quem(debate) - {V.MEDIACAO}
    out = []
    for t in autoria:
        if t.get("autoria") != "certa" or t.get("quem") not in cands:
            continue
        if t.get("inicio") not in pos or t.get("fim") not in pos or pos[t["fim"]] < pos[t["inicio"]]:
            raise ValueError(f"trecho {t!r}: início e fim têm que ser marcações da transcrição, em ordem")
        palavras = [(p, k) for k in range(pos[t["inicio"]], pos[t["fim"]] + 1) for p in marcas[k][2].split()]
        atual, ini = [], None
        for j, (p, k) in enumerate(palavras):
            if ini is None:
                ini = k
            atual.append(p)
            prox = palavras[j + 1][1] if j + 1 < len(palavras) else None
            if prox is None or RE_FIM.search(p) or prox >= ini + V.JANELA:
                out.append({"timestamp": marcas[ini][0], "quem": t["quem"], "frase": " ".join(atual)})
                atual, ini = [], None
    return [{"id": f"r-{n:04d}", **f} for n, f in enumerate(out, 1)]


def cego(fs):
    """id, a frase e as vizinhas na lista (vazias nas pontas): o que o etiquetador recebe. Nada de quem falou."""
    return [{"id": f["id"], "anterior": fs[i - 1]["frase"] if i else "", "frase": f["frase"],
             "seguinte": fs[i + 1]["frase"] if i + 1 < len(fs) else ""} for i, f in enumerate(fs)]


def juntar(fs, etiquetas):
    """retorica.json: cada frase com a etiqueta dela; "fora" sai. Id desconhecido, faltando ou etiqueta inválida
    levanta ValueError."""
    ids = {f["id"] for f in fs}
    erros = [f"etiqueta para id desconhecido {i!r}" for i in sorted(set(etiquetas) - ids)]
    erros += [f"falta etiqueta para {i!r}" for i in sorted(ids - set(etiquetas))]
    erros += [f"{i!r}: etiqueta {e!r} fora de {list(V.ETIQUETAS) + [FORA]}" for i, e in sorted(etiquetas.items())
              if i in ids and e not in V.ETIQUETAS and e != FORA]
    if erros:
        raise ValueError("; ".join(erros))
    return [{**f, "etiqueta": etiquetas[f["id"]]} for f in fs if etiquetas[f["id"]] != FORA]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 3 and argv[0] == "cego":
        fs = frases(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(json.dumps(cego(fs), ensure_ascii=False, indent=1))
        return 0
    if len(argv) == 4 and argv[0] == "juntar":
        fs = frases(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        rt = juntar(fs, json.loads(Path(argv[3]).read_text(encoding="utf-8")))
        (Path(argv[1]) / "retorica.json").write_text(json.dumps(rt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(rt)} frases em {Path(argv[1]) / 'retorica.json'}")
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
