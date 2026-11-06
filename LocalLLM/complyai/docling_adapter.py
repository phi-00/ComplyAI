"""Docling JSON -> ParsedDocument (same contract as parser.parse_pdf)."""
from . import config
from .parser import (MATRIX_LEVEL, Table, _table_lines, _HEAD_NUM, _number_depth,
                     _numbers, _HISTORY, _DEFINITIONS, _split_long)

DOCLING_PARSER_VERSION = "complyai-docling/1.0"


def _walk(doc):
    """Itens do Docling em ordem de leitura (body -> grupos -> texts/tables)."""
    def rec(node):
        for child in node.get("children", []):
            _, kind, idx = child["$ref"].split("/")          # "#/texts/12"
            item = doc[kind][int(idx)]
            if kind in ("texts", "tables"):
                yield kind, item
            elif kind == "groups":
                yield from rec(item)
    yield from rec(doc["body"])


def _page(item):
    prov = item.get("prov") or []
    return prov[0]["page_no"] if prov else 1


def _table_rows(tbl):
    grid = (tbl.get("data") or {}).get("grid") or []
    rows = [[(c.get("text") or "").strip() for c in r] for r in grid]
    return [r for r in rows if any(r)]


def parse_docling(docling: dict, source_file: str) -> dict:
    items = list(_walk(docling))

    # níveis do Docling são quase sempre 1: derivo-os da numeração ("5.4.3" -> 3)
    headers = [it for k, it in items if k == "texts" and it.get("label") == "section_header"]
    letters = any((m := _HEAD_NUM.match(h["text"])) and not _numbers(m["num"]) for h in headers)

    def level_of(text, fallback):
        m = _HEAD_NUM.match(text)
        if not m:
            return fallback or 1
        return _number_depth(m["num"]) + (1 if letters and _numbers(m["num"]) else 0)

    chunks, outline, front, revision = [], [], [], []
    stack = []   # [(level, text)]
    cur = {"parts": [], "size": 0, "page": None, "page_end": None, "path": [], "section": "", "table": 0}
    seen = False
    drop_level = demote_level = None

    def matrix_section():
        for lvl, txt in reversed(stack):
            if lvl <= MATRIX_LEVEL:
                return txt
        return stack[0][1] if stack else ""

    def flush():
        text = "\n".join(cur["parts"]).strip()
        if text:
            chunks.append({"page": cur["page"], "page_end": cur["page_end"], "section": cur["section"],
                           "path": cur["path"], "kind": "table" if cur["table"] > len(text) / 2 else "text",
                           "text": text})
        cur.update(parts=[], size=0, page=None, page_end=None, table=0)

    def add(text, page, table=False):
        if not text:
            return
        if not seen:
            front.append(text)
            return
        pieces = [text] if len(text) <= config.CHUNK_MAX_CHARS else _split_long(text, config.CHUNK_MAX_CHARS)
        for piece in pieces:
            if cur["parts"] and cur["size"] + len(piece) > config.CHUNK_MAX_CHARS:
                flush()
            if not cur["parts"]:
                cur["page"], cur["path"], cur["section"] = page, [t for _, t in stack], matrix_section()
            cur["page_end"] = page
            cur["parts"].append(piece)
            cur["size"] += len(piece) + 1
            if table:
                cur["table"] += len(piece)

    for kind, it in items:
        page = _page(it)
        if kind == "tables":
            if drop_level is None:
                for row in _table_lines(Table(page, (0, 0, 0, 0), _table_rows(it))):
                    add(row, page, table=True)
            continue

        text = (it.get("text") or "").strip()
        if not text or it.get("label") in ("page_header", "page_footer"):
            continue

        if it.get("label") == "section_header":
            level = level_of(text, it.get("level"))
            m = _HEAD_NUM.match(text)
            title = m["title"] if m else text
            if drop_level is not None and level > drop_level:
                continue
            drop_level = None
            if demote_level is not None and level > demote_level:
                add(text, page)                    # entrada de glossário: fica texto
                continue
            demote_level = None
            if _HISTORY.search(title):
                drop_level = level                 # histórico de revisões: descartado
                continue
            if _DEFINITIONS.search(title):
                demote_level = level
            seen = True
            while stack and stack[-1][0] >= level:
                stack.pop()
            if level <= MATRIX_LEVEL or cur["size"] >= config.CHUNK_MAX_CHARS // 2:
                flush()
            stack.append((level, text))
            outline.append({"level": level, "heading": text, "page": page})
            if level > MATRIX_LEVEL:
                add(text, page)
            continue

        if drop_level is not None:
            revision.append(text)
            continue
        add(text, page)
    flush()

    # sem estrutura utilizável: tudo o que veio antes do 1.º título passa a texto
    if len(outline) < 3 and front:
        packed, buf, size = [], [], 0
        for t in front:
            if buf and size + len(t) > config.CHUNK_MAX_CHARS:
                packed.append(buf)
                buf, size = [], 0
            buf.append(t)
            size += len(t) + 1
        packed.append(buf)
        chunks = [{"page": 1, "page_end": 1, "section": "", "path": [], "kind": "text",
                   "text": "\n".join(b)} for b in packed] + chunks
        front = []

    first_pages = "\n".join((it.get("text") or "") for k, it in items
                            if k == "texts" and _page(it) <= 2)[:6000]
    return {"source_file": source_file, "pages": len(docling.get("pages", {})),
            "parser": DOCLING_PARSER_VERSION, "first_pages_text": first_pages,
            "outline": outline, "chunks": chunks,
            "front_matter": "\n".join(front)[:5000],
            "revision_history": "\n".join(revision)[:20000], "stats": {}}





def parse_paragraphs(data: dict, source_file: str) -> dict:
    chunks, buf, size, page = [], [], 0, None

    def flush():
        nonlocal buf, size, page
        if buf:
            chunks.append({"page": page, "page_end": page, "section": "",
                           "path": [], "kind": "text", "text": "\n".join(buf)})
        buf, size, page = [], 0, None

    for p in data["paragraphs"]:
        t = p["text"]
        if buf and size + len(t) > config.CHUNK_MAX_CHARS:
            flush()
        if not buf:
            page = p["pages"][0]
        buf.append(t)
        size += len(t) + 1
    flush()

    pages = {pg for p in data["paragraphs"] for pg in p["pages"]}
    return {"source_file": source_file, "pages": len(pages),
            "parser": "complyai-paragraphs/1.0", "first_pages_text": "",
            "outline": [], "chunks": chunks, "front_matter": "",
            "revision_history": "", "stats": {}}