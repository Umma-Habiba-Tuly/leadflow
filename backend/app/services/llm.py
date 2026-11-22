"""A tiny provider-agnostic LLM layer.

The rest of the app depends on `LLMClient` only. Swap Gemini for another provider by
writing one more class with `generate_json`, no other code changes.
"""
import json
import time
from typing import Protocol

import httpx

from app.core.config import settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_STATUSES = {500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.5


def _api_error_message(resp) -> str:
    """The provider's own explanation (e.g. 'model no longer available'), kept short."""
    try:
        return str(resp.json()["error"]["message"])[:200]
    except (KeyError, TypeError, ValueError):
        return "no details"


class LLMError(RuntimeError):
    """Anything that went wrong talking to the model."""


class LLMNotConfigured(LLMError):
    pass


class LLMRateLimited(LLMError):
    pass


class LLMClient(Protocol):
    def generate_json(self, system: str, prompt: str, schema: dict) -> dict: ...


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        if not self.api_key:
            raise LLMNotConfigured("GEMINI_API_KEY is not set")

        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }

        resp = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                # Key goes in a header, never in the URL (URLs end up in logs).
                resp = httpx.post(
                    GEMINI_URL.format(model=self.model),
                    headers={"x-goog-api-key": self.api_key},
                    json=body,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException:
                # Found by the eval: 2 of 60 calls timed out. Slow replies are usually transient.
                if attempt < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_SECONDS * attempt)
                    continue
                raise LLMError(f"Gemini timed out ({MAX_ATTEMPTS} attempts)")
            except httpx.HTTPError as exc:
                raise LLMError(f"Could not reach Gemini: {type(exc).__name__}")
            # Temporary overload ("high demand"): wait a bit and try again.
            if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS * attempt)
                continue
            break

        if resp.status_code == 429:
            raise LLMRateLimited("Gemini rate limit reached")
        if resp.status_code != 200:
            raise LLMError(f"Gemini HTTP {resp.status_code}: {_api_error_message(resp)}")

        try:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMError("Gemini returned an unexpected response")


def get_llm_client() -> LLMClient:
    """FastAPI dependency. Tests override this with a fake."""
    return GeminiClient(settings.gemini_api_key, settings.llm_model)
