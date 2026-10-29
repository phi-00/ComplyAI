# LEONI COMPLY-AI — AI engine

Local-LLM engine that reads customer requirement documents (CSR / STD), stores them, maps them
against LEONI's Work Instructions (ITs), detects **conflicts / gaps** and **requirement changes
between versions**, raises notifications and exports the compliance matrix (Excel, IT 3535-11 A5 style).

Scope of this repo: the AI part and the PDF parser (`complyai/parser.py`). The server and the App are owned
by other team members; the storage (SQLite) is temporary.

```
                ┌────────────┐ ParsedDocument JSON ┌────────────────────────────────── engine.py ─┐
 IT PDF ───────►│ parser.py  │────────────────────►│ ingest_it (once per IT version):             │
                │ (headings, │                     │   700-char windows + embeddings (bge-m3)     │
 CSR / STD PDF ►│ tables)    │                     │   IT profile (purpose/scope/trigger) + rules │
                └────────────┘                     │ ingest_csr:                                  │
 WI/IC index .xlsx ──► catalog.py (305 ITs)        │   1 LLM extracts requirements, drops         │
                                                   │     definitions/info, grounds numbers, dedup │
                                                   │   2 change detection vs client's older reqs  │
                                                   │   3 retrieve IT rules/passages + index ITs   │
                                                   │     (requirement, section heading, ISO clause│
                                                   │   4 LLM judge per IT -> 5 strict verification│
                                                   │   6 section-level IT mapping (matrix)        │
                                                   │   7 findings = notifications                 │
                                                   └──────────┬────────────────────┬──────────────┘
                                                              ▼                    ▼
                                                 data/complyai.db      data/exports/Matriz_*.xlsx
                                                 data/notifications.jsonl
```

Models: qwen3:8b (chat) and bge-m3 (embeddings), both local via Ollama; which step uses which model, in which
mode, is in **`docs/models.md`**; why these and not others in `docs/llm_options_evaluation.md`.

## Setup

1. Install [Ollama](https://ollama.com), then pull the models:
   ```bash
   ollama pull qwen3:8b
   ```
   ```bash
   ollama pull bge-m3
   ```
2. Ollama server settings (environment variables read when Ollama starts; on Windows set them as user
   variables and restart the Ollama app after changing them):

   | Variable | Value | Why |
   |---|---|---|
   | `OLLAMA_NUM_PARALLEL` | `4` | GPU batches 4 requests at once (8 was not faster on a 4070 Ti) |
   | `OLLAMA_FLASH_ATTENTION` | `1` | required for the quantised KV cache, faster |
   | `OLLAMA_KV_CACHE_TYPE` | `q8_0` | halves KV-cache VRAM per slot |
   | `OLLAMA_MAX_LOADED_MODELS` | `2` | chat model and embedding model stay in VRAM together |

   VRAM used = model + `NUM_CTX` × `OLLAMA_NUM_PARALLEL` KV cache. Keep `COMPLYAI_NUM_CTX=4096` (prompts are
   capped to fit). **Only use models that fit entirely in VRAM** — check `ollama ps` shows `100% GPU`.
   If VRAM overflows, Windows pages GPU memory to RAM (~10× slower); a model partly on the CPU also puts
   every CPU core at full load for as long as the run lasts (qwen3:14b on this 12 GB card did this).
3. Python 3.11+ with `pip install -r requirements.txt`.
4. `python -m complyai check` confirms the LLM server and models are reachable.

### Files not in the repository

The documents LEONI provided for this project and everything the engine generates are kept out of version
control (`.gitignore`). The commands, tests and tools expect them at these paths, relative to the repository root:

| Path | What | Used by |
|---|---|---|
| `Leoni/Leoni/*.pdf`, `Leoni/Leoni/WI_Indice_11_Rev199.xlsx`, `Leoni/Leoni/IC_Indice_11_Rev113.xlsx` | first 7 LEONI IT documents and the WI / IC index | `load-index`, `ingest-it`, `tests/scenario.py`, `tests/test_parser.py`, `tools/rebuild_real_db.sh` |
| `Leoni/Leoni/RE__Pedido_de_Documentação_Exemplo/` | second IT batch (27 documents, 2026-10-22) | `tools/load_new_its.sh`, `tests/test_parser.py` |
| `Cliente/Cliente/*.pdf`, `Cliente/SupplierQualityManual2022 version3.0/` | the 7 customer documents (Cummins, John Deere, Caterpillar) | `ingest-csr`, `tests/test_parser.py`, `tools/rebuild_real_db.sh` |
| `IT-3535-11-A5_Matriz_ CSR_CUMMINS_jan- 2026.xls.xlsx` | LEONI's filled Cummins matrix (evaluation only, never a source of answers) | `tests/eval_cummins.py` |
| `IT-3535-11-A4_Requisitos clientes – análise da conformidade.xlsx` | LEONI's filled conformity-analysis form (layout only) | `tools/make_a4_template.py` (the blank templates made from both LEONI forms, `complyai/templates/`, are in the repository) |
| `LEONI-Comply-AI (1).pdf` | project brief | — |
| `data/` | database, Excel exports, notifications, logs, snapshots | created by the engine on the first run |

**Language:** everything the AI writes (requirements, analyses, actions, alerts) and all labels are in
English, like LEONI's correspondence matrices. IT titles and quotes stay as written in the source
documents, except section headings in the matrix, which are translated once per document and cached
(`section_labels`), e.g. "K. Competência (7.2)" -> "K. Competence (7.2)".
`COMPLYAI_OUTPUT_LANGUAGE="Portuguese (Portugal)"` switches the AI output to Portuguese.

## Usage (CLI emulating the server)

```bash
python -m complyai load-index Leoni/Leoni/WI_Indice_11_Rev199.xlsx Leoni/Leoni/IC_Indice_11_Rev113.xlsx
```
```bash
python -m complyai ingest-it "Leoni/Leoni/*.pdf"
```
```bash
python -m complyai ingest-csr "Cliente/Cliente/JDS-G223X3 - Production Part Approval (PPAP) Requirements_Nov2021.pdf"
```
```bash
python -m complyai findings
```

| Command | What it does |
|---|---|
| `docs` | list documents, versions, status |
| `findings [--all]` | alerts (conflicts, gaps, requirement changes) |
| `export <doc_id>` | regenerate the Excel matrix (LEONI IT 3535-11 A5 format + detail sheets) |
| `reassess <doc_id> [--changed-only]` | re-run only the IT comparison (after new ITs / prompt changes), no re-extraction. `--changed-only`: only requirements whose ITs for the judge differ from those of their stored assessment (after a change to the IT selection; running it again resumes) |
| `translate <doc_id>` | switch an already processed document to the output language without re-analysis (statements, analyses, actions, alerts; source quotes and IT evidence stay as written) |
| `retry-failed <doc_id>` | re-extract passages whose extraction failed (marked in `chunks.extract_failed`) and assess them |
| `it-knowledge [--profiles-only]` | rebuild IT profiles + rules of all active ITs (`--profiles-only`: one fast call per IT) |
| `parse <pdf> [--json out.json] [--text]` | run only the parser: outline, passages, what was removed (no LLM, no database) |
| `reset` | delete database and notifications |

**Interrupted runs** (power cut, crash): just run the same command again. A document is marked
`processing` until its requirements are complete (a re-run purges and redoes it); after that, the IT
comparison writes each requirement's result as soon as it is ready, and a re-run of the same file
finishes an incomplete comparison (`docs` flags it).

`ingest-csr` options: `--client --code --version --title` (otherwise the LLM reads them from the first
pages) and `--max-chunks N` for quick tests. Ingesting the same content twice is skipped (hash).
Both `ingest-*` commands accept a PDF **or a `.json` ParsedDocument** (e.g. saved with `parse --json`).

`ingest-it --no-recheck` is for a **batch of new ITs**: each new IT normally re-assesses every requirement close
to it, which repeats work when many ITs arrive together; with the flag, run `reassess <doc_id>` once per customer
document afterwards. `bash tools/load_new_its.sh <folder> <batch>` does both, resumable (snapshot first, ITs skipped
by hash, documents already re-assessed in the batch skipped). IT codes come from the file name or the first page:
local `WI/IT/IC` codes carry the plant suffix (`WI 3234-11 A1`), central LEONI procedures do not (`VA 3160 A2`).
Only PDFs are read: Excel / PowerPoint annexes (blank forms, calculators) are not ingested.

## Parser (`complyai/parser.py`)

Made for digital PDFs (with a text layer — every customer and LEONI document so far), on PyMuPDF only:

1. **Lines** with font, size, boldness and position. Pieces of one visual row stored separately are joined
   (heading number + title, bullet + text, "IT :" + its duty in two-column layouts).
2. **Noise removed**: running headers/footers (lines or frame tables repeated across pages, digits ignored),
   page numbers, printed tables of contents, navigation bars (Caterpillar's on every page), revision
   histories (section or table), the cover block before the first heading (unless it is longer than the rest of
   the document: then it is a form whose labels looked like headings, and it is kept), text below 4 pt
   (thumbnails), the second copy of a form printed twice side by side on one sheet (2-up: same lines at the same
   height, about half a page apart; only the left copy is read).
3. **Tables** (ruled) read as tables: one self-contained line per row, `Header: value; Header: value`;
   values stacked in one cell per column are split into rows; long tables are split by rows.
4. **Headings** from numbering (`5.4.3`, `A.`/`AA.`, `1.0`, `Annex B`) + typography (bold or bigger than the
   body text) + the document's own table of contents or bookmarks. A numbered line with *shall/must/deve…*
   is a numbered requirement, not a heading; numbering must form a sequence (a bold "1." after section 6 is
   a list item); "Anexo 9 Corte:" (annex/letter numbering ending with a colon) introduces a list, it is not a
   section; in a numbered document an unnumbered line is a heading only if the TOC lists it. A numbered title
   wrapped onto a second line (in the TOC or in the text, also with a hanging indent) is joined.
   **Levels** from the numbering (letters = level 1, numbers under them level 2), else the TOC indentation,
   else the level of headings with the same font. Entries under a definitions / acronyms heading stay text;
   "(CONTINUED)" titles and a title repeated on the next page are not new sections.
5. **Chunks** of ≤ `CHUNK_MAX_CHARS` that never cross a matrix-level heading (level ≤ 2), end preferably where
   a sub-section ends, keep deeper headings inline as lines, keep paragraphs / list items / table rows on
   their own lines and never cut a sentence if avoidable.

Measured on the 14 PDFs (`tests/test_parser.py`, ~1 min): 0.1–1.6 % of the old parser's words are gone, all
headings or cover/legal boilerplate; matrix rows Caterpillar SQM 3 → 39, Cummins handbook 36 → 61 (all
lettered sections plus their sub-sections, like LEONI's own matrix); ~0.1–9 s per document. The second batch of
LEONI ITs (28 PDFs, 2026-10-22) is covered too: expected headings for WI 3157-11, 3196-11, 3236-11 and the 2-up
forms WI 3326-11 A1/A2; the parser changes for it left the output of the 14 earlier PDFs unchanged (same content
hashes, so nothing already in the database is seen as a new version).
Not handled: scanned PDFs (no text layer → no OCR), multi-column body text (reading order follows the
PDF's content stream, which is correct for Word-generated documents), tables without ruling lines (kept as
text lines), headings that are images.

### ParsedDocument contract

```json
{
  "source_file": "WI-3404-11.pdf",
  "pages": 9,
  "parser": "complyai-pdf/1.0",
  "first_pages_text": "raw text of the first 2 pages (code / version / client detection)",
  "outline": [{"level": 1, "heading": "5 CONTEÚDO", "page": 4},
              {"level": 2, "heading": "5.1 Planeamento de produção", "page": 4}],
  "chunks": [
    {"page": 4, "page_end": 4, "kind": "text",
     "path": ["5 CONTEÚDO", "5.1 Planeamento de produção"],
     "section": "5.1 Planeamento de produção",
     "text": "As encomendas planeadas no FORS são importadas no LPMCS ...\n5.1.1 Fecho das ordens de produção\n..."}
  ],
  "front_matter": "cover text before the first heading (not analysed)",
  "revision_history": "revision history rows (not analysed)",
  "stats": {"boilerplate_lines": 63, "toc_lines": 8, "history_tables": 1, "tables": 1, "front_matter_chars": 840}
}
```

* `chunks` in reading order. `path` = headings from the top level down to where the chunk starts (shown to the
  LLM as `5 CONTEÚDO > 5.1 Planeamento de produção`, embedded with the text); `section` = the matrix-level
  heading (deepest of `path` with level ≤ 2), the unit of the matrix rows; `kind` = `table` when most of the
  text is table rows. `path[0]` is the top-level section used for the section-level IT mapping.
* `outline` = every heading with its level: the Excel matrix lists levels 1–2 (level 1 bold), like LEONI's form.
* Required for the engine: `source_file` and `page` / `text` per chunk; everything else has a default
  (`engine._normalize`), so generated ParsedDocuments (mock ITs, tests) can stay minimal.

## How each requirement of the brief is covered

| Brief | Where |
|---|---|
| Centralised IT base with versions | `ingest_it`: IT stored once (windows + embeddings + profile + rules); a new version of the same code supersedes the old one and re-assesses every *active* requirement linked or close to it; finding `IT_UPDATED` |
| AI reads CSR/STD paragraph by paragraph | `ingest_csr`: passages with obligation language (EN/PT/DE/ES pre-filter) → LLM returns atomic requirements (statement in English by default (`COMPLYAI_OUTPUT_LANGUAGE`), verbatim quote, kind, category, obligation, parameters) |
| Semantic mapping requirement ↔ ITs | `assess_requirements`: retrieval over IT windows **and** extracted IT rules; index candidates from the requirement, its section heading and the ISO clause in the heading; LLM judges each IT with its profile, closest rules and an excerpt, and picks the related index ITs |
| Conflicts / warnings | `conflict` → `CONFLICT` (high), `partial` → `GAP` (medium), each confirmed by `_verify` |
| Version deltas | `detect_changes`: vs. the previous version of the same document (`REQ_MODIFIED`, `REQ_NEW`, `REQ_REMOVED`, old requirements superseded). Changed numbers are never treated as "unchanged". `cross_document_check`: vs. the client's OTHER documents only real contradictions (LEONI cannot satisfy both) raise `REQ_CONTRADICTION`; repetitions and elaborations (manual vs. its annex) are normal and not flagged |
| Excel matrix | `map_sections`: per top-level section one reasoning-mode call picks the ITs that govern it (heading + its requirements + pooled index candidates), like LEONI builds IT 3535-11 A5. `export.py`: sheet **Matrix in LEONI's own form IT 3535-11 Anexo 5** (template `complyai/templates/IT-3535-11-A5_template.xlsx`, made from LEONI's Cummins matrix): every section of the document with page, PROCESSO LEONI and the local ITs under PROC. WPTGU ("• IT 3157-11 …"); PROC. WSD lists the central procedures (VA / PI codes) the requirements of the section were linked to, as LEONI's matrix does ("• VA 3160 …"); only VA 3160 A2 is loaded so far, the rest of that column is completed by hand. Extra sheets: *Status by section* (verdicts), *Requirements* (per requirement with evidence/actions), *Alerts* |

## Accuracy safeguards

| Safeguard | Against |
|---|---|
| **Context lock**: the model runs offline without tools; each call holds only the passage / IT excerpts in question; every system prompt ends with `prompts.GROUNDING` (use only the given text, nothing from general knowledge, leave empty if not stated, quote word for word); the code then checks what came back (next rows). `tests/audit_grounding.py` measures it on any database | answers from the model's general knowledge or invented text |
| Quote check (`_ground_quotes`): a requirement whose quote is not in its passage (< 50 % of the words) is dropped, a partial match is marked | requirements the document does not contain |
| IT rule check: a rule extracted from an IT with a number that is not in the IT passage is dropped | invented values entering the IT knowledge (seen: "código 1238" for 128) |
| Evidence shown as real IT text (`_source_sentence`): evidence the model paraphrased or translated is replaced by the IT sentence it refers to (bge-m3 match), else marked "[not verbatim]" | the matrix showing IT "quotes" that are not in the IT (15 % before) |
| Optional cross-encoder **reranker** (`COMPLYAI_RERANK=1`, `complyai/rerank.py`, bge-reranker-v2-m3 via PyTorch + transformers): re-scores the closest IT passages/rules per requirement by their best sentence, with values masked on both sides (so an IT that *contradicts* the requirement still counts as relevant); only those ≥ `RERANK_MIN` reach the judge. **Off**: measured 2026-10-19 in two versions. Version 2 keeps contradictions (scenario 14/14), but on the real Cummins handbook it saves only 4 % of the judge work and does not reduce wrong alerts; see `docs/llm_options_evaluation.md` | ITs that share words with a requirement but not its activity |
| "Magnet" texts (2026-10-23): IT rules of fewer than 9 words without a number are not retrieval candidates, and every IT window / rule is ranked by its cosine minus 0.3 × its mean cosine to its 10 closest requirements of all documents (`_hubs`, `_candidates`; `IT_RULE_MIN_WORDS`, `COMPLYAI_IT_HUB_WEIGHT`, only with ≥ 200 requirements stored). Measured without the LLM: labelled relevant pairs the judge sees 32 → 50 of 109, unrelated 49 → 30 of 144; LEONI's Cummins ITs shown 8 → 10 of 12; blind sample of the changed slots: 4/30 added vs 1/30 dropped are relevant | generic IT texts close to every requirement ("The supplier's description must be provided." won 17 % of all IT slots, short rules 26 %), because the requirements are all written "The supplier shall/must …" |
| Optional IT families (`COMPLYAI_IT_PER_FAMILY=1`, **off**): a base IT and its annexes take one of the 3 IT slots per requirement, through the member with the best passage. Measured 2026-10-22: alerts 530 → 485 (the 42 duplicates against two annexes of one IT gone), but no accuracy gain on a hand-reviewed sample (the freed slots go to weaker ITs; the judge sees only one annex of the family), so it stays off | annexes with many generic rules (WI 3326-11 A1/A3/A6) filling all 3 slots |
| `kind` classification, only `supplier_requirement` kept | definitions / informative text becoming "requirements" |
| Number grounding (`_ground_numbers`): every number in a statement must be in the source passage, one repair call otherwise | mistranslated values ("4,8 horas" for "48 horas") |
| Near-duplicate removal (cosine ≥ 0.95 and same numbers) | the same obligation counted twice |
| IT profile (purpose / applies to / trigger / out of scope) shown to the judge | an IT judged against activities it was not written for |
| `same_subject` gate + reasoning-first JSON field order | verdicts given before the model has reasoned |
| Numeric cross-check over **every** IT sentence (excerpt + rules) with a number in the same unit (`_value_sentences` + narrow LLM question) | a different value for the same parameter called "partial"/"compliant" instead of "conflict" |
| Compliant check (`_verify_compliant`): the key element must be quoted from the IT, and the quote must exist in the IT text; generic wording does not count | missed gaps ("normas aplicáveis" accepted as "ISO-3834") |
| IT direction filter: each IT profile records whether it is directed at customers/production, at LEONI's own suppliers or at internal units; own-supplier/internal ITs are not compared with customer requirements unless these mention sub-suppliers (`SUBSUPPLIER_RE`) | requirements on parts returned *by the customer* judged against ITs on returns *to LEONI's suppliers* |
| Judge rules: an IT stricter than the requirement is compliant; a generic wording does not cover a specific value/standard/approver | false conflicts on stricter ITs, false "compliant" on vague ITs |
| Evidence check: a conflict must quote text that exists in the IT | made-up contradictions |
| **Verification pass** (`_verify`, qwen3 reasoning mode) on every conflict/partial: same activity? already covered in substance? contradicting rule? | false alarms (removed ~half of them on Cummins) |
| A numeric conflict confirmed by the number check can only be dismissed by the verifier as "different activity", never softened | the verifier talking itself out of a real value contradiction |

## Performance (RTX 4070 Ti 12 GB, qwen3:8b, 4 parallel)

| Step | Time |
|---|---|
| IT ingestion incl. profile + rules (7 ITs, ~375 rules) | ~2 min, once |
| Cummins Supplier Handbook, 44 pages → 277 requirements, extraction | ~6.5 min |
| IT comparison + verification of the same 277 requirements (7 real ITs) | ~14 min |
| same, demo database (82 ITs; more matches -> more verification calls) | ~43 min |
| Section-level IT mapping (24 sections, reasoning mode) | ~3 min |
| IT comparison only, per requirement (no verification) | ~3 s |

Whole customer documents (real database, 7 ITs; first run, single pass):

| Document | Pages | Requirements | Time |
|---|---|---|---|
| Caterpillar Supplier Quality Manual 2022 | 32 | 79 | 11 min |
| John Deere DLW 25046 | 18 | 82 | 15 min |
| John Deere JDS-G223X3 PPAP | 18 | 134 | 19 min |
| Cummins 18227 harness spec | 39 | 185 | 22 min |
| Cummins Supplier Handbook (PT) | 44 | 277 | ~26 min |
| Caterpillar 1E2358 | 51 | 307 | 35 min |
| John Deere JDS-G223 SQM | 57 | 362 | 50 min |

Rebuild with the new parser and the context lock (2026-10-19, `tools/rebuild_real_db.sh`, 2 h 14 min in total
incl. index and ITs):

| Document | Requirements (old parser → new) | Time |
|---|---|---|
| Cummins Supplier Handbook (PT) | 277 → 406 (tables read as rows, sections X/D/Z no longer lost) | 31 min |
| John Deere JDS-G223X3 PPAP | 134 → 164 | 11 min |
| John Deere DLW 25046 | 82 → 92 | 10 min |
| Caterpillar Supplier Quality Manual 2022 | 91 → 81 | 8 min |
| Cummins 18227 harness spec | 239 → 244 | 15 min |
| Caterpillar 1E2358 | 369 → 371 | 26 min |
| John Deere JDS-G223 SQM | 431 → 464 | 32 min |

Against LEONI's Cummins matrix the requirement-level IT recall went from 4/12 to 8/12 (section level unchanged,
4/12); 11 near-duplicate pairs among the 406 Cummins requirements (5 before among 277).

Second IT batch (2026-10-22, `tools/load_new_its.sh`): 27 IT documents ingested in ~4 min (12–26 s each, profile
+ rules), then one `reassess` per customer document against the 34 ITs, 2 h 11 min in total (incl. section
mapping and export):

| Document | Requirements | Reassess with 34 ITs (comparison with 7 ITs, 2026-10-19) |
|---|---|---|
| Cummins Supplier Handbook (PT) | 406 | 32 min (23–25 min) |
| John Deere JDS-G223X3 PPAP | 164 | 16 min (~8 min) |
| John Deere DLW 25046 | 92 | 9 min (~8 min) |
| Caterpillar Supplier Quality Manual 2022 | 81 | 8 min (~5 min) |
| Cummins 18227 harness spec | 244 | 13 min (~10 min) |
| Caterpillar 1E2358 | 371 | 23 min (~20 min) |
| John Deere JDS-G223 SQM | 464 | 29 min (~24 min) |

More ITs do not mean more judge calls (every requirement already saw ~3 ITs with 7 ITs); the extra time is the
verification of the extra "partial" / "compliant" verdicts.

Rule of thumb: **minutes ≈ requirements / 7**; requirements per page vary 2–7 (dense specs are highest), so
pages alone do not predict it. (These runs lost 14 dense passages to a too-small output limit, since fixed
and recovered with `retry-failed`: final counts 91 / 82 / 134 / 239 / 277 / 369 / 431.) A new version of a
document only re-assesses new and changed requirements; resubmitting the same file is skipped.

`python tests/bench.py --levels 1 2 4` measures throughput on the current machine.

## Mock data (LEONI's full IT base is private)

34 real IT documents are available (15 ITs with their annexes: the first 7 documents in `Leoni/Leoni/`, 27 more in
`Leoni/Leoni/RE__Pedido_de_Documentação_Exemplo/` since 2026-10-22). Two kinds of synthetic data stand in for the rest:

| What | Tool | Used for |
|---|---|---|
| **Mock ITs**: one generated IT per index entry without a PDF (title, process, ISO clause and department from the real index; LEONI IT structure; concrete values) | `tools/mock_its.py --top 80` / `--all` → `mock_data/its/*.json` (ParsedDocument + `"synthetic": true`) | the **demo database** `data/demo/` built by `tools/build_demo.py`: a full-looking IT base for demos and for testing the pipeline at realistic scale |
| **Labelled judge set**: real customer requirements + generated IT passages with a known relation (compliant / conflict / partial, plus an unrelated IT) | `tests/make_judge_set.py` → `tests/fixtures/judge_set.json` | `tests/eval_judge.py`: precision / recall of the judge without LEONI's labels |

Rules that keep this honest:
* Mock ITs are invented. **A conflict or gap against a mock IT is fictional.** They are flagged `synthetic`
  in the database; alerts say `[simulated IT]`, the Excel marks them with `*` and shows a red warning, and
  `docs` lists them as `[SIMULATED]`. They only go into `data/demo/`, never into the real database.
  `build_demo.py` skips a mock IT whose code exists as a real IT (9 of the 75 since the second batch), which
  would otherwise supersede the real one as a "newer version".
* No person names in mock ITs (the index's process owners are real employees); departments only.
* The judge set is generated by the same model family that judges it, so its scores are an optimistic
  upper bound; it is meant to compare pipeline versions, not to certify accuracy. Generated variants are
  filtered for label leaks ("viola", "não menciona", …) and for numbers that contradict their label.

```bash
python tools/mock_its.py --top 80
```
```bash
python tools/build_demo.py
```

## Testing and evaluation

| Script | Purpose |
|---|---|
| `tests/scenario.py` | known-answer test (separate DB in `data/test/`): real ITs + synthetic John Deere standard in two revisions with planted changes/conflicts vs WI 3600-11, then an IT update that must resolve them. **14/14** |
| `tests/test_units.py` | deterministic rule helpers (document codes, number grounding, unit matching, ISO clauses, direction filter, parser heading/TOC/table rules, reranker value masking and sentence split), no LLM, < 1 s |
| `tests/test_parser.py` | parser on the 14 real PDFs plus 3 ITs and 2 forms of the second IT batch: expected headings and levels (from each document's own TOC and LEONI's Cummins matrix), no TOC / header / footer leftovers, chunk sizes and pages, forms printed twice read once; no LLM, ~1 min |
| `tools/review_sheet.py` | workbook for a LEONI expert to judge a sample of the alerts (all conflicts + random gaps per document), in **LEONI's own form IT 3535-11 Anexo 4** "Requisitos clientes – análise da conformidade" (template `complyai/templates/IT-3535-11-A4_template.xlsx`, made from LEONI's filled form by `tools/make_a4_template.py`; layout only). COMPLY-AI fills in the form's own fields (comments = its analysis and the IT text, action plan, action status "to be determined", the IT that reflects the requirement, STATUS "Do not comply" / "Action required"), and the expert checks and corrects them as in any conformity analysis; grey columns keep the AI's original proposal, and two calculated columns plus a block on RESUMO turn the expert's final STATUS and IT into "alert confirmed" and "right IT" rates; no LLM |
| `tests/report_docs.py` | per-document summary of a database: requirements, IT coverage, alerts, changes, cross-document contradictions |
| `tests/test_resume.py` | recovery after an interrupted run (power cut): half-ingested document redone, interrupted comparison resumed, duplicates skipped |
| `tests/eval_cummins.py` | AI IT mapping vs LEONI's manual Cummins matrix (IT-3535-11-A5): section-level picks and requirement-level links, per section |
| `tests/eval_judge.py [--no-verify] [--model M] [--think-model M] [--judge-think] --tag T` | judge precision / recall / confusion matrix on the labelled synthetic set (items in parallel, ~4 min with qwen3:8b); results appended to `data/judge_eval/results.jsonl`. Model comparison: `docs/llm_options_evaluation.md` |
| `tests/audit_grounding.py <db> \| --judge-runs` | context lock: share of quotes, numbers and IT evidence written by the model that really are in the source text (no LLM) |
| `tests/eval_rerank.py [--db D] [--min X]` | reranker only (no chat LLM, ~1 min): judge-set ITs and the scenario's planted conflicts kept, and on the Cummins handbook which ITs reach the judge with the reranker off / on, scored on 253 hand labels (`tests/fixtures/rerank_labels_cummins.json`; 183 with the first 7 ITs, 70 with the 34 ITs) |
| `tests/verify_experiment.py` | re-runs only the verification step with another model and compares against hand labels |
| `tests/bench.py` | throughput at different concurrency levels |

`data/snapshots/` keeps the Cummins databases of earlier pipeline versions for before/after comparisons.

**Measured accuracy** (2026-10-11, qwen3:8b):

| Test | Result |
|---|---|
| Known-answer scenario | 14/14 |
| Labelled synthetic judge set (14 requirements × 4 ITs) | alert precision 100%, recall 93%, 0 false alarms on compliant/unrelated ITs, exact label 91% |
| Same set on 2026-10-19 (current pipeline incl. context lock; direction filter off for this set) | precision 100%, recall 86%, 0 false alarms, exact label 88%; with the reranker (version 2) 100% / 93% / 96%; model comparison in `docs/llm_options_evaluation.md` |
| Cummins handbook, real DB (7 ITs), 25 alerts reviewed by hand | ~16% of alerts correct |
| Cummins handbook, demo DB (82 ITs), 20 alerts reviewed against the IT text | ~40–45% of alerts correct; the IT direction filter then removed 14 more (all wrong) alerts, 99 -> 85 |
| Section-level IT mapping vs LEONI's Cummins matrix | 4/12 at ~3 ITs per section (6/12 incl. requirement-level ITs) |
| Real DB with 34 ITs (2026-10-22), all 7 documents re-assessed | alerts 248 → 530 (conflicts 18 → 24); requirements with a related IT 253 → 504; Cummins matrix: requirement level 8/12 (unchanged), section level 3/12 (was 4/12), central VA 3160 in section M found; grounding audit 100 / 100 / 100 / 96 % |
| Same, hand review of random alerts (my reading of the IT text) | right IT and a plausible real gap: 36 % of 45 alerts against the new ITs vs 20 % of 40 alerts before; unrelated IT: 29 % vs 30 % |
| "Magnet" filter applied (2026-10-25, `reassess --changed-only`, 1,379 requirements) | alerts 530 → 519, compliant links 77 → 88; of 20 alerts it removed 20 % had the right IT and a plausible gap and 45 % an unrelated IT, of 20 it added 35 % and 30 %; grounding 100 / 100 / 100 / 97 %; Cummins matrix section 4/12, requirement 8/12 |

The gap between the judge set and the real document is retrieval/coverage: with the right IT in front of
it the judge is accurate; most false alerts come from requirements compared with an IT that does not govern
them (wrong activity, or LEONI-as-customer ITs vs LEONI-as-supplier requirements).

**Known limits.** Only 15 of ~300 ITs are loaded (34 documents with annexes), so many customer requirements
have no IT with the right content and the model compares them with the closest wrong one — that is the main
source of false alerts. The second IT batch (2026-10-22) raised the share of correct alerts but doubled the
number of alerts. Each annex counts as its own IT when the 3 ITs per requirement are picked, so annexes with many
generic rules (WI 3326-11 A3 on PPAP, WI 3069-11 A2, which quotes customer traceability requirements, WI 3404-11
A5) take many of those slots; 210 of the 530 alerts are against the WI 3326-11 family. The biggest accuracy gains
still come from data: all IT and central PI/WSD PDFs, and the existing manual correspondence matrices for other
customers as labelled test data.
