# File structure

What each file and folder of the COMPLY-AI engine is for. Setup, commands and details are in
[README.md](../README.md).

A document goes **PDF → parser → engine (asks the local LLM, stores the results) → Excel export**, all run from the
command line: `python -m complyai <command>`.

## Top level

| Path | Purpose |
|---|---|
| [README.md](../README.md) | Full technical reference: setup, commands, parser output format, how the brief is covered, accuracy safeguards, timings, mock data, tests |
| [requirements.txt](../requirements.txt) | Python packages: `httpx` (Ollama client), `numpy` (vector search), `openpyxl` (Excel), `PyMuPDF` (PDF reading); the reranker's optional packages are noted there |
| [.gitignore](../.gitignore) | Keeps the database, LEONI's and customers' documents and local notes out of git |

## `complyai/`: the engine

| File | Purpose |
|---|---|
| [`__main__.py`](../complyai/__main__.py) | Command line (`ingest-it`, `ingest-csr`, `reassess`, `export`, `parse`, …); does what LEONI's server will trigger |
| [`parser.py`](../complyai/parser.py) | PDF → clean text sections: removes headers, footers and tables of contents, finds headings, splits the text into passages |
| [`engine.py`](../complyai/engine.py) | Main logic: extracts requirements from customer documents, detects changes between versions, picks the ITs to compare each requirement with, asks the LLM whether the IT complies, double-checks the answer |
| [`prompts.py`](../complyai/prompts.py) | Every instruction and answer format sent to the LLM; output language (English) and the "use only the given text" rule |
| [`llm.py`](../complyai/llm.py) | The only file that talks to the model server (chat answers and embeddings): Ollama's API or any OpenAI-compatible server (vLLM, llama.cpp, ...), chosen by a setting |
| [`store.py`](../complyai/store.py) | SQLite database: tables and updates of older databases; moving to PostgreSQL only touches this file |
| [`customers.py`](../complyai/customers.py) | Which customers a text names (JOHN DEERE, CAT -PERKINS, ...), so IT text written for another customer is never used as evidence |
| [`catalog.py`](../complyai/catalog.py) | Loads LEONI's IT index spreadsheets (~300 ITs), so a requirement can point to an IT whose PDF is not loaded |
| [`export.py`](../complyai/export.py) | Excel matrix in LEONI's form IT 3535-11 Anexo 5, plus detail sheets |
| [`config.py`](../complyai/config.py) | All settings (models, limits, thresholds); each one can be changed with an environment variable |
| [`rerank.py`](../complyai/rerank.py) | Optional reranker; off, because it was measured and did not help |
| [`templates/`](../complyai/templates) | Empty copies of LEONI's forms: **A5** (correspondence matrix) and **A4** (conformity analysis, used for the review workbook) |

## `docs/`

| File | Purpose |
|---|---|
| [llm_options_evaluation.md](llm_options_evaluation.md) | Comparison of llama.cpp, vLLM, smaller and reasoning models, with benchmarks; why qwen3:8b stays; which models fit a server GPU of 8-80 GB and the benchmark to run there |
| [models.md](models.md) | Which model does which step, how they run, and why other models are not used |
| [file_structure.md](file_structure.md) | This file |

## `mock_data/its/`

75 synthetic ITs (`*_SIMULADA.json`), written by the LLM for index entries whose PDFs are private. They are for the
**demo** database only, never the real one; everything derived from them is marked `[simulated IT]`.

## `tests/`

| Kind | Files |
|---|---|
| Fast, no LLM | [`test_units.py`](../tests/test_units.py) (rule-based helpers, < 1 s), [`test_parser.py`](../tests/test_parser.py) (parser on the real PDFs, ~1 min), [`audit_grounding.py`](../tests/audit_grounding.py) (are the AI's quotes and numbers really in the source text?) |
| Needs Ollama | [`scenario.py`](../tests/scenario.py) (end-to-end test with known answers, ~10 min), [`test_resume.py`](../tests/test_resume.py) (recovery after an interrupted run) |
| Accuracy | [`eval_judge.py`](../tests/eval_judge.py) + [`make_judge_set.py`](../tests/make_judge_set.py) (labelled test set for the compliance judge), [`eval_cummins.py`](../tests/eval_cummins.py) (comparison with LEONI's Cummins matrix), [`eval_rerank.py`](../tests/eval_rerank.py) (reranker only), [`review_regression.py`](../tests/review_regression.py) (the alerts of the first expert review, re-checked on a copy of the database) |
| One-off / reports | [`bench.py`](../tests/bench.py) (speed at different parallel settings), [`report_docs.py`](../tests/report_docs.py) (summary per document), [`verify_experiment.py`](../tests/verify_experiment.py) (another model for the verification step) |
| [`fixtures/`](../tests/fixtures) | Test inputs: two revisions of a synthetic John Deere standard, a changed WI 3600-11, the judge test set, hand labels for the reranker, the expected results of the reviewed alerts |

## `tools/`

| File | Purpose |
|---|---|
| [`rebuild_real_db.sh`](../tools/rebuild_real_db.sh) | Rebuilds the real database from the PDFs (several hours); safe to rerun after an interruption |
| [`load_new_its.sh`](../tools/load_new_its.sh) | Adds a batch of new ITs, then re-checks each customer document once |
| [`review_sheet.py`](../tools/review_sheet.py) | Alert review workbook for a LEONI expert, in form A4 |
| [`make_a4_template.py`](../tools/make_a4_template.py) | Builds the empty A4 template from LEONI's filled form |
| [`mock_its.py`](../tools/mock_its.py), [`build_demo.py`](../tools/build_demo.py) | Create the synthetic ITs and the demo database |

## Not in the repository

- `data/`: database, exports, logs, snapshots (created by the engine).
- `Leoni/`, `Cliente/`: the ITs, index spreadsheets and customer standards provided by LEONI.
- LEONI's filled forms and the project brief.

A fresh clone needs those documents and a database build first; see README, "Files not in the repository".
