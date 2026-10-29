"""Loads Leoni's IT index spreadsheets (WI_Indice / IC_Indice) into it_catalog.

The index lists ~300 ITs while only some have their PDF uploaded; the catalog lets
the engine still point a requirement at the right IT by title/process/ISO clause.
"""
import re
from pathlib import Path

import openpyxl

from . import llm
from .store import Store, to_blob

CODE_RE = re.compile(r"(\d{4})\s*-\s*(\d{2})")


def norm_code(raw: str, prefix: str) -> str | None:
    """'WI-3635-11' / '3002-11' -> 'WI 3635-11'."""
    m = CODE_RE.search(str(raw or ""))
    return f"{prefix} {m.group(1)}-{m.group(2)}" if m else None


def _find_header(rows):
    for i, r in enumerate(rows[:10]):
        cells = [str(c or "").lower() for c in r]
        if any("título" in c for c in cells) and any("nr" in c for c in cells):
            return i, cells
    raise ValueError("header row with 'Nr' and 'Título' not found")


def load_index(store: Store, path: str | Path) -> int:
    path = Path(path)
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True)]
    h, cells = _find_header(rows)
    prefix = "IC" if cells[0].startswith("ic") else "WI"

    def col(*names):
        for n in names:
            for j, c in enumerate(cells):
                if n in c:
                    return j
        return None

    c_code, c_proc, c_title = 0, col("mapa de processos"), col("título")
    c_rev, c_iso, c_owner = col("revisão"), col("iso 9001"), col("dono do processo")

    entries = []
    for r in rows[h + 1:]:
        code = norm_code(r[c_code], prefix)
        title = r[c_title] if c_title is not None else None
        if not code or not title:
            continue
        owner = " / ".join(str(x) for x in r[c_owner:c_owner + 2] if x) if c_owner is not None else ""
        entries.append({
            "code": code, "kind": prefix, "title": " ".join(str(title).split()),
            "process": str(r[c_proc] or "") if c_proc is not None else "",
            "revision": str(r[c_rev] or "") if c_rev is not None else "",
            "iso_clause": str(r[c_iso] or "") if c_iso is not None else "",
            "owner": owner,
        })

    # Title only: process codes / ISO clauses dilute the embedding and hurt matching.
    embs = llm.embed([e["title"] for e in entries])
    for e, v in zip(entries, embs):
        store.db.execute("INSERT OR REPLACE INTO it_catalog VALUES (?,?,?,?,?,?,?,?)",
                         (e["code"], e["kind"], e["title"], e["process"], e["revision"],
                          e["iso_clause"], e["owner"], to_blob(v)))
    store.commit()
    return len(entries)
