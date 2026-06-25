"""Unified Bedrock client for all classifier raters.

Uses the Bedrock Converse API, which normalises message format across model
families (Claude, Nova, Llama, Mistral) so calling code doesn't need to know
which family it's talking to. The same JSON-extraction + retry logic wraps
every call.

Each ``RaterConfig`` carries its own model_id + region, so a single review
can mix model families and/or regions (e.g. Sonnet in apac, Llama in us).
Clients are cached per (provider, region) — boto3 sessions are cheap to keep
around and a fresh one per call would dominate the cost of a small request.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

from .config import RaterConfig

# Defer the boto3 import: it's heavy (~300ms) and only needed when we actually
# invoke Bedrock. This keeps non-LLM commands snappy.
_boto3 = None
# Cached clients keyed by (region, profile) — profile is part of the key so
# you can mix raters that use different AWS profiles in one process.
_clients: dict[tuple[str, str], Any] = {}
_clients_lock = threading.Lock()


def _ensure_boto3() -> Any:
    global _boto3
    if _boto3 is None:
        import boto3  # type: ignore

        _boto3 = boto3
    return _boto3


def _client_for(region: str, profile: str = "") -> Any:
    """Cached bedrock-runtime client per (region, profile).

    Empty ``profile`` means "use the default credential chain" (env vars,
    instance role, etc.). A non-empty profile constructs a named ``Session``
    so credentials come from that ``~/.aws/credentials`` entry.
    """
    key = (region, profile)
    with _clients_lock:
        if key not in _clients:
            boto3 = _ensure_boto3()
            if profile:
                session = boto3.Session(profile_name=profile, region_name=region)
                _clients[key] = session.client("bedrock-runtime")
            else:
                _clients[key] = boto3.client("bedrock-runtime", region_name=region)
        return _clients[key]


class LLMError(RuntimeError):
    """Raised when a Bedrock call fails after retries or returns unparseable output."""


# --- Public API ----------------------------------------------------------


def invoke_json(
    rater: RaterConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    retries: int = 3,
) -> dict:
    """Call ``rater``'s model with the given prompts and return parsed JSON.

    Uses Bedrock's ``Converse`` API. Tells the model to return JSON via the
    system prompt (Bedrock's structured-output / response-format support varies
    by model family, but every supported family handles "return JSON" well at
    temp=0). Tolerates ``` fences and stripped wrappers when extracting JSON.
    """
    if not rater.is_bedrock:
        raise LLMError(f"unsupported rater provider: {rater.provider}")

    client = _client_for(rater.region, rater.aws_profile)

    # Bedrock Converse takes ``system`` as a list of dicts and ``messages`` as
    # role+content blocks. content is a list — each block has a single field
    # (``text`` for text, ``image`` for images, etc.).
    system_blocks = [{"text": (system_prompt + ("\n" + rater.prompt_suffix if rater.prompt_suffix else ""))}]
    messages = [{"role": "user", "content": [{"text": user_prompt}]}]
    inference_config = {"temperature": temperature, "maxTokens": max_tokens}

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.converse(
                modelId=rater.model_id,
                system=system_blocks,
                messages=messages,
                inferenceConfig=inference_config,
            )
            text = _converse_text(resp)
            return _extract_json(text)
        except Exception as e:  # noqa: BLE001 — boto3 raises ClientError subclasses
            last_err = e
            msg = str(e)
            # Throttling / transient failures: exponential backoff.
            transient = (
                "ThrottlingException" in msg
                or "ServiceUnavailable" in msg
                or "ModelTimeoutException" in msg
                or "InternalServerError" in msg
            )
            if transient and attempt < retries - 1:
                time.sleep(min(2**attempt, 8))
                continue
            raise LLMError(f"{rater.label} ({rater.model_id}): {e}") from e
    # Unreachable: loop either returns or raises.
    raise LLMError(f"{rater.label} exhausted retries: {last_err}")


# --- Helpers -------------------------------------------------------------


def _converse_text(resp: dict) -> str:
    """Pull the text payload out of a Converse response."""
    out = resp.get("output") or {}
    msg = out.get("message") or {}
    parts = msg.get("content") or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


_JSON_FENCE = re.compile(r"^```[a-zA-Z]*\n?")
_TRAILING_FENCE = re.compile(r"\n?```$")


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of a model response (tolerates ``` fences + prose)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = _JSON_FENCE.sub("", t)
        t = _TRAILING_FENCE.sub("", t).strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start : end + 1]
    if not t:
        raise LLMError("model returned empty response")
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise LLMError(f"could not parse JSON from response: {e}; raw={text[:200]!r}") from e


def warm(rater: RaterConfig) -> None:
    """Touch the boto3 client so it's initialised before workers race for it.

    A no-op if AWS credentials are missing — actual calls will fail with a
    clearer error message later. We don't actually invoke the model here
    (that would cost tokens); we just construct the boto3 client.
    """
    try:
        _client_for(rater.region, rater.aws_profile)
    except Exception as e:  # noqa: BLE001
        print(f"  warning: could not init Bedrock client for {rater.label}: {e}")
