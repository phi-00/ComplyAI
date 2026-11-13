"""Regression set from the first alert review (tests/fixtures/review_regression.json): re-assesses only those
requirements on a COPY of the real database and compares each requirement / IT pair with its expected result
(~70 requirements, ~10 min of GPU; the real database is never written).

    python tests/review_regression.py [--db data/complyai.db] [--no-replace] [--fresh] [--tag NAME]
    python tests/review_regression.py --score-only [--before data/snapshots/X.db] --tag NAME   # no LLM: stored verdicts

Before the comparison WI 3069-11 A2 is read again with the current parser (`ingest_it(replace=True)`: one passage
per customer column) unless --no-replace. Its rules are extracted by the LLM and differ a little from run to run,
which changes the ITs some requirements see; so the copy with WI 3069-11 A2 re-read is kept
(data/test/review_regression_prepared_<db>.db) and reused by later runs, which then differ only in the judge's
answers. --fresh reads it again; the copy is also redone when the database or the parser is newer.
Results: data/test/review_regression_results/result_<tag>.json (kept across runs).
"""
import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--db", default=str(ROOT / "data" / "complyai.db"))
ap.add_argument("--no-replace", action="store_true", help="keep the stored WI 3069-11 A2 passages")
ap.add_argument("--fresh", action="store_true", help="read WI 3069-11 A2 again even if a prepared copy exists")
ap.add_argument("--score-only", action="store_true",
                help="no LLM: score the verdicts already stored in --db (e.g. after a full re-assessment)")
ap.add_argument("--before", help="database whose stored verdicts are shown as 'before' (default: --db before the run)")
ap.add_argument("--tag", default="current")
args = ap.parse_args()
src = Path(args.db)
work = ROOT / "data" / "test" / "review_regression"
results = ROOT / "data" / "test" / "review_regression_results"
prepared = ROOT / "data" / "test" / f"review_regression_prepared_{src.stem}.db"
reuse = (not args.score_only and not args.no_replace and not args.fresh and prepared.exists()
         and prepared.stat().st_mtime > max(src.stat().st_mtime, (ROOT / "complyai" / "parser.py").stat().st_mtime))
shutil.rmtree(work, ignore_errors=True)
work.mkdir(parents=True)
results.mkdir(parents=True, exist_ok=True)
shutil.copy(prepared if reuse else src, work / "complyai.db")
os.environ["COMPLYAI_DATA"] = str(work)  # notifications of this run go to the copy's folder as well
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from complyai import engine, llm  # noqa: E402
from complyai.parser import parse_pdf  # noqa: E402
from complyai.store import Store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


class _Count(logging.Handler):
    """Counts prompts close to NUM_CTX (llm.py warns; Ollama would cut longer ones silently)."""
    n = 0

    def emit(self, record):
        if "leaves little room" in record.getMessage():
            _Count.n += 1


logging.getLogger("complyai.llm").addHandler(_Count())
ALERTS = ("conflict", "partial")
OK = {"conflict": lambda v: v == "conflict", "alert": lambda v: v in ALERTS, "not_conflict": lambda v: v != "conflict",
      "no_alert": lambda v: v not in ALERTS, "stricter": lambda v: v == "stricter"}

items = json.loads((ROOT / "tests" / "fixtures" / "review_regression.json").read_text(encoding="utf-8"))["items"]
store = Store(work / "complyai.db")
if not args.score_only:
    llm.check()
req_ids = sorted({x["req"] for x in items})


def verdicts(db):
    out = {}
    marks = ",".join("?" * len(req_ids))
    for req_id, it_code, verdict in db.execute(f"SELECT req_id, it_code, verdict FROM req_it_links WHERE source='text' "
                                               f"AND req_id IN ({marks})", req_ids):
        out[(req_id, it_code)] = verdict
    return out


before = verdicts(sqlite3.connect(f"file:{Path(args.before).resolve().as_posix()}?mode=ro", uri=True)
                  if args.before else store.db)
t0 = time.time()
if args.score_only:
    print(f"score only: verdicts stored in {src}")
elif reuse:
    print(f"WI 3069-11 A2: re-read copy reused ({prepared.name}; --fresh to read it again)")
elif not args.no_replace:
    res = engine.ingest_it(store, parse_pdf(ROOT / "Leoni" / "Leoni" / "RE__Pedido_de_Documentação_Exemplo"
                                            / "WI-3069-11-A2.pdf"), replace=True, recheck=False)
    print("WI 3069-11 A2:", json.dumps(res))
    store.commit()
    with sqlite3.connect(prepared) as dst:
        store.db.backup(dst)
if not args.score_only:
    engine.assess_requirements(store, req_ids)
after = verdicts(store.db)
secs = time.time() - t0

rows, score = [], Counter()
for x in items:
    b, a = before.get((x["req"], x["it"]), "-"), after.get((x["req"], x["it"]), "not judged")
    exp = x.get("expect")
    ok = None if exp is None else OK[exp](a if a != "not judged" else "not_related")
    if ok is not None:
        score[(x["source"].split()[0] if x["source"].startswith("Claude") else x["source"], ok)] += 1
    others = sorted(f"{c}:{v}" for (r, c), v in after.items() if r == x["req"] and c != x["it"]
                    and v in ("conflict", "partial", "stricter"))
    rows.append({**x, "before": b, "after": a, "ok": ok, "other_alerts": others})
    flag = "  -  " if ok is None else ("PASS " if ok else "FAIL ")
    print(f"{flag}#{x['finding']:<5} req {x['req']:<5} {x['it']:<14} {b:>12} -> {a:<12} expect {exp or '-':<12} "
          f"{('also ' + ', '.join(others)) if others else ''}")

count = lambda vs, v: sum(1 for k, x in vs.items() if x == v)  # noqa: E731
print(f"\n=== review regression ({len(req_ids)} requirements, {secs:.0f}s, prompts near NUM_CTX: {_Count.n}) ===")
for src in sorted({s for s, _ in score}):
    print(f"{src:<14} {score[(src, True)]}/{score[(src, True)] + score[(src, False)]} as expected")
print(f"all labelled   {sum(v for (s, ok), v in score.items() if ok)}/{sum(score.values())} as expected")
for name, vs in (("before", before), ("after", after)):
    print(f"{name:<7} conflicts {count(vs, 'conflict')}, gaps {count(vs, 'partial')}, IT stricter "
          f"{count(vs, 'stricter')}, compliant {count(vs, 'compliant')} (all ITs of these requirements)")
(results / f"result_{args.tag}.json").write_text(json.dumps({"seconds": round(secs), "near_ctx": _Count.n, "rows": rows},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
