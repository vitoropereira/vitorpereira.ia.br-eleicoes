# Zerar o estado do ensaio em `vivo/` (24/10)

O ensaio de 09 a 15/10 rodou como eleição 6258, que deve ser o código real do 2º turno. O que ficou no bucket pode
contaminar a noite de 25/10: a rodada parte de `_parcial.json` (ou `agora.json`) quando o `ele` bate
(`executar.ts:218-219`), e o HUD abre direto no 2º turno sempre que `agora.json` existe (`hud/app.js:239`).

**Nunca rodar em 25/10 depois das 17h.** O cron continua ativo depois do roteiro: sem eleição ele devolve `sem-eleicao`.

Alvos: `_estado.json`, `_parcial.json`, `agora.json`, `feed.json` e tudo sob `serie/`.
`config.json` **fica** (é a chave da presença, PROPOSTA 6c).

## 1. Dry-run

```bash
python3 supabase/zerar_ensaio.py
```
Não abre conexão: só imprime a sequência (pausar, esperar a trava, apagar, conferir, reativar). Ler antes de seguir.

## 2. Secrets

```bash
supabase secrets list --project-ref qzczyicspbizosjogmlq
```
`ELEICAO_FORCADA` **não** pode aparecer (publicaria o 1º turno como se fosse o 2º). Se aparecer:
`supabase secrets unset ELEICAO_FORCADA --project-ref qzczyicspbizosjogmlq`.

## 3. Executar

```bash
python3 supabase/zerar_ensaio.py --executar
```
Lê `SUPABASE_PROJECT_REF` e `SUPABASE_TOKEN` do `.env`; a service role vem da Management API e não é impressa.
Se apagar ou conferir falhar, o script sai com código 1, lista o que ficou para trás e **deixa o cron pausado**.

## 4. Checagem pública (depois de ~15 s de cache da Vercel)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://eleicoes2026.vitorpereira.ia.br/vivo/agora.json   # 400 ou 404
curl -sS -o /dev/null -w '%{http_code}\n' https://eleicoes2026.vitorpereira.ia.br/vivo/feed.json    # 400 ou 404
```
O HUD em `/ao-vivo/` mostra "sem dado" em vez de abrir no 2º turno.

## 5. `config.json` intacto

```bash
curl -sS https://eleicoes2026.vitorpereira.ia.br/vivo/config.json   # o mesmo de antes
```

## 6. Caminho manual (se o script falhar)

SQL no editor do Supabase (ou `POST /v1/projects/<ref>/database/query` com o PAT):
```sql
select cron.alter_job(job_id := (select jobid from cron.job where jobname = 'eleicoes-agregador'), active := false);
select jobname, schedule, active from cron.job where jobname = 'eleicoes-agregador';   -- active = false
```
Esperar uns 2 min (a trava dura no máximo 130 s; `travaAte` em `_estado.json`, epoch ms). Depois, com
`SERVICE_ROLE_KEY` e `SUPABASE_URL` na shell (nunca em arquivo do repo):
```bash
# listar serie/
curl -sS -X POST "$SUPABASE_URL/storage/v1/object/list/vivo" -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" -d '{"prefix":"serie/","limit":1000}'
# apagar (incluir cada serie/<nome> da lista acima)
curl -sS -X DELETE "$SUPABASE_URL/storage/v1/object/vivo" -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prefixes":["_estado.json","_parcial.json","agora.json","feed.json","serie/index.json"]}'
# conferir: cada um deve dar 400/404
curl -sS -o /dev/null -w '%{http_code}\n' "$SUPABASE_URL/storage/v1/object/vivo/agora.json" \
  -H "Authorization: Bearer $SERVICE_ROLE_KEY"
```
```sql
select cron.alter_job(job_id := (select jobid from cron.job where jobname = 'eleicoes-agregador'), active := true);
select jobname, schedule, active from cron.job where jobname = 'eleicoes-agregador';   -- active = true
```

## 7. Rollback

Não há volta para os objetos apagados: são dado de ensaio, e o agregador recria tudo na primeira rodada com eleição.
O cron volta com o `alter_job(... active := true)` acima.
