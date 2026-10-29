"""Throughput benchmark of the IT-comparison step at different concurrency levels.

Runs on a COPY of data/complyai.db (needs a CSR already ingested). The Ollama server must be started
with OLLAMA_NUM_PARALLEL >= the highest level tested.

    python tests/bench.py --levels 1 2 4 --n 16
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4])
ap.add_argument("--n", type=int, default=16, help="requirements per level")
args = ap.parse_args()

bench_dir = ROOT / "data" / "bench"
bench_dir.mkdir(parents=True, exist_ok=True)
shutil.copy(ROOT / "data" / "complyai.db", bench_dir / "complyai.db")
os.environ["COMPLYAI_DATA"] = str(bench_dir)
sys.path.insert(0, str(ROOT))

from complyai import config, engine  # noqa: E402
from complyai.store import Store  # noqa: E402

store = Store()
ids = [r["id"] for r in store.q("SELECT id FROM requirements WHERE status='active' ORDER BY id")]
engine.assess_requirements(store, ids[:2])  # warm-up: loads both models into VRAM

offset = 2
print(f"{'parallel':>8} {'reqs':>5} {'total s':>8} {'s/req':>6} {'req/min':>8}")
for level in args.levels:
    batch = ids[offset:offset + args.n]
    offset += args.n
    config.LLM_WORKERS = level
    t = time.time()
    engine.assess_requirements(store, batch)
    dt = time.time() - t
    print(f"{level:>8} {len(batch):>5} {dt:>8.1f} {dt / len(batch):>6.2f} {60 * len(batch) / dt:>8.1f}", flush=True)
