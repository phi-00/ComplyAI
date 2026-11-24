"""Project chat: answers a LEONI user's question about one project (a customer's documents) from what the database
holds. Used by the app's chat page (server.py, POST /projects/<client>/chat); no CLI command.

What the model gets in one call (everything must fit in config.NUM_CTX with room for the answer):
  * system prompt: prompts.CHAT_SYSTEM (what COMPLY-AI does, its terms, how reliable alerts are) + the glossary
    entries of prompts.CHAT_TERMS that the question or the context mentions;
  * the conversation so far as real chat turns (chat_history);
  * the user message: the project's documents with counts, the items the conversation names (req / alert ids,
    IT codes: full detail), the requirements closest to the question with their IT verdicts and alerts, what the
    cited ITs are (index title, profile), matrix-level ITs of those sections, the closest passages of the customer
    documents, recent human changes, then the question.
Each part gets a share of the room (whole items only, most relevant first); room a part does not use goes to the next.
"""
import json
import re

import numpy as np

from . import config, llm, prompts

HISTORY_TURNS = 6         # last messages of the conversation (3 questions + 3 answers)
TURN_CHARS = 600          # each earlier message is shortened to this
HISTORY_CHARS = 2000      # whole history; the oldest messages go first
REQUIREMENTS = 8          # requirements closest to the question
PASSAGES = 4              # passages of the customer documents closest to the question
FOCUS_MAX = 4             # requirements / alerts / ITs named in the conversation shown in full (each)
CHARS_PER_TOKEN = 3.6     # measured 2026-11-24: 3.7 characters per qwen3 token on these prompts (PT / EN, codes)
# room shares of the parts after the project documents (always shown in full)
SHARES = (("ITEMS NAMED IN THE CONVERSATION", 0.36),
          ("REQUIREMENTS RELATED TO THE QUESTION (with their assessment against the ITs and alerts)", 0.30),
          ("ITS CITED ABOVE", 0.08), ("PASSAGES OF THE CUSTOMER DOCUMENTS", 0.22),
          ("RECENT HUMAN CHANGES", 0.04))
# alert types a question asks about by name -> all of them (up to FOCUS_MAX) shown in full; GAPs are too many: the
# ones of the related requirements are shown with them
ALERT_WORDS = ((r"conflit|conflict", ("CONFLICT",)), (r"stricter|mais exigente|mais restrit", ("IT_STRICTER",)),
               (r"contradi", ("REQ_CONTRADICTION",)),
               (r"alterad|modific|mudan|chang|novos? requisit|new requirement|removid|removed|vers[ãa]o|version",
                ("REQ_MODIFIED", "REQ_NEW", "REQ_REMOVED", "IT_UPDATED")))
VERDICTS = {"compliant": "compliant", "partial": "gap (IT covers it only in part)", "conflict": "CONFLICT",
            "stricter": "IT stricter than required", "candidate": "candidate (title match, not judged)"}
# Only the answer: the app no longer shows a "sources" list (it cluttered the screen; the answer cites ids and pages),
# and not writing one saves answer tokens. The reply keeps "sources": [] for the app.
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"],
          "additionalProperties": False}
# Questions about where files are ("onde está o ficheiro", "where is the PDF", "pasta", "caminho") get a FILES ON THE
# SERVER part: the project folder's files, where each document's PDF is, the IT index spreadsheets
FILE_WORDS = re.compile(r"ficheir|\bfile|\bpdf|pasta|folder|diret[óo]ri|directory|caminho|\bpath|onde (?:est|fica|se "
                        r"encontr|guard)|where (?:is|are|can)|locali[sz]|descarreg|download|guardad|stored|excel|xlsx",
                        re.I)
_FILE_SKIP = {".git", "__pycache__", "snapshots", "node_modules", ".vs", "bin", "obj", "packages", "test",
              "judge_eval", "logs", "paragraphs", "extracted", "output"}
_file_index: dict = {"at": 0.0, "roots": (), "names": {}}

_REQ_RE = re.compile(r"\b(?:req(?:uisito|uirement)?s?\.?|requisitos?)\s*(?:n\.?\s*[ºo°]?\s*|#|id\s*)?(\d{1,6})", re.I)
_ALERT_RE = re.compile(r"\b(?:alert(?:a|as|s)?|findings?|conflit(?:o|os)|conflicts?|lacunas?|gaps?)\s*"
                       r"(?:n\.?\s*[ºo°]?\s*|#|id\s*)?(\d{1,6})\b", re.I)
_IT_RE = re.compile(r"\b(WI|IC|VA|PI|IT)\s*-?\s*(\d{4})(?:\s*-\s*(\d{2}))?(?:\s*(?:A|Anexo|Annex)\s*(\d{1,2}))?\b",
                    re.I)


# "segundo o cliente" = "according to the customer": not an ordinal when an article / pronoun follows
_ORDINALS = ((r"primeir[oa]|\bfirst\b|\b1\s*[ºo°]", 1),
             (r"\bsegund[oa](?!\s+(?:o|a|os|as|este|esta|ele|ela|eles|elas|consta)\b)|\bsecond\b|\b2\s*[ºo°]", 2),
             (r"terceir[oa]|\bthird\b|\b3\s*[ºo°]", 3), (r"quart[oa]|\bfourth\b|\b4\s*[ºo°]", 4),
             (r"quint[oa]|\bfifth\b|\b5\s*[ºo°]", 5), (r"sext[oa]|\bsixth\b|\b6\s*[ºo°]", 6),
             (r"[úu]ltim[oa]|\blast\b", -1))


def ordinal(message: str) -> int | None:
    """Position the question points at in the previous answer's list ("o segundo", "the third", "o último" = -1)."""
    text = message.lower()
    for pattern, n in _ORDINALS:
        if re.search(pattern, text):
            return n
    return None


def plain_text(text: str) -> str:
    """The app's chat box shows text as it is: Markdown the model still writes (**bold**, `code`, # headings,
    * bullets) is removed or turned into plain lines."""
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text or "")
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    return re.sub(r"(?m)^(\s*)[*•]\s+", r"\1- ", text).strip()


def clean(value) -> str:
    return " ".join(str(value or "").replace("�", "").split())


def history_turns(raw, message: str) -> list[dict]:
    """The app's history -> chat turns {"role", "content"}. The app appends the current question to the history before
    sending it: dropped here so it is not there twice. Long messages are shortened and the oldest go first, so the
    history does not take the room of the project context; the history always starts with a question."""
    turns = [{"role": "user" if item.get("role") == "user" else "assistant", "content": clean(item.get("content"))}
             for item in raw or [] if isinstance(item, dict) and item.get("content")]
    if turns and turns[-1]["role"] == "user" and turns[-1]["content"] == clean(message):
        turns.pop()
    turns = turns[-HISTORY_TURNS:]
    for turn in turns:
        if len(turn["content"]) > TURN_CHARS:
            turn["content"] = turn["content"][:TURN_CHARS] + " […]"
    while turns and (sum(len(t["content"]) for t in turns) > HISTORY_CHARS or turns[0]["role"] == "assistant"):
        turns.pop(0)
    return turns


def take(items: list[str], limit: int) -> list[str]:
    """The first items (already sorted by relevance) that fit in `limit` characters, whole."""
    out, used = [], 0
    for item in items:
        if used + len(item) + 1 > limit:
            break
        out.append(item)
        used += len(item) + 1
    return out


def named_ids(texts: list[str]) -> tuple[list[int], list[int], list[str]]:
    """Requirement ids, alert ids and IT codes ("WI 3326-11 A3") named in the texts, first text first, in the order
    they appear, no repeats."""
    reqs, alerts, its = [], [], []
    for text in texts:
        reqs += [int(m) for m in _REQ_RE.findall(text or "")]
        alerts += [int(m) for m in _ALERT_RE.findall(text or "")]
        for kind, num, sub, annex in _IT_RE.findall(text or ""):
            kind = kind.upper()
            code = f"{kind} {num}" + (f"-{sub}" if sub else ("" if kind in ("VA", "PI") else "-11"))
            its.append(code + (f" A{int(annex)}" if annex else ""))
    return list(dict.fromkeys(reqs)), list(dict.fromkeys(alerts)), list(dict.fromkeys(its))


def _find_files(roots: tuple) -> dict:
    """file name (lower case) -> paths under `roots` (the server's files/ folder and the engine folder), refreshed every
    5 minutes; build / cache / test folders skipped."""
    import os
    import time
    if _file_index["roots"] != roots or time.time() - _file_index["at"] > 300:
        names = {}
        for root in roots:
            for folder, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in _FILE_SKIP and not d.startswith(".")]
                for name in files:
                    if name.lower().endswith((".pdf", ".xlsx", ".xls", ".xlt", ".xltx", ".ppt", ".docx")):
                        names.setdefault(name.lower(), []).append(os.path.join(folder, name))
        _file_index.update(at=time.time(), roots=roots, names=names)
    return _file_index["names"]


def _shown_path(path, base) -> str:
    """Path as shown to the user: relative to the server folder when inside it, with forward slashes."""
    from pathlib import Path
    try:
        return Path(path).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _file_items(store, documents, titles, project_dir, it_codes) -> list[str]:
    """FILES ON THE SERVER: where the project's PDFs, the ITs' PDFs and the IT index are."""
    from pathlib import Path
    base = Path.cwd()
    roots = tuple(str(p) for p in dict.fromkeys(
        [Path(project_dir).resolve().parent if project_dir else base / "files", config.ROOT]) if Path(p).is_dir())
    names = _find_files(roots)
    items = [f"- Server folder: {base.as_posix()} (paths below are relative to it). Customer PDFs uploaded through the "
             f"app are kept in files/<project>/; the matrix of a document is downloaded from the app (Projects -> "
             f"Descarregar matriz)."]
    if project_dir and Path(project_dir).is_dir():
        files = sorted(p.name for p in Path(project_dir).iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
        items.append(f"- Project folder {_shown_path(project_dir, base)}/: "
                     + (", ".join(files[:15]) if files else "no PDF files"))
    for d in documents:
        found = names.get(str(d["source_file"] or "").lower(), [])
        items.append(f"- doc {d['id']} ({titles.get(d['id'])}): original file {clean(d['source_file'])}"
                     + (f" at {', '.join(_shown_path(p, base) for p in found[:2])}" if found else
                        " (not found under that name on the server; see the project folder)"))
    for code in it_codes:
        code, doc, cat = _it_lookup(store, code)
        if doc:
            src = store.one("SELECT source_file FROM documents WHERE id=?", (doc["id"],))["source_file"]
            found = names.get(str(src or "").lower(), [])
            items.append(f"- IT {code}: file {clean(src)}"
                         + (f" at {', '.join(_shown_path(p, base) for p in found[:2])}" if found else
                            " (file not found on the server; its text is in the database)"))
        else:
            items.append(f"- IT {code}: NO file on the server (LEONI has not provided it; only its title is in the "
                         f"index)")
    index = [p for n, ps in names.items() if "indice" in n and n.endswith((".xlsx", ".xls")) for p in ps]
    if index:
        items.append("- LEONI's IT index (titles of all ITs): " + ", ".join(_shown_path(p, base) for p in index[:3]))
    return items


def _it_lookup(store, code: str):
    """IT code as written by the user -> (code as stored, document row or None, index row or None). "IT 3326-11"
    tries WI and IC; an annex without its own document falls back to the base IT."""
    kinds = ("WI", "IC") if code.startswith("IT ") else (code.split()[0],)
    rest = code.split(" ", 1)[1]
    for kind in kinds:
        cand = f"{kind} {rest}"
        doc = store.one("SELECT id, code, title, meta_json FROM documents WHERE kind='IT' AND code=? "
                        "AND status='active' ORDER BY id DESC", (cand,))
        base = cand.split(" A")[0] if re.search(r" A\d+$", cand) else cand
        cat = store.one("SELECT code, kind, title, process, iso_clause FROM it_catalog WHERE code IN (?, ?)",
                        (cand, base))
        if doc or cat:
            return cand, doc, cat
    return code, None, None


def _profile(doc) -> dict:
    try:
        return (json.loads(doc["meta_json"] or "{}") or {}).get("profile") or {}
    except (TypeError, ValueError):
        return {}


def _it_line(store, code: str, project_marks: str, args: tuple, full: bool) -> str:
    code, doc, cat = _it_lookup(store, code)
    title = clean(doc["title"] if doc else (cat["title"] if cat else ""))
    parts = [f"- IT {code}: {title or 'not in the IT index'}"]
    if cat:
        parts.append(f"process {clean(cat['process'])}, ISO clause {clean(cat['iso_clause'])}")
    parts.append("full text loaded" if doc else "only its title is known (text not loaded)")
    line = "; ".join(parts)
    if full:
        prof = _profile(doc) if doc else {}
        for key in ("purpose", "applies_to", "out_of_scope"):
            if prof.get(key):
                line += f"\n    {key.replace('_', ' ')}: {clean(prof[key])[:220]}"
        counts = store.q(f"SELECT type, COUNT(*) AS n FROM findings WHERE it_code=? AND doc_id IN ({project_marks}) "
                         f"GROUP BY type", (code, *args))
        line += "\n    alerts in this project: " + (", ".join(f"{r['type']} {r['n']}" for r in counts) or "none")
        reqs = store.q(f"SELECT l.req_id, l.verdict FROM req_it_links l JOIN requirements r ON r.id=l.req_id "
                       f"WHERE l.it_code=? AND r.doc_id IN ({project_marks}) AND r.status='active' "
                       f"AND l.verdict IN ('compliant', 'partial', 'conflict', 'stricter') ORDER BY l.score DESC "
                       f"LIMIT 12", (code, *args))
        if reqs:
            line += "\n    requirements judged against it: " + ", ".join(f"req {r['req_id']} ({r['verdict']})"
                                                                         for r in reqs)
    return line


def _requirement_item(store, row, titles: dict, links: list, findings: list, full: bool, label: str = "") -> str:
    lines = [f"- {label}[req {row['id']} | {titles.get(row['doc_id'], row['doc_id'])} | p.{row['page']} | "
             f"{clean(row['section'])[:80]}] {clean(row['statement'])}"]
    if full and row["quote"]:
        lines.append(f"    original text: \"{clean(row['quote'])[:400]}\"")
    for link in links[:3 if not full else 5]:
        lines.append(f"    IT {link['it_code']}: {VERDICTS.get(link['verdict'], link['verdict'])}. "
                     f"{clean(link['explanation'])[:220 if not full else 400]}"
                     + (f" | action: {clean(link['action'])[:160]}" if link["action"] else "")
                     + (f" | IT text: \"{clean(link['evidence'])[:200]}\"" if full and link["evidence"] else ""))
    if not links:
        lines.append("    (no loaded IT was judged related to this requirement)")
    for f in findings[:3]:
        lines.append(f"    ALERT {f['id']} ({f['type']}, {f['severity']}, IT {f['it_code'] or '-'}, status "
                     f"{f['status']}): {clean(f['title'])[:160]}")
    return "\n".join(lines)


def answer(store, client: str, documents: list, message: str, raw_history=None, return_prompt=False,
           project_dir=None) -> dict:
    """One chat answer for `message` about the project whose customer documents are `documents` (rows of the
    documents table, newest first); project_dir = the project's folder on the server (files/<project>), for questions
    about where files are. Returns {"answer", "sources": []} (+ "prompt" with return_prompt, for tests)."""
    documents = list(documents)[:20]
    doc_ids = tuple(d["id"] for d in documents)
    marks = ", ".join("?" for _ in doc_ids)
    titles = {d["id"]: (clean(d["source_file"]) if "�" in str(d["title"] or "")
                        else clean(d["title"] or d["source_file"])) or str(d["id"]) for d in documents}
    history = history_turns(raw_history, message)

    # Search with the question, and for follow-ups ("and for John Deere?", "the second one") also with the question
    # plus the two previous questions; each passage / requirement counts with the better of the two similarities
    previous = [t["content"] for t in history if t["role"] == "user"][-2:]
    queries = [message] + ([" ".join(previous + [message])] if previous else [])
    try:
        query_embs = llm.embed(queries)
    except Exception:  # embedding server down: fall back to document order
        query_embs = None

    def ranked(rows, top):
        if query_embs is None:
            return list(rows)[:top]
        rows = [r for r in rows if r["emb"] is not None]
        if not rows:
            return []
        scores = (np.vstack([np.frombuffer(r["emb"], dtype=np.float32) for r in rows]) @ query_embs.T).max(axis=1)
        return [rows[i] for i in np.argsort(scores)[::-1][:top]]

    def links_and_findings(req_ids):
        links, finds = {}, {}
        if req_ids:
            m = ", ".join("?" for _ in req_ids)
            for r in store.q(f"SELECT req_id, it_code, verdict, explanation, action, evidence FROM req_it_links "
                             f"WHERE req_id IN ({m}) AND verdict IN ('compliant', 'partial', 'conflict', 'stricter') "
                             f"ORDER BY score DESC", tuple(req_ids)):
                links.setdefault(r["req_id"], []).append(r)
            for r in store.q(f"SELECT id, req_id, type, severity, it_code, title, detail, action, status FROM findings "
                             f"WHERE req_id IN ({m}) ORDER BY id", tuple(req_ids)):
                finds.setdefault(r["req_id"], []).append(r)
        return links, finds

    req_cols = "id, doc_id, page, section, statement, quote, emb"
    # 1. documents of the project, with counts (answers "how many conflicts are there?")
    req_counts = {r["doc_id"]: r["n"] for r in store.q(
        f"SELECT doc_id, COUNT(*) AS n FROM requirements WHERE doc_id IN ({marks}) AND status='active' GROUP BY doc_id",
        doc_ids)}
    alert_counts = {}
    for r in store.q(f"SELECT doc_id, type, COUNT(*) AS n FROM findings WHERE doc_id IN ({marks}) "
                     f"GROUP BY doc_id, type", doc_ids):
        alert_counts.setdefault(r["doc_id"], []).append(f"{r['type']} {r['n']}")
    its_loaded = store.one("SELECT COUNT(*) AS n FROM documents WHERE kind='IT' AND status='active'")["n"]
    its_indexed = store.one("SELECT COUNT(*) AS n FROM it_catalog")["n"]
    doc_items = [f"- [doc {d['id']}] {titles[d['id']]}; customer {clean(d['client']) or 'not stated'}; code "
                 f"{clean(d['code'])}; version {clean(d['version'])}; {req_counts.get(d['id'], 0)} requirements; alerts: "
                 f"{', '.join(alert_counts.get(d['id'], [])) or 'none'}" for d in documents]
    doc_items.append(f"- ITs loaded with full text: {its_loaded} documents (ITs and annexes) of the {its_indexed} ITs "
                     f"in LEONI's index")

    total_alerts = {}
    for r in store.q(f"SELECT type, COUNT(*) AS n FROM findings WHERE doc_id IN ({marks}) GROUP BY type", doc_ids):
        total_alerts[r["type"]] = r["n"]
    customers = list(dict.fromkeys(clean(d["client"]) for d in documents if clean(d["client"])))
    doc_items.insert(0, f"- WHOLE PROJECT \"{client}\" (the project's name in the app = its folder on the server): "
                        f"customer documents of {', '.join(customers) or 'customers not stated'}; "
                        f"{len(documents)} documents, {sum(req_counts.values())} requirements, "
                        f"{sum(total_alerts.values())} alerts ("
                        + (", ".join(f"{t} {n}" for t, n in sorted(total_alerts.items())) or "none") + ")")

    # 2. items the conversation names. In full: what the question names (ids, IT codes, alert types like
    # "conflicts"). Short and numbered: the requirements / alerts the previous answer listed, so "the second one"
    # can be resolved. IT codes of earlier questions stay in focus too.
    now_reqs, now_alerts, now_its = named_ids([message])
    last_answer = history[-1]["content"] if history and history[-1]["role"] == "assistant" else ""
    prev_reqs, prev_alerts, _ = named_ids([last_answer])
    # "the second one": resolved here (the 8B model often picks another item of the list); that item goes first, in
    # full, with a note saying which one the user means
    pos = ordinal(message) if (prev_reqs or prev_alerts) and not (now_reqs or now_alerts) else None
    meant = None
    if pos is not None:
        listed = prev_reqs or prev_alerts
        if -len(listed) <= (pos - 1 if pos > 0 else pos) < len(listed):
            meant = listed[pos - 1 if pos > 0 else pos]
            (now_reqs if prev_reqs else now_alerts).append(meant)
    its_named = list(dict.fromkeys(now_its + named_ids([t["content"] for t in reversed(history)
                                                        if t["role"] == "user"])[2]))[:FOCUS_MAX]
    alert_cols = "id, req_id, type, severity, it_code, title, detail, action, status"
    alerts = []
    if now_alerts or prev_alerts:
        ids = list(dict.fromkeys(now_alerts + (prev_alerts if not now_alerts else [])))[:FOCUS_MAX]
        m = ", ".join("?" for _ in ids)
        rows = {r["id"]: r for r in store.q(f"SELECT {alert_cols} FROM findings WHERE id IN ({m}) "
                                            f"AND doc_id IN ({marks})", (*ids, *doc_ids))}
        alerts += [rows[i] for i in ids if i in rows]
    none_found = []   # the question asks about a kind of alert the project has none of: say so (else the model invents)
    for pattern, types in ALERT_WORDS:
        if re.search(pattern, message.lower()):
            m = ", ".join("?" for _ in types)
            found = store.q(f"SELECT {alert_cols} FROM findings WHERE type IN ({m}) AND doc_id IN ({marks}) "
                            f"ORDER BY id DESC LIMIT {FOCUS_MAX}", (*types, *doc_ids))
            alerts += found
            if not found:
                none_found.append("/".join(types))
    alerts = list({a["id"]: a for a in alerts}.values())[:FOCUS_MAX]
    focus_items, focus_reqs, cited_its, sources = [], [], [], []
    for types in none_found:
        focus_items.append(f"- FACT: this project has NO {types} alerts.")
    if any("REQ_MODIFIED" in t for t in none_found):
        older = store.one(f"SELECT COUNT(*) AS n FROM documents WHERE kind='CSR' AND superseded_by IN ({marks})",
                          doc_ids)["n"]
        focus_items.append(f"- FACT: {older} older versions of these documents are stored, so no requirement changes "
                           f"between versions were detected" if not older else
                           f"- FACT: {older} older versions are stored; no requirement changes were found between them")
    if meant is not None:
        focus_items.append(f"- NOTE: the user's \"{message[:60]}\" means item {pos if pos > 0 else 'last'} of your "
                           f"previous answer = {'req' if prev_reqs else 'alert'} {meant}. Answer about that one.")
    for f in alerts:
        req = store.one("SELECT doc_id, page FROM requirements WHERE id=?", (f["req_id"],)) if f["req_id"] else None
        where = f", requirement req {f['req_id']} in doc {req['doc_id']} page {req['page']}" if req else ""
        focus_items.append(f"- ALERT {f['id']} ({f['type']}, {f['severity']}, IT {f['it_code'] or '-'}, status "
                           f"{f['status']}{where}): {clean(f['title'])}\n    detail: {clean(f['detail'])[:700]}"
                           + (f"\n    action: {clean(f['action'])[:250]}" if f["action"] else ""))
        if f["it_code"]:
            cited_its.append(f["it_code"])
    full_ids = list(dict.fromkeys(now_reqs + [a["req_id"] for a in alerts if a["req_id"]]))[:FOCUS_MAX]
    short_ids = [i for i in prev_reqs if i not in full_ids][:8]
    if full_ids or short_ids:
        ids = full_ids + short_ids
        m = ", ".join("?" for _ in ids)
        rows = {r["id"]: r for r in store.q(f"SELECT {req_cols} FROM requirements WHERE id IN ({m}) "
                                            f"AND doc_id IN ({marks})", (*ids, *doc_ids))}
        focus_reqs = [rows[i] for i in ids if i in rows]
        links, finds = links_and_findings([r["id"] for r in focus_reqs])
        for r in focus_reqs:
            full = r["id"] in full_ids
            label = "" if full else f"(item {prev_reqs.index(r['id']) + 1} of your previous answer) "
            focus_items.append(_requirement_item(store, r, titles, links.get(r["id"], []), finds.get(r["id"], []),
                                                 full, label))
            cited_its += [lk["it_code"] for lk in links.get(r["id"], [])]
            sources.append(f"{titles.get(r['doc_id'])} (page {r['page']}, req {r['id']})")
    for code in its_named:
        focus_items.append(_it_line(store, code, marks, doc_ids, full=True))
    it_named = its_named

    # 3. requirements closest to the question (not already shown in full)
    shown = {r["id"] for r in focus_reqs}
    near = [r for r in ranked(store.q(f"SELECT {req_cols} FROM requirements WHERE doc_id IN ({marks}) "
                                      f"AND status='active' ORDER BY doc_id, page, id", doc_ids),
                              REQUIREMENTS + len(shown)) if r["id"] not in shown][:REQUIREMENTS]
    links, finds = links_and_findings([r["id"] for r in near])
    req_items = []
    for r in near:
        req_items.append(_requirement_item(store, r, titles, links.get(r["id"], []), finds.get(r["id"], []), False))
        cited_its += [lk["it_code"] for lk in links.get(r["id"], [])[:3]]
        sources.append(f"{titles.get(r['doc_id'])} (page {r['page']}, req {r['id']})")

    # 4. what the cited ITs are, and the ITs LEONI's matrix row of those sections lists (section level)
    named_set = set(it_named[:FOCUS_MAX])
    it_items = [_it_line(store, c, marks, doc_ids, full=False)
                for c in dict.fromkeys(cited_its) if c not in named_set][:10]
    sections = list(dict.fromkeys((r["doc_id"], r["section"]) for r in focus_reqs + near))[:4]
    for doc_id, section in sections:
        rows = store.q("SELECT it_code FROM section_its WHERE doc_id=? AND section=?", (doc_id, section))
        if rows:
            it_items.append(f"- matrix, section \"{clean(section)[:60]}\" of doc {doc_id}: "
                            + ", ".join(r["it_code"] for r in rows))

    # 5. passages of the customer documents closest to the question
    passage_items = []
    for r in ranked(store.q(f"SELECT id, doc_id, page, section, text, emb FROM chunks WHERE doc_id IN ({marks}) "
                            f"ORDER BY doc_id, idx", doc_ids), PASSAGES):
        text = clean(r["text"])
        if text:
            passage_items.append(f"[{titles.get(r['doc_id'])} | page {r['page']} | {clean(r['section'])[:80]}]\n"
                                 f"{text[:700]}")
            sources.append(f"{titles.get(r['doc_id'])} (page {r['page']})")

    # 6. recent human changes (table created by server.py)
    try:
        changes = store.q(f"SELECT change_type, item_id, changes_json, updated_at, updated_by FROM document_changes "
                          f"WHERE doc_id IN ({marks}) ORDER BY id DESC LIMIT 5", doc_ids)
    except Exception:
        changes = []
    change_items = [f"- [{r['change_type']} | item {r['item_id']} | by {r['updated_by']} | {r['updated_at']}] "
                    f"{clean(r['changes_json'])[:200]}" for r in changes]

    # system prompt: background + the glossary terms the question / context / history mention
    parts = (focus_items, req_items, it_items, passage_items, change_items)
    docs_block = "PROJECT DOCUMENTS:\n" + "\n".join(doc_items)
    if FILE_WORDS.search(message):
        # ITs whose file may be meant: named in the question / earlier questions, in the previous answer ("the IT of
        # that conflict"), of the alerts shown
        file_its = list(dict.fromkeys(its_named + named_ids([last_answer])[2]
                                      + [a["it_code"] for a in alerts if a["it_code"]]))[:6]
        docs_block += "\n\nFILES ON THE SERVER:\n" + "\n".join(
            _file_items(store, documents, titles, project_dir, file_its))
    seen_text = " ".join([message, *(t["content"] for t in history), *focus_items, *req_items[:4]]).lower()
    terms = [text for pattern, text in prompts.CHAT_TERMS.items() if re.search(pattern, seen_text)]
    system = prompts.CHAT_SYSTEM + ("\n\nMORE TERMS:\n" + "\n".join(f"- {t}" for t in terms) if terms else "")

    # room: the whole call (system + grounding + history + message) must leave CHAT_MAX_TOKENS for the answer
    question = f"QUESTION:\n{message[:1500]}"
    room = int((config.NUM_CTX - config.CHAT_MAX_TOKENS - 150) * CHARS_PER_TOKEN)
    budget = room - len(system) - len(prompts.GROUNDING) - sum(len(t["content"]) + 20 for t in history) \
        - len(question) - len(docs_block) - 300
    blocks, carry = [docs_block], 0
    for (heading, share), items in zip(SHARES, parts):
        limit = int(budget * share) + carry  # room a part does not use goes to the next
        chosen = take(items, limit)
        carry = limit - sum(len(i) + 1 for i in chosen)
        if chosen:
            blocks.append(f"{heading}:\n" + "\n".join(chosen))
    user = f"Project: {client}\n\n" + "\n\n".join(blocks) + f"\n\n{question}"
    result = llm.chat_json(system, user, SCHEMA, max_tokens=config.CHAT_MAX_TOKENS, interactive=True, history=history)
    result = {"answer": plain_text(result.get("answer", "")), "sources": []}
    if return_prompt:
        result["prompt"] = {"system": system, "history": history, "user": user}
    return result
