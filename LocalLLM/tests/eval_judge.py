"""Score the requirement-vs-IT judge on the labelled set (tests/fixtures/judge_set.json).

For each item, a throwaway database holds 4 tiny ITs — compliant / conflict / partial variants of the
requirement's IT plus one unrelated IT (another item's compliant passage) — and the real engine pipeline
(IT profile + rules, retrieval, judge, numeric check, verification) assesses the requirement. Each item has its
own database, so the labels are unambiguous and the items run in parallel.

    python tests/eval_judge.py                 # full pipeline, current model setup
    python tests/eval_judge.py --no-verify     # without the verification pass (to measure its effect)
    python tests/eval_judge.py --model qwen3.5:4b --tag small                  # another model for every step
    python tests/eval_judge.py --judge-think --tag judge_think                 # reasoning mode for the judge too
    python tests/eval_judge.py --model qwen3.5:4b --think-model qwen3:8b       # small model + 8B reasoning verifier

Results are appended to data/judge_eval/results.jsonl (one line per run) for comparisons.
"""
import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--no-verify", action="store_true")
ap.add_argument("--limit", type=int)
ap.add_argument("--model", help="chat model for every step (default: COMPLYAI_CHAT_MODEL / qwen3:8b)")
ap.add_argument("--think-model", help="model for the reasoning-mode steps (verification)")
ap.add_argument("--judge-think", action="store_true", help="per-IT judge in reasoning mode too")
ap.add_argument("--rerank", action="store_true", help="cross-encoder reranker between retrieval and judge")
ap.add_argument("--workers", type=int, default=4, help="items assessed in parallel")
ap.add_argument("--tag", default="default", help="name of this run in results.jsonl")
args = ap.parse_args()
out_dir = ROOT / "data" / "judge_eval"
data_dir = out_dir / args.tag
shutil.rmtree(data_dir, ignore_errors=True)
os.environ["COMPLYAI_DATA"] = str(data_dir)
os.environ["COMPLYAI_VERIFY"] = "0" if args.no_verify else "1"
# The set's synthetic ITs were generated before the IT direction rule and often read as LEONI's own-supplier
# procedures ("O QM deve notificar o fornecedor"): with the filter on they never reach the judge this set measures.
os.environ["COMPLYAI_DIRECTION_FILTER"] = "0"
if args.model:
    os.environ["COMPLYAI_CHAT_MODEL"] = args.model
if args.think_model:
    os.environ["COMPLYAI_THINK_MODEL"] = args.think_model
if args.judge_think:
    os.environ["COMPLYAI_JUDGE_THINK"] = "1"
if args.rerank:
    os.environ["COMPLYAI_RERANK"] = "1"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import logging  # noqa: E402

from complyai import config, engine, llm  # noqa: E402
from complyai.store import Store, now, to_blob  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
config.IT_MAX_PER_REQ = 4  # all 4 test ITs are shown to the judge
LABELS = ["conflict", "partial", "compliant", "not_related"]

llm.check()
items = json.loads((ROOT / "tests" / "fixtures" / "judge_set.json").read_text(encoding="utf-8"))[:args.limit]
t0 = time.time()


def it_doc(code, title, text):
    return {"source_file": f"{code}.json", "synthetic": True, "pages": 1,
            "first_pages_text": f"{code}\nInstrução de Trabalho\n{title}\nVersão: 1",
            "chunks": [{"page": 1, "section": "1. Objetivo", "text": f"Definir {title.lower()}."},
                       {"page": 1, "section": "5. Realização", "text": text}]}


def run_item(i):
    """Ingest the item's 4 ITs into its own database (profile + rules built exactly as for real ITs), insert the
    requirement directly (this evaluates the judge, not the extraction) and assess it."""
    it = items[i]
    others = [j for j in range(len(items)) if j != i and items[j]["category"] != it["category"]]
    other = others[0] if others else (i + 1) % len(items)
    gold = {f"TEST {i:02d}-CONF": "conflict", f"TEST {i:02d}-PART": "partial",
            f"TEST {i:02d}-COMP": "compliant", f"TEST {other:02d}-COMP": "not_related"}
    texts = {f"TEST {i:02d}-{label[:4].upper()}": (it["it_title"], text) for label, text in it["variants"].items()}
    texts[f"TEST {other:02d}-COMP"] = (items[other]["it_title"], items[other]["variants"]["compliant"])
    store = Store(data_dir / f"item{i:02d}.db")
    for code, (title, text) in texts.items():
        engine.ingest_it(store, it_doc(code, title, text), code=code, version="1", title=title, recheck=False)
    doc_id = store.insert("documents", kind="CSR", code="JUDGE-SET", title="judge set", client=it["client"],
                          status="active", ingested_at=now(), meta_json="{}")
    v = llm.embed([f"{it['statement']}\n{it['quote']}"])[0]
    chunk = store.insert("chunks", doc_id=doc_id, idx=0, page=1, section="", text=it["quote"])
    rid = store.insert("requirements", doc_id=doc_id, chunk_id=chunk, client=it["client"], page=1, section="",
                       statement=it["statement"], quote=it["quote"], category=it["category"],
                       obligation="mandatory", parameters_json="[]", emb=to_blob(v))
    store.commit()
    engine.assess_requirements(store, [rid])
    got = {l["it_code"]: l["verdict"] for l in store.q(
        "SELECT it_code, verdict FROM req_it_links WHERE req_id=? AND source='text'", (rid,))}
    return i, gold, got


confusion = Counter()
details = []
with ThreadPoolExecutor(max_workers=args.workers) as ex:
    for i, gold, got in ex.map(run_item, range(len(items))):
        for code, g in gold.items():
            p = got.get(code, "not_related")  # not retrieved / not judged = no finding
            confusion[(g, p)] += 1
            details.append({"req": items[i]["statement"][:90], "it": code, "gold": g, "pred": p})
        print(f"{i + 1}/{len(items)} " + " ".join(f"{g[:4]}->{got.get(c, 'not_related')[:4]}" for c, g in gold.items()),
              flush=True)

# report
secs = time.time() - t0
setup = (f"chat={config.CHAT_MODEL}, reasoning={config.THINK_MODEL}"
         f"{', judge reasoning' if config.JUDGE_THINK else ''}{', reranker' if config.RERANK else ''}"
         f"{', no verification' if args.no_verify else ''}")
print(f"\n=== judge evaluation ({setup}, {len(items)} requirements, {secs:.0f}s) ===")
print("gold \\ predicted " + "".join(f"{l:>13}" for l in LABELS))
for g in LABELS:
    print(f"{g:<17}" + "".join(f"{confusion[(g, p)]:>13}" for p in LABELS))
flag = {"conflict", "partial"}
tp = sum(n for (g, p), n in confusion.items() if g in flag and p in flag)
fp = sum(n for (g, p), n in confusion.items() if g not in flag and p in flag)
fn = sum(n for (g, p), n in confusion.items() if g in flag and p not in flag)
exact = sum(n for (g, p), n in confusion.items() if g == p)
n = sum(confusion.values())
print(f"\nalerts (conflict+partial): precision {tp}/{tp + fp} = {tp / max(tp + fp, 1):.0%}, "
      f"recall {tp}/{tp + fn} = {tp / max(tp + fn, 1):.0%}")
print(f"conflicts found as conflict: {confusion[('conflict', 'conflict')]}/{len(items)}   "
      f"false alarms on compliant ITs: {sum(confusion[('compliant', p)] for p in flag)}/{len(items)}   "
      f"false alarms on unrelated ITs: {sum(confusion[('not_related', p)] for p in flag)}/{len(items)}")
print(f"exact label accuracy: {exact}/{n} = {exact / n:.0%}")
(data_dir / "judge_eval_details.json").write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
with open(out_dir / "results.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"tag": args.tag, "date": now(), "setup": setup, "items": len(items), "seconds": round(secs),
                         "precision": round(tp / max(tp + fp, 1), 3), "recall": round(tp / max(tp + fn, 1), 3),
                         "conflict_as_conflict": confusion[("conflict", "conflict")],
                         "false_alarms": fp, "exact": round(exact / n, 3),
                         "confusion": {f"{g}->{p}": c for (g, p), c in confusion.items()}}) + "\n")
