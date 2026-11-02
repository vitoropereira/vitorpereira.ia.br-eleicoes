#!/usr/bin/env python3
"""Lê direto do CDN do TSE (HTTP Range, sem baixar o ZIP) os logs de urna do 2º turno de 2026 e grava, por seção,
cada voto computado em 25/10/2026: hora, tempo na mesa, tempo na cabine e tipo de habilitação.

Fonte: bu_imgbu_logjez_rdv_vscmr_2026_2t_UF.zip (um por UF). Só o pedaço *-log.jez de cada seção é pedido ao servidor.
Nome da seção no ZIP: o03221 + uf + município (5) + zona (4) + seção (4), ex. o03221rr0300000040011.
Saída (nunca commitada): horarios/brutos/2t_UF.jsonl.gz, uma linha por seção:
  {"mun": "03000", "zona": "0004", "secao": "0011", "t": [...], "mesa": [...], "cab": [...], "hab": "bbm?..."}
  t = segundos desde 00:00 no relógio da urna (hora local); mesa/cab em segundos (-1 = sem registro);
  hab: b = biometria, m = manual, ? = sem registro. Nada identifica o eleitor.
Nunca roda em 25/10 (mesma trava do rastro/baixar.py).
Uso: python3 horarios/ler_logs.py [UF ...] [--threads N]   (sem UF: todas, da menor para a maior)"""
import argparse, gzip, http.client, io, json, os, re, struct, sys, threading, time, zipfile, zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent))
from rastro.baixar import DIA_APURACAO, UA  # noqa: E402

OUT = H / "brutos"
URL = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_2t_{uf}.zip"
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO ZZ".split()
DIA = "25/10/2026"
NOME = re.compile(r"o\d{5}([a-z]{2})(\d{5})(\d{4})(\d{4})-log\.jez$")
_local = threading.local()


def _conexao(host):
    c = getattr(_local, "c", None)
    if c is None:
        c = _local.c = http.client.HTTPSConnection(host, timeout=60)
    return c


def faixa(url, ini, fim):
    """Bytes [ini, fim] do url (Range), com conexão keep-alive por thread e até 5 tentativas."""
    u = urlsplit(url)
    for tent in range(5):
        try:
            c = _conexao(u.netloc)
            c.request("GET", u.path, headers={"User-Agent": UA, "Range": f"bytes={ini}-{fim}"})
            r = c.getresponse()
            dados = r.read()
            if r.status != 206:
                raise IOError(f"HTTP {r.status} em {url}")
            return dados
        except (OSError, http.client.HTTPException):
            _local.c = None
            if tent == 4:
                raise
            time.sleep(2 ** tent)


class Remoto(io.RawIOBase):
    """Arquivo remoto só-leitura e com seek, para o zipfile ler o diretório central (usado só nessa etapa)."""
    def __init__(self, url):
        self.url, self.pos = url, 0
        u = urlsplit(url)
        c = http.client.HTTPSConnection(u.netloc, timeout=60)
        c.request("HEAD", u.path, headers={"User-Agent": UA})
        r = c.getresponse(); r.read()
        self.tam = int(r.getheader("Content-Length"))

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.tam + off}[whence]
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.tam - self.pos)
        if n <= 0:
            return 0
        d = faixa(self.url, self.pos, self.pos + n - 1)
        b[:len(d)] = d
        self.pos += len(d)
        return len(d)


def entrada(url, info):
    """Bytes descomprimidos de uma entrada do ZIP remoto, pedindo só o seu trecho."""
    folga = 30 + len(info.filename.encode()) + 1024  # cabeçalho local; o extra local pode diferir do central
    d = faixa(url, info.header_offset, info.header_offset + folga + info.compress_size - 1)
    assert d[:4] == b"PK\x03\x04", info.filename
    n, m = struct.unpack("<HH", d[26:30])
    corpo = d[30 + n + m: 30 + n + m + info.compress_size]
    if info.compress_type == zipfile.ZIP_STORED:
        return corpo
    assert info.compress_type == zipfile.ZIP_DEFLATED, info.compress_type
    return zlib.decompress(corpo, -15)


def _seg(ln):
    return int(ln[11:13]) * 3600 + int(ln[14:16]) * 60 + int(ln[17:19])


def votos(logd):
    """Do texto do logd.dat: listas (t, mesa, cab, hab) dos votos computados no dia DIA."""
    t, mesa, cab, hab = [], [], [], []
    ident = habil = None
    tipo = "?"
    for ln in logd.splitlines():
        if not ln.startswith(DIA):
            continue
        if "Identificador do eleitor digitado pelo mes" in ln:
            ident, habil, tipo = _seg(ln), None, "?"
        elif "Tipo de habilita" in ln and "[biom" in ln:
            tipo = "b"
        elif "habilitação manual" in ln or "habilita\xe7\xe3o manual" in ln:
            tipo = "m"
        elif "Eleitor foi habilitado" in ln:
            habil = _seg(ln)
        elif "O voto do eleitor foi computado" in ln:
            s = _seg(ln)
            t.append(s)
            mesa.append(habil - ident if ident is not None and habil is not None else -1)
            cab.append(s - habil if habil is not None else -1)
            hab.append(tipo)
            ident = habil = None
            tipo = "?"
    return t, mesa, cab, "".join(hab)


def secao(url, info):
    m = NOME.search(info.filename)
    with zipfile.ZipFile(io.BytesIO(entrada(url, info))) as z:
        texto = z.read("logd.dat").decode("latin1")
    t, mesa, cab, hab = votos(texto)
    return dict(mun=m[2], zona=m[3], secao=m[4], t=t, mesa=mesa, cab=cab, hab=hab)


def ler_uf(uf, threads=8, out=OUT):
    dest = out / f"2t_{uf}.jsonl.gz"
    if dest.exists():
        return f"{uf}: já existe ({dest.name})"
    url = URL.format(uf=uf)
    with zipfile.ZipFile(Remoto(url)) as z:
        logs = sorted((i for i in z.infolist() if NOME.search(i.filename)), key=lambda i: i.header_offset)
    out.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    n_votos, ini = 0, time.time()
    with gzip.open(tmp, "wt", encoding="utf-8") as f, ThreadPoolExecutor(threads) as ex:
        for k, s in enumerate(ex.map(lambda i: secao(url, i), logs), 1):
            f.write(json.dumps(s, separators=(",", ":")) + "\n")
            n_votos += len(s["t"])
            if k % 2000 == 0:
                print(f"  {uf} {k}/{len(logs)} seções, {n_votos} votos, {time.time() - ini:.0f}s", flush=True)
    os.replace(tmp, dest)
    return f"{uf}: {len(logs)} seções, {n_votos} votos, {time.time() - ini:.0f}s"


def main():
    if date.today() == DIA_APURACAO:
        raise SystemExit("25/10: não ler nada do TSE no dia da apuração")
    ap = argparse.ArgumentParser()
    ap.add_argument("ufs", nargs="*")
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    ufs = [u.upper() for u in a.ufs] or sorted(UFS, key=lambda u: Remoto(URL.format(uf=u)).tam)
    for uf in ufs:
        print(ler_uf(uf, a.threads), flush=True)


if __name__ == "__main__":
    main()
