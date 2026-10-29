#!/bin/bash
# Rebuild the REAL database from the source PDFs with the current parser and engine (~3-3.5 h on the RTX 4070 Ti).
# Resumable: after a power cut just run it again (finished documents are skipped by content hash, a half-ingested
# one is purged and redone, an interrupted IT comparison is resumed). The first run snapshots the old database.
#
#   bash tools/rebuild_real_db.sh            (log: data/logs/rebuild_real_db.log)
cd "$(dirname "$0")/.." || exit 1
LOG=data/logs/rebuild_real_db.log
SNAP=data/snapshots/real_before_new_parser.db

if [ ! -f "$SNAP" ]; then
  cp data/complyai.db "$SNAP" && [ -d data/exports ] && mv data/exports data/snapshots/exports_before_new_parser
  python -m complyai reset
  echo "$(date +%T) snapshot -> $SNAP, database reset" | tee -a "$LOG"
fi

run() { echo "$(date +%T) $*" | tee -a "$LOG"; python -u -m complyai "$@" >> "$LOG" 2>&1; }

run load-index Leoni/Leoni/WI_Indice_11_Rev199.xlsx Leoni/Leoni/IC_Indice_11_Rev113.xlsx || exit 1
run ingest-it "Leoni/Leoni/*.pdf" || exit 1
# same order as before, so the customer documents keep their ids 8-14
run ingest-csr "Cliente/Cliente/Supplier Handbook-Portuguese-January 2026_0.pdf" --client Cummins || exit 1
run ingest-csr "Cliente/Cliente/JDS-G223X3 - Production Part Approval (PPAP) Requirements_Nov2021.pdf" --client "John Deere" || exit 1
run ingest-csr "Cliente/Cliente/DLW 25046_A_Sep2023.pdf" --client "John Deere" || exit 1
run ingest-csr "Cliente/SupplierQualityManual2022 version3.0/SupplierQualityManual2022 version3.0.pdf" --client Caterpillar || exit 1
run ingest-csr "Cliente/Cliente/18227_013.pdf" --client Cummins || exit 1
run ingest-csr "Cliente/Cliente/1E2358_32.pdf" --client Caterpillar || exit 1
run ingest-csr "Cliente/Cliente/JDS-G223 Supplier Quality Manual_Nov2021.pdf" --client "John Deere" || exit 1
run docs
echo "$(date +%T) rebuild finished" | tee -a "$LOG"
