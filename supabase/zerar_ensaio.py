"""Zera em `vivo/` o estado deixado pelo ensaio de 09 a 15/10, antes da noite de 25/10. Roteiro: `supabase/zerar-ensaio.md`.

    python3 supabase/zerar_ensaio.py              # dry-run (padrão): só imprime o que faria, sem abrir conexão
    python3 supabase/zerar_ensaio.py --executar   # pausa o cron, espera a trava, apaga, confere e reativa

Apaga `_estado.json`, `_parcial.json`, `agora.json`, `feed.json` e tudo sob `serie/`. Nunca toca em `config.json`
(é a chave da presença, PROPOSTA 6c). Credenciais: `SUPABASE_PROJECT_REF` e `SUPABASE_TOKEN` (PAT) do `.env`; a
service role do Storage vem da Management API e só fica em memória. Se apagar ou conferir falhar, o cron fica pausado.
Nunca rodar em 25/10 depois das 17h.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent.parent
JOB = "eleicoes-agregador"
BUCKET = "vivo"
ALVOS = ["_estado.json", "_parcial.json", "agora.json", "feed.json"]
SERIE = "serie/"
INTOCAVEL = "config.json"
ESPERA_INICIAL = 10  # s: uma chamada do pg_net disparada logo antes da pausa ainda pega a trava
ESPERA_MAX = 300  # s: a trava dura no máximo orçamento (100 s) + 30 s; acima disso é trava velha
SQL_PAUSA = f"select cron.alter_job(job_id := (select jobid from cron.job where jobname = '{JOB}'), active := false);"
SQL_REATIVA = f"select cron.alter_job(job_id := (select jobid from cron.job where jobname = '{JOB}'), active := true);"
SQL_ESTADO = f"select jobname, schedule, active from cron.job where jobname = '{JOB}';"


def ler_env():
    env = {}
    arq = R / ".env"
    if arq.is_file():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    env.update({k: v for k, v in os.environ.items() if k.startswith("SUPABASE_")})
    return env


def pedir(metodo, url, token, corpo=None):
    dados = None if corpo is None else json.dumps(corpo).encode()
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


class Cliente:
    """Management API (SQL) com o PAT; Storage com a service role, buscada na hora e nunca impressa."""

    def __init__(self):
        env = ler_env()
        self.ref, self.pat = env.get("SUPABASE_PROJECT_REF"), env.get("SUPABASE_TOKEN")
        if not self.ref or not self.pat:
            raise SystemExit("faltam SUPABASE_PROJECT_REF e SUPABASE_TOKEN no .env")
        self.api = f"https://api.supabase.com/v1/projects/{self.ref}"
        self.storage = f"https://{self.ref}.supabase.co/storage/v1"
        chaves = json.loads(pedir("GET", f"{self.api}/api-keys?reveal=true", self.pat))
        self.chave = next((c["api_key"] for c in chaves if c.get("name") == "service_role"), None)
        if not self.chave:
            raise SystemExit("a Management API não devolveu a chave service_role")

    def sql(self, q):
        return json.loads(pedir("POST", f"{self.api}/database/query", self.pat, {"query": q}))

    def listar(self, prefixo):
        nomes, offset = [], 0
        while True:
            lote = json.loads(pedir("POST", f"{self.storage}/object/list/{BUCKET}", self.chave,
                                    {"prefix": prefixo, "limit": 1000, "offset": offset}))
            nomes += [prefixo + o["name"] for o in lote if o.get("id")]  # sem id = pasta
            if len(lote) < 1000:
                return nomes
            offset += len(lote)

    def ler(self, caminho):
        try:
            return pedir("GET", f"{self.storage}/object/{BUCKET}/{urllib.parse.quote(caminho)}", self.chave)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):  # o Storage responde 400 + NoSuchKey para objeto ausente
                return None
            raise

    def apagar(self, caminhos):
        pedir("DELETE", f"{self.storage}/object/{BUCKET}", self.chave, {"prefixes": list(caminhos)})


def dry_run():
    print("dry-run: nada é executado. Para valer: python3 supabase/zerar_ensaio.py --executar\n")
    print(f"1. pausaria o cron ({JOB}) pela Management API:\n   {SQL_PAUSA}\n   {SQL_ESTADO}  -- active = false")
    print(f"2. esperaria {ESPERA_INICIAL} s e então a trava: travaAte de _estado.json (epoch ms), "
          f"no máximo {ESPERA_MAX} s")
    print(f"3. apagaria de {BUCKET}/:")
    for a in ALVOS:
        print(f"   - {a}")
    print(f"   - tudo sob {SERIE} (listado na hora)")
    print(f"   ({INTOCAVEL} fica: é a chave da presença)")
    print("4. conferiria que cada alvo responde ausente (400/404) e que serie/ ficou vazia")
    print("   se algo falhar, para aqui com o cron pausado")
    print("5. lembraria de conferir que ELEICAO_FORCADA não está em `supabase secrets list`")
    print(f"6. reativaria o cron:\n   {SQL_REATIVA}\n   {SQL_ESTADO}  -- active = true")
    return 0


def restantes(cliente, alvos):
    try:
        return [a for a in alvos if cliente.ler(a) is not None] + [
            s for s in cliente.listar(SERIE) if s not in alvos]
    except Exception:
        return list(alvos)


def executar(cliente, dormir, agora):
    print(f"1. pausando o cron {JOB}")
    cliente.sql(SQL_PAUSA)
    print(f"   {cliente.sql(SQL_ESTADO)}")

    print(f"2. esperando {ESPERA_INICIAL} s e a trava (travaAte de _estado.json)")
    dormir(ESPERA_INICIAL)
    try:
        trava = (json.loads(cliente.ler("_estado.json") or b"{}") or {}).get("travaAte") or 0
    except ValueError:
        trava = 0
    falta = trava / 1000 - agora()
    if falta > 0:
        espera = min(falta + 5, ESPERA_MAX)
        print(f"   trava ativa: esperando {espera:.0f} s")
        dormir(espera)

    alvos = ALVOS + []
    try:
        alvos += cliente.listar(SERIE)
        alvos = [a for a in alvos if a != INTOCAVEL]
        print(f"3. apagando {len(alvos)} objetos")
        cliente.apagar(alvos)
        print("4. conferindo")
        sobra = restantes(cliente, alvos)
    except Exception as e:
        print(f"   erro: {e}")
        sobra = restantes(cliente, alvos)
        if not sobra:
            sobra = ["(não deu para conferir)"]
    if sobra:
        print("falhou: o que ficou para trás:")
        for s in sobra:
            print(f"   - {s}")
        print(f"o cron continua pausado. Depois de resolver, reative à mão:\n   {SQL_REATIVA}")
        return 1
    for a in alvos:
        print(f"   {a}: ausente")

    print("5. confira que ELEICAO_FORCADA não está em: supabase secrets list --project-ref <ref>")
    print(f"6. reativando o cron {JOB}")
    cliente.sql(SQL_REATIVA)
    print(f"   {cliente.sql(SQL_ESTADO)}")
    return 0


def main(argv=None, fabrica=Cliente, dormir=time.sleep, agora=time.time):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--executar", action="store_true", help="escreve em produção (sem isso, dry-run)")
    a = ap.parse_args(argv)
    if not a.executar:
        return dry_run()
    return executar(fabrica(), dormir, agora)


if __name__ == "__main__":
    sys.exit(main())
