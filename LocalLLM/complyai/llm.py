"""Thin client for the local LLM server (Ollama HTTP API).

Only two operations are needed by the engine:
  * chat_json(): a chat completion constrained to a JSON schema
  * embed():     vector embeddings for semantic search
Swapping Ollama for another runtime (vLLM, llama.cpp server...) only touches this file.
"""
import json
import logging
import time

import httpx
import numpy as np

from . import config, prompts

log = logging.getLogger("complyai.llm")
_client = httpx.Client(base_url=config.OLLAMA_URL, timeout=config.LLM_TIMEOUT)


class LLMError(RuntimeError):
    pass


class TruncatedError(LLMError):
    """The answer hit max_tokens: retrying the same request does not help, the caller must split it."""


def check() -> dict:
    """Verify the server is up and the configured models are present."""
    try:
        tags = _client.get("/api/tags").json()
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama not reachable at {config.OLLAMA_URL}: {e}") from e
    names = {m["name"] for m in tags.get("models", [])}
    missing = [m for m in dict.fromkeys((config.CHAT_MODEL, config.THINK_MODEL, config.EMBED_MODEL))
               if m not in names and f"{m}:latest" not in names]
    if missing:
        raise LLMError(f"Missing models {missing}. Run: ollama pull <model>")
    return {"url": config.OLLAMA_URL, "chat": config.CHAT_MODEL, "think": config.THINK_MODEL,
            "embed": config.EMBED_MODEL}


def chat_json(system: str, user: str, schema: dict, max_tokens: int = config.MAX_OUTPUT_TOKENS,
              retries: int = 1, think: bool = False) -> dict:
    """think=True lets reasoning models (qwen3) think before answering: slower, used only for verification
    (and the section mapping); such calls go to config.THINK_MODEL (= the chat model unless set)."""
    payload = {
        "model": config.THINK_MODEL if think else config.CHAT_MODEL,
        "messages": [{"role": "system", "content": f"{system}\n\n{prompts.GROUNDING}"},
                     {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "think": think,
        "keep_alive": "30m",
        # num_predict caps runaway generations (a model looping inside a JSON array would
        # otherwise run until the context is full); repeat_penalty discourages the loop.
        "options": {"temperature": 0, "num_ctx": config.NUM_CTX, "num_predict": max_tokens,
                    "repeat_penalty": 1.1},
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = _client.post("/api/chat", json=payload)
            r.raise_for_status()
            body = r.json()
            log.debug("llm: %d in / %d out tokens, %.1fs", body.get("prompt_eval_count", 0),
                      body.get("eval_count", 0), body.get("total_duration", 0) / 1e9)
            # Ollama silently truncates prompts longer than the context; leave >= 600 tokens for the answer
            if body.get("prompt_eval_count", 0) > config.NUM_CTX - 600:
                log.warning("prompt of %d tokens leaves little room in NUM_CTX=%d (may be truncated)",
                            body["prompt_eval_count"], config.NUM_CTX)
            if body.get("done_reason") == "length":
                raise TruncatedError(f"output truncated at {max_tokens} tokens")
            return json.loads(body["message"]["content"])
        except TruncatedError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, LLMError) as e:
            last_err = e
            # a truncated/looping answer is retried once with a little randomness
            payload["options"]["temperature"] = 0.3
            time.sleep(1)
    raise LLMError(f"chat failed after {retries + 1} attempts: {last_err}")


def embed(texts: list[str], batch: int = 32) -> np.ndarray:
    """Return L2-normalised float32 embeddings, shape (len(texts), dim)."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    out = []
    for i in range(0, len(texts), batch):
        for attempt in range(3):  # a model being (un)loaded can answer 400/5xx for a moment
            try:
                r = _client.post("/api/embed", json={"model": config.EMBED_MODEL, "input": texts[i:i + batch]})
                r.raise_for_status()
                break
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise LLMError(f"embedding failed: {e}") from e
                time.sleep(2 * (attempt + 1))
        out.extend(r.json()["embeddings"])
    v = np.asarray(out, dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return v
