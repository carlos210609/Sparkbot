from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class AIResponse:
    provider: str
    model: str
    content: str
    latency_ms: float
    fallback: bool = False


class AIClient:
    """OpenAI-compatible AI gateway with NVIDIA as the default provider.

    The provider/model can be changed by environment variables. NVIDIA model
    discovery is used when SPARKBOT_NVIDIA_MODEL=auto, avoiding a hard-coded
    model that may disappear from the catalog.
    """

    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL_PREFERENCES = (
        "deepseek-ai/deepseek-v3.2",
        "qwen/qwen3.5-397b-a17b",
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.1-8b-instruct",
    )

    def __init__(self) -> None:
        self.provider = os.getenv("SPARKBOT_AI_PROVIDER", "nvidia").lower()
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self.base_url = os.getenv("SPARKBOT_AI_BASE_URL", self.NVIDIA_BASE_URL).rstrip("/")
        self.model = os.getenv("SPARKBOT_NVIDIA_MODEL", "auto")
        self.timeout = float(os.getenv("SPARKBOT_AI_TIMEOUT", "45"))

    def status(self) -> dict[str, Any]:
        configured = bool(self.nvidia_key) if self.provider == "nvidia" else True
        return {
            "provider": self.provider,
            "configured": configured,
            "base_url": self.base_url,
            "model": self.model,
            "mode": "remote" if self.provider == "nvidia" else "compatible",
        }

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.provider == "nvidia":
            if not self.nvidia_key:
                raise RuntimeError("NVIDIA_API_KEY is not configured")
            headers["Authorization"] = f"Bearer {self.nvidia_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode())

    def available_models(self) -> list[str]:
        try:
            data = self._request("/models")
            return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            return []

    def select_model(self) -> str:
        if self.model != "auto":
            return self.model
        available = self.available_models()
        for preferred in self.DEFAULT_MODEL_PREFERENCES:
            if preferred in available:
                return preferred
        return available[0] if available else self.DEFAULT_MODEL_PREFERENCES[-1]

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.2,
             max_tokens: int = 1024) -> AIResponse:
        import time

        start = time.perf_counter()
        model = self.select_model()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            data = self._request("/chat/completions", payload)
            content = data["choices"][0]["message"]["content"]
            return AIResponse(
                provider=self.provider,
                model=model,
                content=str(content),
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except (OSError, ValueError, KeyError, IndexError, RuntimeError, urllib.error.URLError) as exc:
            return AIResponse(
                provider=self.provider,
                model=model,
                content=f"AI unavailable: {type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - start) * 1000,
                fallback=True,
            )
