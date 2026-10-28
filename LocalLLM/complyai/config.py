"""Central configuration. Every value can be overridden with an environment variable
so the same code runs locally and on Leoni's server without edits."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("COMPLYAI_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "complyai.db"
NOTIFICATIONS_PATH = DATA_DIR / "notifications.jsonl"
EXPORT_DIR = DATA_DIR / "exports"

# Local LLM (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("COMPLYAI_CHAT_MODEL", "qwen3:8b")
EMBED_MODEL = os.getenv("COMPLYAI_EMBED_MODEL", "bge-m3")
# Context per request. Ollama reserves NUM_CTX x OLLAMA_NUM_PARALLEL of KV cache in VRAM, so keep this
# as small as the prompts allow (prompts are capped to fit, see EXCERPT_CHARS).
NUM_CTX = int(os.getenv("COMPLYAI_NUM_CTX", "4096"))
LLM_WORKERS = int(os.getenv("COMPLYAI_LLM_WORKERS", "4"))  # match OLLAMA_NUM_PARALLEL on the server
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
VERIFY_MAX_TOKENS = 2400
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

# Chunking
CHUNK_MAX_CHARS = 1800       # parser chunks (unit of requirement extraction)
IT_WINDOW_CHARS = 700        # IT retrieval windows (unit of semantic search)
