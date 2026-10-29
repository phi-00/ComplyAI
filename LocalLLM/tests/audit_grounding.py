"""Grounding audit ("is the model locked to the given context?"): checks, without any LLM, how much of what the
model wrote is really in the source text it was given.

  requirements   quote found in its passage (>= 80 % of the words) / numbers of the statement in the passage
  IT rules       numbers of each extracted rule present in the IT passage it came from
  IT evidence    evidence quoted for a conflict / partial / compliant verdict found in that IT's own text
                 (the IT passages only, not the model-written rules)

    python tests/audit_grounding.py data/complyai.db
    python tests/audit_grounding.py --judge-runs          # every setup of tests/eval_judge.py, one line each
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from complyai.engine import _numbers_ok, _overlap as overlap  # noqa: E402


def audit(paths: list[Path]) -> dict:
    n = {k: [0, 0] for k in ("quote", "statement_numbers", "rule_numbers", "evidence")}
    bad = {k: [] for k in n}

    def count(key, ok, example):
        n[key][0] += bool(ok)
        n[key][1] += 1
        if not ok and len(bad[key]) < 5:
            bad[key].append(example)

    for path in paths:
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        chunk_text = {r["id"]: r["text"] for r in db.execute("SELECT id, text FROM chunks")}
        it_text = {}
        for r in db.execute("SELECT d.code, c.text FROM chunks c JOIN documents d ON d.id=c.doc_id WHERE d.kind='IT'"):
            it_text[r["code"]] = it_text.get(r["code"], "") + "\n" + r["text"]
        for r in db.execute("SELECT r.statement, r.quote, r.chunk_id FROM requirements r JOIN documents d "
                            "ON d.id=r.doc_id WHERE d.code != 'JUDGE-SET'"):
            src = chunk_text.get(r["chunk_id"], "")
            if r["quote"]:
                count("quote", overlap(r["quote"], src) >= 0.8, r["quote"][:120])
            count("statement_numbers", _numbers_ok(r["statement"], src), r["statement"][:120])
        for r in db.execute("SELECT rule, chunk_id FROM it_rules"):
            count("rule_numbers", _numbers_ok(r["rule"], chunk_text.get(r["chunk_id"], "")), r["rule"][:120])
        for r in db.execute("SELECT it_code, evidence FROM req_it_links WHERE source='text' AND "
                            "verdict IN ('conflict','partial','compliant') AND evidence != ''"):
            count("evidence", overlap(r["evidence"], it_text.get(r["it_code"], "")) >= 0.8, r["evidence"][:120])
    return {k: (ok, tot) for k, (ok, tot) in n.items()} | {"examples": bad}


def line(name: str, res: dict) -> str:
    def pct(k):
        ok, tot = res[k]
        return f"{ok}/{tot} ({ok / tot:.0%})" if tot else "-"
    return (f"{name:<28} quotes {pct('quote'):<16} statement numbers {pct('statement_numbers'):<16} "
            f"rule numbers {pct('rule_numbers'):<16} IT evidence {pct('evidence')}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--judge-runs"]:
        base = ROOT / "data" / "judge_eval"
        for d in sorted(p for p in base.iterdir() if p.is_dir() and list(p.glob("item*.db"))):
            print(line(d.name, audit(sorted(d.glob("item*.db")))))
    else:
        for p in sys.argv[1:]:
            res = audit([Path(p)])
            print(line(Path(p).parent.name + "/" + Path(p).name, res))
            for k, ex in res["examples"].items():
                for e in ex:
                    print(f"   not grounded ({k}): {e}")
