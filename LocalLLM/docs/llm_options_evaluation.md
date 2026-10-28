# Evaluation: llama.cpp, vLLM, smaller models, reasoning models, one model per step

*Written 2026-10-19 for LEONI COMPLY-AI. Hardware: RTX 4070 Ti 12 GB, Windows 11. Benchmark of five setups at
the end (`tests/eval_judge.py`): the current setup, qwen3:8b with reasoning only where it is hard, stays.*

## Short answer

The suggestions split into two kinds:

* **Runtimes (llama.cpp, vLLM)** change speed, memory use and the features available. They do not change
  how *accurate* the answers are: the same model with the same weights gives the same answers in Ollama,
  llama.cpp or vLLM. Ollama already *is* llama.cpp underneath (our Ollama log shows `RUNNER llamacpp`,
  process `llama-server.exe`).
* **Models (smaller, reasoning, several per step)** change accuracy. Here the idea is good, but only in a
  specific form for this project. The useful form is a small *specialised* model for the step where we lose
  the most accuracy. A smaller general chat model is not that form.

Where accuracy is lost today, from our own measurements:

| Measurement | Result | What it means |
|---|---|---|
| Judge on the labelled set (right IT in front of it) | precision 100 %, recall 93 %, exact label 91 % | the 8B judge is good when it sees the right IT |
| Alerts on the real Cummins handbook, 7 real ITs | ~16 % correct | most requirements are compared with an IT that does not govern them |
| Same with 82 ITs (demo) | ~40–45 % correct | more coverage → much better |
| Section ITs vs LEONI's Cummins matrix | 6/12 found | retrieval / coverage |
| *Update 2026-10-22:* real DB with 34 real IT documents (15 ITs incl. annexes), 7 documents | right IT and plausible real gap in 36 % of 45 sampled new alerts (20 % before), alerts 248 → 530 | real IT text helps, but retrieval now picks generic annexes too often |

So the weak point is **finding the right IT** (retrieval) and **having the IT at all** (7 of ~300 IT PDFs on
2026-10-19; 15 ITs / 34 documents since 2026-10-22). Neither a new runtime nor a stronger judge fixes a missing IT.
The suggestions are judged below against that.

## 1. llama.cpp directly (instead of Ollama)

| Pros | Cons |
|---|---|
| Same engine, but every option is reachable: speculative decoding (a tiny "draft" model proposes tokens, the 8B confirms them, typically 1.5–2× faster generation), unified KV cache across parallel slots, grammars, per-slot prompt cache | We would manage binaries, CUDA builds, model files (GGUF) and the server process ourselves; Ollama does that for us |
| **Has a reranking endpoint** (`--reranking`, `/v1/rerank`) for cross-encoder models like bge-reranker-v2-m3. Ollama has no rerank endpoint (long-open GitHub request). This is the most useful feature for us (see section 5) | No accuracy gain by itself: same weights, same answers |
| Can run several models behind one server (router mode or llama-swap) | More configuration to document for the teammate who deploys the server |
| Our code only talks to the LLM in `llm.py`, and llama-server speaks the OpenAI-compatible API, so switching takes about a day | |

**Verdict:** worth it **only together with a reranker** or speculative decoding. On its own it is the
same thing as now with more maintenance.

## 2. vLLM

| Pros | Cons |
|---|---|
| Built for throughput: PagedAttention gives KV memory to requests as needed (Ollama/llama.cpp reserve a fixed `NUM_CTX` per slot), continuous batching, prefix caching. With many requests at once it is typically several times faster | **No official Windows support.** It needs WSL2 or Docker (Docker Model Runner added vLLM on Windows in Dec 2025, WSL2-based); native Windows builds are unofficial community builds |
| Production standard on Linux servers with datacenter GPUs; good choice for LEONI's server *if* it is Linux + a large GPU | On 12 GB an 8B model does not fit in full precision (16 GB). It needs 4-bit AWQ/GPTQ (~5.5 GB) or FP8 (~8.5 GB, little room left for KV), so the quality is about the same as our GGUF Q4 |
| Structured output (JSON schema) is supported | Our workload is a batch job of a few thousand calls per document, already 4 in parallel. It gains from vLLM, but the gain matters less than accuracy |
| | Loads one model per process, so several models means several processes or swapping |

**Verdict:** **not on this PC.** Reconsider when the system moves to LEONI's server: if that server is Linux
with a ≥ 24 GB GPU and many documents or users, vLLM is the right runtime there. The switch is again
limited to `llm.py`.

## 3. Smaller models ("more focused")

| Pros | Cons |
|---|---|
| Faster (a 4B model generates roughly 1.7–2× faster than 8B) and smaller, so more parallel slots and more context fit in 12 GB | A smaller *general* model is not more focused; it is the same kind of model with less knowledge and weaker reading. Our steps need nuanced reading of Portuguese/English/German legal-style text: modal verbs, who must do what, numbers with units. The 8B already needs deterministic safety nets for nuanced rules (direction filter, number checks) |
| Can be **fine-tuned** (LoRA on 12 GB is feasible for 4B). A fine-tuned small model *can* beat a general 8B on one narrow task | Fine-tuning needs labelled examples. LEONI will not provide labelled matrices; synthetic labels made by the same model family would teach the model its own mistakes |
| Good fit for **simple steps**: reading code/version/client from the first pages, translating headings, "is this a requirement or a definition?" | Multilingual quality drops fastest at small sizes (PT/DE documents) |

**Verdict:** use a small model **only for simple steps, and only after measuring** that it is as good there.
Do not use it for the judge or the verification. Benchmark: `qwen3.5:4b` for every step doubled the false
alarms on compliant ITs (2 → 4) against `qwen3:8b`.

## 4. Reasoning models (thinking mode)

| Pros | Cons |
|---|---|
| Better on multi-step judgments. We already measured it: the reasoning-mode verification pass removed about half of the false alarms on Cummins | 3–10× more output tokens per call (a verification call may use up to 2,400 tokens), so much slower if used everywhere |
| qwen3 is a *hybrid* model: one model, thinking switched on per call, so no second model in VRAM | Thinking tokens need context. Prompt + thinking can pass our 4,096-token window, and a bigger window means fewer parallel slots on 12 GB |
| | It can "talk itself out" of a correct answer. We saw this and added a rule: a confirmed numeric conflict can only be dismissed as "different activity", never softened |

**Verdict:** the project **already uses this the right way.** Reasoning is on for the hard, low-volume steps
(verification, section-level IT mapping) and off for the high-volume ones (extraction, first judgment).
Benchmark: reasoning also for the first judgment gave no gain (recall 89 → 82 %, +30 % time). A dedicated
reasoning model as verifier can be tried with the same switch (`COMPLYAI_THINK_MODEL`).

## 5. Several models, one per step

| Pros | Cons |
|---|---|
| Each step gets the right size: small for simple steps, larger or reasoning for hard ones | **VRAM:** 12 GB holds one 8B model + KV + the embedding model. A second large model means swapping (seconds per load), and our pipeline interleaves judge → verify per requirement, so it would need to be reorganised to run step by step |
| A model from a **different family** as verifier gives an independent second opinion: errors of two different models are less correlated (relevant because our judge test set was written by qwen too) | More models means more evaluations to keep up to date and more for the teammate deploying the server |
| **Specialised non-chat models** are much better at their one job than a chat LLM: a cross-encoder **reranker** (bge-reranker-v2-m3, ~0.6B, multilingual) reads requirement + IT passage *together* and scores relevance. Our bi-encoder (bge-m3) embeds them separately, and that is exactly the retrieval step where we lose accuracy | Voting ensembles (2–3 models on every judgment) multiply the run time |

**Verdict:** the most promising idea of the list, **in this order:**

1. **Add a reranker** between retrieval and the judge. It re-scores the closest IT passages per requirement
   and passes only those that really match. This targets the main error source, needs ~1.1 GB of VRAM, and
   scores ~30 pairs per second. **Implemented as a small PyTorch model in two versions and measured: it stays
   off.** Version 1 hid contradicting IT passages. Version 2 (best sentence, numbers masked) no longer does, but
   on real LEONI ITs it neither saves work nor removes wrong alerts (see "Reranker" below).
2. **Small model for simple steps** (metadata, heading translation, requirement/definition filter) only if a
   test shows no loss; for the judge it doubled the false alarms (benchmark).
3. **Different-family verifier** once a second model fits (on LEONI's server, not on 12 GB next to the 8B).

## Context lock: the model may only use the information it is given

Requirement: the LLM must answer only from the project documents it is shown (customer document, LEONI ITs,
IT index) and not from its general knowledge or anything else, to prevent hallucination.

**Can a model be "locked"?** Not by a switch: no model, small or large, can have its general knowledge
turned off. That knowledge is in its weights. The lock has to come from how the system calls the model and
from what the code accepts back. All of the following is independent of the model, so it works the same
for every model in the benchmark:

| Layer | How | Status |
|---|---|---|
| No other sources | The model runs offline in Ollama with no tools and no web access. Each call is stateless and contains only the passage / IT excerpts for that one question: no memory between calls, no other customers' documents (except the same customer's other documents in the contradiction check, on purpose) | in place |
| Closed choices | IT codes can only be picked from the list given in the prompt (JSON schema enum); verdicts are a fixed set incl. "not related" / empty answers | in place |
| Instruction | Every system prompt says: use only the text in this message, nothing from general knowledge; if it is not stated, leave it empty | added 2026-10-19 |
| Verbatim quotes, checked in code | Each requirement must quote the customer text. A quote not found word for word is replaced by the passage sentence that supports the requirement (marked); a requirement nothing in the passage supports is dropped. Numbers in statements must exist in the source (one repair call, then marked) | numbers: in place; quote check: added |
| IT rules checked | Rules the model extracts from ITs must not contain numbers absent from the IT passage | added |
| Evidence checked and shown as real IT text | A conflict / compliant claim must be backed by IT text found in the IT; evidence the model paraphrased or translated is replaced by the IT's own sentence it refers to (multilingual embedding match), so the matrix always shows verifiable text | conflict/compliant check: in place; snapping to the real sentence: added |
| Measured | `tests/audit_grounding.py` counts how much of what the model wrote is really in the source text, per database or per benchmark setup | added |

Measured on the real database before the additions (old parser): quotes 100 % found, statement numbers 99 %,
IT-rule numbers 99 % (the misses were real errors, e.g. "código 1238" for 128), **IT evidence 85 %**. The other
15 % were translations or paraphrases of the IT sentence, sometimes with a comment of the model added; that is
what the evidence snapping fixes.

Effect on the labelled judge set (qwen3:8b, same test as the benchmark):

| | Precision | Recall | False alarms | Exact label | IT evidence verbatim |
|---|---|---|---|---|---|
| before the context lock | 93 % | 89 % | 2 | 84 % | 72 % |
| with the context lock | **100 %** | 86 % | **0** | **88 %** | **100 %** |

The known-answer scenario stays at 14/14. One lesson from building it: a hard "drop the requirement if its
quote is not found" rule once removed three real requirements (the model returned an unusable quote for a
passage that does contain them). The check now first looks for the passage sentence that supports the
requirement and only drops it when none does (threshold calibrated on 150 real requirements: 98 % of real
ones kept, 91 % of unsupported ones dropped).

**Per model:** all tested models work with the lock, because it lives in the pipeline, not in the model.
They differ in how disciplined they are before the checks: qwen3.5:4b and 9b quoted IT evidence word for word
98–100 % of the time, qwen3:8b 72 % (now corrected by the snapping).

## Reranker (implemented in two versions and measured: stays off)

`complyai/rerank.py` + `COMPLYAI_RERANK=1`: bge-reranker-v2-m3 (PyTorch on the GPU, ~1.1 GB, ~30 pairs/s)
re-scores up to 12 IT passages and 12 IT rules per requirement; only those with relevance ≥ `RERANK_MIN` (0.1)
can reach the judge, ranked by the reranker instead of the embedding similarity.

### Version 1: whole passages

| Check | Result |
|---|---|
| Judge set, reranker on | precision 100 %, recall 93 %, exact 89 % (without: 100 / 86 / 88 %): no harm |
| Real Cummins requirements vs the 7 real ITs (720 candidate pairs, all passing today's similarity threshold) | the reranker keeps 21 % at 0.1. The pairs it cuts that I read were all clearly unrelated (e.g. a Safety Data Sheet requirement vs a passage on change documentation) |
| Weak spot | short fragments containing the customer's name get top scores (e.g. a revision-history line "Atualizar etiqueta Cummins no A5" vs an ISO 9001 requirement). The new parser removes revision histories, which takes away part of this |
| Real alerts (Cummins handbook after the rebuild, 406 requirements, comparison re-run twice on copies) | off: 61 alerts, 1,200 IT judgments, 25 min · on: 55 alerts, **902 judgments (−25 %)**, 22.6 min. The rebuild's own run without it gave 69, so ±8 alerts is run-to-run variation. LEONI-matrix recall unchanged (8/12) |
| Which alerts change (hand review of a sample, my reading, no LEONI labels) | of 12 alerts it removed (IT no longer shown to the judge) ~10 were wrong or weak, incl. a false conflict ("long-term actions within 30 days" vs "actions still in place after 6 weeks"); of 11 it added ~7 compare failure-analysis / root-cause requirements with the right IT (the 8D procedure), ~4 are weak (one short-fragment mismatch) |
| Known-answer scenario, reranker on | **13/14**: the planted numeric conflict (customer "fill rate ≥ 98 %" vs IT "95 %–100 %") is missed because the reranker keeps WI 3600-11 away from the judge. Probe: the judge finds it 3/3 times when it sees the IT (with or without the context-lock instruction) |
| Why | (1) rerankers are trained to score "does this passage *answer* the query", so a passage that *contradicts* the requirement scores low, and contradictions are what we look for; (2) whole passages / rules dilute the one relevant sentence: the IT sentence "Deve ser alcançada uma taxa de preenchimento da manga de 95%- 100%" alone scores 0.79 (0.95 with numbers masked), inside its rule or window 0.01–0.04 |
| Verdict | **stays off.** As a hard filter it hides conflicts. It did improve which IT the judge sees in the sample and saves a quarter of the judge work, so it is worth a second version: score sentence by sentence (max over the sentences of a passage) with numbers masked on both sides (topic relevance, not agreement), then re-run this table and the scenario |

### Version 2: best sentence, values masked (current code)

What changed in `rerank.scores`: each candidate IT window or rule is split into sentences (sentence ends and
table cells; fragments under 40 characters are joined to the next one), values are masked on both sides ("98 %",
"10 mm", "24 h" → "N"; identifiers such as ISO 9001, WI 3600, 8D, D3 keep their digits), and the passage gets the
score of its **best sentence**. The IT title is no longer put in front (tested: "title: sentence" scored the
fill-rate rule 0.80 instead of 0.99). `RERANK_MIN` stays 0.1 (calibration below).

| Check | Version 1 (whole passage) | Version 2 (best sentence, values masked) |
|---|---|---|
| Scenario's planted conflict: reranker score of the WI 3600-11 window / rule | 0.00 / 0.04 | **0.98 / 0.99** |
| Known-answer scenario, reranker on | 13/14 | **14/14, run twice** |
| Judge set (`eval_judge --rerank`): precision / recall / exact label, conflicts found as conflict | 100 / 93 / 89 %, 10/14 | **100 / 93 / 96 %, 13/14**. Without the reranker (`base_grounded`): 100 / 86 / 88 %, 10/14. The one partial it misses was shown to the judge, which called it unrelated (same miss as without the reranker) |
| Judge set, reranker scores only (14 requirements × 56 IT texts): own ITs kept / conflict variants kept / other items' ITs passed, at 0.1 | 100 % / 100 % / 62 % | 100 % / 100 % / 71 % |
| Cummins: IT judgments at 0.1 (reranker off: 1,200) | 900 (−25 %) | 1,150 (−4 %) |
| Cummins, 80 IT links labelled by hand (the 69 alerts + 11 "compliant" of the reranker-off run; 59 with an IT about the same activity, 21 with an unrelated IT): relevant kept / unrelated removed | 44/59 / 8/21 | 44/59 / 7/21 |
| Cummins, random 25 of the IT links version 2 adds and 25 it removes vs reranker off: IT about the same activity | – | added 4/25, removed 2/25 |
| Reranking time, Cummins (9,744 candidates) | 23 s | 52 s (23,632 sentences) |
| Cummins real alerts (`reassess 8` on a copy of the real DB). Reranker off, two runs: 69 and 61 alerts (1 conflict each), 1,200 judgments, 25 min; 20 and 15 of their alerts compare with an unrelated IT | 55 alerts (2 conflicts), 902 judgments, 22.5 min. Of the 47 alerts both off runs share, it removed 27 (19 with a relevant IT, 8 with an unrelated one) | 57 alerts (**6 conflicts**), 1,154 judgments, 24.9 min. Of the 47 shared alerts it removed 28 (20 relevant-IT, 8 unrelated-IT); 14 of its 57 alerts compare with an unrelated IT (25 %; off: 29 % and 25 %). The 5 extra conflicts are all false alarms by my reading (e.g. "SCAR responses analysed by Cummins SQE" vs "5D report released by Quality Management"). LEONI-matrix requirement-level recall unchanged (8/12) |
| All of the above on one command (reranker only, ~1 min): `tests/eval_rerank.py` with the hand labels (183 on 2026-10-19, 253 since 2026-10-23) in `tests/fixtures/rerank_labels_cummins.json` | – | judge sees relevant 79/102 (off 86), unrelated 49/81 (off 56) |

**`RERANK_MIN` calibration.** The judge set keeps 100 % of its relevant and contradicting ITs at any threshold
≤ 0.1 (98 % at 0.2–0.5). On the hand-labelled Cummins links the threshold hardly matters (0.05: 45/59 kept,
0.1: 44/59, 0.5: 38/59): the losses come from the re-ranking, where inflated scores push relevant ITs out of the
top 3 shown to the judge. So 0.1 stays; no threshold turns it into a good filter.

**Why version 2 barely filters.** The cross-encoder gives short sentences without content near-top scores for
almost any requirement: "Ver detalhes no Anexo 8 desta instrução." ("see annex 8") scores 0.97–1.00 against SCAR,
calibration and audit requirements, "The supplier's description must be provided." 0.89 against "provide quality
data within one business day". With the best sentence counting, almost every passage has one. Tried with the same
reranker-only probe and rejected: sentences of ≥ 80 characters or windows of 2–3 sentences (the dilution comes
back: the planted conflict drops to 0.22–0.37), a bge-m3 similarity floor per sentence (0.4–0.5: 1–9 % fewer
judgments, no better separation on the labels), the IT title as context (worse).

**Version 1 re-checked with the same yardstick.** The two reranker-off runs share only 47 of their alerts (69 and
61; 36 differ: run-to-run variation). Of these 47 stable alerts (34 with an IT about the same activity, 13 with an
unrelated IT), version 1 removed 27: 19 relevant-IT and 8 unrelated-IT alerts, the same rate (56 % vs 62 %). The
earlier "most removed alerts were wrong" is true but only because most real alerts are wrong (~16 % correct); it
did not pick out the wrong ones.

**Verdict: stays off** (`COMPLYAI_RERANK` default 0). Version 2 does what it was built for: contradicting IT
text now reaches the judge (scenario 14/14 twice, judge set 13/14 conflicts found, no recall loss). It fails the
third condition, fewer wrong alerts on a real document. On the Cummins handbook it cuts only 4 % of the judge work.
It reshuffles which ITs and passages the judge sees: two thirds of the alerts change, twice the run-to-run
variation. The share of alerts that compare with an unrelated IT stays the same, and it adds false
high-severity conflicts (6 instead of 1), probably because the passage it picks for the judge is the one with
the best sentence, often a terse form fragment. Both versions also fetch model metadata from huggingface.co when
the model loads (relevant if it is ever deployed on a server without internet: set `HF_HUB_OFFLINE=1`).

Worth another try only when (1) many more IT PDFs are in the database: with 7 of ~300 ITs most requirements
have no IT that governs them, so any filter only chooses between wrong ITs; and (2) a version is found that
content-free sentences cannot fool, for example by counting a sentence only if it scores clearly higher for this
requirement than for a few unrelated ones. Check it first with `tests/eval_rerank.py` (reranker only, ~1 min),
then the scenario, `eval_judge --rerank` and the Cummins on/off comparison.

*2026-10-22:* condition (1) is now partly met (34 real IT documents). Most wrong alerts with them come from
generic annexes taking the 3 IT slots (each annex counts as an IT). A per-family selection (base IT + annexes = one
slot, `COMPLYAI_IT_PER_FAMILY=1`) was tried the same day: 42 duplicate alerts gone, but no accuracy gain on a
hand-reviewed sample, so it is off (README, "Accuracy safeguards"). The first 183 hand labels of `eval_rerank.py` cover only the first 7 ITs, so new labels for
the new ITs are needed before the reranker can be judged on this database. Run on the 34-IT database anyway: of
the 102 labelled relevant pairs the judge sees 27 with the reranker off (86 with 7 ITs: the new ITs took the
slots) and 23 with it on; of the 81 unrelated pairs 9 and 12. No reason to switch it on.

*2026-10-23, fair re-test with the 34 ITs:* 70 more hand labels, sampled from the pairs the reranker drops (25),
adds (25) and keeps (20) on the Cummins handbook; relevant among them 0, 2 and 5. The reranker changes about half
the IT slots (592 pairs dropped, 596 added) but not how many relevant ones the judge sees: all 253 labels, relevant
30 vs 32 of 109 without it, unrelated 50 vs 49 of 144. **Still off; the Cummins GPU run was not made.**
The re-test showed where the slots go instead: short, content-free IT rules. The requirements are all written
"The supplier shall/must …", and rules extracted from forms and templates with the same phrasing are close to all
of them in bge-m3: "The supplier's description must be provided." (WI 3404-11 A5) alone wins 17 % of the 5,435
IT slots of the 7 documents, rules of 8 words or fewer 26 %. A cross-encoder does not fix this either (it scores
such sentences high too, see "Why version 2 barely filters"); a filter on those rules is the next thing to test.

## Hardware and deployment notes

* Only models that fit **entirely** in the GPU are usable here (a partly offloaded qwen3:14b crashed this
  PC once). Candidates that fit: qwen3.5:4b (~3.4 GB), qwen3:8b (current, 6.4 GB loaded),
  qwen3.5:9b (~6.6 GB, the newer generation of the current model).
* The GPU is shared with other applications. Measured today: with a game running, generation dropped from
  ~60 to 0.6 tokens/s. Benchmarks and long runs need the GPU to themselves.
* The production server is unknown. Everything above is contained in `llm.py` (the only LLM client), so the
  runtime choice can be made when the server is known.

## Benchmark (labelled judge set, `tests/eval_judge.py`)

14 customer requirements × 4 ITs each (compliant / conflict / partial / unrelated), full pipeline: IT
profile + rules, retrieval, judge, numeric check, verification. Same test as the "precision 100 % /
recall 93 %" line above. It is optimistic (the set was generated by the qwen family), so read it as a
**comparison between setups**, not as real-world accuracy.

Run on 2026-10-19 (each setup builds its own IT knowledge with its model; 56 judgments; the IT direction filter
is off for this set because its synthetic ITs were generated before that rule). "Evidence verbatim" =
share of quoted IT evidence found word for word in the IT (`tests/audit_grounding.py --judge-runs`).

| Setup | Command | Precision | Recall | Conflicts as conflict | False alarms | Exact label | Time | Evidence verbatim |
|---|---|---|---|---|---|---|---|---|
| **qwen3:8b, reasoning for verification only (current)** | `--tag base` | 93 % | **89 %** | 9/14 | 2 | **84 %** | **4 min** | 72 % |
| qwen3:8b, reasoning also for the judge | `--judge-think --tag judge_think` | 92 % | 82 % | 10/14 | 2 | 84 % | 5.5 min | 72 % |
| qwen3.5:4b for every step (small model) | `--model qwen3.5:4b --tag small` | 85 % | 82 % | 12/14 | 4 | 82 % | 19 min | 100 % |
| qwen3.5:4b + qwen3:8b reasoning verifier (one model per step) | `--model qwen3.5:4b --think-model qwen3:8b --tag cascade` | 91 % | 75 % | 9/14 | 2 | 79 % | 9 min | 80 % |
| qwen3.5:9b for every step (newer same-size model) | `--model qwen3.5:9b --tag q35_9b` | **96 %** | 75 % | 10/14 | **1** | 82 % | 30 min | **98 %** |

What it shows (56 judgments: one judgment ≈ 2 points, so only large gaps count):

* **No setup clearly beats the current one: qwen3:8b stays.** It has the best recall and exact accuracy and
  is by far the fastest.
* **Reasoning for the first judgment does not help** (recall 89 → 82 %, same precision, +30 % time). Keeping
  reasoning only for verification and section mapping is confirmed.
* **The small model raises false alarms** (2 → 4 on compliant ITs) and is not faster here (see the next point).
* **The two-model cascade is worse on recall** (75 %) and twice as slow: on 12 GB the two chat models cannot
  stay loaded together with the embedding model, so Ollama keeps swapping them.
* **qwen3.5:9b is the most precise and the most disciplined quoter** (1 false alarm; quotes the IT word for
  word 98 % of the time against 72 % for qwen3:8b), but finds fewer gaps (recall 75 %).
* **Runtime finding:** Ollama runs both qwen3.5 models (a partly recurrent architecture) with **1 parallel slot
  instead of 4** (seen in the Ollama log), hence 19–30 min instead of 4. Their speed is a runtime limitation,
  not a property of the models. qwen3.5:9b is worth re-testing if the runtime moves to one that batches it
  (check llama.cpp / vLLM support for this architecture first), or on LEONI's server.
* The first run, with the direction filter on, gave 90 % / 64 %: the filter removed most test ITs before the
  judge. On real documents it was checked by hand (it removed 14 wrong alerts), so it stays on in production.

## Sources

* vLLM on Windows: [state of support 2026](https://fazm.ai/t/vllm-windows-support-2026),
  [Docker Model Runner adds vLLM on Windows](https://www.docker.com/blog/docker-model-runner-vllm-windows),
  [community native build](https://dev.to/aivrar/running-vllm-natively-on-windows-4ahm)
* Reranking: [Ollama rerank request #4510](https://github.com/ollama/ollama/issues/4510),
  [llama.cpp rerank API](https://www.simplified.guide/llama-cpp/server-call-rerank-api),
  [bge-reranker-v2-m3 GGUF](https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF)
* Models: [Ollama qwen3.5](https://ollama.com/library/qwen3.5), [Ollama gemma4](https://ollama.com/library/gemma4),
  [small local LLMs 2026](https://localaimaster.com/blog/small-language-models-guide-2026)
