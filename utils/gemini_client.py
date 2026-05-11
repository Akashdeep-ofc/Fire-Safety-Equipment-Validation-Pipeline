"""
Thin wrapper around the google-genai SDK.

All checks import `call_gemini` from here — keeping the API surface
consistent and usage tracking centralised.
"""

import json
import os
import time
from typing import Any

from google import genai
from google.genai import types

from checks.base import UsageRecord

# ---------------------------------------------------------------------------
# Client (singleton — initialised once, reused across all checks)
# ---------------------------------------------------------------------------

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY environment variable is not set. "
                "Run: export GEMINI_API_KEY='your_key'"
            )
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Core call
# ---------------------------------------------------------------------------

def call_gemini(
    *,
    model: str,
    images: list[bytes],
    prompt: str,
    usage: UsageRecord,
    retries: int = 3,
    backoff: float = 10.0,
) -> dict[str, Any]:
    """
    Send `images` + `prompt` to Gemini and return the parsed JSON response.

    Always requests JSON output (`response_mime_type="application/json"`).
    Retries on rate-limit errors (429) with exponential back-off.

    Args:
        model:    Gemini model string, e.g. "gemini-2.5-flash"
        images:   Raw bytes for each image (JPEG/PNG)
        prompt:   The full instruction prompt
        usage:    UsageRecord to update with token counts
        retries:  Max retry attempts on 429 / transient errors
        backoff:  Initial back-off seconds (doubles on each retry)

    Returns:
        Parsed JSON dict from the model response.

    Raises:
        RuntimeError on non-retryable errors or exhausted retries.
    """
    client = get_client()

    # Build the multi-part content list: images first, then the prompt text
    parts: list[Any] = []
    for img_bytes in images:
        mime = _detect_mime(img_bytes)
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
    parts.append(types.Part.from_text(text=prompt))

    attempt = 0
    wait = backoff

    while True:
        try:
            response = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )

            # Track usage
            meta = response.usage_metadata
            usage.add(
                input_tok=meta.prompt_token_count or 0,
                output_tok=meta.candidates_token_count or 0,
                thinking_tok=meta.thoughts_token_count or 0,
                cached_tok=meta.cached_content_token_count or 0,
                total_tok=meta.total_token_count or 0,
            )

            raw = response.text.strip()
            # Strip markdown fences if the model wraps its JSON
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            return json.loads(raw)

        except Exception as exc:
            msg = str(exc)
            is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg.upper()

            if attempt < retries and (is_rate_limit or _is_transient(msg)):
                attempt += 1
                print(f"  [gemini_client] {exc!r} — retry {attempt}/{retries} in {wait:.0f}s")
                time.sleep(wait)
                wait *= 2
            else:
                raise RuntimeError(
                    f"Gemini call failed after {attempt} retries: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_mime(data: bytes) -> str:
    """Detect JPEG vs PNG by magic bytes."""
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    # Default to JPEG for unknown formats
    return "image/jpeg"


def _is_transient(msg: str) -> bool:
    keywords = ("503", "500", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED")
    return any(k in msg.upper() for k in keywords)
