#!/bin/sh
# Lote diário do Rastro (VPS). Versionado, mas não instalado: ver rastro/README.md, "Fila e lotes diários".
# A trava de 23 a 26/10 está em rastro/lote.py (config.json), então vale também para quem rodar à mão.
set -e
cd "$(dirname "$0")/.."
mkdir -p rastro/brutos
{
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) =="
  git fetch origin
  git checkout main
  git pull --ff-only
  python3 rastro/lote.py
} >> rastro/brutos/lote.log 2>&1
