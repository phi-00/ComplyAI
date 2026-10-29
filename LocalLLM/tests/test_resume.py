"""Interrupted-ingestion recovery (power cut during a run). Needs Ollama; takes ~1 min.

    python tests/test_resume.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["COMPLYAI_DATA"] = tempfile.mkdtemp(prefix="complyai_resume_")
sys.path.insert(0, str(ROOT))

from complyai import engine  # noqa: E402
from complyai.store import Store, now  # noqa: E402

parsed = json.loads((ROOT / "tests" / "fixtures" / "JD_DLW20803_revA.json").read_text(encoding="utf-8"))
parsed["chunks"] = parsed["chunks"][:1]
store = Store()
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


# 1. a document left in 'processing' by a power cut is purged and redone, not skipped
ghost = store.insert("documents", kind="CSR", code="DLW20803", client="John Deere", file_hash=engine._hash(parsed),
                     status="processing", ingested_at=now(), meta_json="{}")
store.insert("chunks", doc_id=ghost, idx=0, page=1, section="", text="half-written")
store.commit()
res = engine.ingest_csr(store, parsed)
check("half-ingested document is redone", res["status"] == "ok" and res["requirements"] > 0)
check("ghost document's partial data is gone",  # (SQLite may reuse the ghost's id for the new document)
      not store.one("SELECT 1 FROM chunks WHERE text='half-written'") and
      store.one("SELECT COUNT(*) n FROM documents")["n"] == 1)

# 2. interrupted during the IT comparison -> running the same file again resumes the comparison
engine._set_meta(store, res["doc_id"], assessed=False)
store.commit()
res2 = engine.ingest_csr(store, parsed)
check("interrupted comparison is resumed", res2["status"] == "resumed" and res2["doc_id"] == res["doc_id"])

# 3. a complete document is skipped
check("complete document is skipped", engine.ingest_csr(store, parsed)["status"] == "skipped")
check("exactly one copy of the document", store.one("SELECT COUNT(*) n FROM documents")["n"] == 1)
sys.exit(0 if ok else 1)
