"""End-to-end scenario with known answers (needs Ollama running).

Uses a separate database in data/test/. Ingests the real Leoni ITs, then a synthetic John Deere
standard in two revisions whose differences / conflicts with WI 3600-11 are known in advance.

    python tests/scenario.py            (add --model qwen3:14b to compare models)
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--model")
args = ap.parse_args()
os.environ["COMPLYAI_DATA"] = str(ROOT / "data" / "test")
if args.model:
    os.environ["COMPLYAI_CHAT_MODEL"] = args.model
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")  # alert texts contain "→"; a log file on Windows defaults to cp1252

import json  # noqa: E402
import logging  # noqa: E402

from complyai import config, engine  # noqa: E402
from complyai.catalog import load_index  # noqa: E402
from complyai.export import export_matrix  # noqa: E402
from complyai.parser import parse_pdf  # noqa: E402
from complyai.store import Store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

for f in (config.DB_PATH, config.NOTIFICATIONS_PATH):
    Path(f).unlink(missing_ok=True)
store = Store()
t0 = time.time()
for x in sorted((ROOT / "Leoni" / "Leoni").glob("*.xlsx")):
    load_index(store, x)
for pdf in sorted((ROOT / "Leoni" / "Leoni").glob("*.pdf")):
    engine.ingest_it(store, parse_pdf(pdf))

fx = ROOT / "tests" / "fixtures"
a = engine.ingest_csr(store, json.loads((fx / "JD_DLW20803_revA.json").read_text(encoding="utf-8")))
b = engine.ingest_csr(store, json.loads((fx / "JD_DLW20803_revB.json").read_text(encoding="utf-8")))
print("\nrev A:", a, "\nrev B:", b)


def reqs_matching(doc_id, *words):
    rows = store.q("SELECT * FROM requirements WHERE doc_id=?", (doc_id,))
    return [r for r in rows if all(w.lower() in (r["statement"] + " " + r["quote"]).lower() for w in words)]


def verdicts(req_rows, it_code):
    ids = [r["id"] for r in req_rows]
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    return {l["verdict"] for l in store.q(
        f"SELECT verdict FROM req_it_links WHERE source='text' AND it_code=? AND req_id IN ({marks})", (it_code, *ids))}


def finding(type_, doc_id, *words):
    rows = store.q("SELECT * FROM findings WHERE type=? AND doc_id=?", (type_, doc_id))
    return [f for f in rows if all(w.lower() in (f["detail"] or "").lower() for w in words)]


checks = [
    ("A: same client/code detected for rev B", b["client"] == a["client"] and b["superseded_docs"] == [a["doc_id"]]),
    ("A: fill rate 95% compliant with WI 3600-11", "compliant" in verdicts(reqs_matching(a["doc_id"], "95"), "WI 3600-11")),
    ("A: tape 10-15 mm compliant with WI 3600-11", "compliant" in verdicts(reqs_matching(a["doc_id"], "15 mm"), "WI 3600-11")),
    ("B: fill rate 98% flagged as REQ_MODIFIED", bool(finding("REQ_MODIFIED", b["doc_id"], "98"))),
    ("B: fill rate 98% conflict/partial vs WI 3600-11",
     verdicts(reqs_matching(b["doc_id"], "98"), "WI 3600-11") & {"conflict", "partial"}),
    ("B: tape 20-25 mm flagged as REQ_MODIFIED", bool(finding("REQ_MODIFIED", b["doc_id"], "25"))),
    ("B: tape 20-25 mm conflict vs WI 3600-11",
     "conflict" in verdicts(reqs_matching(b["doc_id"], "25"), "WI 3600-11")),
    ("B: change notice 90->120 days flagged as REQ_MODIFIED", bool(finding("REQ_MODIFIED", b["doc_id"], "120"))),
    ("B: records 10 years flagged as REQ_REMOVED", bool(finding("REQ_REMOVED", b["doc_id"], "10"))),
    ("B: harness label flagged as REQ_NEW", bool(store.q(
        "SELECT 1 FROM findings WHERE type='REQ_NEW' AND doc_id=? AND (detail LIKE '%etiqueta%' OR detail LIKE '%label%')",
        (b["doc_id"],)))),
    ("B: 8D requirements unchanged (no REQ_MODIFIED on 8D)", not finding("REQ_MODIFIED", b["doc_id"], "8D")),
]

conflicts_before = store.q("SELECT * FROM findings WHERE type='CONFLICT' AND it_code='WI 3600-11' AND doc_id=?",
                           (b["doc_id"],))

# LEONI updates WI 3600-11 to the new customer values -> the conflicts must disappear
it2 = engine.ingest_it(store, json.loads((fx / "WI-3600-11_v2.json").read_text(encoding="utf-8")),
                       code="WI 3600-11", version="2")
print("IT update:", it2)

checks += [
    ("IT v2: old WI 3600-11 superseded + IT_UPDATED raised",
     bool(it2.get("superseded")) and bool(store.q("SELECT 1 FROM findings WHERE type='IT_UPDATED'"))),
    ("IT v2: conflicts with WI 3600-11 resolved after the IT update",
     len(conflicts_before) >= 1 and not store.q(
         "SELECT 1 FROM findings WHERE type='CONFLICT' AND it_code='WI 3600-11' AND doc_id=?", (b["doc_id"],))),
    ("IT v2: rev B tape 20-25 mm now compliant with WI 3600-11",
     "compliant" in verdicts(reqs_matching(b["doc_id"], "25"), "WI 3600-11")),
]
print(f"\n=== {config.CHAT_MODEL}: scenario checks ({time.time() - t0:.0f}s) ===")
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print(f"{sum(bool(ok) for _, ok in checks)}/{len(checks)} passed")

print("\nFindings rev B:")
for f in store.q("SELECT * FROM findings WHERE doc_id=? ORDER BY id", (b["doc_id"],)):
    print(f"  [{f['severity']}] {f['type']}: {f['title']}\n      {f['detail'][:220]!r}")
print("\nmatrix:", export_matrix(store, b["doc_id"]))
