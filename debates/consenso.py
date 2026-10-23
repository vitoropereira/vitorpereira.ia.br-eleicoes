"""Consenso entre classificadores de um debate (checagem e retórica), só biblioteca padrão. Procedimento: debates/README.md, seções 6 e 8.

Uso:
  python3 debates/consenso.py cego-checagem <pasta> [--de pesquisa/]     → itens cegos da checagem na saída padrão
  python3 debates/consenso.py checagem <votos...> [--cego cego.json]      → decididos, divergências e refazer
  python3 debates/consenso.py retorica <votos...> --cego cego.json        → idem, divergências no formato cego
  python3 debates/consenso.py aplicar <decididos.json> <juiz...> [--pasta <pasta> [--falas falas.json]] → {id: categoria}

Cada arquivo de voto é [{id, etiqueta ou categoria, confianca, motivo}] ou {id: etiqueta}. Na checagem, um voto com
`checou_coisa_certa: false` põe o id em `refazer`. Os relatórios (concordância, contagens) saem no stderr.
Quem classifica só vê a entrada cega: nem `quem`, nem o debate.json, nem veredito."""
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from debates import retorica as R
from debates import validar as V

ESCALAS = {"checagem": V.VEREDITO, "retorica": V.ETIQUETAS + (R.FORA,)}
CHAVES_ROTULO = ("etiqueta", "categoria", "veredito")
CHAVES_VEREDITO = ("veredito", "veredito_sugerido")
COMO = ("unanime", "maioria", "juiz", "regra")


def _ler(caminho):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def normalizar_votos(voto, escala):
    """{id: rótulo} de um voto em lista [{id, etiqueta|categoria, ...}] ou em dict {id: etiqueta}. Rótulo fora da
    escala levanta ValueError com o id e o valor."""
    if isinstance(voto, dict):
        pares = list(voto.items())
    else:
        pares = []
        for item in voto:
            rotulo = next((item[k] for k in CHAVES_ROTULO if k in item), None)
            pares.append((item.get("id"), rotulo))
    out = {}
    for i, r in pares:
        if r not in escala:
            raise ValueError(f"{i!r}: rótulo {r!r} fora de {list(escala)}")
        out[i] = r
    return out


def refazer(votos_brutos):
    """ids que algum voto marcou com `checou_coisa_certa: false` (o classificador não achou a coisa certa)."""
    return sorted({i["id"] for v in votos_brutos if isinstance(v, list) for i in v if i.get("checou_coisa_certa") is False})


def decidir(votos, escala=None, ids=None, primeiros_iguais=True):
    """(decididos, como, divergentes). `unanime`: todos iguais. `maioria`: mais da metade e, com primeiros_iguais,
    os dois primeiros votos entre eles. O resto, ou id faltando num voto, diverge: {id: [rótulos votados]}.
    `ids` é a referência (o cego): id de voto fora dela levanta ValueError."""
    votos = [normalizar_votos(v, escala) if escala else v for v in votos]
    vistos = set().union(*votos) if votos else set()
    if ids is not None and (extra := vistos - set(ids)):
        raise ValueError(f"id fora da referência: {sorted(extra)}")
    decididos, como, divergentes = {}, {}, {}
    for i in sorted(ids if ids is not None else vistos):
        dados = [v[i] for v in votos if i in v]
        conta = Counter(dados)
        rotulo, n = conta.most_common(1)[0] if conta else (None, 0)
        if len(dados) == len(votos) and n == len(votos):
            decididos[i], como[i] = rotulo, "unanime"
        elif len(dados) == len(votos) and n > len(votos) / 2 and (not primeiros_iguais or dados[0] == dados[1]):
            decididos[i], como[i] = rotulo, "maioria"
        else:
            divergentes[i] = dados
    return decididos, como, divergentes


def divergencias_retorica(div_ids, cego):
    """Itens da entrada cega {id, anterior, frase, seguinte} dos ids em divergência (só {id} se o id não está no cego)."""
    por_id = {c["id"]: c for c in cego}
    return [por_id.get(i, {"id": i}) for i in sorted(div_ids)]


def concordancia(votos):
    """(total de pares de votos sobre o mesmo id, pares que concordam, %)."""
    total = ok = 0
    for a, b in combinations(votos, 2):
        for i in set(a) & set(b):
            total += 1
            ok += a[i] == b[i]
    return total, ok, (100 * ok / total if total else 100.0)


def aplicar(saida, juizes, modo=None):
    """(final {id: rótulo}, como {id: unanime|maioria|juiz|regra}). Juízes de acordo decidem; juízes divergentes ou
    ausentes caem na regra: nao-comprovado na checagem; na retórica, o primeiro de V.ETIQUETAS entre os rótulos votados
    (`fora` só se for o único). Voto de juiz em id que não divergiu levanta ValueError."""
    modo = modo or saida["modo"]
    escala = ESCALAS[modo]
    div = {(d if isinstance(d, str) else d["id"]) for d in saida.get("divergencias", [])}
    votos_div = saida.get("votos", {})
    juizes = [normalizar_votos(j, escala) for j in juizes]
    if extra := set().union(*juizes) - div if juizes else set():
        raise ValueError(f"juiz votou em id sem divergência: {sorted(extra)}")
    final, como = dict(saida["decididos"]), dict(saida["como"])
    for i in sorted(div):
        dos_juizes = [j[i] for j in juizes if i in j]
        if dos_juizes and len(set(dos_juizes)) == 1:
            final[i], como[i] = dos_juizes[0], "juiz"
            continue
        votados = set(votos_div.get(i, [])) | set(dos_juizes)
        if modo == "checagem":
            final[i] = "nao-comprovado"
        else:
            final[i] = next((e for e in V.ETIQUETAS if e in votados), R.FORA)
        como[i] = "regra"
    return final, como


def _contexto(marcas, ts):
    pos = next((k for k, m in enumerate(marcas) if m[0] == ts), None)
    if pos is None:
        return ""
    return " ".join(m[2] for m in marcas[max(pos - 1, 0):pos + 2])


def _checagens_de(pasta, de):
    itens = []
    arquivos = sorted(Path(de).glob("*.json")) if de else [Path(pasta) / "checagens.json"]
    for a in arquivos:
        if a.exists():
            dados = _ler(a)
            itens += dados if isinstance(dados, list) else [dados]
    return {i["id"]: i for i in itens if isinstance(i, dict) and "id" in i}


def cego_checagem(pasta, de=None):
    """[{id, tipo, afirmacao, trecho, contexto, explicacao, fontes}] das afirmações `certa` de candidato. Sem quem,
    veredito nem nome: contexto é a marcação da afirmação com a anterior e a seguinte na transcrição."""
    debate, transcricao = R._ler(pasta)
    marcas = V.marcacoes(transcricao)
    cands = V._quem(debate) - {V.MEDIACAO}
    base = _checagens_de(pasta, de)
    out = []
    for a in _ler(Path(pasta) / "afirmacoes.json"):
        if a.get("autoria") != "certa" or a.get("quem") not in cands:
            continue
        c = base.get(a["id"], {})
        out.append({"id": a["id"], "tipo": a["tipo"], "afirmacao": a["afirmacao"], "trecho": a["trecho"],
                    "contexto": _contexto(marcas, a["timestamp"]), "explicacao": c.get("explicacao", ""),
                    "fontes": c.get("fontes", [])})
    return out


def relatorio(como, votos=None):
    linhas = []
    if votos is not None:
        total, ok, pct = concordancia(votos)
        linhas.append(f"concordância: {ok}/{total} pares de votos ({pct:.1f}%)")
    conta = Counter(como.values())
    linhas.append("; ".join(f"{k}: {conta.get(k, 0)}" for k in COMO))
    return linhas


def _opcao(argv, nome):
    """(argv sem a opção, valor ou None)."""
    if nome not in argv:
        return argv, None
    k = argv.index(nome)
    if k + 1 >= len(argv):
        raise ValueError(f"{nome} sem valor")
    return argv[:k] + argv[k + 2:], argv[k + 1]


def _quem_dos_ids(modo, pasta, falas):
    if modo == "checagem":
        return {a["id"]: a.get("quem") for a in _ler(Path(pasta) / "afirmacoes.json")}
    if falas is None:
        return None
    return {f["id"]: f["quem"] for f in R.frases(pasta, _ler(falas))}


def _consenso(modo, args, cego_arq):
    brutos = [_ler(a) for a in args]
    cego = _ler(cego_arq) if cego_arq else []
    votos = [normalizar_votos(v, ESCALAS[modo]) for v in brutos]
    ids = [c["id"] for c in cego] if cego else None
    decididos, como, div = decidir(votos, ids=ids)
    saida = {"modo": modo, "decididos": decididos, "como": como,
             "divergencias": divergencias_retorica(div, cego), "votos": div, "refazer": refazer(brutos)}
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    for linha in relatorio(como, votos):
        print(linha, file=sys.stderr)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) >= 2 and argv[0] == "cego-checagem":
            resto, de = _opcao(argv[1:], "--de")
            if len(resto) != 1:
                raise ValueError("uso")
            print(json.dumps(cego_checagem(resto[0], de), ensure_ascii=False, indent=1))
            return 0
        if len(argv) >= 2 and argv[0] in ("checagem", "retorica"):
            resto, cego = _opcao(argv[1:], "--cego")
            if not resto or (argv[0] == "retorica" and cego is None):
                raise ValueError("uso")
            return _consenso(argv[0], resto, cego)
        if len(argv) >= 3 and argv[0] == "aplicar":
            resto, falas = _opcao(argv[1:], "--falas")
            resto, pasta = _opcao(resto, "--pasta")
            if len(resto) < 2 or (falas and not pasta):
                raise ValueError("uso")
            saida = _ler(resto[0])
            final, como = aplicar(saida, [_ler(j) for j in resto[1:]])
            print(json.dumps(final, ensure_ascii=False, indent=1))
            for linha in relatorio(como):
                print(linha, file=sys.stderr)
            if saida.get("refazer"):
                print(f"refazer: {', '.join(saida['refazer'])}", file=sys.stderr)
            quem = _quem_dos_ids(saida["modo"], pasta, falas) if pasta else None
            if quem:
                div = Counter(quem.get(i, "?") for i, c in como.items() if c in ("juiz", "regra"))
                print("divergências por quem: " + "; ".join(f"{q}: {n}" for q, n in sorted(div.items())), file=sys.stderr)
            return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        if str(e) != "uso":
            print(f"erro: {e}", file=sys.stderr)
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
