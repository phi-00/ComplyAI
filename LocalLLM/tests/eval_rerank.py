"""Reranker-only evaluation (no chat LLM, ~2 min on the GPU): does complyai.rerank.scores keep the IT text a
requirement must be compared with, including text that CONTRADICTS it, and drop IT text it should not be compared
with? Run it before any full GPU run when the reranker changes (docs/llm_options_evaluation.md, "Reranker").

1. Judge set (tests/fixtures/judge_set.json): each requirement vs all 56 IT variants. Its own 3 variants
   (compliant / conflict / partial) should pass RERANK_MIN, other items' variants should not.
2. Planted conflicts of tests/scenario.py (its database, data/test): WI 3600-11 vs "fill rate >= 98 %" and
   "tape 20 to 25 mm" must pass RERANK_MIN.
3. Cummins Supplier Handbook vs the real ITs (database opened read-only): which ITs reach the judge with the
   reranker off / on (the selection of engine.assess_requirements, replicated), scored on hand labels
   (tests/fixtures/rerank_labels_cummins.json: does the IT govern the same activity as the requirement?).

    python tests/eval_rerank.py [--db data/complyai.db] [--min 0.1]
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from complyai import config, rerank  # noqa: E402
from complyai.engine import _candidates, _hubs, _pick_its  # noqa: E402
from complyai.store import Store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", default=str(ROOT / "data" / "complyai.db"))
ap.add_argument("--min", type=float, default=config.RERANK_MIN, help="RERANK_MIN to evaluate")
args = ap.parse_args()
TH = args.min
t0 = time.time()


def ro(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


# 1. judge set
items = json.loads((ROOT / "tests" / "fixtures" / "judge_set.json").read_text(encoding="utf-8"))
variants = [(i, label, text) for i, it in enumerate(items) for label, text in it["variants"].items()]
pairs = [(f"{it['statement']}\n{it['quote']}", text) for it in items for _, _, text in variants]
S = np.array(rerank.scores(pairs)).reshape(len(items), len(variants))
own = np.array([[o == i for o, _, _ in variants] for i in range(len(items))])
conf = np.array([[o == i and lab == "conflict" for o, lab, _ in variants] for i in range(len(items))])
print(f"1. judge set at {TH}: own ITs kept {np.mean(S[own] >= TH):.0%}, conflict variants kept "
      f"{np.mean(S[conf] >= TH):.0%} (min {S[conf].min():.2f}), other items' ITs passed {np.mean(S[~own] >= TH):.0%}")

# 2. planted conflicts of the scenario
test_db = ROOT / "data" / "test" / "complyai.db"
if test_db.exists():
    db = ro(test_db)
    it = db.execute("SELECT id FROM documents WHERE code='WI 3600-11' ORDER BY id LIMIT 1").fetchone()
    texts = [r["text"] for r in db.execute("SELECT text FROM chunks WHERE doc_id=?", (it["id"],))]
    texts += [r["rule"] for r in db.execute("SELECT rule FROM it_rules WHERE doc_id=?", (it["id"],))]
    for like in ("%fill rate%98%", "%20 to 25%"):
        r = db.execute("SELECT statement, quote FROM requirements WHERE statement LIKE ? ORDER BY id DESC", (like,)).fetchone()
        if r:
            best = max(rerank.scores([(f"{r['statement']}\n{r['quote']}", t) for t in texts]))
            print(f"2. scenario conflict '{r['statement'][:60]}' vs WI 3600-11 v1: best {best:.2f} "
                  f"{'PASS' if best >= TH else 'FAIL (hidden from the judge)'}")
else:
    print("2. scenario database missing (run tests/scenario.py once)")

# 3. Cummins handbook vs the real ITs, on the hand labels
db = ro(args.db)
doc = db.execute("""SELECT id FROM documents WHERE kind='CSR' AND status='active' AND source_file LIKE 'Supplier Handbook%'
                    ORDER BY id DESC""").fetchone()
if not doc:
    sys.exit("3. Cummins handbook not in this database")
emb = lambda b: np.frombuffer(b, dtype=np.float32)  # noqa: E731
reqs = db.execute("SELECT * FROM requirements WHERE doc_id=? AND status='active' AND emb IS NOT NULL", (doc["id"],)).fetchall()
chunks = db.execute("""SELECT c.*, d.code it_code FROM chunks c JOIN documents d ON d.id=c.doc_id
                       WHERE d.kind='IT' AND d.status='active' AND c.emb IS NOT NULL""").fetchall()
rules = db.execute("""SELECT r.*, d.code it_code FROM it_rules r JOIN documents d ON d.id=r.doc_id
                      WHERE d.kind='IT' AND d.status='active' AND r.emb IS NOT NULL""").fetchall()
knowledge = {d["code"]: {"profile": json.loads(d["meta_json"] or "{}").get("profile", {})}
             for d in db.execute("SELECT code, meta_json FROM documents WHERE kind='IT' AND status='active'")}
R = np.vstack([emb(r["emb"]) for r in reqs])
hubs = _hubs(Store(args.db), chunks, rules)  # the engine's own retrieval and selection, reranker off and on
rerank_default = config.RERANK
config.RERANK_MIN = TH
off, on = {}, {}
for rerank_on, sel in ((False, off), (True, on)):
    config.RERANK = rerank_on
    cands, rel, _ = _candidates(reqs, R, chunks, rules, knowledge, hubs)
    for i, r in enumerate(reqs):
        sel[r["statement"]] = {code for code, _, _ in _pick_its(r, cands[i], rel[i], knowledge)}
config.RERANK = rerank_default
labels = [x for x in json.loads((ROOT / "tests" / "fixtures" / "rerank_labels_cummins.json").read_text(encoding="utf-8"))["labels"]
          if x["statement"] in off]
print(f"3. Cummins ({len(reqs)} requirements, {len(labels)} labelled requirement/IT pairs found): IT judgments "
      f"off {sum(map(len, off.values()))}, on {sum(map(len, on.values()))}")
# 2019 labels: pairs of alerts with the first 7 ITs; 2026-10-23 labels: a sample of the pairs the reranker drops /
# adds / keeps with the 34-IT database (25 / 25 / 20, unlabelled at the time)
for group, subset in (("all labels", labels),
                      ("first 7 ITs (2026-10-19)", [x for x in labels if not x["source"].startswith("2026-10-23")]),
                      ("34-IT sample (2026-10-23)", [x for x in labels if x["source"].startswith("2026-10-23")])):
    if not subset:
        continue
    print(f"   {group}:")
    for name, sel in (("reranker off", off), (f"reranker on at {TH}", on)):
        rel = [x for x in subset if x["relevant"]]
        unrel = [x for x in subset if not x["relevant"]]
        print(f"     {name:<20} judge sees: relevant {sum(x['it'] in sel[x['statement']] for x in rel)}/{len(rel)}, "
              f"unrelated {sum(x['it'] in sel[x['statement']] for x in unrel)}/{len(unrel)}")
print(f"({time.time() - t0:.0f}s)")
