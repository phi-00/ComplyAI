"""Central configuration. Every value can be overridden with an environment variable
so the same code runs locally and on Leoni's server without edits."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("COMPLYAI_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "complyai.db"
NOTIFICATIONS_PATH = DATA_DIR / "notifications.jsonl"
EXPORT_DIR = DATA_DIR / "exports"

# Local LLM server. LLM_API "ollama" (default: Ollama's own API) or "openai" (any OpenAI-compatible server: vLLM,
# llama.cpp llama-server, LM Studio, TGI, or Ollama's /v1 endpoint; docs/llm_options_evaluation.md, "Server").
LLM_API = os.getenv("COMPLYAI_LLM_API", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_URL = os.getenv("COMPLYAI_LLM_URL", OLLAMA_URL)
EMBED_URL = os.getenv("COMPLYAI_EMBED_URL", LLM_URL)   # vLLM serves the embedding model from its own process / port
LLM_API_KEY = os.getenv("COMPLYAI_LLM_API_KEY", "")
# How an OpenAI-compatible server is told to think or not (qwen3 thinks by default): "template" =
# chat_template_kwargs.enable_thinking (vLLM, llama-server, SGLang); "effort" = reasoning_effort "none" / "medium"
# (Ollama's /v1 ignores the template switch and thinks in every call, 2026-11-11: ~9x slower, long calls truncated)
LLM_THINK_PARAM = os.getenv("COMPLYAI_LLM_THINK_PARAM", "template")
# Server presets per GPU size (docs/llm_options_evaluation.md, "Server: model options per GPU size"): COMPLYAI_PRESET
# sets the chat model, the context per request and the parallel requests in one go; each single COMPLYAI_* variable
# (CHAT_MODEL, THINK_MODEL, NUM_CTX, LLM_WORKERS, VERIFY_MAX_TOKENS) still overrides its own value. Only gpu12 (this PC,
# the default) is measured; gpu8 runs the same model with fewer parallel requests (same answers, slower); every other
# preset must pass the benchmark recipe on the server first. Model names are Ollama tags: on vLLM start the model with
# `--served-model-name <tag>` or set COMPLYAI_CHAT_MODEL to vLLM's name. "gpu_gb" = approx. GPU memory used, incl. bge-m3.
PRESETS = {
    "gpu6": {"model": "qwen3:4b", "ctx": 4096, "workers": 2, "gpu_gb": 5,
             "note": "smaller model of the same family; judge set 2026-11-12: no false alarms but recall 54 % (qwen3:8b "
                     "82 %) and 0 of 14 conflicts found: only if nothing larger fits (gpu8 is the better small choice)"},
    "gpu8": {"model": "qwen3:8b", "ctx": 4096, "workers": 2, "gpu_gb": 7.5,
             "note": "the measured model with 2 parallel requests: same answers as gpu12, about half the throughput"},
    "gpu12": {"model": "qwen3:8b", "ctx": 4096, "workers": 4, "gpu_gb": 8,
              "note": "this PC (RTX 4070 Ti): the measured baseline of every number in README and CLAUDE.md"},
    "gpu16": {"model": "qwen3:14b", "ctx": 4096, "workers": 4, "gpu_gb": 11.5,
              "note": "larger model of the same family; NOT measured"},
    "gpu24": {"model": "qwen3:30b-a3b", "ctx": 4096, "workers": 4, "gpu_gb": 21,
              "note": "mixture of experts (3B of 30B active per token): large-model reading at small-model speed; "
                      "NOT measured"},
    "gpu48": {"model": "qwen3:32b", "ctx": 8192, "workers": 8, "gpu_gb": 42,
              "note": "strongest dense model that fits, longer context; vLLM recommended; NOT measured"},
    "gpu80": {"model": "qwen3:32b", "ctx": 8192, "workers": 16, "gpu_gb": 70,
              "note": "as gpu48 with more documents / users at once; vLLM; NOT measured"},
}
PRESET = os.getenv("COMPLYAI_PRESET", "gpu12").strip().lower()
if PRESET not in PRESETS:
    raise ValueError(f"COMPLYAI_PRESET={PRESET!r} is not a preset: use one of {', '.join(PRESETS)}")
_PRESET = PRESETS[PRESET]
CHAT_MODEL = os.getenv("COMPLYAI_CHAT_MODEL") or _PRESET["model"]
EMBED_MODEL = os.getenv("COMPLYAI_EMBED_MODEL", "bge-m3")  # keep: every stored vector is bge-m3 (else re-ingest all)
# Context per request. Ollama reserves NUM_CTX x OLLAMA_NUM_PARALLEL of KV cache in VRAM, so keep this
# as small as the prompts allow (prompts are capped to fit, see EXCERPT_CHARS).
NUM_CTX = int(os.getenv("COMPLYAI_NUM_CTX") or _PRESET["ctx"])
LLM_WORKERS = int(os.getenv("COMPLYAI_LLM_WORKERS") or _PRESET["workers"])  # = OLLAMA_NUM_PARALLEL / vLLM --max-num-seqs
LLM_TIMEOUT = float(os.getenv("COMPLYAI_LLM_TIMEOUT", "180"))
MAX_OUTPUT_TOKENS = int(os.getenv("COMPLYAI_MAX_OUTPUT_TOKENS", "1500"))
EXTRACT_MAX_TOKENS = 2500        # dense passages hold many requirements (split in halves if still too long)

# Retrieval / decision thresholds (cosine similarity, bge-m3)
IT_CHUNK_TOP_K = 6           # IT passages retrieved per requirement
IT_MAX_PER_REQ = 3           # distinct ITs shown to the judge per requirement
# "1": a base IT and its annexes take one of those slots together (best passage of the family). Off: measured
# 2026-10-22 on the real DB (34 ITs), it removed duplicate alerts but gave the freed slots to weaker ITs and showed
# the judge only one annex of a family; no accuracy gain on a hand-reviewed sample (README, "Accuracy safeguards")
IT_PER_FAMILY = os.getenv("COMPLYAI_IT_PER_FAMILY", "0") == "1"
RULES_PER_IT = 4             # closest extracted IT rules shown per IT

# Verification pass on flagged findings (conflict / partial)
VERIFY_FINDINGS = os.getenv("COMPLYAI_VERIFY", "1") == "1"
VERIFY_THINK = os.getenv("COMPLYAI_VERIFY_THINK", "1") == "1"   # qwen3 reasoning mode for this step only
# Multi-model / reasoning experiments (defaults = one model, reasoning only for verification + section mapping):
THINK_MODEL = os.getenv("COMPLYAI_THINK_MODEL") or CHAT_MODEL       # model for every reasoning-mode call
JUDGE_THINK = os.getenv("COMPLYAI_JUDGE_THINK", "0") == "1"         # per-IT judge in reasoning mode too
# Answer budget of the reasoning-mode calls (thinking + JSON): 2,400 at NUM_CTX 4,096 (measured); half the context
# with a longer one (8,192 -> 4,096), where long verifications were cut before
VERIFY_MAX_TOKENS = int(os.getenv("COMPLYAI_VERIFY_MAX_TOKENS") or max(2400, NUM_CTX // 2))
# Narrow yes/no check of every conflict that is not a confirmed numeric contradiction ("does following this IT rule
# break the requirement?", engine._conflict_confirmed); a conflict it does not confirm, whose contradicting rule is not
# real IT text, or whose verification failed becomes a gap (2026-11-12: none of the 17 conflicts of the 2026-11-11 run
# was clearly real). Dry run 2026-11-12 on those 17 + 15 known real conflicts (509 and the judge set's 14): "think"
# kept 15/15 real and 4/17 false, "1" (no reasoning) 15/15 and 6/17; ~4 s per conflict, few findings reach it
CONFLICT_CHECK = os.getenv("COMPLYAI_CONFLICT_CHECK", "think")  # "think" reasoning mode, "1" without, "0" off
EXCERPT_CHARS = 1100         # per IT excerpt (window + neighbours), keeps the prompt < NUM_CTX
IT_MIN_SIM = 0.42            # below this an IT passage is not even shown to the LLM
# "Magnet" texts: requirements are all written "The supplier shall/must ...", so short generic IT rules in the same
# words ("The supplier's description must be provided.") are close to every requirement and took 26 % of the IT
# slots (2026-10-23). Rules shorter than this without a number are not retrieval candidates, and each IT text is
# ranked by its cosine minus IT_HUB_WEIGHT x its mean cosine to its IT_HUB_K closest requirements (all documents;
# only with >= IT_HUB_MIN_REQS requirements stored). Measured without the LLM: README "Accuracy safeguards".
IT_RULE_MIN_WORDS = 9
IT_HUB_WEIGHT = float(os.getenv("COMPLYAI_IT_HUB_WEIGHT", "0.3"))
IT_HUB_K = 10
IT_HUB_MIN_REQS = 200
# ITs whose profile says they govern LEONI's own suppliers / internal units are not compared with customer
# requirements (README "Accuracy safeguards"); off only for the synthetic judge set, whose ITs predate this rule
DIRECTION_FILTER = os.getenv("COMPLYAI_DIRECTION_FILTER", "1") == "1"
# Cross-encoder reranker between retrieval and the judge (complyai/rerank.py). With it, a wider pool of passages
# and rules is re-scored and only those the reranker finds relevant reach the judge. Off: measured 2026-10-19, it
# does not reduce wrong alerts on real documents (docs/llm_options_evaluation.md, "Reranker"; tests/eval_rerank.py).
RERANK = os.getenv("COMPLYAI_RERANK", "0") == "1"
RERANK_MODEL = os.getenv("COMPLYAI_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_POOL = 12             # passages and rules per requirement re-scored (closest by cosine first)
RERANK_MIN_SIM = 0.35        # cosine floor of that pool (wider than IT_MIN_SIM: the reranker filters)
RERANK_MIN = float(os.getenv("COMPLYAI_RERANK_MIN", "0.1"))  # relevance (0-1) needed to reach the judge
CATALOG_TOP_K = 8            # IT index entries (title only) offered to the LLM per requirement
CATALOG_MIN_SIM = 0.50
CATALOG_BY_HEADING = 3       # + index entries closest to the section heading
CATALOG_BY_CLAUSE = 3        # + index entries filed under the ISO/IATF clause quoted in the heading
MATRIX_ITS_PER_SECTION = 5   # ITs listed per section in the Excel matrix (ranked)
SECTION_CANDIDATES = 14      # pooled IT index candidates shown for a section-level mapping
SECTION_MAX_STATEMENTS = 12  # requirement statements shown per section
QUOTE_MIN_SIM = 0.65         # context lock: a requirement whose best-matching passage sentence is below this is
                             # not supported by its passage and is dropped (bge-m3 cosine, works across languages;
                             # measured on 150 real requirements: 98 % of real ones kept, 91 % of unsupported dropped)
REQ_SAME_SIM = 0.97          # practically identical requirement -> unchanged, no LLM call
REQ_CANDIDATE_SIM = 0.72     # above this an older requirement is a candidate "same / modified"

# Customers LEONI Portugal works for, with the names / brands their documents and LEONI's ITs use (complyai/customers.py).
# An IT passage, table column, heading or sentence that names only OTHER customers is not evidence for a requirement of
# this customer (review feedback 2026-11: the label annexes hold one column / section per customer). Brands of one group
# count as that customer (FENDT = AGCO; Perkins = Caterpillar, as in LEONI's own "CAT -PERKINS" column).
CUSTOMER_ALIASES = {
    "John Deere": [r"john[\s-]*deere?", r"\bdeere\b", r"\bJD\b"],
    "Cummins": [r"cummins"],
    "Caterpillar": [r"caterpillar", r"\bCAT\b", r"perkins"],
    "AGCO": [r"\bagco", r"\bfendt\b", r"\bvaltra\b", r"massey\s+ferguson"],
    "JCB": [r"\bjcb\b"],
    "Volvo CE": [r"\bvolvo\b"],
    "Scania": [r"\bscania\b"],
    "CNH": [r"\bcnh\b"],
    "Eolane": [r"\beolane\b"],
}
CUSTOMER_SCOPE = os.getenv("COMPLYAI_CUSTOMER_SCOPE", "1") == "1"
# Customer text shown around each requirement (exceptions and relaxations often follow the sentence): characters of the
# source passage before / after the quoted sentence (the next passage of the same section is used when needed)
REQ_CONTEXT_BEFORE = 250
REQ_CONTEXT_AFTER = 700
# The judge prompt (3 ITs + index list + that context) must leave room for the answer in NUM_CTX: the context is
# shortened when system + user prompt would exceed this many characters (~3.6 characters per token measured: no
# earlier run reached the NUM_CTX - 600 warning with prompts up to ~12,700 characters)
JUDGE_PROMPT_CHARS = int((NUM_CTX - 600) * 3.6)

# Chunking
CHUNK_MAX_CHARS = 1800       # parser chunks (unit of requirement extraction)
IT_WINDOW_CHARS = 700        # IT retrieval windows (unit of semantic search)
