"""PDF parser: turns a customer document (CSR / standard) or a LEONI work instruction into the ParsedDocument
the engine ingests (README "Parser contract").

Made for digital PDFs (with a text layer), which is what customers and LEONI publish:
  1. lines with font, size, boldness and position (PyMuPDF); a heading number printed apart from its title
     ("6.1" | "Actions to Address Risks"), a bullet apart from its text or a label apart from its value is
     joined back into one line
  2. noise removed: running headers/footers (lines or frame tables repeated across pages), page numbers,
     tables of contents and navigation bars, revision histories, the cover block before the first heading
  3. ruled tables read as tables: one "header: value; header: value" line per row
  4. headings recognised from numbering + typography (bold or bigger than the body text) + the document's own
     table of contents or bookmarks; levels from the numbering, the table of contents or the font size.
     Entries under a definitions / acronyms heading stay text (they are not sections of the matrix)
  5. text packed into chunks of ~CHUNK_MAX_CHARS that never cross a matrix-level heading (level <= 2) and
     preferably end where a sub-section ends
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path

import fitz  # PyMuPDF

from . import config

PARSER_VERSION = "complyai-pdf/1.0"
MATRIX_LEVEL = 2  # headings down to this level are rows of the correspondence matrix and chunk boundaries

fitz.TOOLS.mupdf_display_errors(False)  # malformed structure trees only produce noise on stderr
if hasattr(fitz, "no_recommend_layout"):
    fitz.no_recommend_layout()  # PyMuPDF's advert for its ML layout add-on (evaluated, not needed: README)


# =============================================================================================
# Lines
# =============================================================================================
@dataclass
class Line:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float
    bold: bool

    @property
    def style(self) -> tuple[float, bool]:
        return round(self.size * 2) / 2, self.bold


_TRANS = str.maketrans({"­": "", "​": "", "‌": "", "‍": "", "﻿": "",
                        " ": " ", " ": " ", " ": " ", "‐": "-", "‑": "-",
                        "": "•", "": "•", "": "•", "": "•", "": "•", "": "•"})
_PUA = re.compile(r"[-]")  # Symbol/Wingdings glyphs without unicode: in practice bullets


def _clean(s: str) -> str:
    s = _PUA.sub("•", unicodedata.normalize("NFC", s).translate(_TRANS))
    return re.sub(r"[ \t]+", " ", s)


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or bool(re.search(r"bold|black|heavy|semibold|demi", span["font"], re.I))


def _raw_lines(page, pno: int) -> list[Line]:
    flags = (fitz.TEXTFLAGS_DICT | fitz.TEXT_MEDIABOX_CLIP) & ~fitz.TEXT_PRESERVE_LIGATURES & ~fitz.TEXT_PRESERVE_IMAGES
    out = []
    for b in page.get_text("dict", flags=flags)["blocks"]:
        for l in b.get("lines", []):
            if abs(l["dir"][1]) > 0.1:  # rotated text: margin stamps, axis labels
                continue
            spans = [s for s in l["spans"] if s["size"] >= 4]  # smaller is hidden / decorative text
            text = _clean("".join(s["text"] for s in spans)).strip()
            if not text:
                continue
            visible = [s for s in spans if s["text"].strip()]
            weight = Counter()
            for s in visible:
                weight[s["size"]] += len(s["text"].strip())
            n = sum(len(s["text"].strip()) for s in visible)
            bold = sum(len(s["text"].strip()) for s in visible if _is_bold(s)) >= 0.75 * n
            x0 = min(s["bbox"][0] for s in visible)
            y0 = min(s["bbox"][1] for s in visible)
            x1 = max(s["bbox"][2] for s in visible)
            y1 = max(s["bbox"][3] for s in visible)
            out.append(Line(pno, x0, y0, x1, y1, text, weight.most_common(1)[0][0], bold))
    return out


def _copy_shift(lines: list[Line], page_w: float) -> float | None:
    """A form printed twice side by side on one sheet (2-up, cut in half after printing): the horizontal distance
    between the two copies, when many text lines have a twin with the same text on the same row at that distance
    (about half the page: repeated column headers of a wide table are closer together)."""
    by_text: dict[str, list[Line]] = {}
    for ln in lines:
        if len(ln.text) >= 8:
            by_text.setdefault(ln.text, []).append(ln)
    shifts = Counter(round(b.x0 - a.x0) for group in by_text.values() for a in group for b in group
                     if b.x0 - a.x0 > 0.3 * page_w and abs(b.y0 - a.y0) < 1.5)
    if not shifts:
        return None
    dx = shifts.most_common(1)[0][0]
    twins = sum(c for s, c in shifts.items() if abs(s - dx) <= 2)
    return dx if twins >= max(8, 0.3 * sum(map(len, by_text.values()))) else None


_NUM_TOKEN = re.compile(r"^(\d{1,2}(\.\d{1,3}){0,5}\.?|[A-Z]{1,2}\.|[IVX]{1,4}\.)$")
_BULLET_TOKEN = re.compile(r"^([•●○◦▪■►▸‣∙·*\-–—]|o|[a-z]\)|\(?[0-9ivx]{1,3}\)|[a-z]\.)$")


def _same_row(a: Line, b: Line) -> bool:
    return abs(a.y1 - b.y1) < 0.35 * min(a.size, b.size) + 1


def _join_pieces(lines: list[Line]) -> list[Line]:
    """Join pieces of one visual row that the PDF stores separately (consecutive in reading order, same baseline,
    left to right): heading number + title, bullet + text, label + value. A heading number alone on its line
    is joined with the line below it."""
    out: list[Line] = []
    for ln in lines:
        prev = out[-1] if out else None
        if prev and prev.page == ln.page:
            token = _NUM_TOKEN.match(prev.text) or _BULLET_TOKEN.match(prev.text)
            row = _same_row(prev, ln) and ln.x0 >= prev.x1 - 2
            below = (_NUM_TOKEN.match(prev.text) and 0 <= ln.y0 - prev.y1 < 1.2 * prev.size
                     and ln.x0 >= prev.x0 - 5)
            if row or below:
                if token:  # the style of "6.1 Title" is the style of the title
                    size, bold = ln.size, ln.bold
                else:
                    size, bold = max((prev, ln), key=lambda x: len(x.text)).size, prev.bold and ln.bold
                out[-1] = Line(prev.page, min(prev.x0, ln.x0), min(prev.y0, ln.y0), max(prev.x1, ln.x1),
                               max(prev.y1, ln.y1), f"{prev.text} {ln.text}", size, bold)
                continue
        out.append(ln)
    return out


def _key(text: str) -> str:
    """Page-independent form of a line, to recognise running headers/footers ('Page 3 of 9' == 'Page 4 of 9')."""
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", text.lower())).strip()


def _inside(ln: Line, bbox) -> bool:
    cx, cy = (ln.x0 + ln.x1) / 2, (ln.y0 + ln.y1) / 2
    return bbox[0] - 1 <= cx <= bbox[2] + 1 and bbox[1] - 1 <= cy <= bbox[3] + 1


# =============================================================================================
# Tables
# =============================================================================================
@dataclass
class Table:
    page: int
    bbox: tuple
    rows: list[list[str]]

    @property
    def key(self) -> str:
        return _key(" ".join(c for r in self.rows for c in r))


def _cell_lines(c) -> list[str]:
    return [_clean(x).strip() for x in (c or "").split("\n") if _clean(x).strip()]


def _tables(page, pno: int, clip=None) -> list[Table]:
    out = []
    try:
        found = page.find_tables(clip=clip).tables
    except Exception:  # table detection is best effort
        return out
    for t in found:
        raw = t.extract()
        if t.row_count < 2 or t.col_count < 2:
            continue  # a frame around text, not a table
        rows = []
        for r in raw:
            cells = [_cell_lines(c) for c in r]
            multi = [len(c) for c in cells if len(c) > 1]
            # values stacked in one cell per column ("2-6\n7-15\n16-25" | "0\n1\n2"): one row per line
            if len(multi) >= 2 and len(set(multi)) == 1 and rows:
                k = multi[0]
                for i in range(k):
                    rows.append([c[i] if len(c) == k else " ".join(c) for c in cells])
            else:
                rows.append([" ".join(c) for c in cells])
        rows = [r for r in rows if any(r)]
        if len(rows) >= 2 and sum(1 for j in range(len(rows[0])) if any(r[j] for r in rows)) >= 2:
            out.append(Table(pno, tuple(t.bbox), rows))
    return out


def _table_lines(t: Table) -> list[str]:
    """One self-contained line per row: 'Header: value; Header: value' (the header row is detected when the
    first row is short labels); merged header cells take the name of the cell on their left."""
    def header(row):
        if not (all(len(c) <= 60 for c in row) and sum(1 for c in row if c) >= 2):
            return None
        names, last = [], ""
        for c in row:
            last = c or last
            names.append(last)
        return names

    names = header(t.rows[0])
    if names is None:
        return [" | ".join(c for c in r if c) for r in t.rows]
    out, expect_header = [], False
    for r in t.rows[1:]:
        cells = [c for c in r if c]
        if len(cells) == 1 and _CAPTION.match(cells[0]):
            out.append(cells[0])  # "Table 5 ...": a second table drawn right below the first one
            expect_header = True
            continue
        if expect_header and (h := header(r)):
            names, expect_header = h, False
            continue
        parts = [f"{n}: {v}" if n and n != v else v for n, v in zip(names, r) if v]
        if parts:
            out.append("; ".join(parts))
    return out


# =============================================================================================
# Tables of contents, bookmarks, noise
# =============================================================================================
_TOC_TITLE = re.compile(r"^(table of contents|contents?|índice|indice|sumário|sumario|conteúdos?|"
                        r"inhalt(sverzeichnis)?|list of (tables|figures)|lista de (tabelas|figuras)|"
                        r"índice de (tabelas|figuras))\s*:?$", re.I)
_LEADER = re.compile(r"(\.\s?){4,}|…{2,}|_{4,}")
_TOC_ENTRY = re.compile(r"^(?P<title>.*?\S)\s*(?:(?:\.\s?){2,}|…+|_{3,})?\s*(?P<page>\d{1,3}(?:\s*[-–,]\s*\d{1,3})?)$")
_PAGE_NO = re.compile(r"^(-\s*)?((page|página|pagina|pág\.?|seite|p\.)\s*)?\d{1,4}(\s*(of|de|von|/)\s*\d{1,4})?(\s*-)?$",
                      re.I)
_HISTORY = re.compile(r"revision history|change history|record of (changes|revisions)|histórico de (revis|altera)|"
                      r"registo de altera|log de revis|revision log|change log|änderungshistorie|änderungsverzeichnis|"
                      r"änderungsprotokoll|history and description of chang|^revisions?$|^history$|^histórico$", re.I)
_HISTORY_COLS = re.compile(r"^(vers|rev|date|data|datum|change|altera|modifica|änderung|author|autor|descri|"
                           r"motivo|ersteller|ecn|chg)", re.I)
_DEFINITIONS = re.compile(r"defini|terms|termos|glossar|acrónimo|acronimo|acronym|abbreviation|abreviatura|"
                          r"begriffe|abkürzung|siglas|terminolog", re.I)
_CAPTION = re.compile(r"^(note|nota|notas|observação|observacao|obs\.|table|tabela|tabla|figure|figura|fig\.|"
                      r"abbildung|tabelle|example|exemplo|beispiel|hinweis|anmerkung|source|fonte)\b", re.I)
_CONTINUED = re.compile(r"\((continued|cont\.?|continuação|continuacao|fortsetzung|forts\.)\)\s*$", re.I)
# a numbered line with a modal verb is a numbered requirement, not a heading ("4.6.1. Devices ... shall be ...")
_MODAL = re.compile(r"\b(shall|must|should|will be|is to|are to|deve|devem|deverá|deverão|muss|müssen|soll|sollen)\b",
                    re.I)


def _title_key(text: str) -> str:
    """Comparable form of a heading / TOC title: no numbering, no punctuation, lower case."""
    m = _HEAD_NUM.match(text)
    t = m["title"] if m else text
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t.lower())).strip()


@dataclass
class TocEntry:
    key: str
    level: int | None


def _toc_entries(lines: list[Line]) -> list[TocEntry]:
    """Entries of printed tables of contents / navigation bars (leader dots or a page number at the end).
    Levels come from the numbering or, for a single-column list, from the indentation."""
    joined: list[Line] = []
    for ln in lines:  # a numbered entry wrapped over two lines: only the second one ends with the page number
        prev = joined[-1] if joined else None
        if (prev and prev.page == ln.page and _TOC_ENTRY.match(ln.text) and not _TOC_ENTRY.match(prev.text)
                and _HEAD_NUM.match(prev.text) and 0 <= ln.y0 - prev.y1 < 0.8 * prev.size):
            joined[-1] = replace(prev, text=f"{prev.text} {ln.text}", x1=max(prev.x1, ln.x1), y1=ln.y1)
        else:
            joined.append(ln)
    raw = []
    for ln in joined:
        m = _TOC_ENTRY.match(ln.text)
        if not m or _TOC_TITLE.match(m["title"]) or len(_title_key(m["title"])) < 3:
            continue
        num = _HEAD_NUM.match(m["title"])
        raw.append((ln, _title_key(m["title"]), _number_depth(num["num"]) if num else None))
    # indentation levels: neighbouring x positions closer than a third of the largest step are one level
    # (a number label printed left of the text); a multi-column navigation bar has no indentation levels
    xs = sorted({round(ln.x0) for ln, _, _ in raw})
    steps = [b - a for a, b in zip(xs, xs[1:])]
    indents = xs[:1] + [b for a, b in zip(xs, xs[1:]) if b - a >= max(6, 0.35 * max(steps))] if steps else xs
    by_indent = 1 < len(indents) <= 4 and xs[-1] - xs[0] <= 120
    out = []
    for ln, key, depth in raw:
        level = sum(1 for x in indents if x <= round(ln.x0)) if by_indent else depth or 1
        out.append(TocEntry(key, level))
    return out


# =============================================================================================
# Headings
# =============================================================================================
_HEAD_NUM = re.compile(
    r"^(?P<num>(?i:(?:section|secção|seção|secao|chapter|capítulo|capitulo|annex|anexo|appendix|apêndice|"
    r"apendice|anhang|kapitel)\s+[0-9A-Z]{1,3}[.:]?)|\d{1,2}(?:\.\d{1,3}){0,5}\.?|[A-Z]{1,2}\.|[IVX]{1,4}\.)"
    r"\s+(?P<title>\S.*)$")


def _number_depth(num: str) -> int:
    """'5' / '5.' / '5.0' -> 1, '5.1' -> 2, '5.4.3' -> 3; letters, roman numerals and annexes -> 1."""
    parts = [p for p in num.rstrip(".:").split(".") if p]
    if not parts or not parts[0].isdigit():
        return 1
    while len(parts) > 1 and set(parts[-1]) == {"0"}:
        parts.pop()
    return len(parts)


def _numbers(num: str) -> list[int] | None:
    parts = [p for p in num.rstrip(".").split(".") if p]
    return [int(p) for p in parts] if parts and all(p.isdigit() for p in parts) else None


@dataclass
class Heading:
    line: Line
    number: str
    title: str
    level: int = 0

    @property
    def text(self) -> str:
        return self.line.text


def _caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _find_headings(lines: list[Line], body: float, left: float, page_w: float,
                   toc: list[TocEntry], spacing: float) -> dict[int, Heading]:
    """Headings by line index. Lines consumed by a wrapped heading are blanked in `lines`."""
    toc_level = {}
    for e in toc:
        toc_level.setdefault(e.key, e.level)

    def in_toc(text):
        k = _title_key(text)
        if k in toc_level:
            return k
        for tk in toc_level:  # truncated or slightly different TOC entries ("Advance" / "ADVANCED ...")
            short, long_ = sorted((k, tk), key=len)
            if len(short) >= 12 and (
                    (len(short) >= 0.6 * len(long_) and (long_.startswith(short) or long_.endswith(short)))
                    or (len(short) >= 0.8 * len(long_) and SequenceMatcher(None, k, tk).ratio() >= 0.9)):
                return tk
        return None

    def basic(ln):
        t = ln.text
        return (2 < len(t) <= 160 and len(t.split()) <= 22 and re.search(r"[^\W\d_]{3}", t)
                and not t.endswith((",", ";")) and not _CAPTION.match(t) and not _LEADER.search(t))

    def styled(ln):
        return (ln.bold and ln.size >= body - 0.6) or ln.size >= body + 1.2

    # pass 1: numbered headings (the numbering sequence must make sense, or it is a numbered list item)
    heads: dict[int, Heading] = {}
    top_seq: list[int] | None = None
    for i, ln in enumerate(lines):
        m = _HEAD_NUM.match(ln.text)
        if not m or not basic(ln) or _CONTINUED.search(ln.text):
            continue
        title = m["title"]
        words = len(title.split())
        sentence = (title.rstrip().endswith(".") and words > 6) or words > 14 or _MODAL.search(title)
        if sentence or not (styled(ln) or in_toc(ln.text) or (_caps(title) and words <= 8)):
            continue
        nums = _numbers(m["num"])
        if not nums and title.rstrip().endswith(":") and not in_toc(ln.text):
            continue  # "Anexo 9 Corte:" introduces a list, it is not a section (unlike "1. Finalidade:")
        if nums and not in_toc(ln.text):
            depth = _number_depth(m["num"])
            if depth == 1 and top_seq and not (0 < nums[0] - top_seq[0] <= 2):
                continue  # "1." after section 6: a list item
            if depth > 1 and top_seq and nums[0] not in (top_seq[0], top_seq[0] + 1):
                continue
        if nums and _number_depth(m["num"]) == 1:
            top_seq = nums
        elif not nums:  # a letter / annex heading restarts the decimal numbering beneath it
            top_seq = None
        heads[i] = Heading(ln, m["num"], title)

    if len(heads) < 3:  # a lone "6 Sigma at Caterpillar" is not a numbering scheme
        heads = {i: h for i, h in heads.items() if in_toc(h.text)}
    num_styles = Counter(h.line.style for h in heads.values())
    # a numbered document: an unnumbered line is a heading only if its table of contents / bookmarks list it
    # (otherwise table column titles, cover lines and bold labels creep in)
    strict = len(heads) >= 5

    def continues(a, b, hanging=False):  # b is the next line of the same paragraph as a
        # hanging: an all-caps numbered title may wrap under its title text ("5.9. PROCEDIMENTO ..." / "DESAPARECIDO")
        return (a.page == b.page and a.style == b.style and -2 <= b.y0 - a.y1 <= spacing * a.size
                and (abs(b.x0 - a.x0) < 4 or (hanging and 0 < b.x0 - a.x0 <= 45 and _caps(a.text) and _caps(b.text))))

    def blank(k):
        lines[k] = replace(lines[k], text="")

    # pass 2: unnumbered headings; any heading may wrap over up to 3 lines of the same style
    i = 0
    while i < len(lines):
        start, ln = i, lines[i]
        run = [ln]
        while (start + len(run) < len(lines) and start + len(run) not in heads
               and continues(run[-1], lines[start + len(run)], hanging=start in heads)):
            run.append(lines[start + len(run)])
        i += len(run)
        text = " ".join(l.text for l in run)
        wrapped = len(run) <= 3 and len(text) <= 160 and not text.endswith((".", ":"))
        if start in heads:  # numbered heading: "Q. Controle de Processos, Produtos e" + "Serviços (8.4)"
            if len(run) > 1 and wrapped:
                h = heads[start]
                heads[start] = Heading(replace(ln, text=text, x1=max(l.x1 for l in run), y1=run[-1].y1),
                                       h.number, f"{h.title} {' '.join(l.text for l in run[1:])}")
                for k in range(start + 1, start + len(run)):
                    blank(k)
            continue
        if _CONTINUED.search(text) and styled(ln):
            for k in range(start, start + len(run)):
                blank(k)  # "PACKAGING (CONTINUED)": the section goes on
            continue
        cand = replace(ln, text=text, x1=max(l.x1 for l in run), y1=run[-1].y1)
        if (not wrapped or _HEAD_NUM.match(ln.text) or not basic(cand)
                or (text.endswith(".") and len(text.split()) > 6)):
            continue
        aligned = ln.x0 <= left + 80 or abs((ln.x0 + ln.x1) / 2 - page_w / 2) < 40
        if in_toc(text) and (styled(ln) or _caps(text)):
            pass
        elif not (not strict and styled(ln) and aligned and len(text.split()) <= 14
                  and (ln.size >= body + 0.5 or _caps(text) or num_styles[ln.style] >= 2)):
            continue
        heads[start] = Heading(cand, "", text)
        for k in range(start + 1, start + len(run)):
            blank(k)

    # with a table of contents, unlisted unnumbered "headings" before the first real one are the cover page
    anchors = [i for i, h in heads.items() if h.number or in_toc(h.text)]
    if len(toc_level) >= 5 and anchors:
        for i in [i for i in heads if i < min(anchors)]:
            del heads[i]
    # a title repeated on the next page ("GLOSSARY OF TERMS" on 4 pages) is one section
    last = None
    for i in sorted(heads):
        k = _title_key(heads[i].text)
        if k == last:
            del heads[i]
            blank(i)
        last = k
    _assign_levels([heads[i] for i in sorted(heads)], toc_level, in_toc)
    return heads


def _assign_levels(heads: list[Heading], toc_level: dict, in_toc):
    """Level from the numbering ('5.4.3' -> 3; under letter headings 'A.' the numbered ones are one deeper),
    else from the table of contents, else from the level of numbered / listed headings with the same font,
    else from the font size compared with them."""
    letters = any(h.number and not _numbers(h.number) for h in heads)
    by_style: dict[tuple, Counter] = {}
    for h in heads:
        if h.number:
            nums = _numbers(h.number)
            h.level = _number_depth(h.number) + (1 if letters and nums else 0)
        elif (k := in_toc(h.text)) and toc_level.get(k):
            h.level = toc_level[k]
        else:
            continue
        by_style.setdefault(h.line.style, Counter())[h.level] += 1
    sized = sorted(((s, c.most_common(1)[0][0]) for s, c in by_style.items()), key=lambda x: -x[0][0])
    plain_sizes = sorted({h.line.size for h in heads if not h.number}, reverse=True)
    for h in heads:
        if h.level:
            continue
        if h.line.style in by_style:
            h.level = by_style[h.line.style].most_common(1)[0][0]
        elif sized:
            # the shallowest numbered level whose headings are not bigger than this one, else one deeper
            fits = [lvl for (size, _), lvl in sized if size <= h.line.size + 0.5]
            h.level = min(fits) if fits else max(lvl for _, lvl in sized) + 1
        else:
            h.level = plain_sizes.index(h.line.size) + 1 if h.line.size in plain_sizes else 1
    if heads:
        top = min(h.level for h in heads)
        for h in heads:
            h.level = min(h.level - top + 1, 6)


# =============================================================================================
# Document
# =============================================================================================
_LIST_START = re.compile(r"^([•●○◦▪■►▸‣∙·*\-–—]\s|o\s|[a-z]\)\s|[a-z]\.\s|\(?[0-9ivx]{1,3}\)\s|"
                         r"\d{1,2}(\.\d{1,3})+\.?\s|\d{1,2}[.)]\s)")


def parse_pdf(path: str | Path) -> dict:
    path = Path(path)
    doc = fitz.open(path)
    n = len(doc)
    first_pages_text = "\n".join(doc[i].get_text("text") for i in range(min(2, n)))[:6000]
    page_w = doc[0].rect.width if n else 612
    stats = Counter()

    # 1) raw material per page
    pages_lines, pages_tables, heights = [], [], []
    for pno, page in enumerate(doc, start=1):
        lines, clip = _raw_lines(page, pno), None
        if dx := _copy_shift(lines, page.rect.width):  # the same form twice on one sheet: read the left copy only
            split = min(l.x0 for l in lines) + dx - 3
            lines = [l for l in lines if l.x0 < split]
            clip = fitz.Rect(0, 0, split, page.rect.height)
            stats["duplicate_copies"] += 1
        pages_tables.append(_tables(page, pno, clip))
        pages_lines.append(lines)
        heights.append(page.rect.height)

    # 2) running headers / footers: lines or frame tables repeated across pages (digits ignored)
    def in_margin(l, h):
        return l.y1 < 0.12 * h or l.y0 > 0.88 * h

    margin_keys, any_keys, table_keys = Counter(), Counter(), Counter()
    for lines, h in zip(pages_lines, heights):
        margin_keys.update({_key(l.text) for l in lines if in_margin(l, h)})
        any_keys.update({_key(l.text) for l in lines})
    for tables in pages_tables:
        table_keys.update({t.key for t in tables})
    margin_boiler = {k for k, c in margin_keys.items() if n >= 2 and c >= max(2, 0.3 * n)}  # only in margins
    boiler = {k for k, c in any_keys.items() if n >= 3 and c >= max(3, 0.5 * n) and len(k) >= 4}  # anywhere

    toc_lines: list[Line] = []
    bookmarks = [TocEntry(_title_key(t), lvl) for lvl, t, _ in doc.get_toc()
                 if not _TOC_TITLE.match(t.strip()) and len(_title_key(t)) >= 3]
    flow_pages: list[list] = []  # per page: Line or Table, in reading order
    revision_history: list[str] = []
    prev_toc = False
    for lines, tables, h in zip(pages_lines, pages_tables, heights):
        kept_tables = []
        for t in tables:
            if n >= 2 and table_keys[t.key] >= max(2, 0.3 * n):
                stats["boilerplate_tables"] += 1
            elif sum(1 for c in t.rows[0] if _HISTORY_COLS.match(c)) >= 2 or any(
                    _HISTORY.search(c) for c in t.rows[0]):
                revision_history += _table_lines(t)
                stats["history_tables"] += 1
            else:
                kept_tables.append(t)
        all_tables = tables
        body_lines = []
        for l in lines:
            if any(_inside(l, t.bbox) for t in all_tables):
                continue  # read through the table (or dropped with it)
            if _key(l.text) in boiler or (in_margin(l, h) and (_key(l.text) in margin_boiler
                                                                 or _PAGE_NO.match(l.text))):
                stats["boilerplate_lines"] += 1
                if _LEADER.search(l.text):
                    toc_lines.append(l)  # navigation bars repeated on every page still list the headings
                continue
            body_lines.append(l)
        body_lines = _join_pieces(body_lines)

        # tables of contents: a TOC title, or a page mostly made of "title ..... 12" lines
        entries = [l for l in body_lines if _TOC_ENTRY.match(l.text) and (_LEADER.search(l.text) or
                                                                        len(l.text.split()) >= 2)]
        leaders = [l for l in body_lines if _LEADER.search(l.text)]
        title_at = next((i for i, l in enumerate(body_lines[:12]) if _TOC_TITLE.match(l.text)), None)
        is_toc = ((title_at is not None and len(entries) >= 3)
                  or (len(leaders) >= 5 and len(leaders) >= 0.4 * len(body_lines))
                  or (prev_toc and len(entries) >= 0.5 * max(len(body_lines), 1)))
        if is_toc:
            start = title_at or 0
            toc_lines += body_lines[start:]
            stats["toc_lines"] += len(body_lines) - start
            body_lines = body_lines[:start]
        else:
            for l in leaders:  # stray leader lines (list of figures under the TOC title of another page)
                toc_lines.append(l)
            body_lines = [l for l in body_lines if not _LEADER.search(l.text)]
        prev_toc = is_toc

        # reading order: a table goes where its first line would have been
        flow = list(body_lines)
        for t in kept_tables:
            pos = next((k for k, x in enumerate(flow) if isinstance(x, Line) and x.y0 >= t.bbox[1] - 1
                        and x.x0 < t.bbox[2]), len(flow))
            flow.insert(pos, t)
        flow_pages.append(flow)

    toc = bookmarks if len(bookmarks) >= 3 else []
    toc += _toc_entries(toc_lines)

    # 3) body font and left margin, from the remaining text
    content = [x for flow in flow_pages for x in flow if isinstance(x, Line)]
    sizes = Counter()
    for l in content:
        sizes[round(l.size * 2) / 2] += len(l.text)
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    lefts = Counter(round(l.x0) for l in content if abs(l.size - body) < 0.6)
    left = lefts.most_common(1)[0][0] if lefts else 72
    # normal space between two lines of a paragraph, relative to the font size (single / 1.5 line spacing...)
    ratios = Counter(round((b.y0 - a.y1) / a.size * 20) / 20 for a, b in zip(content, content[1:])
                     if a.page == b.page and abs(a.size - b.size) < 0.6 and -0.2 * a.size <= b.y0 - a.y1 < 1.5 * a.size)
    spacing = max(ratios.most_common(1)[0][0], 0.0) + 0.35 if ratios else 0.55

    # 4) headings
    flat = [x for flow in flow_pages for x in flow]
    line_idx = [i for i, x in enumerate(flat) if isinstance(x, Line)]
    only_lines = [flat[i] for i in line_idx]
    heads = _find_headings(only_lines, body, left, page_w, toc, spacing)
    for k, i in enumerate(line_idx):  # wrapped-heading lines consumed by _find_headings
        flat[i] = only_lines[k]
    head_at = {line_idx[k]: h for k, h in heads.items()}

    # definitions / acronym lists: their sub-entries are text; revision histories are dropped
    final: dict[int, Heading] = {}
    demote_below = drop_below = None
    for i in sorted(head_at):
        h = head_at[i]
        if drop_below is not None and h.level > drop_below:
            final[i] = Heading(h.line, h.number, h.title, -1)  # inside a history section
            continue
        drop_below = None
        if demote_below is not None and h.level > demote_below:
            continue  # stays a line of text
        demote_below = None
        if _HISTORY.search(h.title):
            drop_below = h.level
            final[i] = Heading(h.line, h.number, h.title, -1)
            continue
        if _DEFINITIONS.search(h.title):
            demote_below = h.level
        final[i] = h

    # 5) paragraphs -> chunks
    chunks: list[dict] = []
    outline: list[dict] = []
    stack: list[Heading] = []
    cur = {"parts": [], "size": 0, "page": None, "page_end": None, "path": [], "section": "", "table": 0}
    seen_heading = False
    front: list[str] = []
    dropping = False

    def matrix_section(st):
        for h in reversed(st):
            if h.level <= MATRIX_LEVEL:
                return h.text
        return st[0].text if st else ""

    def flush():
        text = "\n".join(cur["parts"]).strip()
        if text:
            chunks.append({"page": cur["page"], "page_end": cur["page_end"], "section": cur["section"],
                           "path": cur["path"], "kind": "table" if cur["table"] > len(text) / 2 else "text",
                           "text": text})
        cur.update(parts=[], size=0, page=None, page_end=None, table=0)

    def start_if_empty(page):
        if not cur["parts"]:
            cur["page"] = page
            cur["path"] = [h.text for h in stack]
            cur["section"] = matrix_section(stack)
        cur["page_end"] = page

    def add(text, page, table=False):
        if not text:
            return
        if not seen_heading:
            front.append(text)
            return
        if dropping:
            revision_history.append(text)
            return
        pieces = [text] if len(text) <= config.CHUNK_MAX_CHARS else _split_long(text, config.CHUNK_MAX_CHARS)
        for piece in pieces:
            if cur["parts"] and cur["size"] + len(piece) > config.CHUNK_MAX_CHARS:
                flush()
            start_if_empty(page)
            cur["parts"].append(piece)
            cur["size"] += len(piece) + 1
            if table:
                cur["table"] += len(piece)

    para: list[Line] = []

    def end_para():
        if para:
            add(_join_lines(para), para[0].page)
            para.clear()

    for i, x in enumerate(flat):
        if isinstance(x, Table):
            end_para()
            for row in _table_lines(x):
                add(row, x.page, table=True)
            stats["tables"] += 1
            continue
        if not x.text:
            continue
        h = final.get(i)
        if i in head_at and h is None:  # demoted (definition entry): a text line of its own
            end_para()
            para.append(x)
            end_para()
            continue
        if h is not None:
            end_para()
            if h.level == -1:
                dropping = True
                continue
            dropping = False
            seen_heading = True
            while stack and stack[-1].level >= h.level:
                stack.pop()
            if h.level <= MATRIX_LEVEL or cur["size"] >= config.CHUNK_MAX_CHARS // 2:
                flush()
            stack.append(h)
            outline.append({"level": h.level, "heading": h.text, "page": h.line.page})
            if h.level > MATRIX_LEVEL:
                add(h.text, h.line.page)  # sub-section title stays visible inside the chunk
            continue
        if para and not _continues_para(para[-1], x, spacing):
            end_para()
        para.append(x)
    end_para()
    flush()

    # no usable structure, or a "cover block" longer than the rest of the document (a form whose labels looked
    # like headings): keep everything before the first heading as text
    front_chars = sum(len(t) for t in front)
    if len(outline) < 3 or (front_chars > 1500 and front_chars > sum(len(c["text"]) for c in chunks)):
        chunks = _pack(front, flat) + chunks
        front = []
    stats["front_matter_chars"] = sum(len(t) for t in front)

    return {"source_file": path.name, "pages": n, "parser": PARSER_VERSION,
            "first_pages_text": first_pages_text, "outline": outline, "chunks": chunks,
            "front_matter": "\n".join(front)[:5000], "revision_history": "\n".join(revision_history)[:20000],
            "stats": dict(stats)}


def _pack(texts: list[str], flat) -> list[dict]:
    """Chunks for text without headings (documents where no structure was found)."""
    page = next((x.page for x in flat if isinstance(x, (Line, Table))), 1)
    out, buf = [], []
    for t in texts:
        if buf and sum(len(b) + 1 for b in buf) + len(t) > config.CHUNK_MAX_CHARS:
            out.append(buf)
            buf = []
        buf.append(t)
    if buf:
        out.append(buf)
    return [{"page": page, "page_end": page, "section": "", "path": [], "kind": "text", "text": "\n".join(b)}
            for b in out]


def _continues_para(prev: Line, ln: Line, spacing: float) -> bool:
    """Same paragraph: next line close below (or the top of the next page after an unfinished sentence),
    not a new list item."""
    if _LIST_START.match(ln.text):
        return False
    if ln.page != prev.page:
        return not prev.text.endswith((".", ":", ";", "!", "?")) and ln.text[:1].islower()
    gap = ln.y0 - prev.y1
    return -2 <= gap <= spacing * prev.size and abs(ln.size - prev.size) < 1.5


def _join_lines(lines: list[Line]) -> str:
    out = lines[0].text
    for ln in lines[1:]:
        if out.endswith("-") and len(out) > 1 and out[-2].isalpha() and ln.text[:1].islower():
            out += ln.text  # "adequando-" + "se" -> "adequando-se" (hyphens are kept: Portuguese needs them)
        else:
            out += " " + ln.text
    return out


def _split_long(text: str, limit: int) -> list[str]:
    """A paragraph longer than a chunk: cut at sentence ends (or row/line breaks), never mid-sentence if avoidable."""
    sentences = [s for s in re.split(r"(?<=[.;!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9(\"“•-])|\n", text) if s.strip()]
    out, buf = [], ""
    for s in sentences:
        while len(s) > limit:  # one enormous sentence: cut at a space
            cut = s.rfind(" ", 0, limit) or limit
            if buf:
                out.append(buf)
                buf = ""
            out.append(s[:cut])
            s = s[cut:].strip()
        if buf and len(buf) + len(s) + 1 > limit:
            out.append(buf)
            buf = ""
        buf = f"{buf} {s}".strip()
    if buf:
        out.append(buf)
    return out
