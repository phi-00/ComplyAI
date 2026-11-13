"""Thin client for the local LLM server: the only place that talks to it.

Only two operations are needed by the engine:
  * chat_json(): a chat completion constrained to a JSON schema
  * embed():     vector embeddings for semantic search
Two APIs (config.LLM_API): "ollama" (Ollama's own API, default) and "openai" (any OpenAI-compatible server: vLLM,
llama.cpp llama-server, LM Studio, TGI, Ollama's /v1 endpoint), so the runtime on LEONI's server can be chosen
without touching the engine (docs/llm_options_evaluation.md, "Server").
"""
import json
import logging
import time

import httpx
import numpy as np

from . import config, prompts

log = logging.getLogger("complyai.llm")
_headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"} if config.LLM_API_KEY else {}
_client = httpx.Client(base_url=config.LLM_URL, timeout=config.LLM_TIMEOUT, headers=_headers)
_embed_client = _client if config.EMBED_URL == config.LLM_URL else \
    httpx.Client(base_url=config.EMBED_URL, timeout=config.LLM_TIMEOUT, headers=_headers)
OPENAI = config.LLM_API.lower() == "openai"


class LLMError(RuntimeError):
    pass


class TruncatedError(LLMError):
    """The answer hit max_tokens: retrying the same request does not help, the caller must split it."""


def setup() -> dict:
    """The active model setup (config.PRESET plus any single overrides), the settings the LLM server needs for it, and
    warnings about parts that were never measured. Printed by `python -m complyai check`; no server call."""
    p = config.PRESETS[config.PRESET]
    models = list(dict.fromkeys((config.CHAT_MODEL, config.THINK_MODEL)))
    warnings = []
    if config.PRESET != "gpu12" or config.CHAT_MODEL != "qwen3:8b" or config.THINK_MODEL != config.CHAT_MODEL:
        warnings.append("not the measured setup (gpu12, qwen3:8b for every step): run the benchmark recipe in "
                        "docs/llm_options_evaluation.md before using the results")
    for m in models:
        if "qwen3" not in m.lower():
            warnings.append(f"{m}: the thinking on/off switch was only tested with qwen3 / qwen3.5 models; check that "
                            "normal calls do not think (fast) and verification calls do (eval_judge.py --limit 3)")
    if "qwen3.5" in " ".join(models).lower() and not OPENAI:
        warnings.append("qwen3.5 on Ollama 0.40.6 ran with 1 parallel request only (4-7x slower): check the Ollama log")
    if OPENAI:
        server = {"vllm": f"vllm serve <model> --served-model-name {config.CHAT_MODEL} --max-model-len {config.NUM_CTX} "
                          f"--max-num-seqs {config.LLM_WORKERS} --reasoning-parser qwen3",
                  "llama-server": f"llama-server -m <model.gguf> -c {config.NUM_CTX * config.LLM_WORKERS} "
                                  f"-np {config.LLM_WORKERS} --jinja",
                  "think_param": config.LLM_THINK_PARAM}
    else:
        server = {"OLLAMA_NUM_PARALLEL": config.LLM_WORKERS, "OLLAMA_FLASH_ATTENTION": 1, "OLLAMA_KV_CACHE_TYPE": "q8_0",
                  "OLLAMA_MAX_LOADED_MODELS": len(models) + 1,
                  "pull": [f"ollama pull {m}" for m in models + [config.EMBED_MODEL]]}
    return {"preset": config.PRESET, "note": p["note"], "approx_gpu_gb": p["gpu_gb"] if
            (config.CHAT_MODEL, config.NUM_CTX, config.LLM_WORKERS) == (p["model"], p["ctx"], p["workers"]) else "?",
            "chat_model": config.CHAT_MODEL, "think_model": config.THINK_MODEL, "embed_model": config.EMBED_MODEL,
            "num_ctx": config.NUM_CTX, "parallel_requests": config.LLM_WORKERS,
            "verify_max_tokens": config.VERIFY_MAX_TOKENS, "server_settings": server, "warnings": warnings}


def check() -> dict:
    """Verify the server is up and the configured models are present."""
    try:
        if OPENAI:
            names = {m["id"] for m in _client.get("/v1/models").json().get("data", [])}
            if _embed_client is not _client:
                names |= {m["id"] for m in _embed_client.get("/v1/models").json().get("data", [])}
        else:
            names = {m["name"] for m in _client.get("/api/tags").json().get("models", [])}
    except httpx.HTTPError as e:
        raise LLMError(f"LLM server not reachable at {config.LLM_URL}: {e}") from e
    missing = [m for m in dict.fromkeys((config.CHAT_MODEL, config.THINK_MODEL, config.EMBED_MODEL))
               if m not in names and f"{m}:latest" not in names]
    if missing:
        raise LLMError(f"Missing models {missing} on {config.LLM_URL} (available: {sorted(names)[:10]})"
                       + ("" if OPENAI else ". Run: ollama pull <model>"))
    return {"api": config.LLM_API, "url": config.LLM_URL, "chat": config.CHAT_MODEL, "think": config.THINK_MODEL,
            "embed": config.EMBED_MODEL}


def _payload(system: str, user: str, schema: dict, max_tokens: int, think: bool) -> tuple[str, dict]:
    model = config.THINK_MODEL if think else config.CHAT_MODEL
    messages = [{"role": "system", "content": f"{system}\n\n{prompts.GROUNDING}"}, {"role": "user", "content": user}]
    if not OPENAI:
        return "/api/chat", {
            "model": model, "messages": messages, "format": schema, "stream": False, "think": think,
            "keep_alive": "30m",
            # num_predict caps runaway generations (a model looping inside a JSON array would
            # otherwise run until the context is full); repeat_penalty discourages the loop.
            "options": {"temperature": 0, "num_ctx": config.NUM_CTX, "num_predict": max_tokens,
                        "repeat_penalty": 1.1}}
    # OpenAI-compatible: the context length is the server's setting (vLLM --max-model-len, llama-server -c);
    # qwen3's thinking switch goes through the chat template (vLLM, llama-server, SGLang) or reasoning_effort
    # (Ollama's /v1: config.LLM_THINK_PARAM), plus qwen3's own "/no_think" marker
    if not think and "qwen3" in model.lower():
        messages[1]["content"] += "\n/no_think"
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens, "frequency_penalty": 0.1,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "schema": schema, "strict": True}}}
    if config.LLM_THINK_PARAM == "effort":
        body["reasoning_effort"] = "medium" if think else "none"
    else:
        body["chat_template_kwargs"] = {"enable_thinking": think}
    return "/v1/chat/completions", body


def _answer(body: dict, max_tokens: int) -> tuple[str, int, str]:
    """(answer text, prompt tokens, stop reason) of either API."""
    if not OPENAI:
        return body["message"]["content"], body.get("prompt_eval_count", 0), body.get("done_reason", "")
    choice = body["choices"][0]
    return choice["message"]["content"] or "", body.get("usage", {}).get("prompt_tokens", 0), \
        choice.get("finish_reason", "")


def chat_json(system: str, user: str, schema: dict, max_tokens: int = config.MAX_OUTPUT_TOKENS,
              retries: int = 1, think: bool = False) -> dict:
    """think=True lets reasoning models (qwen3) think before answering: slower, used only for verification
    (and the section mapping); such calls go to config.THINK_MODEL (= the chat model unless set)."""
    path, payload = _payload(system, user, schema, max_tokens, think)
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = _client.post(path, json=payload)
            r.raise_for_status()
            text, prompt_tokens, stop = _answer(r.json(), max_tokens)
            log.debug("llm: %d prompt tokens, stop=%s", prompt_tokens, stop)
            # Ollama silently truncates prompts longer than the context; leave >= 600 tokens for the answer
            if prompt_tokens > config.NUM_CTX - 600:
                log.warning("prompt of %d tokens leaves little room in NUM_CTX=%d (may be truncated)",
                            prompt_tokens, config.NUM_CTX)
            if stop == "length":
                raise TruncatedError(f"output truncated at {max_tokens} tokens")
            return json.loads(text)
        except TruncatedError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, LLMError) as e:
            last_err = e
            # a truncated/looping answer is retried once with a little randomness
            (payload if OPENAI else payload["options"])["temperature"] = 0.3
            time.sleep(1)
    raise LLMError(f"chat failed after {retries + 1} attempts: {last_err}")


def embed(texts: list[str], batch: int = 32) -> np.ndarray:
    """Return L2-normalised float32 embeddings, shape (len(texts), dim)."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    out = []
    path = "/v1/embeddings" if OPENAI else "/api/embed"
    for i in range(0, len(texts), batch):
        for attempt in range(3):  # a model being (un)loaded can answer 400/5xx for a moment
            try:
                r = _embed_client.post(path, json={"model": config.EMBED_MODEL, "input": texts[i:i + batch]})
                r.raise_for_status()
                break
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise LLMError(f"embedding failed: {e}") from e
                time.sleep(2 * (attempt + 1))
        body = r.json()
        out.extend([d["embedding"] for d in sorted(body["data"], key=lambda d: d["index"])] if OPENAI
                   else body["embeddings"])
    v = np.asarray(out, dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return v
