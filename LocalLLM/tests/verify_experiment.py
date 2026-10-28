"""Re-run only the verification step on the current findings with another model, to compare verifiers.

    python tests/verify_experiment.py --model qwen3:14b [--no-think] [--labels 14,34,23,24]

`--labels` = finding ids judged correct by a human; prints how many survive / are removed.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--no-think", action="store_true")
ap.add_argument("--labels", default="")
args = ap.parse_args()
os.environ["COMPLYAI_CHAT_MODEL"] = args.model
os.environ["COMPLYAI_VERIFY_THINK"] = "0" if args.no_think else "1"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np  # noqa: E402

from complyai import config, engine  # noqa: E402
from complyai.store import Store, from_blob, matrix  # noqa: E402

store = Store()
good = {int(x) for x in args.labels.split(",") if x}
findings = store.q("""SELECT f.*, l.verdict, l.explanation, l.evidence FROM findings f
                      JOIN req_it_links l ON l.req_id=f.req_id AND l.it_code=f.it_code AND l.source='text'
                      WHERE f.type IN ('CONFLICT','GAP')""")
knowledge = engine._it_knowledge(store)
rules = store.active_it_rules()
chunks = store.active_it_chunks()


def it_context(req, code):
    v = from_blob(req["emb"])
    rs = [r for r in rules if r["it_code"] == code]
    cs = [c for c in chunks if c["it_code"] == code]
    top_rules = [rs[j]["rule"] for j in np.argsort(-(matrix(rs) @ v))[:config.RULES_PER_IT]] if rs else []
    best = cs[int(np.argmax(matrix(cs) @ v))]
    k = knowledge[code]
    return {"code": code, "title": k["title"], "profile": k["profile"], "rules": top_rules,
            "excerpts": [{"page": best["page"], "section": best["section"],
                          "text": engine._with_context(store, best)}]}


def run(f):
    req = store.one("SELECT r.*, d.code doc FROM requirements r JOIN documents d ON d.id=r.doc_id WHERE r.id=?",
                    (f["req_id"],))
    a = {"verdict": f["verdict"], "explanation": f["explanation"] or "", "evidence": f["evidence"] or ""}
    return f, engine._verify(req, it_context(req, f["it_code"]), a)


kept, good_kept = [], []
for f, out in engine._pmap(run, findings, "verify"):
    keep = out["verdict"] in ("conflict", "partial")
    if keep:
        kept.append(f["id"])
        if f["id"] in good:
            good_kept.append(f["id"])
    tag = "GOOD " if f["id"] in good else "     "
    print(f"{tag}#{f['id']:<4} {f['verdict']:>8} -> {out['verdict']:<11} {f['it_code']}")
print(f"\n{args.model} think={not args.no_think}: kept {len(kept)}/{len(findings)}"
      + (f", correct kept {len(good_kept)}/{len(good)}, precision of kept {len(good_kept)}/{len(kept)}"
         if good else ""))
