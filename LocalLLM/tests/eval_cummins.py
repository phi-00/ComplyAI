"""Compare the AI's IT mapping for the Cummins Supplier Handbook with LEONI's manual matrix
(IT-3535-11-A5_Matriz_CSR_CUMMINS). Run after:
    python -m complyai ingest-csr "Cliente/Cliente/Supplier Handbook-Portuguese-January 2026_0.pdf"

Ground truth = WI/IT codes LEONI listed per handbook section (A., B., ... BB.), limited to ITs that exist
in the LP index. Measures recall per section. Central procedures (VA / PI, column PROC. WSD) are scored apart and
only when one of their documents is loaded (most are not in our data).
"""
import re
import sqlite3
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "complyai.db")  # optional: other DB
db.row_factory = sqlite3.Row
in_index = {r["code"] for r in db.execute("SELECT code FROM it_catalog")}
central_loaded = {" ".join(r["code"].split()[:2]) for r in db.execute(
    "SELECT code FROM documents WHERE kind='IT' AND status='active' AND (code LIKE 'VA %' OR code LIKE 'PI %')")}
LETTER = re.compile(r"\s*([A-Z]{1,2})\.\s")

# ground truth
ws = openpyxl.load_workbook(ROOT / "IT-3535-11-A5_Matriz_ CSR_CUMMINS_jan- 2026.xls.xlsx", data_only=True)["Matrix"]
truth: dict[str, set[str]] = {}
central: dict[str, set[str]] = {}
letter = None
for r in ws.iter_rows(min_row=9, values_only=True):
    if not r[1]:
        continue
    if m := LETTER.match(str(r[1])):
        letter = m.group(1)
    txt = " ".join(str(c) for c in r[4:] if c)
    if "PI WI" in txt:  # "PI WI3330" is a central procedure, not LP's WI 3330-11
        txt = txt.replace("PI WI", "PI ")
    for a, b in re.findall(r"(?:WI|IT)\s*(\d)\s?(\d{3})", txt):
        code = f"WI {a}{b}-11"
        if code in in_index:
            truth.setdefault(letter, set()).add(code)
    for p, a, b in re.findall(r"\b(VA|PI)\s*(\d)\s?(\d{3})", txt):
        if f"{p} {a}{b}" in central_loaded:
            central.setdefault(letter, set()).add(f"{p} {a}{b}")

# AI output: walk the requirements in document order and carry the current letter section
doc = db.execute("SELECT id FROM documents WHERE kind='CSR' AND client LIKE '%ummins%' AND status='active'"
                 " AND source_file LIKE 'Supplier Handbook%' ORDER BY id DESC").fetchone()  # not the 18227 spec
if not doc:
    sys.exit("Cummins handbook not ingested yet")
ai: dict[str, set[str]] = {}
letter = None
for r in db.execute("""SELECT r.id, c.top_section FROM requirements r JOIN chunks c ON c.id=r.chunk_id
                       WHERE r.doc_id=? ORDER BY c.idx, r.id""", (doc["id"],)):
    if m := LETTER.match(r["top_section"] or ""):
        letter = m.group(1)
    for l in db.execute("""SELECT it_code FROM req_it_links WHERE req_id=? AND
                           (source='catalog' OR verdict IN ('conflict','partial','compliant'))""", (r["id"],)):
        ai.setdefault(letter, set()).add(" ".join(l["it_code"].split()[:2]))

# section-level mapping (what the Excel matrix shows first)
sect: dict[str, set[str]] = {}
for r in db.execute("SELECT section, it_code FROM section_its WHERE doc_id=?", (doc["id"],)):
    if m := LETTER.match(r["section"] or ""):
        sect.setdefault(m.group(1), set()).add(r["it_code"])
s_hits = sum(len(truth[k] & sect.get(k, set())) for k in truth)
s_total = sum(len(truth[k]) for k in truth)
print(f"section-level mapping: recall {s_hits}/{s_total} = {s_hits / s_total:.0%}  "
      f"(avg {sum(map(len, sect.values())) / max(len(sect), 1):.1f} ITs per section)")
for k in sorted(truth, key=lambda s: (len(s), s)):
    print(f"  {k:<4} LEONI {', '.join(sorted(truth[k])):<36} AI {', '.join(sorted(sect.get(k, set())))}")
print()

hits = total = 0
print(f"{'sec':<4} {'LEONI matrix':<28} {'AI found':<8} AI suggestions")
for sec in sorted(truth, key=lambda s: (len(s), s)):
    found = truth[sec] & ai.get(sec, set())
    hits += len(found)
    total += len(truth[sec])
    print(f"{sec:<4} {', '.join(sorted(truth[sec])):<28} {len(found)}/{len(truth[sec]):<6} "
          f"{', '.join(sorted(ai.get(sec, set())))}")
n_sugg = [len(v) for v in ai.values()]
print(f"\nrecall: {hits}/{total} = {hits / total:.0%}   "
      f"(avg {sum(n_sugg) / max(len(n_sugg), 1):.1f} ITs suggested per section, {len(ai)} sections)")

if central:  # requirement-level only: the section mapping picks from the LP index, which has no central procedures
    c_hits = sum(len(central[k] & ai.get(k, set())) for k in central)
    print(f"central procedures loaded (PROC. WSD), requirement level: {c_hits}/{sum(map(len, central.values()))}  "
          + ", ".join(f"{k}: {', '.join(sorted(v))} {'found' if v <= ai.get(k, set()) else 'missing'}"
                      for k, v in sorted(central.items())))
