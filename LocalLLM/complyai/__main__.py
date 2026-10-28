"""Command line entry point — emulates what Leoni's server will trigger.

  python -m complyai check
  python -m complyai load-index Leoni/Leoni/WI_Indice_11_Rev199.xlsx Leoni/Leoni/IC_Indice_11_Rev113.xlsx
  python -m complyai ingest-it Leoni/Leoni/*.pdf [--no-recheck]   (bulk load: then `reassess` each document once)
  python -m complyai ingest-csr "Cliente/Cliente/18227_013.pdf" --client Cummins
  python -m complyai ingest-csr parsed.json            (a ParsedDocument saved with `parse --json`)
  python -m complyai parse <pdf> [--json out.json]      (show / save the parser output, no LLM)
  python -m complyai reassess <doc_id>                  (re-run only the IT comparison)
  python -m complyai it-knowledge                       (rebuild IT profiles + rules, e.g. after prompt changes)
  python -m complyai retry-failed <doc_id>              (re-extract passages whose extraction failed)
  python -m complyai translate <doc_id>                 (switch an already processed document to the output language)
  python -m complyai docs | findings | export <doc_id> | reset
"""
import argparse
import glob
import json
import logging
import sys
import time
from pathlib import Path

from . import config, engine, llm
from .catalog import load_index
from .export import export_matrix
from .parser import parse_pdf
from .store import Store


def _load(path: str) -> dict:
    """Accept a PDF or a ParsedDocument JSON (README "Parser contract")."""
    if path.lower().endswith(".json"):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_pdf(path)


def _expand(patterns):
    out = []
    for p in patterns:
        out.extend(sorted(glob.glob(p)) or [p])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="complyai")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("load-index"); p.add_argument("files", nargs="+")
    p = sub.add_parser("ingest-it"); p.add_argument("files", nargs="+")
    p.add_argument("--code"); p.add_argument("--version"); p.add_argument("--title")
    p.add_argument("--no-recheck", action="store_true",
                   help="do not re-assess existing requirements per IT (bulk loads: run `reassess` once per document)")
    p = sub.add_parser("ingest-csr"); p.add_argument("files", nargs="+")
    p.add_argument("--client"); p.add_argument("--code"); p.add_argument("--version"); p.add_argument("--title")
    p.add_argument("--max-chunks", type=int, help="only process the first N passages (quick tests)")
    p.add_argument("--no-export", action="store_true")
    sub.add_parser("docs")
    p = sub.add_parser("findings"); p.add_argument("--all", action="store_true", help="include info/low")
    p = sub.add_parser("export"); p.add_argument("doc_id", type=int)
    p = sub.add_parser("reassess", help="re-run the IT comparison for a document (no re-extraction)")
    p.add_argument("doc_id", type=int); p.add_argument("--no-export", action="store_true")
    p.add_argument("--changed-only", action="store_true",
                   help="only requirements whose ITs for the judge changed (after an IT-selection change; resumable)")
    p = sub.add_parser("translate", help="switch a processed document to the output language (no re-analysis)")
    p.add_argument("doc_id", type=int); p.add_argument("--no-export", action="store_true")
    sub.add_parser("reground", help="replace stored IT evidence that is not verbatim by the IT's own sentence, re-export")
    p = sub.add_parser("retry-failed", help="re-extract passages whose extraction failed, then assess them")
    p.add_argument("doc_id", type=int)
    p = sub.add_parser("it-knowledge", help="rebuild profiles + rules of all active ITs")
    p.add_argument("--profiles-only", action="store_true", help="only the profiles (fast), keep the rules")
    p = sub.add_parser("parse", help="parse a PDF and show its outline and passages (no LLM, no database)")
    p.add_argument("file"); p.add_argument("--json", help="write the ParsedDocument to this file")
    p.add_argument("--text", action="store_true", help="also print every passage")
    sub.add_parser("reset")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # Portuguese / German text on the Windows console

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if a.cmd == "reset":
        for f in (config.DB_PATH, config.NOTIFICATIONS_PATH):
            Path(f).unlink(missing_ok=True)
        print("database and notifications cleared")
        return
    if a.cmd == "check":
        print(json.dumps(llm.check(), indent=2))
        return
    if a.cmd == "parse":
        t = time.time()
        parsed = parse_pdf(a.file)
        if a.json:
            Path(a.json).write_text(json.dumps(parsed, ensure_ascii=False, indent=1), encoding="utf-8")
        chunks = parsed["chunks"]
        print(f"{parsed['source_file']}: {parsed['pages']} pages, {len(parsed['outline'])} headings, "
              f"{len(chunks)} passages ({sum(c['kind'] == 'table' for c in chunks)} mostly table), "
              f"{sum(len(c['text']) for c in chunks)} chars in {time.time() - t:.1f}s")
        print(f"removed: {json.dumps(parsed['stats'])}")
        for o in parsed["outline"]:
            print(f"  {'  ' * (o['level'] - 1)}{o['heading']}  (p.{o['page']})")
        if a.text:
            for i, c in enumerate(chunks):
                print(f"\n--- [{i}] p.{c['page']}-{c['page_end']} {c['kind']} | {' > '.join(c['path'])}\n{c['text']}")
        return

    store = Store()
    if a.cmd in ("load-index", "ingest-it", "ingest-csr"):
        llm.check()

    if a.cmd == "load-index":
        for f in _expand(a.files):
            print(f"{f}: {load_index(store, f)} ITs loaded into catalog")

    elif a.cmd == "ingest-it":
        for f in _expand(a.files):
            t = time.time()
            res = engine.ingest_it(store, _load(f), code=a.code, version=a.version, title=a.title,
                                   recheck=not a.no_recheck)
            print(f"{f}: {json.dumps(res, ensure_ascii=False)}  ({time.time() - t:.0f}s)")

    elif a.cmd == "ingest-csr":
        for f in _expand(a.files):
            t = time.time()
            res = engine.ingest_csr(store, _load(f), client=a.client, code=a.code, version=a.version,
                                    title=a.title, max_chunks=a.max_chunks)
            print(f"{f}: {json.dumps(res, ensure_ascii=False, default=list)}  ({time.time() - t:.0f}s)")
            if res.get("status") in ("ok", "resumed") and not a.no_export:
                print("  matrix ->", export_matrix(store, res["doc_id"]))

    elif a.cmd == "docs":
        for d in store.q("""SELECT d.*, (SELECT COUNT(*) FROM requirements r WHERE r.doc_id=d.id) nreq
                            FROM documents d ORDER BY kind, client, code, id"""):
            meta = json.loads(d["meta_json"] or "{}")
            pending = d["kind"] == "CSR" and not meta.get("assessed", True)
            sim = "[SIMULATED] " if meta.get("synthetic") else ""
            print(f"[{d['id']:>3}] {d['kind']:<3} {d['status']:<10} {d['client'] or '':<14} {d['code'] or '':<22} "
                  f"v{d['version'] or '-':<10} reqs={d['nreq']:<4} {sim}{d['title'] or ''}"[:160]
                  + ("  <- IT comparison incomplete: run `reassess`" if pending else ""))

    elif a.cmd == "findings":
        sev = "" if a.all else "WHERE severity IN ('high','medium')"
        for f in store.q(f"""SELECT * FROM findings {sev} ORDER BY
                             CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id"""):
            print(f"\n#{f['id']} [{f['severity'].upper()}] {f['type']} — {f['title']}\n  {f['detail']}"
                  + (f"\n  -> {f['action']}" if f["action"] else ""))

    elif a.cmd == "reassess":
        llm.check()
        t = time.time()
        n = engine.reassess_document(store, a.doc_id, changed_only=a.changed_only)
        print(f"{n} requirements re-assessed in {time.time() - t:.0f}s")
        if not a.no_export:
            print("  matrix ->", export_matrix(store, a.doc_id))

    elif a.cmd == "translate":
        llm.check()
        t = time.time()
        res = engine.translate_document(store, a.doc_id)
        print(f"{res['texts']} texts translated to {res['language']} in {time.time() - t:.0f}s")
        if not a.no_export:
            print("  matrix ->", export_matrix(store, a.doc_id))

    elif a.cmd == "reground":
        llm.check()
        print(f"{engine.reground_evidence(store)} evidence texts replaced by the IT's own sentence")
        for d in store.q("SELECT id FROM documents WHERE kind='CSR' AND status='active' ORDER BY id"):
            print("  matrix ->", export_matrix(store, d["id"]))

    elif a.cmd == "retry-failed":
        llm.check()
        n = engine.retry_failed_chunks(store, a.doc_id)
        print(f"{n} new requirements from previously failed passages")
        if n:
            print("  matrix ->", export_matrix(store, a.doc_id))

    elif a.cmd == "it-knowledge":
        llm.check()
        docs = store.q("SELECT * FROM documents WHERE kind='IT' AND status='active'")

        def rebuild(d):
            if not a.profiles_only:
                store.db.execute("DELETE FROM it_rules WHERE doc_id=?", (d["id"],))
            engine._build_it_knowledge(store, d["id"], d["code"], d["title"], profile_only=a.profiles_only)

        for _ in engine._pimap(rebuild, docs, "IT knowledge", workers=1 if not a.profiles_only else None):
            pass
        print("IT knowledge rebuilt; run `reassess <doc_id>` to apply it to existing requirements")

    elif a.cmd == "export":
        print(export_matrix(store, a.doc_id))


if __name__ == "__main__":
    sys.exit(main())
