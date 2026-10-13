#!/usr/bin/env python3
"""Base CNPJ da Receita, só dos fornecedores PJ dos eleitos: lê os ZIPs (em streaming, sem extrair) e grava
rastro/dados/fornecedores.json. Sócio só com o CPF mascarado que a Receita já publica.
Uso: python3 -m rastro.cnpj --baixar [--mes AAAA-MM]  (baixa um ZIP por vez, processa e apaga)
     python3 -m rastro.cnpj --mes AAAA-MM             (só processa os ZIPs já em rastro/brutos/cnpj/<mes>/)"""
import argparse
import base64
import contextlib
import csv
import http.client
import io
import json
import logging
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from rastro import baixar
    from rastro.contas import SAIDA_CONTAS, cpf_valido, digitos, gravar, limpar_texto
except ImportError:  # rodado como script: python3 rastro/cnpj.py
    import baixar
    from contas import SAIDA_CONTAS, cpf_valido, digitos, gravar, limpar_texto

log = logging.getLogger("rastro.cnpj")
AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "dados" / "fornecedores.json"
# compartilhamento Nextcloud público da Receita, via WebDAV: usuário = token do compartilhamento, senha vazia
WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav"
TOKEN = "YggdBLfdninEJX9"
# página pública do compartilhamento; indicadores.py deriva dela o link de fonte mostrado ao leitor
BASE_CNPJ = f"https://arquivos.receitafederal.gov.br/index.php/s/{TOKEN}/download"
RE_MES = r"\d{4}-(0[1-9]|1[0-2])"
RETENTATIVAS = 3
PARTES = 10  # Empresas0..9, Estabelecimentos0..9, Socios0..9
SITUACAO = {"01": "NULA", "02": "ATIVA", "03": "SUSPENSA", "04": "INAPTA", "08": "BAIXADA"}
RE_MASCARA = re.compile(r"\*{3}\d{6}\*{2}")


def nomes_zip():
    return ([f"{g}{i}.zip" for g in ("Empresas", "Estabelecimentos", "Socios") for i in range(PARTES)]
            + ["Simples.zip"])


def ordem_processamento():
    """Estabelecimentos primeiro (de lá sai o índice por CNPJ básico), depois Empresas, Socios e Simples."""
    nomes = nomes_zip()
    return [n for g in ("Estabelecimentos", "Empresas", "Socios", "Simples") for n in nomes if n.startswith(g)]


def url_zip(mes, nome, base=WEBDAV):
    return f"{base}/{mes}/{nome}"


def _req(url, metodo="GET", token=TOKEN, **cab):
    auth = "Basic " + base64.b64encode(f"{token}:".encode()).decode()  # à mão: o handler só manda após um 401
    return urllib.request.Request(url, method=metodo, headers={"Authorization": auth, "User-Agent": baixar.UA, **cab})


def _abrir(req, opener):
    try:
        return opener(req, timeout=120)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SystemExit(f"Receita recusou o acesso (HTTP {e.code}) em {req.full_url}: o token do compartilhamento "
                             "mudou? Confira TOKEN em rastro/cnpj.py") from e
        raise


_PROP = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/></d:prop></d:propfind>'


def listar(base, pasta, opener=urllib.request.urlopen, token=TOKEN):
    """PROPFIND (Depth 1) em base/pasta: {nome: tamanho em bytes, ou None para subpasta}."""
    pasta = pasta.strip("/")
    req = _req(f"{base}/{pasta}/" if pasta else f"{base}/", "PROPFIND", token, Depth="1",
               **{"Content-Type": "application/xml"})
    req.data = _PROP
    with contextlib.closing(_abrir(req, opener)) as r:
        raiz = ET.fromstring(r.read())
    proprio = (urllib.parse.urlparse(base).path.rstrip("/") + "/" + pasta).strip("/")
    achados = {}
    for resp in raiz.iter("{DAV:}response"):
        href = urllib.parse.unquote(urllib.parse.urlparse(resp.findtext("{DAV:}href") or "").path).strip("/")
        if not href or href == proprio:
            continue
        tam = (resp.findtext(".//{DAV:}getcontentlength") or "").strip()
        achados[href.rsplit("/", 1)[-1]] = int(tam) if tam.isdigit() else None
    return achados


def mes_mais_recente(base=WEBDAV, opener=urllib.request.urlopen, token=TOKEN):
    meses = [n for n in listar(base, "", opener, token) if re.fullmatch(RE_MES, n)]
    if not meses:
        raise SystemExit(f"nenhuma pasta AAAA-MM em {base}/")
    return max(meses)


def esperados(tamanhos):
    """Os tamanhos dos 31 arquivos do mês (extras são ignorados); aborta dizendo quais faltam."""
    faltam = [n for n in nomes_zip() if tamanhos.get(n) is None]
    if faltam:
        raise SystemExit(f"a listagem da Receita não tem: {', '.join(faltam)}")
    return {n: tamanhos[n] for n in nomes_zip()}


def checar_disco(pasta, tamanhos, disk_usage=shutil.disk_usage):
    """Exige 2x o maior arquivo livre (um .part já baixado conta como espaço que já usamos)."""
    pasta = Path(pasta)
    necessario = 2 * max(tamanhos.values())
    ref = pasta
    while not ref.exists() and ref != ref.parent:
        ref = ref.parent
    livre = disk_usage(ref).free + sum(p.stat().st_size for p in pasta.glob("*.part"))
    if livre < necessario:
        raise SystemExit(f"pouco espaço em {ref}: livre {livre / 1e9:.1f} GB, necessário {necessario / 1e9:.1f} GB "
                         "(2x o maior arquivo)")


def baixar_webdav(url, dest, tamanho, opener=urllib.request.urlopen, token=TOKEN, espera=time.sleep):
    """Baixa url em dest.part, retomando com Range, confere tamanho e 'PK' e só então renomeia para dest."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for tentativa in range(RETENTATIVAS + 1):
        ja = part.stat().st_size if part.exists() else 0
        if ja < tamanho:
            cab = {"Range": f"bytes={ja}-"} if ja else {}
            try:
                with contextlib.closing(_abrir(_req(url, "GET", token, **cab), opener)) as r:
                    if ja and getattr(r, "status", None) != 206:
                        ja = 0  # servidor ignorou o Range: recomeça do zero, sem concatenar
                    with open(part, "ab" if ja else "wb") as f:
                        shutil.copyfileobj(r, f)
            except urllib.error.HTTPError:
                raise
            except (OSError, http.client.HTTPException) as e:
                log.warning("%s: conexão cortada (%s)", dest.name, e)
        ja = part.stat().st_size if part.exists() else 0
        if ja >= tamanho:
            break
        if tentativa < RETENTATIVAS:
            espera(2 * (tentativa + 1))
    if ja != tamanho:
        if ja > tamanho:
            part.unlink()
        raise SystemExit(f"{dest.name}: tamanho {ja} diferente do informado pela Receita ({tamanho})")
    with open(part, "rb") as f:
        if f.read(2) != b"PK":
            part.unlink()
            raise SystemExit(f"{dest.name}: não é um ZIP (sem 'PK'); a Receita devolveu outra coisa?")
    part.replace(dest)
    return dest


def cnpjs_alvo(dir_contas):
    """Conjunto de CNPJs (14 dígitos) de fornecedores_pj em dir_contas/<sq>.json."""
    alvo = set()
    for arq in sorted(Path(dir_contas).glob("*.json")):
        desp = json.loads(arq.read_text(encoding="utf-8")).get("despesas") or {}
        for f in desp.get("fornecedores_pj", []):
            doc = digitos(f.get("cnpj"))
            if len(doc) == 14:
                alvo.add(doc)
            else:
                log.warning("%s: documento de fornecedor PJ com tamanho errado ignorado", arq.name)
    return alvo


def situacao(cod):
    cod = (cod or "").strip()
    if cod not in SITUACAO:
        log.warning("situação cadastral desconhecida: %r", cod)
        return cod or None
    return SITUACAO[cod]


def data_iso(txt):
    txt = (txt or "").strip()
    if not txt or txt == "00000000":
        return None
    try:
        return datetime.strptime(txt, "%Y%m%d").date().isoformat()
    except ValueError:
        log.warning("data inválida: %r", txt)
        return None


def _norm(txt):
    sem = unicodedata.normalize("NFD", txt or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem.upper()).strip()


def endereco_chave(tipo, logradouro, numero, cep):
    """'RUA DAS FLORES|123|01234567'; sem logradouro ou sem CEP de 8 dígitos não há chave."""
    rua = _norm(f"{tipo or ''} {logradouro or ''}") if (logradouro or "").strip() else ""
    cep = digitos(cep)
    if not rua or len(cep) != 8:
        return None
    num = _norm(numero)
    if num in ("", "S/N", "SN"):
        num = "SN"
    return f"{rua}|{num}|{cep}"


def cpf_mascarado(identificador, campo):
    """Só PF, e só o que já vem mascarado. CPF inteiro ou lixo nunca é gravado."""
    if (identificador or "").strip() != "2":
        return None
    campo = (campo or "").strip()
    if RE_MASCARA.fullmatch(campo):
        return campo
    if cpf_valido(digitos(campo)):
        log.warning("sócio PF com CPF sem máscara descartado")
    else:
        log.warning("sócio PF com CPF em formato inesperado descartado: %r", re.sub(r"\d", "9", campo))
    return None


def ler_zip(caminho):
    """Linhas (listas) do único membro do ZIP: ';', latin-1, sem cabeçalho. Nada vai a disco."""
    with zipfile.ZipFile(caminho) as z:
        membros = z.namelist()
        if len(membros) != 1:
            raise FileNotFoundError(f"{caminho}: esperava 1 membro, achei {membros}")
        with z.open(membros[0]) as bruto:
            yield from csv.reader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")


def _zips(dir_zips, prefixo):
    achados = sorted(Path(dir_zips).glob(f"{prefixo}*.zip"))
    if not achados:
        raise FileNotFoundError(f"nenhum {prefixo}*.zip em {dir_zips}: gravar assim marcaria todos os CNPJs como ausentes")
    return achados


def _col(linha, i):
    return linha[i] if len(linha) > i else ""


def _estab(z, alvo, forn):
    for l in ler_zip(z):
        cnpj = _col(l, 0) + _col(l, 1) + _col(l, 2)
        if cnpj in alvo:
            forn[cnpj] = {"razao": None, "abertura": data_iso(_col(l, 10)), "situacao": situacao(_col(l, 5)),
                          "cnae": _col(l, 11).strip() or None, "mei": False, "simples": False,
                          "endereco_chave": endereco_chave(_col(l, 13), _col(l, 14), _col(l, 15), _col(l, 18)),
                          "socios": []}


def _empresas(z, forn, por_basico):
    for l in ler_zip(z):
        if _col(l, 0) in por_basico:
            razao = limpar_texto(_col(l, 1)) or None
            for c in por_basico[l[0]]:
                forn[c]["razao"] = razao


def _socios(z, forn, por_basico):
    for l in ler_zip(z):
        if _col(l, 0) in por_basico:
            socio = {"nome": limpar_texto(_col(l, 2)) or None, "cpf_mascarado": cpf_mascarado(_col(l, 1), _col(l, 3))}
            for c in por_basico[l[0]]:
                forn[c]["socios"].append(socio)


def _simples(z, forn, por_basico):
    for l in ler_zip(z):
        if _col(l, 0) in por_basico:
            optante = _col(l, 1).strip() == "S" and not data_iso(_col(l, 3))
            mei = _col(l, 4).strip() == "S" and not data_iso(_col(l, 6))
            for c in por_basico[l[0]]:
                forn[c]["simples"], forn[c]["mei"] = optante or mei, mei


class _Acumulador:
    """Filtra a base pelos CNPJs-alvo, um ZIP por vez. Ordem obrigatória: Estabelecimentos, Empresas, Socios, Simples
    (o índice por CNPJ básico sai dos estabelecimentos)."""

    def __init__(self, alvo):
        self.alvo, self.forn, self.por_basico = alvo, {}, None

    def processar(self, nome, caminho):
        if nome.startswith("Estabelecimentos"):
            if self.por_basico is not None:
                raise RuntimeError(f"{nome} fora de ordem")
            return _estab(caminho, self.alvo, self.forn)
        if self.por_basico is None:
            self.por_basico = {}
            for c in sorted(self.forn):
                self.por_basico.setdefault(c[:8], []).append(c)
        fn = {"Empresas": _empresas, "Socios": _socios, "Simples": _simples}[re.match(r"[A-Za-z]+", nome).group()]
        fn(caminho, self.forn, self.por_basico)

    def finalizar(self, mes, saida):
        """Marca os CNPJs-alvo ausentes da base e grava saida. Devolve (alvos, encontrados)."""
        achados = set(self.forn)
        for cnpj in sorted(self.alvo - achados):
            log.warning("CNPJ %s não está na base da Receita", cnpj)
            self.forn[cnpj] = {"razao": None, "abertura": None, "situacao": None, "cnae": None, "mei": False,
                               "simples": False, "endereco_chave": None, "socios": []}
        obj = {"fonte": [url_zip(mes, n) for n in nomes_zip()], "data_base": f"{mes}-01",
               "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "fornecedores": dict(sorted(self.forn.items()))}
        gravar(saida, obj)
        return len(self.alvo), len(achados)


def gerar(dir_zips, dir_contas, saida, mes):
    """Modo local: filtra os ZIPs já presentes em dir_zips e grava saida. Devolve (alvos, encontrados)."""
    acc = _Acumulador(cnpjs_alvo(dir_contas))
    for prefixo in ("Estabelecimentos", "Empresas", "Socios", "Simples"):
        for z in _zips(dir_zips, prefixo):
            acc.processar(z.name, z)
    return acc.finalizar(mes, saida)


def main(argv=None, opener=urllib.request.urlopen, hoje=None, base=WEBDAV, disk_usage=shutil.disk_usage):
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mes", help="mês de referência da Receita, AAAA-MM (com --baixar, o padrão é o mais recente)")
    ap.add_argument("--baixar", action="store_true", help="baixa os ZIPs um a um (7,8 GB no total), processa e apaga")
    args = ap.parse_args(argv)
    if args.baixar and (hoje or date.today()) == baixar.DIA_APURACAO:
        raise SystemExit("25/10: não baixar nada no dia da apuração (mesmo IP de saída do agregador)")
    mes = args.mes
    if mes is not None and not re.fullmatch(RE_MES, mes):
        raise SystemExit(f"--mes inválido: {mes!r} (use AAAA-MM)")
    if not args.baixar and mes is None:
        raise SystemExit("sem --baixar, informe --mes para processar os ZIPs de rastro/brutos/cnpj/<mes>/")
    alvo = cnpjs_alvo(SAIDA_CONTAS)
    if not alvo:
        raise SystemExit(f"nenhum CNPJ-alvo em {SAIDA_CONTAS}: rode rastro/contas.py antes")
    if not args.baixar:
        alvos, achados = gerar(baixar.OUT / "cnpj" / mes, SAIDA_CONTAS, SAIDA, mes)
    else:
        mes = mes or mes_mais_recente(base, opener)
        tamanhos = esperados(listar(base, mes, opener))
        pasta = baixar.OUT / "cnpj" / mes
        pasta.mkdir(parents=True, exist_ok=True)
        checar_disco(pasta, tamanhos, disk_usage)
        acc = _Acumulador(alvo)
        for nome in ordem_processamento():
            zip_ = baixar_webdav(url_zip(mes, nome, base), pasta / nome, tamanhos[nome], opener)
            acc.processar(nome, zip_)
            zip_.unlink()
            print(f"{nome}: processado")
        alvos, achados = acc.finalizar(mes, SAIDA)
    print(f"{achados} de {alvos} CNPJs-alvo encontrados; saída em {SAIDA}")


if __name__ == "__main__":
    main()
