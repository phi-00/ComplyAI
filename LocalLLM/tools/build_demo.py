"""Build the DEMO database: real data + the synthetic ITs from tools/mock_its.py.

The real database (data/complyai.db) is never modified. The demo database lives in data/demo/ and every
result derived from a synthetic IT is labelled "[simulated IT]" / "*" (see README, "Mock data").

    python tools/build_demo.py             # copy real DB, add mock ITs, re-run the comparison of every CSR
    python tools/build_demo.py --resume    # continue an interrupted build without starting over

Then use the normal CLI on the demo database:  COMPLYAI_DATA=data/demo python -m complyai findings
"""
import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "demo"
ap = argparse.ArgumentParser()
ap.add_argument("--resume", action="store_true", help="keep the existing demo DB (skip ITs already loaded)")
ap.add_argument("--mock-dir", default=str(ROOT / "mock_data" / "its"))
args = ap.parse_args()

if not args.resume or not (DEMO / "complyai.db").exists():
    shutil.rmtree(DEMO, ignore_errors=True)
    DEMO.mkdir(parents=True)
    shutil.copy(ROOT / "data" / "complyai.db", DEMO / "complyai.db")
os.environ["COMPLYAI_DATA"] = str(DEMO)
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from complyai import engine, llm  # noqa: E402
from complyai.export import export_matrix  # noqa: E402
from complyai.store import Store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
llm.check()
store = Store()
t0 = time.time()

files = sorted(Path(args.mock_dir).glob("*.json"))
# a mock IT with the code of a real IT would supersede it as a "newer version": real ITs always win
real = {" ".join(d["code"].split()[:2]) for d in store.q("SELECT code, meta_json FROM documents WHERE kind='IT'")
        if not json.loads(d["meta_json"] or "{}").get("synthetic")}
loaded = 0
for k, f in enumerate(files, start=1):
    parsed = json.loads(f.read_text(encoding="utf-8"))
    code = parsed["generator"]["index_entry"]
    if code in real:
        logging.info("mock IT %d/%d %s: skipped, the real IT is loaded", k, len(files), code)
        continue
    res = engine.ingest_it(store, parsed, code=code, recheck=False)  # identical ones are skipped (resume)
    loaded += res["status"] == "ok"
    logging.info("mock IT %d/%d %s: %s", k, len(files), code, res["status"])
print(f"{loaded} mock ITs added ({time.time() - t0:.0f}s)")

# one comparison pass per customer document instead of one recheck per added IT
for d in store.q("SELECT id, code FROM documents WHERE kind='CSR' AND status='active'"):
    n = engine.reassess_document(store, d["id"])
    print(f"{d['code']}: {n} requirements re-assessed -> {export_matrix(store, d['id'])}")
print(f"demo database ready in {DEMO} ({time.time() - t0:.0f}s)")
