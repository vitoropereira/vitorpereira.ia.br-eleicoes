#!/bin/bash
# 2º turno (25/10): roda gerar_2turno.py a cada 2 min (histórico da trajetória) e, ao cruzar cada marco do % apurado,
# grava o snapshot e publica: PR só com snapshots/2-turno/<leitura>/ + historico_2turno.json, mergeado na hora
# (o push na main dispara o rastro-lote, que regenera e publica o site/). Mesmo papel do watch.sh no 1º turno.
# Estado em .marcos_feitos_2turno (um marco por linha) — re-armar não refaz marco já publicado.
cd "$(dirname "$0")"
MARCOS="${MARCOS:-10 25 50 75 90 99}"
REPO=vitoropereira/vitorpereira.ia.br-eleicoes
touch .marcos_feitos_2turno

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
      --body "Snapshot da projeção no marco de ${m}% (gerado por watch_2turno.sh). Vira página em /apuracao/2-turno/." >/dev/null &&
    gh pr merge -R "$REPO" "$br" --squash --delete-branch >/dev/null)
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
