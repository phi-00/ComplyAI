"""ComplyAI engine: everything the server calls.

    ingest_it(parsed)    store/refresh a Leoni IT, re-check requirements it may affect
    ingest_csr(parsed)   extract requirements from a customer doc, detect changes vs older
                         requirements of the same customer, assess them against the ITs

`parsed` is the parser output (complyai/parser.py, README "Parser contract").
"""
import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import config, llm, prompts, rerank
from .store import Store, matrix, now, to_blob

log = logging.getLogger("complyai")

# Cheap pre-filter: only passages with obligation language go to the LLM for extraction.
OBLIGATION_RE = re.compile(
    r"\b(shall|must|required?|requires|should|expected|is to be|are to be|not (be )?permitted|prohibited|"
    r"deve|devem|deverá|deverão|obrigat[óo]ri|exig|requer|necess[áa]ri|n[ãa]o é permitid|proibid|"
    r"muss|müssen|soll|sollen|ist zu|sind zu|darf|dürfen|erforderlich|verboten|pflicht)",
    re.I)


def _pimap(fn, items, label="", workers=None):
    """Run LLM calls concurrently (Ollama batches up to OLLAMA_NUM_PARALLEL of them) and yield the results
    in order as soon as they are ready, logging progress."""
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers or config.LLM_WORKERS) as ex:
        for i, res in enumerate(ex.map(fn, items), start=1):
            if label and (i % 10 == 0 or i == len(items)):
                log.info("%s: %d/%d (%.0fs)", label, i, len(items), time.time() - t0)
            yield res


def _pmap(fn, items, label="", workers=None):
    return list(_pimap(fn, items, label, workers))


def _hash(parsed: dict) -> str:
    h = hashlib.sha256()
    for c in parsed["chunks"]:
        h.update(c["text"].encode("utf-8"))
    return h.hexdigest()


def extract_metadata(parsed: dict) -> dict:
    text = parsed.get("first_pages_text") or "\n".join(c["text"] for c in parsed["chunks"][:4])
    try:
        return llm.chat_json(prompts.META_SYSTEM, f"File name: {parsed['source_file']}\n\n{text[:6000]}",
                             prompts.META_SCHEMA)
    except llm.LLMError as e:
        log.warning("metadata extraction failed: %s", e)
        return {}


def _windows(chunks: list[dict], size: int = config.IT_WINDOW_CHARS) -> list[dict]:
    """Split chunks into sentence-aligned windows of ~size chars: small passages embed much more
    precisely (one topic each), which matters for retrieval inside long ITs."""
    out = []
    for c in chunks:
        sentences = re.split(r"(?<=[.;:!?])\s+|\n|\s+(?=\d+(?:\.\d+)+\s*[–-]?\s)", c["text"])
        buf = ""
        for s in sentences:
            if buf and len(buf) + len(s) > size:
                out.append({**c, "text": buf.strip()})
                buf = ""
            buf += " " + s
        if buf.strip():
            out.append({**c, "text": buf.strip()})
    return out


def _normalize(parsed: dict) -> dict:
    """Fill the optional fields of the parser contract (README), so generated / hand-made ParsedDocuments
    (mock ITs, tests) only need page, section and text per chunk."""
    chunks = []
    for c in parsed["chunks"]:
        path = c.get("path") or ([c["section"]] if c.get("section") else [])
        chunks.append({**c, "section": c.get("section") or (path[-1] if path else ""), "path": path,
                       "kind": c.get("kind") or "text", "page_end": c.get("page_end") or c["page"]})
    outline = parsed.get("outline")
    if outline is None:
        first_page = {}
        for c in chunks:
            first_page.setdefault(c["section"], c["page"])
        outline = [{"level": 1, "heading": s, "page": p} for s, p in first_page.items() if s]
    return {**parsed, "chunks": chunks, "outline": outline}


def where(c) -> str:
    """'K. Competência (7.2) > Formação no posto': the heading path of a chunk, for prompts."""
    path = json.loads(c["path"] or "[]") if isinstance(c["path"], (str, type(None))) else c["path"]
    return " > ".join(path or ([c["section"]] if c["section"] else []))


def _store_chunks(store: Store, doc_id: int, chunks: list[dict], outline: list[dict]):
    embs = llm.embed([f"{' > '.join(c['path']) or c['section']}\n{c['text']}" for c in chunks])
    for i, (c, v) in enumerate(zip(chunks, embs)):
        store.insert("chunks", doc_id=doc_id, idx=i, page=c["page"], page_end=c["page_end"], section=c["section"],
                     path=json.dumps(c["path"], ensure_ascii=False), top_section=c["path"][0] if c["path"] else "",
                     kind=c["kind"], text=c["text"], emb=to_blob(v))
    for i, o in enumerate(outline):
        store.insert("outline", doc_id=doc_id, idx=i, level=o["level"], heading=o["heading"], page=o["page"])


# =============================================================================================
# ITs
# =============================================================================================
def _it_code_from(parsed: dict) -> str | None:
    """'WI-3234-11-A1.pdf' -> 'WI 3234-11 A1'; central LEONI procedures have no plant suffix:
    'VA-3160-A2_....pdf' -> 'VA 3160 A2'. Falls back to the first page text."""
    first = parsed.get("first_pages_text", "")
    for src in (parsed["source_file"], first[:500]):
        found = [m for m in (re.search(r"\b(WI|IT|IC|PI)[\s_-]*(\d)\s?(\d{3})\s*-\s*(\d{2})(?:[\s_-]*(A\d+))?", src, re.I),
                             re.search(r"\b(VA|PI)[\s_-]*(\d)\s?(\d{3})()(?!\d)(?:[\s_-]*(A\d+))?", src, re.I)) if m]
        if not found:
            continue
        m = min(found, key=lambda m: m.start())  # 'VA-3160-A2_associado a WI-3550-11': the first code names the file
        prefix = m.group(1).upper()
        prefix = "WI" if prefix == "IT" else prefix  # "IT 3234-11" is the PT name of WI 3234-11
        code = f"{prefix} {m.group(2)}{m.group(3)}" + (f"-{m.group(4)}" if m.group(4) else "")
        annex = m.group(5)
        # "IT 3234-11 \n Anexo 1 (02.21)" — only right after the code (the template header
        # "P4000 Anexo 3" must not count)
        if not annex and src is not parsed["source_file"]:
            if a := re.match(r"[^\n]{0,30}\n?\s*Anexo\s*(\d+)", src[m.end():]):
                annex = f"A{a.group(1)}"
        return f"{code} {annex.upper()}" if annex else code
    return None


def ingest_it(store: Store, parsed: dict, code: str | None = None, version: str | None = None,
              title: str | None = None, recheck: bool = True) -> dict:
    """recheck=False skips re-assessing existing requirements (bulk loads: run reassess once at the end).
    parsed["synthetic"]=True marks a generated mock IT: everything derived from it is labelled as such."""
    parsed = _normalize(parsed)
    file_hash = _hash(parsed)
    existing = store.one("SELECT * FROM documents WHERE file_hash=? AND kind='IT'", (file_hash,))
    if existing and existing["status"] != "processing":
        return {"status": "skipped", "reason": "identical IT already ingested"}
    if existing:  # left half-done by an interruption (power cut...): start over
        log.warning("IT %s was interrupted during ingestion, redoing it", existing["code"])
        _purge_document(store, existing["id"])

    code = code or _it_code_from(parsed)
    base_code = " ".join(code.split()[:2]) if code else None
    cat = store.one("SELECT * FROM it_catalog WHERE code=?", (base_code,)) if base_code else None
    meta = {}
    if not code or not (title or cat):
        meta = extract_metadata(parsed)
        code = code or meta.get("code") or Path(parsed["source_file"]).stem
    if not version:
        m = re.search(r"Vers[ãa]o:\s*([\w.]+)|\(Rev\.?\s*([\d.]+)\)|Anexo\s*\d+\s*\(([\d.]+)\s*\)",
                      parsed.get("first_pages_text", "")[:1500])
        version = (next(g for g in m.groups() if g) if m
                   else meta.get("version") or (cat["revision"] if cat else None))
    title = title or (cat["title"] if cat else None) or meta.get("title") or code
    if parsed.get("synthetic"):
        meta["synthetic"] = True
    if code.endswith(tuple(f"A{i}" for i in range(1, 30))) and cat:
        title = f"{cat['title']} — Anexo {code.split()[-1][1:]}"

    previous = store.q("SELECT * FROM documents WHERE kind='IT' AND code=? AND status='active'", (code,))
    doc_id = store.insert("documents", kind="IT", code=code, title=title, client="LEONI", version=version,
                          source_file=parsed["source_file"], file_hash=file_hash, ingested_at=now(),
                          status="processing", meta_json=json.dumps(meta, ensure_ascii=False))
    _store_chunks(store, doc_id, _windows(parsed["chunks"]), parsed["outline"])
    _build_it_knowledge(store, doc_id, code, title)
    for p in previous:
        store.update("documents", p["id"], status="superseded", superseded_by=doc_id)
    store.update("documents", doc_id, status="active")
    store.commit()

    if previous:
        store.add_finding(type="IT_UPDATED", severity="info", client="LEONI", it_code=code, doc_id=doc_id,
                          title=f"{code} updated to version {version}",
                          detail=f"Previous version: {previous[0]['version']}. Requirements linked to this IT were re-assessed.")
    rechecked = recheck_for_it(store, code, doc_id) if recheck else 0
    store.commit()
    log.info("IT %s v%s ingested (%d chunks), %d requirements re-assessed", code, version,
             len(parsed["chunks"]), rechecked)
    return {"status": "ok", "doc_id": doc_id, "code": code, "version": version, "title": title,
            "chunks": len(parsed["chunks"]), "superseded": [p["id"] for p in previous],
            "requirements_rechecked": rechecked}


def _build_it_knowledge(store: Store, doc_id: int, code: str, title: str, profile_only: bool = False):
    """Done ONCE per IT version: a profile (what the IT governs, scope, trigger, direction) and the list of
    concrete rules of every passage, embedded for retrieval. Comparisons then work on these instead of raw text."""
    chunks = store.q("SELECT * FROM chunks WHERE doc_id=? ORDER BY idx", (doc_id,))
    text = "\n".join(c["text"] for c in chunks)[:5000]
    try:
        profile = llm.chat_json(prompts.IT_PROFILE_SYSTEM, prompts.it_profile_user(code, title, text),
                                prompts.IT_PROFILE_SCHEMA, max_tokens=600)
    except llm.LLMError as e:
        log.warning("IT profile failed for %s: %s", code, e)
        profile = {}
    meta = json.loads(store.one("SELECT meta_json FROM documents WHERE id=?", (doc_id,))["meta_json"] or "{}")
    store.update("documents", doc_id, meta_json=json.dumps({**meta, "profile": profile}, ensure_ascii=False))
    if profile_only:
        store.commit()
        return

    def rules_of(c):
        try:
            out = llm.chat_json(prompts.IT_RULES_SYSTEM, prompts.it_rules_user(code, title, where(c), c["text"]),
                                prompts.IT_RULES_SCHEMA, max_tokens=900)
            rules = [r.strip() for r in out.get("rules", []) if r.strip()]
            # context lock: a rule with a number the passage does not contain was not read from the IT
            grounded = [r for r in rules if _numbers_ok(r, c["text"])]
            if len(grounded) < len(rules):
                log.warning("IT %s: %d rule(s) with numbers not in the IT text dropped", code, len(rules) - len(grounded))
            return c, grounded
        except llm.LLMError:
            return c, []

    pairs = [(c, rule) for c, rules in _pmap(rules_of, chunks) for rule in rules]
    embs = llm.embed([rule for _, rule in pairs]) if pairs else []
    for (c, rule), v in zip(pairs, embs):
        store.insert("it_rules", doc_id=doc_id, chunk_id=c["id"], rule=rule, emb=to_blob(v))
    store.commit()
    log.info("IT %s: profile + %d rules extracted", code, len(pairs))


def _it_knowledge(store: Store) -> dict[str, dict]:
    """code -> {profile, title, doc_id} for every active IT."""
    out = {}
    for d in store.q("SELECT * FROM documents WHERE kind='IT' AND status='active'"):
        meta = json.loads(d["meta_json"] or "{}")
        out[d["code"]] = {"title": d["title"], "doc_id": d["id"], "profile": meta.get("profile", {}),
                          "synthetic": bool(meta.get("synthetic"))}
    return out


def recheck_for_it(store: Store, it_code: str, it_doc_id: int) -> int:
    """Re-assess active requirements that were linked to this IT or are semantically close to it."""
    reqs = store.q("SELECT * FROM requirements WHERE status='active' AND emb IS NOT NULL")
    if not reqs:
        return 0
    # only active requirements: superseded ones document the history and must keep their old verdicts
    linked = {r["req_id"] for r in store.q(
        """SELECT DISTINCT l.req_id FROM req_it_links l JOIN requirements r ON r.id=l.req_id
           WHERE l.it_code=? AND l.source='text' AND r.status='active'""", (it_code,))}
    it_chunks = store.q("SELECT emb FROM chunks WHERE doc_id=?", (it_doc_id,))
    sims = matrix(reqs) @ matrix(it_chunks).T
    close = {reqs[i]["id"] for i in np.where(sims.max(axis=1) >= config.IT_MIN_SIM)[0]}
    ids = sorted(linked | close)
    assess_requirements(store, ids)
    return len(ids)


# =============================================================================================
# Customer documents (CSR / STD)
# =============================================================================================
def ingest_csr(store: Store, parsed: dict, client: str | None = None, code: str | None = None,
               version: str | None = None, title: str | None = None, max_chunks: int | None = None) -> dict:
    parsed = _normalize(parsed)
    file_hash = _hash(parsed)
    existing = store.one("SELECT * FROM documents WHERE file_hash=? AND kind='CSR'", (file_hash,))
    if existing and existing["status"] == "processing":  # interrupted before requirements were complete
        log.warning("%s was interrupted during extraction, redoing it", existing["code"])
        _purge_document(store, existing["id"])
    elif existing and not json.loads(existing["meta_json"] or "{}").get("assessed", True):
        log.warning("%s was interrupted during the IT comparison, resuming it", existing["code"])
        reassess_document(store, existing["id"])
        return {"status": "resumed", "doc_id": existing["id"], "reason": "IT comparison completed"}
    elif existing:
        return {"status": "skipped", "reason": "identical document already ingested"}

    meta = extract_metadata(parsed)
    client = _canonical_client(store, client or meta.get("client") or "Desconhecido")
    code = _base_code(code or _doc_code(meta.get("code"), parsed["source_file"], parsed.get("first_pages_text", "")))
    version = version or meta.get("version") or meta.get("date")
    title = title or meta.get("title") or parsed["source_file"]

    previous = store.q("SELECT * FROM documents WHERE kind='CSR' AND client=? AND code=? AND status='active'",
                       (client, code))
    doc_id = store.insert("documents", kind="CSR", code=code, title=title, client=client, version=version,
                          doc_date=meta.get("date"), language=meta.get("language"),
                          source_file=parsed["source_file"], file_hash=file_hash, ingested_at=now(),
                          status="processing", meta_json=json.dumps({**meta, "assessed": False}, ensure_ascii=False))
    chunks = parsed["chunks"][:max_chunks] if max_chunks else parsed["chunks"]
    _store_chunks(store, doc_id, chunks, parsed["outline"])
    store.commit()
    chunk_rows = store.q("SELECT * FROM chunks WHERE doc_id=? ORDER BY idx", (doc_id,))

    # 1) requirement extraction (LLM, only passages with obligation language)
    todo = [c for c in chunk_rows if OBLIGATION_RE.search(c["text"])]
    log.info("%s: %d/%d passages contain obligation language", code, len(todo), len(chunk_rows))

    extracted, embs = _extract_requirements(store, todo, client, f"{code} {title}")
    new_ids = []
    for (c, r), v in zip(extracted, embs):
        new_ids.append(store.insert(
            "requirements", doc_id=doc_id, chunk_id=c["id"], client=client, page=c["page"], section=c["section"],
            statement=r["statement"].strip(), quote=r.get("quote", "").strip(), category=r.get("category"),
            obligation=r.get("obligation"), parameters_json=json.dumps(r.get("parameters", []), ensure_ascii=False),
            quality_note=r.get("quality_note"), emb=to_blob(v)))
    store.commit()
    log.info("%s: %d requirements extracted", code, len(new_ids))

    # 2) change detection vs older requirements of the same customer
    changes = detect_changes(store, doc_id, client, [p["id"] for p in previous])
    cross_document_check(store, doc_id, exclude_doc_ids=[p["id"] for p in previous])
    for p in previous:
        store.update("documents", p["id"], status="superseded", superseded_by=doc_id)
    # requirements + change detection are complete: the document is usable even if the comparison below
    # gets interrupted ("assessed": false -> re-running the same file or `reassess` finishes it)
    store.update("documents", doc_id, status="active")
    store.commit()

    # 3) conflict / compliance assessment against ITs (unchanged ones inherit previous links)
    to_assess = [rid for rid in new_ids if rid not in changes["unchanged"]]
    _copy_links(store, changes["unchanged"])
    assess_requirements(store, to_assess)
    map_sections(store, doc_id)
    _set_meta(store, doc_id, assessed=True)
    store.commit()

    counts = {r["type"]: r["n"] for r in store.q(
        "SELECT type, COUNT(*) n FROM findings WHERE doc_id=? GROUP BY type", (doc_id,))}
    return {"status": "ok", "doc_id": doc_id, "client": client, "code": code, "version": version, "title": title,
            "chunks": len(chunk_rows), "requirements": len(new_ids),
            "unchanged": len(changes["unchanged"]), "modified": changes["modified"], "new": changes["new"],
            "removed": changes["removed"], "superseded_docs": [p["id"] for p in previous], "findings": counts}


def _extract_from_text(client: str, doc_label: str, c, text: str, depth: int = 0) -> list[dict]:
    """LLM extraction of one passage. A passage with more requirements than fit in one answer is split at a
    sentence boundary and each half is extracted (instead of losing the whole passage)."""
    try:
        out = llm.chat_json(prompts.EXTRACT_SYSTEM,
                            prompts.extract_user(client, doc_label, where(c), c["page"], text),
                            prompts.EXTRACT_SCHEMA, max_tokens=config.EXTRACT_MAX_TOKENS)
        return out.get("requirements", [])
    except llm.TruncatedError:
        sentences = _split_sentences(text)
        if depth >= 2 or len(sentences) < 2:
            raise
        half = len(sentences) // 2
        log.info("passage %s too dense, extracting it in two halves", c["id"])
        return (_extract_from_text(client, doc_label, c, " ".join(sentences[:half]), depth + 1)
                + _extract_from_text(client, doc_label, c, " ".join(sentences[half:]), depth + 1))


def _extract_requirements(store: Store, chunks: list, client: str, doc_label: str):
    """Extraction + filtering + number grounding + de-duplication for a list of passages.
    Passages whose extraction fails are marked (chunks.extract_failed) so `retry-failed` can redo them."""
    def extract(c):
        try:
            reqs = _extract_from_text(client, doc_label, c, c["text"])
            return c, reqs, False
        except llm.LLMError as e:
            log.warning("extraction failed on chunk %s: %s", c["id"], e)
            return c, [], True

    raw = []
    for c, rs, failed in _pimap(extract, chunks, "extraction"):
        store.db.execute("UPDATE chunks SET extract_failed=? WHERE id=?", (int(failed), c["id"]))
        raw.extend((c, r) for r in rs if r.get("statement", "").strip())
    store.commit()
    extracted = [(c, r) for c, r in raw if r.get("kind", "supplier_requirement") == "supplier_requirement"]
    log.info("%s: %d items extracted, %d kept as supplier requirements (definitions/informative dropped)",
             doc_label[:40], len(raw), len(extracted))
    extracted = _ground_numbers(_ground_quotes(extracted))
    # statement (LEONI language) + original quote (customer terminology) -> better cross-lingual retrieval
    embs = llm.embed([f"{r['statement']}\n{r.get('quote', '')}" for _, r in extracted])
    return _dedupe(extracted, embs)


def retry_failed_chunks(store: Store, doc_id: int) -> int:
    """Re-extract the passages of a document whose extraction failed (LLM error, interruption) and assess the
    requirements found. Returns the number of new requirements."""
    doc = store.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    chunks = store.q("SELECT * FROM chunks WHERE doc_id=? AND extract_failed=1 ORDER BY idx", (doc_id,))
    if not chunks:
        return 0
    extracted, embs = _extract_requirements(store, chunks, doc["client"], f"{doc['code']} {doc['title']}")
    existing = store.q("SELECT * FROM requirements WHERE doc_id=?", (doc_id,))
    new_ids = []
    E = matrix(existing) if existing else None
    for (c, r), v in zip(extracted, embs):
        if E is not None and float((E @ v).max()) >= 0.95:
            continue  # already extracted from an overlapping passage
        new_ids.append(store.insert(
            "requirements", doc_id=doc_id, chunk_id=c["id"], client=doc["client"], page=c["page"],
            section=c["section"], statement=r["statement"].strip(), quote=r.get("quote", "").strip(),
            category=r.get("category"), obligation=r.get("obligation"), change_type="new",
            parameters_json=json.dumps(r.get("parameters", []), ensure_ascii=False),
            quality_note=r.get("quality_note"), emb=to_blob(v)))
    store.commit()
    assess_requirements(store, new_ids)
    cross_document_check(store, doc_id)
    map_sections(store, doc_id)
    return len(new_ids)


def reassess_document(store: Store, doc_id: int, changed_only: bool = False) -> int:
    """Re-run the IT comparison for all active requirements of a document (no re-extraction). changed_only: only
    those whose ITs for the judge changed (after a change to the IT selection; running it again resumes)."""
    ids = [r["id"] for r in store.q("SELECT id FROM requirements WHERE doc_id=? AND status='active'", (doc_id,))]
    if changed_only:
        ids = selection_changed(store, ids)
        log.info("document %s: %d requirements see other ITs than in their stored assessment", doc_id, len(ids))
    _set_meta(store, doc_id, assessed=False)
    store.commit()
    assess_requirements(store, ids)
    map_sections(store, doc_id)
    _set_meta(store, doc_id, assessed=True)
    store.commit()
    return len(ids)


def map_sections(store: Store, doc_id: int) -> int:
    """Section-level IT mapping, the way LEONI's correspondence matrix is built: per top-level section,
    one reasoning-mode call sees the heading, its requirements and the pooled IT candidates."""
    doc = store.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    reqs = [dict(r) for r in store.q("SELECT * FROM requirements WHERE doc_id=? AND status='active' ORDER BY id",
                                     (doc_id,))]
    cat = store.q("SELECT * FROM it_catalog")
    if not reqs or not cat:
        return 0
    parents = _parent_sections(store, {doc_id})
    for r in reqs:
        r["parent_section"] = parents.get(r["chunk_id"], "")
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(reqs):
        groups.setdefault(r["parent_section"] or r["section"] or "(sem secção)", []).append(i)

    R = matrix(reqs)
    CS = R @ matrix(cat).T
    headings = list(groups)
    heading_row = {h: k for k, h in enumerate(headings)}
    HS = llm.embed(headings) @ matrix(cat).T
    by_code = {c["code"]: c for c in cat}

    jobs = []
    for heading, idxs in groups.items():
        votes: dict[str, list[float]] = {}
        for i in idxs:
            r = {**reqs[i], "parent_section": heading}
            for c in _index_candidates(r, i, {}, cat, CS, HS, heading_row):
                votes.setdefault(c["code"], []).append(c["score"])
            for l in store.q("""SELECT it_code FROM req_it_links WHERE req_id=? AND
                                (source='catalog' OR verdict IN ('conflict','partial','compliant'))""", (reqs[i]["id"],)):
                base = " ".join(l["it_code"].split()[:2])
                if base in by_code:
                    votes.setdefault(base, []).append(1.0)  # chosen by the per-requirement judge: strong vote
        ranked = sorted(votes, key=lambda c: (-len(votes[c]), -max(votes[c])))[:config.SECTION_CANDIDATES]
        cands = [{"code": c, "title": by_code[c]["title"], "iso": by_code[c]["iso_clause"]} for c in ranked]
        statements = [reqs[i]["statement"][:180] for i in idxs[:config.SECTION_MAX_STATEMENTS]]
        jobs.append((heading, statements, cands))

    def pick(job):
        heading, statements, cands = job
        if not cands:
            return job, []
        try:
            out = llm.chat_json(prompts.SECTION_SYSTEM,
                                prompts.section_user(doc["client"], doc["code"], heading, statements, cands),
                                prompts.section_schema([c["code"] for c in cands]),
                                max_tokens=config.VERIFY_MAX_TOKENS, think=config.VERIFY_THINK)
            return job, out.get("selected", [])
        except llm.LLMError as e:
            log.warning("section mapping failed for %r: %s", heading, e)
            return job, None

    n = 0
    for (heading, _, _), selected in _pimap(pick, jobs, "section mapping"):
        if selected is None:
            continue  # keep the previous mapping of this section
        store.db.execute("DELETE FROM section_its WHERE doc_id=? AND section=?", (doc_id, heading))
        for s in {s["it_code"]: s for s in selected if s.get("it_code") in by_code}.values():
            store.insert("section_its", doc_id=doc_id, section=heading, it_code=s["it_code"], reason=s["reason"])
            n += 1
    store.commit()
    log.info("section mapping: %d ITs over %d sections", n, len(jobs))
    return n


def _set_meta(store: Store, doc_id: int, **kv):
    meta = json.loads(store.one("SELECT meta_json FROM documents WHERE id=?", (doc_id,))["meta_json"] or "{}")
    store.update("documents", doc_id, meta_json=json.dumps({**meta, **kv}, ensure_ascii=False))


def _purge_document(store: Store, doc_id: int):
    """Remove a document and everything derived from it (used for half-ingested documents)."""
    req_ids = [r["id"] for r in store.q("SELECT id FROM requirements WHERE doc_id=?", (doc_id,))]
    for rid in req_ids:
        store.db.execute("DELETE FROM req_it_links WHERE req_id=?", (rid,))
    store.db.execute("DELETE FROM findings WHERE doc_id=?", (doc_id,))
    for table in ("requirements", "chunks", "it_rules", "section_its", "outline", "section_labels"):
        store.db.execute(f"DELETE FROM {table} WHERE doc_id=?", (doc_id,))
    store.db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    store.commit()


_MONTH_YEAR = re.compile(r"^(jan|feb|fev|mar|apr|abr|may|mai|jun|jul|aug|ago|sep|set|oct|out|nov|dec|dez)\w*\d{4}$",
                         re.I)


def _doc_code(meta_code: str | None, source_file: str, first_text: str) -> str:
    """Document number. The LLM sometimes picks another number from the title block (Cummins '18227_013.pdf'
    -> '212020-011'); when the file name carries an identifier that also appears on the first page and the
    LLM's code does not contain it, the file name's identifier wins."""
    stem = Path(source_file).stem
    candidates = [t for t in re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", stem)
                  if re.search(r"\d", t) and len(t) >= 4 and not re.fullmatch(r"(19|20)\d\d", t)
                  and not _MONTH_YEAR.match(t)]
    meta_code = (meta_code or "").strip()
    norm = lambda s: re.sub(r"[\s_-]", "", s).lower()
    if meta_code and any(norm(t) in norm(meta_code) or norm(meta_code) in norm(t) for t in candidates):
        return meta_code
    for t in candidates:
        if t in first_text:
            return t
    return meta_code or stem


def _base_code(code: str) -> str:
    """'DLW20803_revB' / 'JDS-G223 Rev. 3' / 'X.pdf' -> code without revision, so versions of the
    same document are recognised as such."""
    code = re.sub(r"\.pdf$", "", code.strip(), flags=re.I)
    code = re.sub(r"[\s_-]*(rev(ision)?\.?|v(er(s[aã]o|sion)?)?\.?)\s*[\w.]{1,6}$", "", code, flags=re.I)
    return code.strip(" _-") or code


def _ground_quotes(items: list) -> list:
    """Context lock: every requirement must quote the passage it was extracted from. A quote that is not in the
    passage word for word is replaced by the passage sentence the requirement matches (multilingual embedding,
    the requirement is marked); a requirement nothing in the passage supports was not read from the document and
    is dropped."""
    out = []
    for c, r in items:
        quote = (r.get("quote") or "").strip()
        if quote and _overlap(quote, c["text"]) >= 0.8:
            out.append((c, r))
            continue
        sentences = [s.strip() for s in dict.fromkeys(re.split(r"(?<=[.;!?])\s+|\n", c["text"])) if len(s.strip()) > 15]
        best, sim = "", 0.0
        if sentences:
            try:
                v = llm.embed([f"{r['statement']}\n{quote}"] + sentences)
                sims = v[1:] @ v[0]
                best, sim = sentences[int(np.argmax(sims))], float(sims.max())
            except llm.LLMError:
                pass
        if sim >= config.QUOTE_MIN_SIM:
            log.info("quote not verbatim, replaced by the source sentence (%.2f): %r", sim, best[:100])
            out.append((c, {**r, "quote": best, "quality_note": "quote taken from the source text (the AI's quote "
                                                                "was not verbatim)"}))
        else:
            log.warning("requirement dropped, not supported by its passage (best %.2f): %r / quote %r",
                        sim, r["statement"][:100], quote[:100])
    return out


def _ground_numbers(items: list) -> list:
    """Every number in a statement must exist in the source passage (catches '4,8 horas' for '48 horas').
    Mismatches get one targeted repair call; if still wrong the requirement is kept but marked."""
    def check(item):
        c, r = item
        if _numbers_ok(r["statement"], c["text"]):
            return item
        try:
            fixed = llm.chat_json(prompts.FIX_NUMBERS_SYSTEM, prompts.fix_numbers_user(r["statement"], r["quote"]),
                                  prompts.FIX_NUMBERS_SCHEMA, max_tokens=400)["statement"]
        except (llm.LLMError, KeyError):
            fixed = r["statement"]
        if _numbers_ok(fixed, c["text"]):
            log.info("number grounding fixed: %r -> %r", r["statement"], fixed)
            return c, {**r, "statement": fixed}
        log.warning("ungrounded numbers kept for review: %r", r["statement"])
        note = "; ".join(filter(None, (r.get("quality_note"), "values not confirmed in the original text")))
        return c, {**r, "statement": fixed, "quality_note": note}
    return _pmap(check, items)


def _norm_numbers(text: str) -> set[str]:
    out = set()
    for n in re.findall(r"\d+(?:[.,]\d+)?", text):
        n = n.replace(",", ".")
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def _numbers_ok(statement: str, source: str) -> bool:
    return _norm_numbers(statement) <= _norm_numbers(source)


def _dedupe(items: list, embs: np.ndarray, threshold: float = 0.95):
    """Drop near-identical requirements extracted twice (overlapping passages / repeated sentences)."""
    keep: list[int] = []
    for i in range(len(items)):
        if not any(float(embs[i] @ embs[j]) >= threshold and _numbers(items[i][1]) == _numbers(items[j][1])
                   for j in keep):
            keep.append(i)
    if len(keep) < len(items):
        log.info("%d duplicate requirements removed", len(items) - len(keep))
    return [items[i] for i in keep], embs[keep]


def _canonical_client(store: Store, name: str) -> str:
    """Reuse an existing client spelling ("Cummins Inc." == "CUMMINS")."""
    key = re.sub(r"[^a-z]", "", name.lower().replace("inc", "").replace("company", ""))
    for r in store.q("SELECT DISTINCT client FROM documents WHERE kind='CSR'"):
        k2 = re.sub(r"[^a-z]", "", r["client"].lower().replace("inc", "").replace("company", ""))
        if key and k2 and (key in k2 or k2 in key):
            return r["client"]
    return name.strip()


# ---------------------------------------------------------------------------------------------
def detect_changes(store: Store, doc_id: int, client: str, prev_doc_ids: list[int]) -> dict:
    """Compare the new document's requirements with the PREVIOUS VERSION of the same document:
    unchanged / modified / new / removed; old requirements become 'superseded' or 'removed'.
    (Other documents of the same client are handled by cross_document_check.)"""
    result = {"unchanged": set(), "modified": 0, "new": 0, "removed": 0}
    new = store.q("SELECT r.*, d.code doc FROM requirements r JOIN documents d ON d.id=r.doc_id WHERE r.doc_id=?",
                  (doc_id,))
    old = []
    if prev_doc_ids:
        marks = ",".join("?" * len(prev_doc_ids))
        old = store.q(f"""SELECT r.*, d.code doc FROM requirements r JOIN documents d ON d.id=r.doc_id
                          WHERE r.status='active' AND r.doc_id IN ({marks})""", prev_doc_ids)
    if not new or not old:
        for r in new:
            store.update("requirements", r["id"], change_type="new")
        if prev_doc_ids:  # previous version had no requirements extracted: everything is new
            result["new"] = len(new)
        return result

    sims = matrix(new) @ matrix(old).T
    matched_old: set[int] = set()
    pending = []
    for i, r in enumerate(new):
        order = np.argsort(-sims[i])
        best = order[0]
        if sims[i, best] >= config.REQ_SAME_SIM and _numbers(r) == _numbers(old[best]):
            store.update("requirements", r["id"], change_type="unchanged", prev_req_id=old[best]["id"])
            matched_old.add(old[best]["id"])
            result["unchanged"].add(r["id"])
            continue
        cands = [old[j] for j in order[:3] if sims[i, j] >= config.REQ_CANDIDATE_SIM]
        if cands:
            pending.append((r, cands))
        else:
            store.update("requirements", r["id"], change_type="new")
            result["new"] += 1
            _finding_new(store, r, doc_id)

    def compare(item):
        r, cands = item
        try:
            return item, llm.chat_json(prompts.CHANGE_SYSTEM, prompts.change_user(r["statement"], r["quote"], cands),
                                       prompts.CHANGE_SCHEMA)
        except llm.LLMError:
            return item, {"relation": "unrelated", "match_index": -1}

    for (r, cands), res in _pmap(compare, pending, "change detection"):
        idx = res.get("match_index", -1)
        rel = res.get("relation", "unrelated")
        if rel == "unrelated" or not (0 <= idx < len(cands)):
            store.update("requirements", r["id"], change_type="new")
            result["new"] += 1
            _finding_new(store, r, doc_id)
            continue
        o = cands[idx]
        matched_old.add(o["id"])
        if rel == "same":
            store.update("requirements", r["id"], change_type="unchanged", prev_req_id=o["id"])
            result["unchanged"].add(r["id"])
            continue
        result["modified"] += 1
        store.update("requirements", r["id"], change_type="modified", prev_req_id=o["id"],
                     change_note=res.get("difference", ""))
        store.add_finding(
            type="REQ_MODIFIED", severity=res.get("impact", "medium"), client=r["client"], req_id=r["id"],
            other_req_id=o["id"], doc_id=doc_id, title=f"Requirement changed in {r['doc']} (p.{r['page']})",
            detail=f"{res.get('difference', '')}\nBefore ({o['doc']} p.{o['page']}): {o['statement']}\n"
                   f"Now ({r['doc']} p.{r['page']}): {r['statement']}",
            action="Review the ITs linked to this requirement.")

    for o in old:
        if o["id"] in matched_old:
            store.update("requirements", o["id"], status="superseded")
        else:
            store.update("requirements", o["id"], status="removed")
            result["removed"] += 1
            store.add_finding(type="REQ_REMOVED", severity="low", client=client, req_id=o["id"], doc_id=doc_id,
                              title=f"Requirement no longer in the new version of {o['doc']}",
                              detail=f"{o['statement']} (previous version p.{o['page']})",
                              action="Check whether the ITs can be simplified / the matrix needs updating.")
    return result


def cross_document_check(store: Store, doc_id: int, exclude_doc_ids: list[int] = ()) -> int:
    """Requirements of this document vs. active requirements of the client's OTHER documents. Documents of one
    customer often repeat or elaborate an obligation; only real contradictions (LEONI cannot satisfy both)
    are flagged (REQ_CONTRADICTION). Change status of the requirements is not touched."""
    doc = store.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    new = store.q("SELECT r.*, d.code doc FROM requirements r JOIN documents d ON d.id=r.doc_id "
                  "WHERE r.doc_id=? AND r.status='active'", (doc_id,))
    skip = {doc_id, *exclude_doc_ids}
    other = [o for o in store.q("""SELECT r.*, d.code doc FROM requirements r JOIN documents d ON d.id=r.doc_id
                                   WHERE r.client=? AND r.status='active' AND d.status='active'""", (doc["client"],))
             if o["doc_id"] not in skip]
    store.db.execute("DELETE FROM findings WHERE doc_id=? AND type='REQ_CONTRADICTION'", (doc_id,))
    if not new or not other:
        store.commit()
        return 0
    sims = matrix(new) @ matrix(other).T
    pending = []
    for i, r in enumerate(new):
        order = np.argsort(-sims[i])[:3]
        cands = [other[j] for j in order if sims[i, j] >= config.REQ_CANDIDATE_SIM]
        # near-identical text with the same numbers cannot contradict: no LLM call
        if cands and not (sims[i, order[0]] >= config.REQ_SAME_SIM and _numbers(r) == _numbers(other[order[0]])):
            pending.append((r, cands))

    def compare(item):
        r, cands = item
        try:
            return item, llm.chat_json(prompts.CROSS_SYSTEM, prompts.change_user(r["statement"], r["quote"], cands),
                                       prompts.CROSS_SCHEMA)
        except llm.LLMError:
            return item, {"relation": "unrelated", "match_index": -1}

    n = 0
    for (r, cands), res in _pmap(compare, pending, "cross-document check"):
        idx = res.get("match_index", -1)
        if res.get("relation") != "contradicts" or not (0 <= idx < len(cands)):
            continue
        o = cands[idx]
        n += 1
        store.add_finding(
            type="REQ_CONTRADICTION", severity=res.get("impact", "medium"), client=r["client"], req_id=r["id"],
            other_req_id=o["id"], doc_id=doc_id,
            title=f"Contradicting requirements: {r['doc']} p.{r['page']} vs {o['doc']} p.{o['page']}",
            detail=f"{res.get('difference', '')}\n{o['doc']} p.{o['page']}: {o['statement']}\n"
                   f"{r['doc']} p.{r['page']}: {r['statement']}",
            action="Clarify with the customer which document prevails.")
    store.commit()
    log.info("%s: %d requirements compared with other %s documents, %d contradictions",
             doc["code"], len(pending), doc["client"], n)
    return n


def _numbers(r) -> set[str]:
    """Numbers in a requirement: a changed value never counts as 'unchanged' on similarity alone."""
    return set(re.findall(r"\d+(?:[.,]\d+)?", f"{r['statement']} {r['quote']}"))


def _finding_new(store: Store, r, doc_id: int):
    store.add_finding(type="REQ_NEW", severity="medium", client=r["client"], req_id=r["id"], doc_id=doc_id,
                      title=f"New requirement in {r['doc']} (p.{r['page']})", detail=r["statement"],
                      action="Check whether the ITs cover it.")


def _copy_links(store: Store, req_ids):
    for rid in req_ids:
        prev = store.one("SELECT prev_req_id FROM requirements WHERE id=?", (rid,))["prev_req_id"]
        for l in store.q("SELECT * FROM req_it_links WHERE req_id=?", (prev,)):
            store.insert("req_it_links", req_id=rid, it_code=l["it_code"], it_doc_id=l["it_doc_id"],
                         source=l["source"], score=l["score"], verdict=l["verdict"],
                         explanation=l["explanation"], action=l["action"], evidence=l["evidence"])


# ---------------------------------------------------------------------------------------------
def _words(t: str) -> list[str]:
    return re.findall(r"\w{3,}", (t or "").lower())


def _overlap(quote: str, source: str) -> float:
    """Share of the quote's words that occur in the source text (1.0 = everything is there). A quote without
    words of 3+ letters ("8D", "D3") is compared as text."""
    q = _words(quote)
    if not q:
        norm = re.sub(r"\s+", " ", (quote or "").strip().lower())
        return float(bool(norm) and norm in re.sub(r"\s+", " ", (source or "").lower()))
    src = set(_words(source))
    return sum(w in src for w in q) / len(q)


_NOT_VERBATIM = "[not verbatim] "
_it_sentences_cache: dict[tuple[int, int], tuple[str, list[str], np.ndarray]] = {}
_it_sentences_lock = threading.Lock()


def _it_sentences(store: Store, doc_id: int) -> tuple[str, list[str], np.ndarray]:
    """Full text, sentences and sentence embeddings of one IT version (computed once per database and process)."""
    key = (id(store), doc_id)
    with _it_sentences_lock:
        if key not in _it_sentences_cache:
            text = "\n".join(r["text"] for r in store.q("SELECT text FROM chunks WHERE doc_id=? ORDER BY idx", (doc_id,)))
            sents = [s.strip() for s in dict.fromkeys(re.split(r"(?<=[.;!?])\s+|\n", text)) if len(s.strip()) > 15]
            _it_sentences_cache[key] = (text, sents, llm.embed(sents) if sents else np.zeros((0, 1024)))
        return _it_sentences_cache[key]


def _source_sentence(store: Store, evidence: str, it_doc_id: int) -> str:
    """Context lock for what the matrix shows: IT evidence the model paraphrased or translated (or took from an
    extracted rule) is replaced by the IT sentence it refers to, searched in the whole IT (multilingual embedding
    match), so quoted IT text can always be found in the IT. Without a close sentence it is marked."""
    evidence = evidence.removeprefix(_NOT_VERBATIM).strip()
    try:
        text, sentences, S = _it_sentences(store, it_doc_id)
        if _overlap(evidence, text) >= 0.8:
            return evidence
        if sentences:
            sims = S @ llm.embed([evidence])[0]
            if float(sims.max()) >= 0.6:
                return sentences[int(np.argmax(sims))]
    except llm.LLMError:
        pass
    return f"{_NOT_VERBATIM}{evidence}"


def reground_evidence(store: Store) -> int:
    """Apply `_source_sentence` to the IT evidence already stored (links and the alert texts quoting it), e.g. after
    improving it, without re-running the comparison. Returns the number of evidence texts changed."""
    n = 0
    for l in store.q("""SELECT id, req_id, it_code, it_doc_id, evidence FROM req_it_links WHERE source='text'
                        AND verdict IN ('conflict','partial','compliant') AND evidence != '' AND it_doc_id IS NOT NULL"""):
        new = _source_sentence(store, l["evidence"], l["it_doc_id"])
        if new != l["evidence"]:
            store.db.execute("UPDATE req_it_links SET evidence=? WHERE id=?", (new, l["id"]))
            store.db.execute("UPDATE findings SET detail=replace(detail, ?, ?) WHERE req_id=? AND it_code=? "
                             "AND type IN ('CONFLICT','GAP')", (f"IT: {l['evidence']}", f"IT: {new}", l["req_id"],
                                                                 l["it_code"]))
            n += 1
    store.commit()
    return n


def _evidence_found(evidence: str, excerpts: list[dict]) -> bool:
    """True if most words of the quoted evidence really occur in the IT excerpts (anti-hallucination)."""
    ev = _words(evidence)
    if len(ev) < 4:
        return False
    src = set(_words(" ".join(e["text"] for e in excerpts)))
    return sum(w in src for w in ev) / len(ev) >= 0.8


SUBSUPPLIER_RE = re.compile(r"sub-?fornecedor|sub-?supplier|tier\s*2|seus (próprios )?fornecedores|"
                            r"cadeia de (fornecimento|suprimento)|fornecedores do fornecedor|its (own )?suppliers",
                            re.I)

_UNIT_ALIASES = {"horas": "h", "hora": "h", "hours": "h", "hour": "h", "hrs": "h", "dias": "d", "dia": "d",
                 "days": "d", "day": "d", "semanas": "wk", "weeks": "wk", "anos": "y", "years": "y", "ano": "y",
                 "ºc": "°c", "meses": "mo", "months": "mo"}
_VALUE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%|mm|cm|°c|ºc|kv|mω|ohm|ppm|horas?|hours?|hrs|h|dias?|days?|"
                       r"semanas|weeks|anos?|years|meses|months|min|s|n|v|a)(?![a-z])", re.I)


def _values(text: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    # "10 a 15 mm" / "10 to 15 mm" / "10-15 mm": the first number shares the unit of the second
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:a|to|-|–|bis)\s*(\d+(?:[.,]\d+)?)\s*([a-z%°º]+)",
                  r"\1 \3 \2 \3", text or "", flags=re.I)
    for num, unit in _VALUE_RE.findall(text):
        unit = _UNIT_ALIASES.get(unit.lower(), unit.lower())
        out.setdefault(unit, set()).add(num.replace(",", "."))
    return out


def _values_differ(req_text: str, evidence: str) -> bool:
    """True if requirement and IT evidence give numbers in the same unit that are not identical."""
    a, b = _values(req_text), _values(evidence)
    return any(a[u] != b[u] for u in a.keys() & b.keys())


def _with_context(store: Store, c) -> str:
    """Retrieved window plus its neighbours, so the judge sees the surrounding rule."""
    rows = store.q("SELECT idx, text FROM chunks WHERE doc_id=? AND idx BETWEEN ? AND ? ORDER BY idx",
                   (c["doc_id"], c["idx"] - 1, c["idx"] + 1))
    # The retrieved window is always kept whole; the remaining budget goes to the neighbours,
    # cut at sentence boundaries (a sentence cut in half can flip the judge's verdict).
    texts = {r["idx"]: r["text"] for r in rows}
    window = texts[c["idx"]]
    budget = max(config.EXCERPT_CHARS - len(window), 0)
    before = _sentences_tail(texts.get(c["idx"] - 1, ""), budget // 2)
    after = _sentences_head(texts.get(c["idx"] + 1, ""), budget - len(before))
    return " […] ".join(t for t in (before, window, after) if t)


def _split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:!?])\s+", text) if s]


def _sentences_head(text: str, limit: int) -> str:
    out = ""
    for s in _split_sentences(text):
        if len(out) + len(s) + 1 > limit:
            break
        out += (" " if out else "") + s
    return out


def _sentences_tail(text: str, limit: int) -> str:
    out = ""
    for s in reversed(_split_sentences(text)):
        if len(out) + len(s) + 1 > limit:
            break
        out = s + (" " + out if out else "")
    return out


def _hubs(store: Store, chunks: list, rules: list) -> tuple[np.ndarray, np.ndarray]:
    """How close each IT window / rule is to requirements in general: its mean cosine to its IT_HUB_K closest active
    requirements of all documents (0 while fewer than IT_HUB_MIN_REQS are stored: too few to tell)."""
    reqs = store.q("SELECT emb FROM requirements WHERE status='active' AND emb IS NOT NULL")

    def hub(rows):
        if len(reqs) < config.IT_HUB_MIN_REQS or not rows:
            return np.zeros(len(rows))
        return np.sort(matrix(reqs) @ matrix(rows).T, axis=0)[-config.IT_HUB_K:].mean(axis=0)
    return hub(chunks), hub(rules)


def _candidates(reqs: list, R: np.ndarray, chunks: list, rules: list, knowledge: dict, hubs=None):
    """Per requirement: candidate IT passages from matching text windows and matching extracted rules,
    (it_code, chunk_id, cosine, text for the reranker; scored sentence by sentence, so no title prefix:
    "IT title: sentence" measured worse, a Portuguese title next to an English rule pulled scores down), and the
    relevance used to pick the ITs: the reranker's (requirement and passage read together) or the cosine.
    Eligible: cosine >= floor; ranked by cosine - IT_HUB_WEIGHT x hub (`_hubs`), so texts close to every
    requirement lose to specific ones; rules under IT_RULE_MIN_WORDS words without a number are left out.
    Also returns the requirement x rule similarities (the judge is shown each IT's closest rules)."""
    S = R @ matrix(chunks).T if chunks else None
    RS = R @ matrix(rules).T if rules else None
    hub_c, hub_r = hubs if hubs is not None else (np.zeros(len(chunks)), np.zeros(len(rules)))
    usable = [len(ru["rule"].split()) >= config.IT_RULE_MIN_WORDS or bool(re.search(r"\d", ru["rule"]))
              for ru in rules]
    pool, floor = ((config.RERANK_POOL, config.RERANK_MIN_SIM) if config.RERANK
                   else (config.IT_CHUNK_TOP_K, config.IT_MIN_SIM))
    candidates, ranking = [], []
    for i in range(len(reqs)):
        cands, rank = [], []
        if S is not None:
            sc = S[i] - config.IT_HUB_WEIGHT * hub_c
            for j in np.argsort(-sc):
                if len(cands) == pool:
                    break
                if S[i, j] >= floor:
                    c = chunks[j]
                    cands.append((c["it_code"], c["id"], float(S[i, j]), c["text"]))
                    rank.append(float(sc[j]))
        if RS is not None:
            sr, n = RS[i] - config.IT_HUB_WEIGHT * hub_r, len(cands)
            for j in np.argsort(-sr):
                if len(cands) - n == pool:
                    break
                ru = rules[j]
                if RS[i, j] >= floor and usable[j] and ru["it_code"] in knowledge:
                    cands.append((ru["it_code"], ru["chunk_id"], float(RS[i, j]), ru["rule"]))
                    rank.append(float(sr[j]))
        candidates.append(cands)
        ranking.append(rank)
    if config.RERANK:
        flat = [(i, k) for i, cands in enumerate(candidates) for k in range(len(cands))]
        scores = rerank.scores([(f"{reqs[i]['statement']}\n{reqs[i]['quote']}", candidates[i][k][3]) for i, k in flat])
        relevance = [[] for _ in candidates]
        for (i, _), s in zip(flat, scores):
            relevance[i].append(s)
    else:
        relevance = ranking
    return candidates, relevance, RS


def selection_changed(store: Store, req_ids: list[int]) -> list[int]:
    """Requirements whose ITs for the judge (current ITs, retrieval and selection) are not the ITs of their stored
    assessment. After a change to the IT selection only these need the LLM again; running the same check after an
    interruption finds only the ones not done yet."""
    if not req_ids:
        return []
    marks = ",".join("?" * len(req_ids))
    reqs = [dict(r) for r in store.q(f"SELECT * FROM requirements WHERE id IN ({marks}) ORDER BY id", req_ids)]
    knowledge = _it_knowledge(store)
    chunks, rules = store.active_it_chunks(), store.active_it_rules()
    candidates, relevance, _ = _candidates(reqs, matrix(reqs), chunks, rules, knowledge, _hubs(store, chunks, rules))
    stored: dict[int, set] = {}
    for l in store.q(f"SELECT req_id, it_code FROM req_it_links WHERE source='text' AND req_id IN ({marks})", req_ids):
        stored.setdefault(l["req_id"], set()).add(l["it_code"])
    return [r["id"] for i, r in enumerate(reqs)
            if {code for code, _, _ in _pick_its(r, candidates[i], relevance[i], knowledge)} != stored.get(r["id"], set())]


def _it_family(code: str) -> str:
    """'WI 3326-11 A3' -> 'WI 3326-11', 'VA 3160 A2' -> 'VA 3160': an IT and its annexes."""
    return " ".join(code.split()[:2])


def _pick_its(r, cands: list[tuple], rel: list[float], knowledge: dict) -> list[tuple[str, float, int]]:
    """The ITs the judge sees for one requirement, from its candidate passages / rules (it_code, chunk_id, cosine,
    text) and their relevance: (code, cosine, chunk_id) of the best passage of each IT, at most IT_MAX_PER_REQ.
    With IT_PER_FAMILY (off, see config) a base IT and its annexes count as one IT (the member with the best
    passage stands for it).
    An IT about LEONI's own suppliers / internal units never governs LEONI's duties as the customer's supplier,
    unless the requirement is about sub-suppliers: such ITs are skipped before the slots are filled
    (deterministic filter: the 8B judge does not reliably respect this "direction" rule on its own)."""
    sub = SUBSUPPLIER_RE.search(f"{r['statement']} {r['quote']}")
    best: dict[str, tuple[float, float, int, str]] = {}  # IT (or family) -> (relevance, cosine, chunk_id, code)
    for (code, chunk_id, cos, _), v in zip(cands, rel):
        k = knowledge.get(code)
        if not k or (config.RERANK and v < config.RERANK_MIN):
            continue
        if (config.DIRECTION_FILTER and not sub
                and k["profile"].get("direction") in ("own_suppliers", "internal_units")):
            continue
        key = _it_family(code) if config.IT_PER_FAMILY else code
        if v > best.get(key, (-1.0,))[0]:
            best[key] = (v, cos, chunk_id, code)
    top = sorted(best.values(), key=lambda b: -b[0])[:config.IT_MAX_PER_REQ]
    return [(code, cos, chunk_id) for _, cos, chunk_id, code in top]


def assess_requirements(store: Store, req_ids: list[int]):
    """For each requirement: retrieve the closest IT rules/passages and IT index titles, let the LLM judge
    each IT (with the IT's profile and rules), re-check every flagged item with a strict verification pass
    (reasoning mode), store the links and raise CONFLICT / GAP findings."""
    if not req_ids:
        return
    marks = ",".join("?" * len(req_ids))
    reqs = [dict(r) for r in store.q(f"""SELECT r.*, d.code doc FROM requirements r JOIN documents d ON d.id=r.doc_id
                                         WHERE r.id IN ({marks})""", req_ids)]
    parents = _parent_sections(store, {r["doc_id"] for r in reqs})
    for r in reqs:
        r["parent_section"] = parents.get(r["chunk_id"], "")
    R = matrix(reqs)
    chunks, rules = store.active_it_chunks(), store.active_it_rules()
    chunk_by_id = {c["id"]: c for c in chunks}
    knowledge = _it_knowledge(store)
    candidates, relevance, RS = _candidates(reqs, R, chunks, rules, knowledge, _hubs(store, chunks, rules))
    cat = store.q("SELECT * FROM it_catalog")
    CS = R @ matrix(cat).T if cat else None
    # section headings ("K. Competência (7.2)") are good queries for the IT index: embed each once
    headings = sorted({r["parent_section"] or r["section"] or "" for r in reqs} - {""})
    heading_row = {h: k for k, h in enumerate(headings)}
    HS = llm.embed(headings) @ matrix(cat).T if cat and headings else None

    jobs = []
    for i, r in enumerate(reqs):
        its: dict[str, dict] = {}
        for code, score, chunk_id in _pick_its(r, candidates[i], relevance[i], knowledge):
            c = chunk_by_id.get(chunk_id)
            if not c:
                continue
            k = knowledge[code]
            it_rules = sorted(((float(RS[i, j]), rules[j]["rule"]) for j in range(len(rules))
                               if rules[j]["it_code"] == code), reverse=True) if RS is not None else []
            its[code] = {"code": code, "title": k["title"], "doc_id": k["doc_id"], "profile": k["profile"],
                         "synthetic": k["synthetic"],
                         "score": score, "rules": [t for _, t in it_rules[:config.RULES_PER_IT]],
                         "excerpts": [{"page": c["page"], "section": c["section"], "text": _with_context(store, c)}]}
        index = _index_candidates(r, i, its, cat, CS, HS, heading_row) if CS is not None else []
        if its or index:
            jobs.append((r, its, index))
        else:
            _clear_assessment(store, r["id"])  # nothing to compare with any more
    store.commit()
    for doc_id in {it["doc_id"] for _, its, _ in jobs for it in its.values()}:
        _it_sentences(store, doc_id)  # evidence lookup tables, built here so the worker threads never read the DB

    def judge(job):
        r, its, index = job
        try:
            out = llm.chat_json(prompts.ASSESS_SYSTEM, prompts.assess_user(r["client"], r, its, index),
                                prompts.assess_schema(list(its), [e["code"] for e in index]),
                                **({"think": True, "max_tokens": config.VERIFY_MAX_TOKENS + config.MAX_OUTPUT_TOKENS}
                                   if config.JUDGE_THINK else {}))
        except llm.LLMError as e:
            log.warning("assessment failed for requirement %s: %s", r["id"], e)
            return job, {}
        for a in out.get("assessments", []):
            it = its.get(a.get("it_code"))
            if not it:
                continue
            if not a.get("same_subject"):
                a["verdict"] = "not_related"
            # Narrow second opinion when ANY sentence of the IT (excerpt or rules, not only the judge's
            # chosen evidence) states a different value in the same unit: small models often call that
            # "partial" or even "compliant" instead of "conflict".
            sentences = _value_sentences(f"{r['statement']} {r['quote']}", it) \
                if a["verdict"] in ("partial", "compliant") else []
            if sentences:
                try:
                    v = llm.chat_json(prompts.VALUE_SYSTEM,
                                      prompts.value_user(r["statement"], r["quote"], " ".join(sentences)),
                                      prompts.VALUE_SCHEMA, max_tokens=400)
                    if v.get("same_parameter") and v.get("values_conflict"):
                        a["verdict"] = "conflict"
                        a["value_conflict"] = True  # deterministic number check + narrow LLM question agree
                        a["evidence"] = " ".join(sentences)
                        a["explanation"] = f"{v.get('explanation', '')} {a.get('explanation', '')}".strip()
                except llm.LLMError:
                    pass
            if a["verdict"] == "conflict" and not _evidence_found(
                    a.get("evidence", ""), it["excerpts"] + [{"text": " ".join(it["rules"])}]):
                a["verdict"] = "partial"  # a contradiction must be backed by real IT text
            # Strict verification of every flagged item (most false alarms are removed here) and of every
            # "compliant" claim (the specific element must really be in the IT, or the gap is missed)
            if a["verdict"] in ("conflict", "partial") and config.VERIFY_FINDINGS:
                a.update(_verify(r, it, a))
            elif a["verdict"] == "compliant" and config.VERIFY_FINDINGS:
                a.update(_verify_compliant(r, it, a))
            if a.get("verdict") in ("conflict", "partial", "compliant") and (a.get("evidence") or "").strip():
                a["evidence"] = _source_sentence(store, a["evidence"], it["doc_id"])
        return job, out

    # Results are written per requirement as they arrive (old ones replaced only then), so an interrupted
    # run (power cut, crash) keeps every requirement in a consistent state: old or new assessment.
    for n, ((r, its, index), out) in enumerate(_pimap(judge, jobs, "IT assessment"), start=1):
        if n % 10 == 0:
            store.commit()
        if not out:  # LLM failure: keep the previous assessment rather than wiping it
            continue
        _clear_assessment(store, r["id"])
        seen = set()
        for a in out.get("assessments", []):
            it = its.get(a.get("it_code"))
            if not it or a["it_code"] in seen:
                continue
            seen.add(a["it_code"])
            verdict = a.get("verdict", "not_related")
            store.insert("req_it_links", req_id=r["id"], it_code=a["it_code"], it_doc_id=it["doc_id"],
                         source="text", score=it["score"], verdict=verdict, explanation=a.get("explanation"),
                         action=a.get("action") if verdict in ("conflict", "partial") else "",
                         evidence=a.get("evidence") if verdict != "not_related" else "",
                         verified=a.get("verified"))
            if verdict in ("conflict", "partial"):
                store.add_finding(
                    type="CONFLICT" if verdict == "conflict" else "GAP",
                    severity="high" if verdict == "conflict" else "medium",
                    client=r["client"], req_id=r["id"], it_code=a["it_code"], doc_id=r["doc_id"],
                    title=("[simulated IT] " if it.get("synthetic") else "")
                    + (f"Conflict: {r['doc']} p.{r['page']} vs {a['it_code']}" if verdict == "conflict"
                       else f"IT {a['it_code']} does not fully cover a requirement of {r['doc']} p.{r['page']}"),
                    detail=f"Requirement: {r['statement']}\nIT: {a.get('evidence', '')}\nAnalysis: {a.get('explanation', '')}",
                    action=a.get("action", ""))
        scores = {e["code"]: e["score"] for e in index}
        for code in dict.fromkeys(out.get("related_index_its", [])):
            if code in scores:
                store.insert("req_it_links", req_id=r["id"], it_code=code, source="catalog",
                             score=scores[code], verdict="candidate")
    store.commit()


def section_labels(store: Store, doc_id: int) -> dict[str, str]:
    """Section headings of a document in the output language (heading -> label), translated once and cached.
    The matrix shows these; the stored sections stay as written in the source document."""
    lang = prompts.OUT_LANG
    cached = {r["section"]: r["label"] for r in store.q(
        "SELECT section, label FROM section_labels WHERE doc_id=? AND language=?", (doc_id, lang))}
    headings = [r["heading"] for r in store.q("SELECT heading FROM outline WHERE doc_id=? ORDER BY idx", (doc_id,))]
    headings += [r["section"] for r in store.q("SELECT section FROM chunks WHERE doc_id=? ORDER BY idx", (doc_id,))]
    sections = [s for s in dict.fromkeys(headings) if s and s not in cached]
    for i in range(0, len(sections), 30):
        batch = sections[i:i + 30]
        try:
            out = llm.chat_json(prompts.HEADINGS_SYSTEM, prompts.headings_user(batch), prompts.HEADINGS_SCHEMA,
                                max_tokens=2000).get("translations", [])
        except llm.LLMError as e:
            log.warning("heading translation failed: %s", e)
            continue
        if len(out) != len(batch):  # misaligned answer: keep the originals rather than risk a wrong row
            log.warning("heading translation returned %d of %d headings, keeping originals", len(out), len(batch))
            continue
        for src, label in zip(batch, out):
            label = re.sub(r"^\[\d+\]\s*", "", label.strip()) or src
            store.db.execute("INSERT OR REPLACE INTO section_labels VALUES (?,?,?,?)", (doc_id, src, lang, label))
            cached[src] = label
    store.commit()
    return cached


def _translate_texts(texts: list[str], batch: int = 12, max_chars: int = 2500) -> list[str]:
    """Translate texts to the output language in batches limited by count AND length (long alert texts would
    otherwise overflow the answer and force slow one-by-one retries); a batch whose answer is misaligned is
    redone one by one, and a text that still fails is kept as it was."""
    def one_batch(chunk):
        try:
            out = llm.chat_json(prompts.TRANSLATE_SYSTEM, prompts.translate_user(chunk), prompts.TRANSLATE_SCHEMA,
                                max_tokens=2400).get("translations", [])
            if len(out) == len(chunk):
                return [re.sub(r"^\[\d+\]\s*", "", t.strip()) or src for src, t in zip(chunk, out)]
        except llm.LLMError:
            pass
        if len(chunk) == 1:
            return chunk
        return [x for t in chunk for x in one_batch([t])]

    chunks, cur, size = [], [], 0
    for t in texts:
        if cur and (len(cur) >= batch or size + len(t) > max_chars):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(t)
        size += len(t)
    if cur:
        chunks.append(cur)
    return [t for part in _pimap(one_batch, chunks, "translation") for t in part]


def translate_document(store: Store, doc_id: int) -> dict:
    """Switch an already processed document to the current output language without re-running the analysis:
    requirement statements, analyses, actions, alerts and section reasons are translated; original quotes
    from the customer document and evidence quoted from the ITs stay as written."""
    jobs = []  # (table, id, column, text)
    for r in store.q("SELECT id, statement, change_note, quality_note FROM requirements WHERE doc_id=?", (doc_id,)):
        jobs += [("requirements", r["id"], col, r[col]) for col in ("statement", "change_note", "quality_note") if r[col]]
    for l in store.q("""SELECT id, explanation, action FROM req_it_links WHERE source='text' AND verdict!='not_related'
                        AND req_id IN (SELECT id FROM requirements WHERE doc_id=?)""", (doc_id,)):
        jobs += [("req_it_links", l["id"], col, l[col]) for col in ("explanation", "action") if l[col]]
    for f in store.q("SELECT id, title, detail, action FROM findings WHERE doc_id=?", (doc_id,)):
        jobs += [("findings", f["id"], col, f[col]) for col in ("title", "detail", "action") if f[col]]
    for s in store.q("SELECT id, reason FROM section_its WHERE doc_id=?", (doc_id,)):
        if s["reason"]:
            jobs.append(("section_its", s["id"], "reason", s["reason"]))
    translated = _translate_texts([j[3] for j in jobs])
    for (table, row_id, col, _), text in zip(jobs, translated):
        store.db.execute(f"UPDATE {table} SET {col}=? WHERE id=?", (text, row_id))
    section_labels(store, doc_id)
    _set_meta(store, doc_id, output_language=prompts.OUT_LANG)
    store.commit()
    return {"texts": len(jobs), "language": prompts.OUT_LANG}


def _clear_assessment(store: Store, req_id: int):
    store.db.execute("DELETE FROM req_it_links WHERE req_id=?", (req_id,))
    store.db.execute("DELETE FROM findings WHERE req_id=? AND type IN ('CONFLICT','GAP') AND status='open'",
                     (req_id,))


_CLAUSE = re.compile(r"\((\d+(?:\.\d+)+)\)")    # ISO/IATF clause in a heading: "(8.2.3)"


def _parent_sections(store: Store, doc_ids: set[int]) -> dict[int, str]:
    """chunk_id -> top-level heading it belongs to ("K. Competência (7.2)" for "Formação no posto")."""
    marks = ",".join("?" * len(doc_ids))
    return {r["id"]: r["top_section"] or "" for r in store.q(
        f"SELECT id, top_section FROM chunks WHERE doc_id IN ({marks})", tuple(doc_ids))}


def _clause_match(section_clause: str, it_clauses: str) -> bool:
    """'7.2' matches an IT indexed under '7.2.2'; '8.5.1.2' matches '8.5.1'."""
    for c in re.split(r"[,;/\s]+", it_clauses or ""):
        if c and (c.startswith(section_clause + ".") or c == section_clause or section_clause.startswith(c + ".")):
            return True
    return False


def _index_candidates(r: dict, i: int, its: dict, cat, CS, HS, heading_row) -> list[dict]:
    """IT index entries offered to the LLM: closest to the requirement, closest to its section heading,
    and ITs indexed under the ISO/IATF clause quoted in the heading."""
    shown = {" ".join(c.split()[:2]) for c in its}
    picked: dict[str, float] = {}

    def add(j, limit_list):
        code = cat[j]["code"]
        if code not in shown and code not in picked:
            picked[code] = float(CS[i, j])
            limit_list.append(code)

    by_req: list = []
    for j in np.argsort(-CS[i]):
        if len(by_req) >= config.CATALOG_TOP_K or CS[i, j] < config.CATALOG_MIN_SIM:
            break
        add(j, by_req)
    heading = r["parent_section"] or r["section"] or ""
    if HS is not None and heading in heading_row:
        by_head: list = []
        for j in np.argsort(-HS[heading_row[heading]])[:10]:
            if len(by_head) >= config.CATALOG_BY_HEADING:
                break
            add(j, by_head)
    m = _CLAUSE.search(f"{heading} {r['section'] or ''}")
    if m:
        by_clause: list = []
        for j in np.argsort(-CS[i]):
            if len(by_clause) >= config.CATALOG_BY_CLAUSE:
                break
            if _clause_match(m.group(1), cat[j]["iso_clause"]):
                add(j, by_clause)
    return [{"code": c, "title": next(e["title"] for e in cat if e["code"] == c), "score": s}
            for c, s in picked.items()]


def _value_sentences(req_text: str, it: dict) -> list[str]:
    """IT sentences (excerpt + extracted rules) giving a number in the same unit as the requirement but a
    different one, e.g. requirement '15 dias úteis' vs IT 'até 20 dias úteis'."""
    text = " ".join([e["text"] for e in it["excerpts"]] + it.get("rules", []))
    return [s for s in dict.fromkeys(_split_sentences(text)) if _values_differ(req_text, s)][:3]


def _verify_compliant(r, it: dict, a: dict) -> dict:
    """Strict check of a 'compliant' verdict: the key element must be quoted from the IT itself."""
    try:
        v = llm.chat_json(prompts.VERIFY_COMPLIANT_SYSTEM,
                          prompts.verify_user(r["client"], r, {**it, "excerpt": it["excerpts"][0]["text"]},
                                              "compliant", a.get("explanation", "")),
                          prompts.VERIFY_COMPLIANT_SCHEMA, max_tokens=config.VERIFY_MAX_TOKENS,
                          think=config.VERIFY_THINK)
    except llm.LLMError as e:
        log.warning("compliant check failed for requirement %s / %s: %s", r["id"], it["code"], e)
        return {"verified": 0}
    sources = it["excerpts"] + [{"text": " ".join(it.get("rules", []))}]
    verdict = v.get("verdict", "compliant")
    if verdict == "conflict" and not _evidence_found(v.get("contradicting_rule", ""), sources):
        verdict = "partial"  # contradiction not backed by real IT text
    if verdict == "compliant" and not _evidence_found(v.get("it_quote", ""), sources):
        verdict = "partial"  # the "proof" of compliance is not actually in the IT
    out = {"verdict": verdict, "verified": 1}
    if verdict != "compliant":
        out["explanation"] = (v.get("missing") or a.get("explanation", "")).strip()
        out["action"] = v.get("action", "")
        out["evidence"] = v.get("contradicting_rule") if verdict == "conflict" else a.get("evidence", "")
    return out


def _verify(r, it: dict, a: dict) -> dict:
    """Second, stricter opinion in reasoning mode. Returns the fields to overwrite on the assessment."""
    try:
        v = llm.chat_json(prompts.VERIFY_SYSTEM,
                          prompts.verify_user(r["client"], r, {**it, "excerpt": it["excerpts"][0]["text"]},
                                              a["verdict"], a.get("explanation", "")),
                          prompts.VERIFY_SCHEMA, max_tokens=config.VERIFY_MAX_TOKENS, think=config.VERIFY_THINK)
    except llm.LLMError as e:
        log.warning("verification failed for requirement %s / %s: %s", r["id"], it["code"], e)
        return {"verified": 0}
    verdict = v.get("verdict", a["verdict"])
    # keep the decision consistent with the checklist answers
    if not v.get("same_activity"):
        verdict = "not_related"
    elif v.get("already_covered") and verdict == "partial":
        verdict = "compliant"
    if verdict == "conflict" and not v.get("contradicting_rule", "").strip():
        verdict = "partial"
    if a.get("value_conflict") and verdict in ("partial", "compliant"):
        # a confirmed numeric contradiction (IT value vs customer value) is the most reliable signal we
        # have; the verifier may only dismiss it as a different activity, not soften it
        return {"verdict": "conflict", "verified": 1}
    out = {"verdict": verdict, "verified": 1}
    if verdict in ("conflict", "partial"):
        out["explanation"] = (v.get("missing") or v.get("reasoning") or a.get("explanation", "")).strip()
        out["action"] = v.get("action") or a.get("action", "")
        if verdict == "conflict":
            out["evidence"] = v["contradicting_rule"]
    elif verdict != a["verdict"]:
        log.debug("verification: req %s / %s %s -> %s", r["id"], it["code"], a["verdict"], verdict)
    return out
