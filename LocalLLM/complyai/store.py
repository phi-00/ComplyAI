"""Temporary persistence layer: one SQLite file + embeddings stored as float32 blobs.

Tables
  documents     every ingested file (IT or CSR), with version + active/superseded status
  chunks        parsed passages of each document with their heading path (+ embedding)
  outline       headings of each document (level, page): the rows of the correspondence matrix
  it_catalog    rows of the WI/IC index spreadsheets (+ embedding of the title)
  requirements  atomic requirements extracted from CSR/STD documents (+ embedding)
  req_it_links  requirement <-> IT assessments (verdict, explanation, action)
  findings      conflicts, gaps and requirement changes = the notifications
"""
import json
import re
import sqlite3
from datetime import datetime

import numpy as np

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                -- IT | CSR
  code TEXT, title TEXT, client TEXT, version TEXT, doc_date TEXT, language TEXT,
  source_file TEXT, file_hash TEXT, ingested_at TEXT,
  status TEXT DEFAULT 'active',      -- active | superseded
  superseded_by INTEGER, meta_json TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY, doc_id INTEGER, idx INTEGER, page INTEGER, section TEXT,
  text TEXT, emb BLOB,
  path TEXT,                         -- JSON list of headings from the top level down to the chunk
  top_section TEXT,                  -- top-level heading ("K. Competência (7.2)")
  kind TEXT,                         -- text | table
  page_end INTEGER
);
CREATE TABLE IF NOT EXISTS outline (    -- headings of each document in reading order (matrix rows = level <= 2)
  doc_id INTEGER, idx INTEGER, level INTEGER, heading TEXT, page INTEGER, PRIMARY KEY (doc_id, idx)
);
CREATE TABLE IF NOT EXISTS it_rules (     -- concrete rules extracted once from each IT passage
  id INTEGER PRIMARY KEY, doc_id INTEGER, chunk_id INTEGER, rule TEXT, emb BLOB
);
CREATE TABLE IF NOT EXISTS section_labels (  -- section headings translated to the output language (cache)
  doc_id INTEGER, section TEXT, language TEXT, label TEXT, PRIMARY KEY (doc_id, section, language)
);
CREATE TABLE IF NOT EXISTS section_its (  -- ITs mapped to a whole customer-document section (matrix level)
  id INTEGER PRIMARY KEY, doc_id INTEGER, section TEXT, it_code TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS it_catalog (
  code TEXT PRIMARY KEY, kind TEXT, title TEXT, process TEXT, revision TEXT,
  iso_clause TEXT, owner TEXT, emb BLOB
);
CREATE TABLE IF NOT EXISTS requirements (
  id INTEGER PRIMARY KEY, doc_id INTEGER, chunk_id INTEGER, client TEXT,
  page INTEGER, section TEXT, statement TEXT, quote TEXT, category TEXT,
  obligation TEXT, parameters_json TEXT, emb BLOB,
  status TEXT DEFAULT 'active',      -- active | superseded | removed
  change_type TEXT,                  -- new | modified | unchanged (vs previous requirements)
  prev_req_id INTEGER, change_note TEXT,
  quality_note TEXT                  -- e.g. numbers not confirmed in the source text
);
CREATE TABLE IF NOT EXISTS req_it_links (
  id INTEGER PRIMARY KEY, req_id INTEGER, it_code TEXT, it_doc_id INTEGER,
  source TEXT,                       -- text (IT content judged by LLM) | catalog (title match)
  score REAL, verdict TEXT, explanation TEXT, action TEXT, evidence TEXT
);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY, created_at TEXT,
  type TEXT,                         -- CONFLICT | GAP | REQ_MODIFIED | REQ_NEW | REQ_REMOVED | IT_UPDATED
  severity TEXT,                     -- high | medium | low | info
  client TEXT, req_id INTEGER, other_req_id INTEGER, it_code TEXT, doc_id INTEGER,
  title TEXT, detail TEXT, action TEXT, status TEXT DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS ix_req_doc ON requirements(doc_id);
CREATE INDEX IF NOT EXISTS ix_req_client ON requirements(client, status);
CREATE INDEX IF NOT EXISTS ix_links_req ON req_it_links(req_id);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def to_blob(v: np.ndarray | None) -> bytes | None:
    return None if v is None else np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes | None) -> np.ndarray | None:
    return None if b is None else np.frombuffer(b, dtype=np.float32)


def matrix(rows, col="emb") -> np.ndarray:
    """Stack the embedding column of rows into an (n, dim) matrix."""
    vs = [from_blob(r[col]) for r in rows]
    return np.vstack(vs) if vs else np.zeros((0, 1024), dtype=np.float32)


class Store:
    def __init__(self, path=config.DB_PATH):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Add columns introduced after a database was created (temporary storage, no migration tool)."""
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(requirements)")}
        if "quality_note" not in cols:
            self.db.execute("ALTER TABLE requirements ADD COLUMN quality_note TEXT")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(chunks)")}
        if "extract_failed" not in cols:
            self.db.execute("ALTER TABLE chunks ADD COLUMN extract_failed INTEGER DEFAULT 0")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(req_it_links)")}
        if "verified" not in cols:
            self.db.execute("ALTER TABLE req_it_links ADD COLUMN verified INTEGER")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(chunks)")}
        if "top_section" not in cols:
            for col in ("path TEXT", "top_section TEXT", "kind TEXT", "page_end INTEGER"):
                self.db.execute(f"ALTER TABLE chunks ADD COLUMN {col}")
            self._backfill_structure()
        self.db.commit()

    def _backfill_structure(self):
        """Documents parsed before the structured parser only have a flat section per chunk: derive the top-level
        heading (lettered 'A.' headings if the document has them, else '4 Title') and an outline from it."""
        top_letter, top_number = re.compile(r"^[A-Z]{1,2}\.\s"), re.compile(r"^\d+\.?\s")
        for (doc_id,) in self.db.execute("SELECT DISTINCT doc_id FROM chunks").fetchall():
            rows = self.q("SELECT id, section, page FROM chunks WHERE doc_id=? ORDER BY idx", (doc_id,))
            top_re = top_letter if any(top_letter.match(r["section"] or "") for r in rows) else top_number
            top, seen = "", {}
            for r in rows:
                sec = (r["section"] or "").strip()
                if top_re.match(sec):
                    top = sec
                if sec and sec not in seen:
                    seen[sec] = (1 if top_re.match(sec) else 2, r["page"])
                path = list(dict.fromkeys(s for s in (top, sec) if s))
                self.db.execute("UPDATE chunks SET path=?, top_section=?, kind='text', page_end=page WHERE id=?",
                                (json.dumps(path, ensure_ascii=False), top, r["id"]))
            for i, (sec, (level, page)) in enumerate(seen.items()):
                self.db.execute("INSERT OR IGNORE INTO outline VALUES (?,?,?,?,?)", (doc_id, i, level, sec, page))

    # generic helpers -------------------------------------------------------
    def q(self, sql, args=()):
        return self.db.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.db.execute(sql, args).fetchone()

    def insert(self, table: str, **cols) -> int:
        keys = ", ".join(cols)
        marks = ", ".join("?" * len(cols))
        cur = self.db.execute(f"INSERT INTO {table} ({keys}) VALUES ({marks})", tuple(cols.values()))
        return cur.lastrowid

    def update(self, table: str, row_id: int, **cols):
        sets = ", ".join(f"{k}=?" for k in cols)
        self.db.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*cols.values(), row_id))

    def commit(self):
        self.db.commit()

    # domain helpers --------------------------------------------------------
    def add_finding(self, **f) -> int:
        f.setdefault("created_at", now())
        fid = self.insert("findings", **f)
        with open(config.NOTIFICATIONS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": fid, **f}, ensure_ascii=False) + "\n")
        return fid

    def active_it_rules(self):
        return self.q("""SELECT r.*, d.code AS it_code FROM it_rules r JOIN documents d ON d.id=r.doc_id
                         WHERE d.kind='IT' AND d.status='active' AND r.emb IS NOT NULL""")

    def active_it_chunks(self):
        return self.q("""SELECT c.*, d.code AS it_code, d.title AS it_title, d.version AS it_version
                         FROM chunks c JOIN documents d ON d.id=c.doc_id
                         WHERE d.kind='IT' AND d.status='active' AND c.emb IS NOT NULL""")
