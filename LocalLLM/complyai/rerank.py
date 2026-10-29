"""Cross-encoder reranker (bge-reranker-v2-m3, multilingual): reads a requirement and an IT passage TOGETHER and
scores whether they are about the same topic (0-1).

The embedding model (bge-m3) encodes requirement and passage separately: good at finding candidates, but it
lets through passages that share words with the requirement without governing the same activity — the main
source of wrong alerts. The cross-encoder decides that much better. It runs in this process with PyTorch on the
GPU (~1.1 GB VRAM in fp16; Ollama has no rerank endpoint) and is only loaded when config.RERANK is on.

Used as a filter it must not hide IT text that CONTRADICTS a requirement — that is what we look for. Two things
made it do that when whole passages were scored (measured 2026-10-19, docs/llm_options_evaluation.md):
rerankers are trained on "does the passage answer the query", so a different value ("fill rate 95 %-100 %" vs
"at least 98 %") reads as a poor answer; and the one relevant sentence is diluted by the rest of its passage
(0.79 alone, 0.01-0.04 inside its window). So a passage is scored by its BEST SENTENCE, with values masked on
both sides: the score measures the topic, the judge decides agreement.
"""
import re
import threading

from . import config

_lock = threading.Lock()
_loaded = None

# Values (98 %, 10 mm, 24 h, 2,5, 2026-10-19) become "N"; identifiers keep their digits (ISO 9001, IATF 16949,
# WI 3600, D3, 8D, A5): a number glued to a letter or right after an upper-case code is part of a name
_VALUE = re.compile(r"(?<!\w)(?<![A-Z][A-Z] )\d+(?:[.,]\d+)*(?![A-Z]\b)")
# sentence ends, table cells (" | ") and table separators ("##"); not ":" (keeps "Header: value" rows whole)
_SPLIT = re.compile(r"(?<=[.;!?])\s+|\s+\|\s+|\s*#{2,}\s*|\n+")
MIN_SENTENCE = 40  # shorter fragments ("Nota:", a table cell) are joined to the next one


def mask_values(text: str) -> str:
    return _VALUE.sub("N", text)


def sentences(text: str) -> list[str]:
    out = []
    for s in (p.strip() for p in _SPLIT.split(text)):
        if not s:
            continue
        if out and len(out[-1]) < MIN_SENTENCE:
            out[-1] += " " + s
        else:
            out.append(s)
    if len(out) > 1 and len(out[-1]) < MIN_SENTENCE:
        last = out.pop()
        out[-1] += " " + last
    return out or [text]


def _load():
    global _loaded
    if _loaded is None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(config.RERANK_MODEL)
        model = AutoModelForSequenceClassification.from_pretrained(
            config.RERANK_MODEL, dtype=torch.float16 if device == "cuda" else torch.float32)
        _loaded = (tokenizer, model.to(device).eval(), device)
    return _loaded


def _cross_scores(pairs: list[tuple[str, str]], batch: int = 64) -> list[float]:
    """Raw cross-encoder score 0-1 of each (query, text) pair, batched by length (less padding)."""
    import torch
    order = sorted(range(len(pairs)), key=lambda k: len(pairs[k][0]) + len(pairs[k][1]))
    out = [0.0] * len(pairs)
    with _lock:  # one GPU model shared by the worker threads
        tokenizer, model, device = _load()
        with torch.no_grad():
            for k in range(0, len(order), batch):
                part = order[k:k + batch]
                enc = tokenizer([pairs[j][0] for j in part], [pairs[j][1] for j in part], padding=True,
                                truncation=True, max_length=512, return_tensors="pt").to(device)
                for j, s in zip(part, torch.sigmoid(model(**enc).logits.view(-1).float()).tolist()):
                    out[j] = s
    return out


def scores(pairs: list[tuple[str, str]]) -> list[float]:
    """Topic relevance 0-1 of each (requirement, IT passage) pair: the best score over the passage's sentences,
    values masked on both sides."""
    if not pairs:
        return []
    unique: dict[tuple[str, str], int] = {}
    owners = []
    for q, passage in pairs:
        q = mask_values(q)
        owners.append([unique.setdefault((q, mask_values(s)), len(unique)) for s in sentences(passage)])
    flat = _cross_scores(list(unique))
    return [max(flat[k] for k in ks) for ks in owners]
