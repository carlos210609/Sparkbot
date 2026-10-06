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

    NVIDIA's current hosted API exposes chat completions at
    /v1/chat/completions. We intentionally do not depend on /v1/models:
    that endpoint is not a reliable discovery mechanism for this service and
    a failed discovery request must never cause SparkBot to select a stale
    model.
    """

    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

    # Keep a known-good current model first. Users can override it with
    # SPARKBOT_NVIDIA_MODEL. The list is also used for a controlled retry if
    # NVIDIA returns 404 for a model that has been retired.
    DEFAULT_MODEL_PREFERENCES = (
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "deepseek-ai/deepseek-v4-flash",
    )

    def __init__(self) -> None:
        self.provider = os.getenv("SPARKBOT_AI_PROVIDER", "nvidia").lower()
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self.base_url = os.getenv(
            "SPARKBOT_AI_BASE_URL", self.NVIDIA_BASE_URL
        ).rstrip("/")
        self.model = os.getenv(
            "SPARKBOT_NVIDIA_MODEL", self.DEFAULT_MODEL_PREFERENCES[0]
        )
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

    def _request(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
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
        """Best-effort discovery for compatible providers.

        NVIDIA hosted inference is not dependent on this endpoint. If a
        provider supports /models, the result can still be used by callers,
        but failure simply returns an empty list.
        """
        try:
            data = self._request("/models")
            return [
                m["id"]
                for m in data.get("data", [])
                if isinstance(m, dict) and m.get("id")
            ]
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            return []

    def select_model(self) -> str:
        # Explicit configuration always wins.
        if self.model != "auto":
            return self.model
        # For NVIDIA, do not probe /models and then fall back to a stale ID.
        return self.DEFAULT_MODEL_PREFERENCES[0]

    @staticmethod
    def _http_error_status(exc: BaseException) -> int | None:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code
        return None

    def _chat_once(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Any | None = None,
        max_tool_rounds: int = 4,
    ) -> str:
        working = [dict(m) for m in messages]
        for _ in range(max(0, max_tool_rounds) + 1):
            payload: dict[str, Any] = {
                "model": model,
                "messages": working,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            if model.startswith("openai/gpt-oss-"):
                payload["reasoning_effort"] = os.getenv("SPARKBOT_REASONING_EFFORT", "medium")
            if tools and tool_executor:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            data = self._request("/chat/completions", payload)
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls or not tool_executor:
                return str(message.get("content", ""))
            working.append(message)
            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name", "")
                raw_args = function.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    result = tool_executor(name, args if isinstance(args, dict) else {})
                except Exception as exc:
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                working.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False)[:12000],
                })
        raise RuntimeError("tool call limit exceeded")

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Any | None = None,
        max_tool_rounds: int = 4,
    ) -> AIResponse:
        import time

        start = time.perf_counter()
        model = self.select_model()
        models_to_try = [model]
        if self.provider == "nvidia" and os.getenv(
            "SPARKBOT_NVIDIA_MODEL", self.model
        ) == "auto":
            models_to_try = list(dict.fromkeys(self.DEFAULT_MODEL_PREFERENCES))

        last_error: BaseException | None = None
        transient_statuses = {408, 425, 429, 500, 502, 503, 504}
        for candidate in models_to_try:
            attempts = 2
            for attempt in range(attempts):
                try:
                    content = self._chat_once(
                        candidate,
                        messages,
                        temperature,
                        max_tokens,
                        tools=tools,
                        tool_executor=tool_executor,
                        max_tool_rounds=max_tool_rounds,
                    )
                    if content.strip():
                        return AIResponse(
                            provider=self.provider,
                            model=candidate,
                            content=content,
                            latency_ms=(time.perf_counter() - start) * 1000,
                        )
                    raise RuntimeError("AI returned an empty response")
                except urllib.error.HTTPError as exc:
                    last_error = exc
                    if self.provider == "nvidia" and exc.code == 404:
                        break
                    if exc.code in transient_statuses and attempt + 1 < attempts:
                        continue
                    break
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    IndexError,
                    RuntimeError,
                    urllib.error.URLError,
                ) as exc:
                    last_error = exc
                    if attempt + 1 < attempts:
                        continue
                    break
            if self.provider != "nvidia" or self._http_error_status(last_error or RuntimeError()) != 404:
                break

        if tools and tool_executor and last_error is not None:
            try:
                content = self._chat_once(
                    model,
                    messages,
                    temperature,
                    max_tokens,
                    tools=None,
                    tool_executor=None,
                    max_tool_rounds=0,
                )
                if content.strip():
                    return AIResponse(
                        provider=self.provider,
                        model=model,
                        content=content,
                        latency_ms=(time.perf_counter() - start) * 1000,
                        fallback=True,
                    )
            except Exception as exc:
                last_error = exc

        exc = last_error or RuntimeError("unknown AI error")
        status = self._http_error_status(exc)
        detail = f"HTTP {status}: {exc}" if status else f"{type(exc).__name__}: {exc}"
        return AIResponse(
            provider=self.provider,
            model=model,
            content=f"AI unavailable: {detail}",
            latency_ms=(time.perf_counter() - start) * 1000,
            fallback=True,
        )
