"""Per-document summary of the current database: requirements, alerts, changes, IT coverage.

    python tests/report_docs.py                       (real database)
    COMPLYAI_DATA=data/demo python tests/report_docs.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from complyai.store import Store  # noqa: E402

store = Store()
print(f"{'id':>3} {'client':<12} {'code':<28} {'pages':>5} {'reqs':>5} {'w/ IT':>6} {'CONF':>5} {'GAP':>4} "
      f"{'MOD':>4} {'NEW':>4} {'REM':>4}  sections->ITs")
for d in store.q("SELECT * FROM documents WHERE kind='CSR' ORDER BY id"):
    reqs = store.q("SELECT id FROM requirements WHERE doc_id=?", (d["id"],))
    covered = store.one("""SELECT COUNT(DISTINCT req_id) n FROM req_it_links WHERE source='text' AND verdict!='not_related'
                           AND req_id IN (SELECT id FROM requirements WHERE doc_id=?)""", (d["id"],))["n"]
    f = Counter(r["type"] for r in store.q("SELECT type FROM findings WHERE doc_id=?", (d["id"],)))
    pages = store.one("SELECT MAX(page) p FROM chunks WHERE doc_id=?", (d["id"],))["p"] or 0
    sec = store.one("SELECT COUNT(DISTINCT section) s, COUNT(*) n FROM section_its WHERE doc_id=?", (d["id"],))
    print(f"{d['id']:>3} {(d['client'] or '')[:12]:<12} {(d['code'] or '')[:28]:<28} {pages:>5} {len(reqs):>5} "
          f"{covered:>6} {f['CONFLICT']:>5} {f['GAP']:>4} {f['REQ_MODIFIED']:>4} {f['REQ_NEW']:>4} "
          f"{f['REQ_REMOVED']:>4}  {sec['s']} sections, {sec['n']} ITs"
          + ("  [superseded]" if d["status"] != "active" else ""))

cross = store.q("SELECT title, detail, severity FROM findings WHERE type='REQ_CONTRADICTION' ORDER BY id")
if cross:
    print(f"\ncross-document contradictions (same client, different documents): {len(cross)}")
    for c in cross[:12]:
        print(f"  [{c['severity']}] {c['title']}\n      {c['detail'].splitlines()[0][:160]}")
