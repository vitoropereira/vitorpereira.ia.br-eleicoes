"""Valida debates/<ano>/<slug>/ (debate.json + afirmacoes.json contra a transcricao.md irmã), só biblioteca padrão.

Uso: python3 debates/validar.py debates/2026/presidente-2-turno-band  → lista os erros (saída 1) ou a contagem (saída 0).

Cada afirmação aponta o timestamp de uma marcação **H:MM:SS** da transcrição e copia o `trecho` literal (com o erro
da legenda) que começa ali; a frase pode seguir pelas próximas marcações, porque a legenda quebra no meio.
A versão limpa vai em `afirmacao`. `quem` é o `id` de um candidato do debate.json ou `mediacao`.
Extração não leva veredito: isso é da checagem. Formato e passo a passo: debates/README.md."""
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

CAMPOS = ("id", "bloco", "tema", "quem", "autoria", "timestamp", "trecho", "afirmacao", "tipo", "tese")
TEMAS = {"seguranca": "seg", "economia": "eco", "social": "soc", "saude": "sau",
         "internacional": "int", "corrupcao-acusacoes": "cor", "outros": "out"}
MEDIACAO = "mediacao"
AUTORIAS = ("certa", "incerta")
TIPOS = ("dado", "fato", "promessa", "acusacao")
BLOCOS = ("1", "2", "3", "finais")
PROIBIDAS = ("veredito", "selo", "checagem", "verdadeiro", "falso")
JANELA = 4  # marcações a partir do timestamp onde o trecho pode estar

DEBATE_STR = ("slug", "cargo", "emissora", "data", "fonte_transcricao")
DEBATE_INT = ("ano", "turno")
FONTES = ("youtube-auto", "whisper", "colado")
CANDIDATO = ("id", "nome_urna", "partido")

RE_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_ID = re.compile(r"^[a-z]+-\d{2}$")
RE_TS = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
RE_MARCA = re.compile(r"^\*\*(\d{1,2}:\d{2}(?::\d{2})?)\*\* — (.*)$")
RE_SECAO = re.compile(r"^## (.*)$")


def _norm(s):
    return " ".join(s.split())


def _bloco(secao):
    if secao.startswith("Considerações finais"):
        return "finais"
    m = re.match(r"Bloco (\d)\b", secao)
    return m.group(1) if m else None


def marcacoes(transcricao):
    """[(timestamp, bloco ou None, texto)] na ordem da transcrição."""
    out, bloco = [], None
    for linha in transcricao.splitlines():
        if m := RE_SECAO.match(linha):
            bloco = _bloco(m.group(1))
        elif m := RE_MARCA.match(linha):
            out.append((m.group(1), bloco, m.group(2)))
    return out


def slugificar(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "-".join(re.findall(r"[a-z0-9]+", s))


def _data_iso(s):
    """date de uma string AAAA-MM-DD válida, senão None."""
    if not RE_DATA.match(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def validar_debate(debate):
    """Erros do debate.json: metadados do debate e candidatos com id estável."""
    if not isinstance(debate, dict):
        return ["o topo de debate.json tem que ser um objeto"]
    erros = []
    for c in DEBATE_STR:
        if not isinstance(debate.get(c), str) or not debate[c].strip():
            erros.append(f"debate.json: falta o campo {c!r} (string)")
    for c in DEBATE_INT:
        if type(debate.get(c)) is not int:
            erros.append(f"debate.json: falta o campo {c!r} (inteiro)")
    if isinstance(debate.get("fonte_transcricao"), str) and debate["fonte_transcricao"] not in FONTES:
        erros.append(f"debate.json: fonte_transcricao {debate['fonte_transcricao']!r} fora de {list(FONTES)}")
    if isinstance(debate.get("data"), str):
        d = _data_iso(debate["data"])
        if d is None:
            erros.append(f"debate.json: data {debate['data']!r} não é AAAA-MM-DD")
        elif type(debate.get("ano")) is int and d.year != debate["ano"]:
            erros.append(f"debate.json: ano {debate['ano']} não bate com a data {debate['data']!r}")
    if all(isinstance(debate.get(c), str) for c in ("slug", "cargo", "emissora")) and type(debate.get("turno")) is int:
        esperado = f"{slugificar(debate['cargo'])}-{debate['turno']}-turno-{slugificar(debate['emissora'])}"
        if debate["slug"] != esperado:
            erros.append(f"debate.json: slug {debate['slug']!r} devia ser {esperado!r}")
    cands = debate.get("candidatos")
    if not isinstance(cands, list) or not cands:
        erros.append("debate.json: falta o campo 'candidatos' (lista não vazia)")
        return erros
    vistos = set()
    for n, c in enumerate(cands):
        if not isinstance(c, dict):
            erros.append(f"debate.json: candidato {n} não é objeto")
            continue
        for k in CANDIDATO:
            if not isinstance(c.get(k), str) or not c[k].strip():
                erros.append(f"debate.json: candidato {n} sem {k!r}")
        if "id_tse" in c and not (isinstance(c["id_tse"], str) and c["id_tse"].isdigit()):
            erros.append(f"debate.json: candidato {n} com id_tse {c['id_tse']!r} (string só de dígitos)")
        i = c.get("id")
        if isinstance(i, str):
            if not RE_SLUG.match(i) or i == MEDIACAO:
                erros.append(f"debate.json: id de candidato {i!r} fora do padrão nome-de-urna-partido")
            if i in vistos:
                erros.append(f"debate.json: id de candidato {i!r} repetido")
            vistos.add(i)
    return erros


def validar_pasta(pasta, debate):
    """Erros de lugar: a pasta tem que ser <ano>/<slug> do debate.json."""
    if not isinstance(debate, dict):
        return []
    pasta = Path(pasta).resolve()
    esperado = (str(debate.get("ano")), debate.get("slug"))
    if (pasta.parent.name, pasta.name) != esperado:
        return [f"pasta {pasta.parent.name}/{pasta.name} devia ser {esperado[0]}/{esperado[1]}"]
    return []


def _quem(debate):
    cands = debate.get("candidatos") if isinstance(debate, dict) else None
    ids = {c.get("id") for c in cands if isinstance(c, dict)} if isinstance(cands, list) else set()
    return {i for i in ids if isinstance(i, str)} | {MEDIACAO}


def validar(itens, transcricao, debate):
    if not isinstance(itens, list):
        return ["o topo de afirmacoes.json tem que ser uma lista"]
    quem = _quem(debate)
    marcas = marcacoes(transcricao)
    pos = {}
    for i, (ts, _, _) in enumerate(marcas):
        pos.setdefault(ts, i)
    erros, vistos = [], set()
    for n, it in enumerate(itens):
        if not isinstance(it, dict):
            erros.append(f"item {n}: não é objeto")
            continue
        nome = f"item {n} ({it.get('id')!r})"
        for c in CAMPOS:
            if not isinstance(it.get(c), str):
                erros.append(f"{nome}: falta o campo {c!r} (string)")
        for c in PROIBIDAS:
            if c in it:
                erros.append(f"{nome}: chave de veredito {c!r} não entra na extração")
        for c, ok in (("tema", TEMAS), ("quem", quem), ("autoria", AUTORIAS), ("tipo", TIPOS), ("bloco", BLOCOS)):
            if c in it and (not isinstance(it[c], str) or it[c] not in ok):
                erros.append(f"{nome}: {c} {it[c]!r} fora de {sorted(ok)}")
        if isinstance(it.get("tese"), str) and not RE_SLUG.match(it["tese"]):
            erros.append(f"{nome}: tese {it['tese']!r} não é slug (minúsculas, dígitos e hífen)")
        i = it.get("id")
        if isinstance(i, str):
            if not RE_ID.match(i):
                erros.append(f"{nome}: id fora do padrão tema-NN")
            elif it.get("tema") in TEMAS and not i.startswith(TEMAS[it["tema"]] + "-"):
                erros.append(f"{nome}: id não usa o prefixo do tema {it['tema']!r} ({TEMAS[it['tema']]}-)")
            if i in vistos:
                erros.append(f"{nome}: id duplicado")
            vistos.add(i)
        if isinstance(it.get("afirmacao"), str) and not it["afirmacao"].strip():
            erros.append(f"{nome}: afirmacao vazia")
        ts, trecho = it.get("timestamp"), it.get("trecho")
        if not isinstance(ts, str) or not isinstance(trecho, str):
            continue
        if not RE_TS.match(ts) or ts not in pos:
            erros.append(f"{nome}: timestamp {ts!r} não é marcação da transcrição")
            continue
        k = pos[ts]
        if not _norm(trecho):
            erros.append(f"{nome}: trecho vazio")
        elif _norm(trecho) not in _norm(" ".join(t for _, _, t in marcas[k:k + JANELA])):
            erros.append(f"{nome}: trecho não está na transcrição a partir de {ts}")
        bloco = marcas[k][1]
        if bloco is None:
            erros.append(f"{nome}: {ts} fica fora dos blocos e das considerações finais")
        elif it.get("bloco") in BLOCOS and it["bloco"] != bloco:
            erros.append(f"{nome}: bloco {it['bloco']!r}, mas {ts} está no bloco {bloco!r}")
    return erros


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python3 debates/validar.py <pasta do debate>", file=sys.stderr)
        return 2
    pasta = Path(argv[0])
    try:
        debate = json.loads((pasta / "debate.json").read_text(encoding="utf-8"))
        itens = json.loads((pasta / "afirmacoes.json").read_text(encoding="utf-8"))
        transcricao = (pasta / "transcricao.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        print(f"{pasta}: {e}", file=sys.stderr)
        return 1
    erros = validar_debate(debate) + validar_pasta(pasta, debate) + validar(itens, transcricao, debate)
    for e in erros:
        print(e, file=sys.stderr)
    if erros:
        return 1
    print(f"{len(itens)} afirmações")
    for campo in ("quem", "bloco", "tema", "tipo", "autoria"):
        print(f"{campo}: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(i[campo] for i in itens).items())))
    for a, b in (("quem", "tipo"), ("quem", "autoria")):
        print(f"{a}×{b}: " + ", ".join(f"{x}/{y}={v}" for (x, y), v in
                                        sorted(Counter((i[a], i[b]) for i in itens).items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
