#!/bin/bash
# Load a batch of new IT PDFs into the REAL database and re-assess every customer document once (instead of one
# recheck per IT). Resumable: after a power cut just run it again (ITs already loaded are skipped by content hash,
# documents already re-assessed in this batch are skipped by their marker; the interrupted one is redone).
# The first run snapshots the database and the exports.
#
#   bash tools/load_new_its.sh "Leoni/Leoni/RE__Pedido_de_Documentação_Exemplo" new_its
#   (folder with the IT PDFs, batch name; log: data/logs/<batch>.log)
cd "$(dirname "$0")/.." || exit 1
DIR=${1:?folder with the IT PDFs}
BATCH=${2:-new_its}
LOG=data/logs/$BATCH.log
DONE=data/logs/$BATCH.done        # one line per customer document re-assessed in this batch
SNAP=data/snapshots/real_before_$BATCH.db

if [ ! -f "$SNAP" ]; then
  cp data/complyai.db "$SNAP" && mkdir -p "data/snapshots/exports_before_$BATCH" \
    && cp data/exports/*.xlsx "data/snapshots/exports_before_$BATCH/"
  echo "$(date +%T) snapshot -> $SNAP" | tee -a "$LOG"
fi
touch "$DONE"

run() { echo "$(date +%T) $*" | tee -a "$LOG"; python -u -m complyai "$@" >> "$LOG" 2>&1; }

run ingest-it --no-recheck "$DIR/*.pdf" || exit 1
for id in $(python -c "import sqlite3; print(*[r[0] for r in sqlite3.connect('data/complyai.db').execute(
    \"SELECT id FROM documents WHERE kind='CSR' AND status='active' ORDER BY id\")])"); do
  grep -qx "$id" "$DONE" && continue
  run reassess "$id" || exit 1
  echo "$id" >> "$DONE"
done
run docs
echo "$(date +%T) batch $BATCH finished" | tee -a "$LOG"
