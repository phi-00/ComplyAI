"""English / Portuguese display mode.

The analysis runs once, in the output language (English, prompts.OUT_LANG): every prompt, safeguard and test is
tuned for it, and a second analysis in Portuguese would give other verdicts. Afterwards every stored text is
translated into the other display language and kept in the `translations` table, so the app / chat / exports can
switch language without any LLM call:

  - customer documents and ITs: passage text (chunks), section headings (section_labels), IT rules, document
    titles, IT profiles, the IT index titles;
  - requirements: statement, original quote, change / quality notes;
  - IT comparisons: explanation, action, IT evidence; alerts: title, detail, action; section reasons.

A text already in a language (detected with stop words, `detect`) is not translated into it: the original is shown.
Each translation keeps the hash of its source text; when the source is edited (e.g. a requirement corrected in the
app) the copy is stale and the original is shown until `translate` runs again. Translations of customer / IT text
are reading aids made by the local model, not the binding text: the grounding checks run on the originals.

Resumable: each batch is written as soon as it is done; rerunning only translates what is missing or stale.
"""
import hashlib
import json
import logging
import re
import time

from . import config, llm, prompts

log = logging.getLogger("complyai.i18n")

LANGS = {"en": "English", "pt": "Portuguese"}       # code -> name (section_labels.language uses the name)

# (table, key column, text columns, condition); "doc" = SQL expression of the row's document id
SOURCES = [
    ("requirements", "id", ("statement", "quote", "change_note", "quality_note"), "status='active'", "doc_id"),
    ("req_it_links", "id", ("explanation", "action", "evidence"), "source='text' AND verdict!='not_related'",
     "(SELECT r.doc_id FROM requirements r WHERE r.id=req_it_links.req_id)"),
    ("findings", "id", ("title", "detail", "action"), "", "doc_id"),
    ("section_its", "id", ("reason",), "", "doc_id"),
    ("chunks", "id", ("text",), "doc_id IN (SELECT id FROM documents WHERE status='active')", "doc_id"),
    ("it_rules", "id", ("rule",), "doc_id IN (SELECT id FROM documents WHERE status='active')", "doc_id"),
    ("documents", "id", ("title",), "status='active'", "id"),
    ("it_catalog", "code", ("title",), "", None),
]
PROFILE_KEYS = ("purpose", "applies_to", "trigger", "actors", "out_of_scope")   # documents.meta_json "profile"

# markers the code puts in front of stored text, kept out of the translation and shown in the display language
MARKERS = {"[not verbatim] ": {"pt": "[não literal] ", "en": "[not verbatim] "}}

STOP = {
    "en": set("the and of to shall must be is are for with in on by or an this that not all which will should from "
              "as it its any each have has been at their where when if than other these those such into".split()),
    "pt": set("de da do das dos e o os as que em no na nos nas para com por um uma ser deve devem é são não ao à "
              "aos pelo pela se ou foi está estão sua seu quando onde cada mais como".split()),
    "de": set("der die und ist mit für von zu den nicht werden sind ein eine auf des im dem zur zum muss müssen "
              "oder bei nach wird sowie".split()),
}
_WORDS = re.compile(r"[^\W\d_]+")
_FILE_NAME = re.compile(r"^\S[^\n]{0,150}\.(?:pdf|xlsx?|xltx?|docx?|pptx?|json|txt)$", re.I)
_ACCENT = {"pt": re.compile(r"[ãõçâêôáéíóúà]"), "de": re.compile(r"[äöüß]")}


def code(lang) -> str:
    """'pt', 'PT-pt', 'Portuguese', 'Português' -> 'pt'; anything else (None, 'en', 'English') -> 'en'."""
    return "pt" if str(lang or "").strip().lower().startswith(("pt", "portug")) else "en"


def analysis_lang() -> str:
    """Language the analysis writes in (requirements, explanations, alerts)."""
    return code(prompts.OUT_LANG)


def detect(text: str) -> str | None:
    """'en' / 'pt' / 'de' by stop words (+ accented letters), None when the text has no clue (codes, single
    words, numbers). Mixed texts get their main language."""
    words = _WORDS.findall((text or "").lower())
    if not words:
        return None
    score = {lang: sum(w in stop for w in words) for lang, stop in STOP.items()}
    for lang, rx in _ACCENT.items():
        score[lang] += 2 * bool(rx.search(text.lower()))
    best = max(score, key=score.get)
    return best if score[best] else None


def needs(text: str, lang: str) -> bool:
    """Does `text` need a translation to be shown in `lang`? Not for empty text, codes and numbers, or text
    already in that language; texts without a clue (short labels) are sent: the model returns them unchanged."""
    if not text or not re.search(r"[^\W\d_]{3,}", text):
        return False
    if _FILE_NAME.search(text.strip()):  # a file name used as title ("SupplierQualityManual2022 version3.0.pdf")
        return False
    return detect(text) != lang


def numbers(text: str) -> list[str]:
    """Digit runs of a text, sorted ("1,5 mm" and "1.5 mm" give the same): the translation must keep them all."""
    return sorted(re.findall(r"\d+", text or ""))


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def _split_marker(text: str) -> tuple[str, str]:
    for m in MARKERS:
        if text.startswith(m):
            return m, text[len(m):]
    return "", text


# ---- what has to be translated ------------------------------------------------------------------------------------
def _display_source(table: str, col: str, value: str, row) -> str:
    """The text as it is shown (actions: engine.action_text, as in the exports), which is what gets translated."""
    if col == "action" and value and (table == "req_it_links" or row["type"] in ("CONFLICT", "GAP", "IT_STRICTER")):
        from .engine import action_text
        return action_text(value)
    return value


def jobs(store, doc_ids=None, langs=("en", "pt"), catalog=True) -> list[tuple]:
    """(table, key, column, lang, source text, hash of the stored value) of every text that has no fresh
    translation yet. doc_ids: only those documents (None = all); catalog: include the IT index titles."""
    # a translation whose numbers differ from the source is not shown (View) and is tried again on the next run
    have = {(r["tbl"], r["key"], r["col"], r["lang"]): r["src_hash"]
            for r in store.q("SELECT tbl, key, col, lang, src_hash FROM translations WHERE ok=1")}
    out = []

    def add(table, key, col, value, shown):
        h = _hash(value)
        for lang in langs:
            if needs(shown, lang) and have.get((table, str(key), col, lang)) != h:
                out.append((table, str(key), col, lang, shown, h))

    for table, key, cols, cond, doc in SOURCES:
        if doc is None and not catalog:
            continue
        where = [cond] if cond else []
        args = ()
        if doc_ids is not None and doc is not None:
            where.append(f"{doc} IN ({', '.join('?' for _ in doc_ids)})")
            args = tuple(doc_ids)
        extra = ", type" if table == "findings" else ""
        sql = f"SELECT {key} AS k, {', '.join(cols)}{extra} FROM {table}" + (f" WHERE {' AND '.join(where)}"
                                                                           if where else "")
        for r in store.q(sql, args):
            for col in cols:
                if r[col]:
                    add(table, r["k"], col, r[col], _display_source(table, col, r[col], r))
    # IT profiles (documents.meta_json "profile")
    sql = "SELECT id, meta_json FROM documents WHERE status='active'"
    args = ()
    if doc_ids is not None:
        sql += f" AND id IN ({', '.join('?' for _ in doc_ids)})"
        args = tuple(doc_ids)
    for r in store.q(sql, args):
        prof = (json.loads(r["meta_json"] or "{}") or {}).get("profile") or {}
        for k in PROFILE_KEYS:
            if isinstance(prof.get(k), str) and prof[k]:
                add("documents", r["id"], f"profile.{k}", prof[k], prof[k])
    return out


# ---- translating ------------------------------------------------------------------------------------------------
def _translate_batch(texts: list[str], lang: str) -> list[tuple[str, bool]]:
    """[(translation, numbers kept)] for one batch; a misaligned answer is split in halves, a text whose numbers
    changed is redone alone once; a text that still fails comes back as None (left for the next run)."""
    try:
        out = llm.chat_json(prompts.bilingual_system(lang), prompts.translate_user(texts), prompts.TRANSLATE_SCHEMA,
                            max_tokens=2400, grounding=prompts.BILINGUAL_GROUNDING).get("translations", [])
    except llm.LLMError as e:
        log.debug("translation batch failed: %s", e)
        out = []
    if len(out) != len(texts):
        if len(texts) == 1:
            return [(None, False)]
        half = len(texts) // 2
        return _translate_batch(texts[:half], lang) + _translate_batch(texts[half:], lang)
    res = []
    for src, t in zip(texts, out):
        t = re.sub(r"^\[\d+\]\s*", "", (t or "").strip())
        ok = bool(t) and numbers(t) == numbers(src)
        if not ok and len(texts) > 1:
            t, ok = _translate_batch([src], lang)[0]
        res.append((t or None, ok))
    return res


def _batches(items: list, batch: int = 12, max_chars: int = 2500) -> list[list]:
    """Group by count AND length (long texts would overflow the answer)."""
    out, cur, size = [], [], 0
    for it in items:
        n = len(it[4])
        if cur and (len(cur) >= batch or size + n > max_chars or cur[0][3] != it[3]):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        out.append(cur)
    return out


def translate(store, doc_ids=None, langs=("en", "pt"), catalog=True, headings=True, limit=None) -> dict:
    """Fill the translations of the given documents (None = the whole DB) in both display languages. Resumable.
    Returns counts: texts translated, failed (kept for the next run), numbers changed (stored, ok=0)."""
    from .engine import _pimap, section_labels
    t0 = time.time()
    todo = jobs(store, doc_ids, langs, catalog)
    todo.sort(key=lambda j: (j[3], j[0], j[1]))
    if limit:
        todo = todo[:limit]
    log.info("translation: %d texts (%d chars) to translate", len(todo), sum(len(j[4]) for j in todo))
    done = failed = changed = 0
    batches = _batches(todo)

    def run(batch):
        marked = [_split_marker(j[4]) for j in batch]
        res = _translate_batch([m[1] for m in marked], batch[0][3])
        return batch, marked, res

    for batch, marked, res in _pimap(run, batches, "translation"):
        for job, (marker, _), (text, ok) in zip(batch, marked, res):
            table, key, col, lang, _, h = job
            if text is None:
                failed += 1
                continue
            if marker:
                text = MARKERS[marker][lang] + text
            store.db.execute("INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?,?)",
                             (table, key, col, lang, text, h, int(ok)))
            done += 1
            changed += not ok
        store.commit()
    if headings:
        ids = doc_ids if doc_ids is not None else [r["id"] for r in store.q(
            "SELECT id FROM documents WHERE status='active'")]
        for doc_id in ids:
            for lang in langs:
                section_labels(store, doc_id, lang)
    log.info("translation: %d done, %d failed, %d with changed numbers in %.0fs", done, failed, changed,
             time.time() - t0)
    return {"texts": done, "failed": failed, "numbers_changed": changed, "seconds": round(time.time() - t0)}


def status(store, doc_ids=None) -> dict:
    """Per language: texts that need a translation, how many are done (fresh), stale / missing, numbers changed."""
    out = {}
    for lang in LANGS:
        missing = jobs(store, doc_ids, (lang,), catalog=doc_ids is None)
        done = store.one("SELECT COUNT(*) AS n, SUM(ok=0) AS bad FROM translations WHERE lang=?", (lang,))
        out[lang] = {"missing_or_stale": len(missing), "stored": done["n"],
                     "numbers_changed (original shown, retried next run)": done["bad"] or 0}
    return out


def enabled() -> bool:
    """Translate during processing (ingest / reassess)? COMPLYAI_BILINGUAL=0 switches it off (tests)."""
    return config.BILINGUAL


def after_processing(store, doc_id: int | None = None) -> dict | None:
    """Hook for the CLI / server after a document was ingested or re-assessed: translate whatever is new or
    stale in the whole DB (a new IT re-checks other documents' requirements too; finding the work takes <1 s) and
    the headings of `doc_id`."""
    if not enabled():
        return None
    try:
        res = translate(store, None, headings=False)
        if doc_id is not None:
            from .engine import section_labels
            for lang in LANGS:
                section_labels(store, doc_id, lang)
        return res
    except Exception as e:  # noqa: BLE001 - a translation problem must not fail the analysis
        log.warning("translation after document %s failed: %s (run `python -m complyai translate-all`)", doc_id, e)
        return None


# ---- reading in a display language --------------------------------------------------------------------------
class View:
    """Stored texts in one display language. rows() returns dicts with the translated columns (fresh
    translations only; the original otherwise). Without a translation table the originals come back."""

    def __init__(self, store, lang=None):
        self.store, self.lang = store, code(lang) if lang else analysis_lang()
        self._labels = {}
        self._shown = set()   # translations this view returned (action(): already in display form)

    @property
    def translated(self) -> bool:
        """True when this view shows another language than the analysis (actions are already in display form)."""
        return self.lang != analysis_lang()

    def _lookup(self, table: str, keys: list[str]) -> dict:
        found = {}
        for i in range(0, len(keys), 500):
            part = keys[i:i + 500]
            for r in self.store.q(f"SELECT key, col, text, src_hash FROM translations WHERE tbl=? AND lang=? AND ok=1 "
                                  f"AND key IN ({', '.join('?' for _ in part)})", (table, self.lang, *part)):
                found[(r["key"], r["col"])] = (r["text"], r["src_hash"])
        return found

    def rows(self, table: str, rows, cols=None, key: str = "id") -> list[dict]:
        rows = [dict(r) for r in rows]
        if not rows:
            return rows
        cols = cols or next(c for t, _, c, *_ in SOURCES if t == table)
        found = self._lookup(table, list(dict.fromkeys(str(r[key]) for r in rows if r.get(key) is not None)))
        for r in rows:
            for col in cols:
                if col in r and r[col]:
                    hit = found.get((str(r.get(key)), col))
                    if hit and hit[1] == _hash(r[col]) and not _FILE_NAME.search(r[col].strip()):
                        r[col] = hit[0]
                        self._shown.add(hit[0])
                    else:  # shown as written (already in this language, or not translated yet): marker in language
                        marker, rest = _split_marker(r[col])
                        if marker:
                            r[col] = MARKERS[marker][self.lang] + rest
        return rows

    def row(self, table: str, row, cols=None, key: str = "id") -> dict | None:
        return self.rows(table, [row], cols, key)[0] if row is not None else None

    def profile(self, doc_id: int, prof: dict) -> dict:
        prof = dict(prof or {})
        keys = [f"profile.{k}" for k in PROFILE_KEYS if isinstance(prof.get(k), str) and prof[k]]
        if keys:
            found = self._lookup("documents", [str(doc_id)])
            for k in PROFILE_KEYS:
                hit = found.get((str(doc_id), f"profile.{k}"))
                if hit and prof.get(k) and hit[1] == _hash(prof[k]):
                    prof[k] = hit[0]
        return prof

    def section(self, doc_id: int, section: str) -> str:
        """A heading in this language (cache only, no LLM call)."""
        if not section:
            return section
        if doc_id not in self._labels:
            from .engine import section_labels
            self._labels[doc_id] = section_labels(self.store, doc_id, self.lang, cached_only=True)
        return self._labels[doc_id].get(section, section)

    def action(self, text: str) -> str:
        """An action as shown: the analysis language gets engine.action_text (verb first); a translation already
        is the translated action_text (an untranslated one still gets action_text)."""
        if text in self._shown:
            return text or ""
        from .engine import action_text
        return action_text(text)

    def t(self, key: str) -> str:
        """A fixed label (export headers, statuses) in this language."""
        return LABELS.get(key, {}).get(self.lang, key) if self.lang != "en" else key


# fixed labels of the exports and the chat (English key -> Portuguese)
LABELS = {k: {"pt": v} for k, v in {
    # statuses / changes
    "Conflict": "Conflito", "Partial – review IT": "Parcial – rever IT",
    "IT stricter than required": "IT mais exigente do que o requerido", "Compliant": "Conforme",
    "To verify (index)": "A verificar (índice)", "No related IT": "Sem IT relacionada",
    "New": "Novo", "Changed": "Alterado", "Unchanged": "Sem alteração",
    "new": "novo", "changed": "alterado",
    # sheet names and headers
    "Status by section": "Estado por secção", "Requirements": "Requisitos", "Alerts": "Alertas",
    "Section": "Secção", "Page": "Página", "ITs assessed / suggested": "ITs avaliadas / sugeridas",
    "Status": "Estado", "Changes vs previous version": "Alterações face à versão anterior", "ID": "ID",
    "Requirement": "Requisito", "Original text": "Texto original", "Category": "Categoria",
    "Obligation": "Obrigação", "Parameters": "Parâmetros", "Change": "Alteração",
    "Change detail": "Detalhe da alteração", "IT assessed": "IT avaliada", "Analysis": "Análise",
    "IT evidence": "Evidência na IT", "Recommended action": "Ação recomendada",
    "Suggested ITs (index)": "ITs sugeridas (índice)", "LEONI process": "Processo LEONI",
    "Date": "Data", "Type": "Tipo", "Severity": "Gravidade", "IT": "IT", "Title": "Título", "Detail": "Detalhe",
    "Action": "Ação", "req.": "req.",
    # matrix header
    "Publication Date": "Data de publicação",
    "Generated by LEONI COMPLY-AI on {date}. PROC. WSD lists only the central LEONI procedures loaded in the "
    "system: complete it manually.":
        "Gerado pelo LEONI COMPLY-AI em {date}. A coluna PROC. WSD lista apenas os procedimentos centrais LEONI "
        "carregados no sistema: completar manualmente.",
    " WARNING: includes SIMULATED ITs (*), generated for demonstration — not real LEONI ITs.":
        " ATENÇÃO: inclui ITs SIMULADAS (*), geradas para demonstração — não são ITs reais da LEONI.",
    "Translated by COMPLY-AI's local model: the customer document and the ITs in their original language are the "
    "reference.": "Traduzido pelo modelo local do COMPLY-AI: o documento do cliente e as ITs na língua original "
                  "são a referência.",
    # severities / alert types (shown as written in the app's data: only the export translates them)
    "high": "alta", "medium": "média", "low": "baixa", "info": "info", "open": "aberto",
    "GAP": "LACUNA", "CONFLICT": "CONFLITO", "IT_STRICTER": "IT MAIS EXIGENTE",
    "REQ_CONTRADICTION": "CONTRADIÇÃO ENTRE REQUISITOS", "REQ_MODIFIED": "REQUISITO ALTERADO",
    "REQ_NEW": "REQUISITO NOVO", "REQ_REMOVED": "REQUISITO REMOVIDO", "IT_UPDATED": "IT ATUALIZADA",
}.items()}
