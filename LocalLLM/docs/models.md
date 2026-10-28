# Models in LEONI COMPLY-AI: which ones, and where

*State 2026-10-22. Why these models and not others: `docs/llm_options_evaluation.md`.*

COMPLY-AI uses **two models**, both running locally on the PC's GPU through Ollama, offline (no internet, no
tools, no memory between calls):

| Model | Kind | Size in GPU memory | What it does |
|---|---|---|---|
| **qwen3:8b** | chat model (LLM) | 6.4 GB | reads text and answers questions about it: extracts requirements, compares them with ITs, checks its own alerts |
| **bge-m3** | embedding model | 0.7 GB | turns a text into a vector, so similar texts (also across Portuguese / English / German) can be found quickly |

A third model, the reranker **bge-reranker-v2-m3**, is built in but switched **off** (see the end).

qwen3:8b works in two modes: **normal** (fast, for the high-volume steps) and **thinking** (it reasons step by step
before answering: 3–10× more output, used only for the few hard checks). It is the same model, switched per call.

The PDF parser uses **no AI model**: it reads the PDFs' text layer with fixed rules (PyMuPDF).

## Where each model is used

```
 PDF ──► parser (rules, no AI) ──► passages
                                      │
 LEONI IT ─────────────────────────── ├─► IT knowledge ........... qwen3:8b: profile + rules     bge-m3: index
 customer document ─────────────────── ├─► requirements ........... qwen3:8b: extraction          bge-m3: index
                                      ├─► changes vs old version . bge-m3: find candidates  ►  qwen3:8b: same / changed?
                                      ├─► IT comparison .......... bge-m3: find the 3 closest ITs  ►  qwen3:8b: judge
                                      │                             ►  qwen3:8b THINKING: verify every alert
                                      └─► Excel matrix ........... qwen3:8b THINKING: ITs per section
```

| Step (code in `complyai/engine.py`) | Model | Mode | Runs |
|---|---|---|---|
| Code / version / customer / title of a document from its first pages (`extract_metadata`) | qwen3:8b | normal | once per customer document; for an IT only if the file name and the IT index do not give them |
| IT profile: what the IT governs, for whom, when (`_build_it_knowledge`) | qwen3:8b | normal | once per IT version |
| IT rules: the concrete rules of each IT passage (same function) | qwen3:8b | normal | once per IT version, one call per passage |
| Indexing IT passages, IT rules, requirements, IT index titles and section headings (`_store_chunks`, `catalog.load_index`, …) | bge-m3 | – | when each is stored |
| Requirement extraction from each customer passage (`_extract_requirements`) | qwen3:8b | normal | once per document, one call per passage with obligation words |
| Number repair: a requirement whose numbers are not in the source is rewritten once (`_ground_numbers`) | qwen3:8b | normal | only for those requirements |
| Quote check: does the passage really support the requirement? (`_ground_quotes`) | bge-m3 | – | every requirement |
| Duplicate removal (`_dedupe`) | bge-m3 | – | every requirement |
| Changes vs the previous version of the document (`detect_changes`): bge-m3 finds the old requirement it may correspond to, qwen3:8b says same / modified | bge-m3 + qwen3:8b | normal | only when an older version exists |
| Contradictions with the same customer's other documents (`cross_document_check`) | bge-m3 + qwen3:8b | normal | every new document |
| **Finding the ITs to compare with** (`_candidates`, `_pick_its`): closest IT passages and rules, at most 3 ITs per requirement; texts close to *every* requirement (e.g. "The supplier's description must be provided.") are ranked down and very short generic rules left out | bge-m3 | – | every requirement |
| **Judge**: compliant / partial / conflict / not related, per IT shown (`assess_requirements`) | qwen3:8b | normal | one call per requirement |
| Number check: same parameter, different value? (narrow yes/no question) | qwen3:8b | normal | when an IT sentence has a number in the same unit |
| **Verification** of every conflict and gap (`_verify`) and of every "compliant" (`_verify_compliant`) | qwen3:8b | **thinking** | per flagged or compliant verdict |
| IT evidence shown as the IT's own sentence (`_source_sentence`) | bge-m3 | – | every verdict with evidence |
| **Section mapping** for the Excel matrix: which ITs govern each section (`map_sections`) | qwen3:8b | **thinking** | one call per top-level section |
| Section headings translated to English for the matrix (`section_labels`), `translate` command | qwen3:8b | normal | once per document (cached) |

Every chat call goes through `complyai/llm.py`, which adds the **context lock** to every prompt (use only the given
text) and returns structured JSON. The code then checks the answer (quotes, numbers, evidence) before storing it.

## How it runs

* **Ollama** serves both models on the local GPU (RTX 4070 Ti, 12 GB): 4 requests in parallel, 4,096 tokens of
  context per request. Both models fit in the GPU together; nothing runs on the CPU.
* Speed: about 3–5 seconds per customer requirement for the whole comparison; a 400-requirement document takes
  25–35 minutes.
* The models are set in `complyai/config.py` and can be changed without touching the code:
  `COMPLYAI_CHAT_MODEL` (default qwen3:8b), `COMPLYAI_THINK_MODEL` (thinking calls; default = the chat model),
  `COMPLYAI_EMBED_MODEL` (default bge-m3), `COMPLYAI_RERANK=1` (reranker on).
* On LEONI's server another runtime (for example vLLM on Linux) can replace Ollama; only `llm.py` would change.

## Not in use

| Model | Why not |
|---|---|
| bge-reranker-v2-m3 (reranker, built in, off) | re-scores which IT passages reach the judge. Measured in two versions: the first hid ITs that contradict a requirement; the second does not, but on real documents it did not reduce wrong alerts. Re-tested with the 34 ITs and new hand labels (2026-10-23): it changes half the IT choices but the judge sees as many relevant ITs as without it |
| qwen3:8b thinking for the judge too | no gain (recall 89 → 82 %), 30 % slower |
| qwen3:14b | does not fit in 12 GB; partly on the CPU it was slower, less accurate, and crashed the PC once |
| qwen3.5:4b | twice the false alarms on compliant ITs |
| qwen3.5:4b + qwen3:8b verifier | lower recall; the two models keep swapping in 12 GB |
| qwen3.5:9b | most precise and best at quoting, but finds fewer gaps and runs 7× slower in Ollama (one request at a time); worth a re-test on another runtime or on LEONI's server |
| pymupdf4llm layout model (PDF parsing) | kept navigation bars and noise headings, ~10× slower than the rule-based parser |
