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
CORES = ("flavio", "lula", "outros")  # variáveis de partido do brand.css; `cor` do candidato é opcional (padrão outros)

VEREDITO_FATO = ("verdadeiro", "verdadeiro-com-ressalva", "exagerado", "falso", "sem-evidencia", "nao-checavel")
VEREDITOS = {"dado": VEREDITO_FATO, "fato": VEREDITO_FATO,
             "promessa": ("ja-existe", "viavel", "depende-do-congresso", "sem-custo-estimado", "inviavel"),
             "acusacao": ("ha-investigacao", "ha-denuncia", "ha-condenacao", "sem-registro-publico")}
CHECAGEM = ("id", "veredito", "explicacao", "atualizado_em")
FONTE = ("url", "titulo", "orgao", "data_publicacao", "acessado_em")
FRASES = (2, 4)

RE_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_ANO_MES = re.compile(r"^\d{4}(-\d{2})?$")
RE_ID = re.compile(r"^[a-z]+-\d{2}$")
RE_TS = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
RE_MARCA = re.compile(r"^\*\*(\d{1,2}:\d{2}(?::\d{2})?)\*\* — (.*)$")
RE_SECAO = re.compile(r"^## (.*)$")
# vídeo de onde saiu a transcrição: os tempos das afirmações viram link para o mesmo segundo nele
RE_VIDEO = re.compile(r"^https://(www\.youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}$")


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


def _data_parcial(s):
    """Primeiro dia de AAAA, AAAA-MM ou AAAA-MM-DD (publicação que só tem ano ou mês), senão None."""
    if RE_ANO_MES.match(s):
        s += "-01-01" if len(s) == 4 else "-01"
    return _data_iso(s)


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
    if "publicado_em" in debate and (not isinstance(debate["publicado_em"], str) or _data_iso(debate["publicado_em"]) is None):
        erros.append(f"debate.json: publicado_em {debate['publicado_em']!r} não é AAAA-MM-DD")
    if "video" in debate and not (isinstance(debate["video"], str) and RE_VIDEO.match(debate["video"])):
        erros.append(f"debate.json: video {debate['video']!r} não é https://www.youtube.com/watch?v=<id> nem https://youtu.be/<id>")
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
        if "cor" in c and c["cor"] not in CORES:
            erros.append(f"debate.json: candidato {n} com cor {c['cor']!r} fora de {list(CORES)}")
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


def _frases(s):
    return len([f for f in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú0-9\"“(])", s.strip()) if f])


def validar_checagens(checagens, itens, hoje=None):
    """Erros do checagens.json: um veredito por afirmação `certa`, na escala do `tipo` dela, com fonte."""
    if not isinstance(checagens, list):
        return ["o topo de checagens.json tem que ser uma lista"]
    hoje = hoje or date.today()
    por_id = {i["id"]: i for i in itens if isinstance(i, dict) and isinstance(i.get("id"), str)} \
        if isinstance(itens, list) else {}
    erros, vistos = [], set()

    def data(nome, campo, v, parcial=False):
        d = (_data_parcial if parcial else _data_iso)(v) if isinstance(v, str) else None
        if d is None:
            erros.append(f"{nome}: {campo} {v!r} não é {'AAAA, AAAA-MM ou ' if parcial else ''}AAAA-MM-DD")
        elif d > hoje:
            erros.append(f"{nome}: {campo} {v!r} é depois de hoje")

    for n, ch in enumerate(checagens):
        if not isinstance(ch, dict):
            erros.append(f"checagem {n}: não é objeto")
            continue
        nome = f"checagem {n} ({ch.get('id')!r})"
        for c in CHECAGEM:
            if not isinstance(ch.get(c), str) or not ch[c].strip():
                erros.append(f"{nome}: falta o campo {c!r} (string não vazia)")
        if "outro_lado" in ch and (not isinstance(ch["outro_lado"], str) or not ch["outro_lado"].strip()):
            erros.append(f"{nome}: outro_lado, quando existe, é string não vazia")
        i = ch.get("id")
        it = por_id.get(i) if isinstance(i, str) else None
        if isinstance(i, str):
            if i in vistos:
                erros.append(f"{nome}: id duplicado")
            vistos.add(i)
            if it is None:
                erros.append(f"{nome}: não há afirmação com esse id")
            elif it.get("autoria") != "certa":
                erros.append(f"{nome}: afirmação de autoria {it.get('autoria')!r} não se checa")
        if it is not None and isinstance(ch.get("veredito"), str):
            ok = VEREDITOS.get(it.get("tipo"), ())
            if ch["veredito"] not in ok:
                erros.append(f"{nome}: veredito {ch['veredito']!r} fora de {list(ok)} (tipo {it.get('tipo')!r})")
        if isinstance(ch.get("explicacao"), str) and ch["explicacao"].strip():
            k = _frases(ch["explicacao"])
            if not FRASES[0] <= k <= FRASES[1]:
                erros.append(f"{nome}: explicacao com {k} frases (de {FRASES[0]} a {FRASES[1]})")
        if isinstance(ch.get("atualizado_em"), str) and ch["atualizado_em"].strip():
            data(nome, "atualizado_em", ch["atualizado_em"])
        fontes = ch.get("fontes")
        if not isinstance(fontes, list) or not fontes:
            erros.append(f"{nome}: falta 'fontes' (lista não vazia, mesmo em sem-evidencia e nao-checavel)")
            continue
        for k, f in enumerate(fontes):
            fn = f"{nome} fonte {k}"
            if not isinstance(f, dict):
                erros.append(f"{fn}: não é objeto")
                continue
            for c in FONTE:
                if not isinstance(f.get(c), str) or not f[c].strip():
                    erros.append(f"{fn}: falta o campo {c!r} (string não vazia)")
            if isinstance(f.get("url"), str) and not f["url"].startswith("https://"):
                erros.append(f"{fn}: url {f['url']!r} não começa com https://")
            for c in ("data_publicacao", "acessado_em"):
                if isinstance(f.get(c), str) and f[c].strip():
                    data(fn, c, f[c], parcial=c == "data_publicacao")
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
        checagens = None
        if (pasta / "checagens.json").exists():
            checagens = json.loads((pasta / "checagens.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"{pasta}: {e}", file=sys.stderr)
        return 1
    erros = validar_debate(debate) + validar_pasta(pasta, debate) + validar(itens, transcricao, debate)
    if checagens is not None:
        erros += validar_checagens(checagens, itens)
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
    if checagens is not None:
        print(f"{len(checagens)} checagens: " + ", ".join(
            f"{k}={v}" for k, v in sorted(Counter(c["veredito"] for c in checagens).items())))
        quem = {i["id"]: i["quem"] for i in itens}
        print("quem×veredito: " + ", ".join(f"{x}/{y}={v}" for (x, y), v in
                                             sorted(Counter((quem[c["id"]], c["veredito"]) for c in checagens).items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
