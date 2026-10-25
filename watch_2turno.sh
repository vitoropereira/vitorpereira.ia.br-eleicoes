#!/bin/bash
# 2º turno (25/10): roda gerar_2turno.py a cada 2 min (histórico da trajetória) e, ao cruzar cada marco do % apurado,
# grava o snapshot e publica: PR só com snapshots/2-turno/<leitura>/ + historico_2turno.json, mergeado na hora
# (o push na main dispara o rastro-lote, que regenera e publica o site/). Mesmo papel do watch.sh no 1º turno.
# Estado em .marcos_feitos_2turno (um marco por linha) — re-armar não refaz marco já publicado.
cd "$(dirname "$0")"
MARCOS="${MARCOS:-10 25 50 75 90 99}"
REPO=vitoropereira/vitorpereira.ia.br-eleicoes
touch .marcos_feitos_2turno

# projeção ao vivo: a cada ciclo, projecao_vivo.json → bucket `vivo` (servido em /vivo/projecao.json, lido pela home).
# Chave de serviço pedida à Management API com o SUPABASE_TOKEN do .env deste projeto; fica só na memória do processo.
ENV_ARQ="${ELEICOES_ENV:-.env}"
CHAVE=""
if [ -f "$ENV_ARQ" ]; then
  REF=$(sed -n 's/^SUPABASE_PROJECT_REF=//p' "$ENV_ARQ" | tr -d '"\r')
  TOKEN=$(sed -n 's/^SUPABASE_TOKEN=//p' "$ENV_ARQ" | tr -d '"\r')
  CHAVE=$(curl -sS -H "Authorization: Bearer $TOKEN" "https://api.supabase.com/v1/projects/$REF/api-keys?reveal=true" |
    python3 -c 'import json,sys; print(next((k["api_key"] for k in json.load(sys.stdin) if k.get("name")=="service_role"),""))' 2>/dev/null)
fi
[ -n "$CHAVE" ] || echo "$(date +%H:%M) AVISO: sem chave do Supabase; a projeção ao vivo não será enviada"
enviar_projecao() {
  [ -n "$CHAVE" ] && [ -f projecao_vivo.json ] || return 0
  curl -sS -o /dev/null -w '%{http_code}' -X POST "https://$REF.supabase.co/storage/v1/object/vivo/projecao.json" \
    -H "Authorization: Bearer $CHAVE" -H "apikey: $CHAVE" -H "x-upsert: true" -H "cache-control: max-age=15" \
    -H "content-type: application/json" --data-binary @projecao_vivo.json | grep -q '^200$' ||
    echo "$(date +%H:%M) ERRO ao enviar projecao.json"
}

publicar() {  # $1 = marco, $2 = pasta do snapshot
  local m=$1 snap=$2 wt br
  br="apuracao-2turno-${m}pct"
  wt=$(mktemp -d)/pub
  git fetch -q origin main && git worktree add -q -B "$br" "$wt" origin/main || return 1
  mkdir -p "$wt/snapshots/2-turno" && cp -R "$snap" "$wt/snapshots/2-turno/" && cp historico_2turno.json "$wt/"
  (cd "$wt" && git add snapshots/2-turno historico_2turno.json &&
    git commit -qm "apuração 2º turno: leitura do marco de ${m}%" &&
    git push -q -u origin "$br" &&
    gh pr create -R "$REPO" --head "$br" --title "Apuração 2º turno: marco de ${m}%" \
      --body "Snapshot da projeção no marco de ${m}% (gerado por watch_2turno.sh). Vira página em /apuracao/2-turno/.")  # o merge fica com o Vitor (auto mode não mergeia sem revisão)
  local ok=$?
  git worktree remove --force "$wt"; git branch -D "$br" >/dev/null 2>&1
  return $ok
}

fails=0
while true; do
  if ! out=$(python3 gerar_2turno.py 2>&1); then
    fails=$((fails+1)); [ $fails -eq 5 ] && echo "$(date +%H:%M) ERRO: gerar_2turno falhou 5x: $(echo "$out" | tail -2 | tr '\n' ' ')"
    sleep 60; continue
  fi
  fails=0
  enviar_projecao
  pst=$(echo "$out" | sed -n 's/.*apurado \([0-9.]*\)%.*/\1/p')
  # marcos cruzados e ainda não publicados: uma publicação só (rotulada pelo maior), todos marcados juntos
  pend=0; cruz=""
  for m in $MARCOS; do
    grep -qx "$m" .marcos_feitos_2turno && continue
    pend=1
    python3 -c "import sys;sys.exit(0 if $pst>=$m else 1)" && cruz="$cruz $m"
  done
  if [ -n "$cruz" ]; then
    m=${cruz##* }
    if out=$(python3 gerar_2turno.py --snapshot 2>&1); then
      snap=$(echo "$out" | sed -n 's/^ok → \([^ ]*\) .*/\1/p')
      if publicar "$m" "$snap"; then
        for x in $cruz; do echo "$x" >> .marcos_feitos_2turno; done
        echo "$(date +%H:%M) MARCO ${m}% publicado (apurado ${pst}%) → $snap | $(echo "$out" | tail -1)"
        grep -qx "${MARCOS##* }" .marcos_feitos_2turno && pend=0
      else
        echo "$(date +%H:%M) ERRO ao publicar o marco ${m}%; tento no próximo ciclo"
      fi
    else
      echo "$(date +%H:%M) ERRO ao gerar no marco ${m}%: $(echo "$out" | tail -3 | tr '\n' ' ')"
    fi
  fi
  [ $pend -eq 0 ] && { echo "FIM: todos os marcos ($MARCOS) publicados"; exit 0; }
  sleep 120
done
