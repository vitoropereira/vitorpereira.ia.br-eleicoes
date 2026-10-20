"""Valida debates/<debate>/afirmacoes.json contra a transcricao.md irmã (só biblioteca padrão).

Uso: python3 debates/validar.py debates/2026-10-18-band  → lista os erros (saída 1) ou a contagem (saída 0).

Cada afirmação aponta o timestamp de uma marcação **H:MM:SS** da transcrição e copia o `trecho` literal (com o erro
da legenda) que começa ali; a frase pode seguir pelas próximas marcações, porque a legenda quebra no meio.
A versão limpa vai em `afirmacao`. Extração não leva veredito: isso é da checagem."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

CAMPOS = ("id", "bloco", "tema", "quem", "timestamp", "trecho", "afirmacao", "tipo")
TEMAS = {"seguranca": "seg", "economia": "eco", "social": "soc", "saude": "sau",
         "internacional": "int", "corrupcao": "cor", "outros": "out"}
QUEM = ("flavio", "lula", "mediacao")
TIPOS = ("numero", "fato", "promessa", "acusacao")
BLOCOS = ("1", "2", "3", "finais")
PROIBIDAS = ("veredito", "selo", "checagem", "verdadeiro", "falso")
JANELA = 4  # marcações a partir do timestamp onde o trecho pode estar

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


def validar(itens, transcricao):
    if not isinstance(itens, list):
        return ["o topo de afirmacoes.json tem que ser uma lista"]
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
        for c, ok in (("tema", TEMAS), ("quem", QUEM), ("tipo", TIPOS), ("bloco", BLOCOS)):
            if c in it and it[c] not in ok:
                erros.append(f"{nome}: {c} {it[c]!r} fora de {sorted(ok)}")
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
    itens = json.loads((pasta / "afirmacoes.json").read_text(encoding="utf-8"))
    erros = validar(itens, (pasta / "transcricao.md").read_text(encoding="utf-8"))
    for e in erros:
        print(e, file=sys.stderr)
    if erros:
        return 1
    print(f"{len(itens)} afirmações")
    for campo in ("quem", "bloco", "tema", "tipo"):
        print(f"{campo}: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(i[campo] for i in itens).items())))
    print("quem×tipo: " + ", ".join(f"{q}/{t}={v}" for (q, t), v in
                                     sorted(Counter((i["quem"], i["tipo"]) for i in itens).items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
