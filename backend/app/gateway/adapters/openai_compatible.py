"""OpenAI-compatible HTTP adapter using plain httpx. Disabled by default.

Policy: any request whose data_class is not ``synthetic`` is rejected before network I/O.
Provider-native payloads never leave this module; failures become ``status=error``.
"""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..contract import DataClass, GatewayRequest
from ..provider import ProviderResult


class _Message(BaseModel):
    content: str = Field(min_length=1)


class _Choice(BaseModel):
    message: _Message


class _Completion(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    choices: list[_Choice] = Field(min_length=1)


class OpenAICompatibleAdapter:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._enabled = enabled
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._transport = transport

    def _result(self, status: str, reason: str) -> ProviderResult:
        return ProviderResult(status=status, model_version=self._model, output=None, reason=reason)  # type: ignore[arg-type]

    def invoke(self, request: GatewayRequest, request_sha256: str) -> ProviderResult:
        # 1. Data policy first, before any other check or I/O.
        if request.data_class is not DataClass.SYNTHETIC:
            return self._result("rejected", "policy_non_synthetic")
        if not self._enabled:
            return self._result("rejected", "adapter_disabled")
        if not self._base_url:
            return self._result("error", "adapter_not_configured")

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps({"task": request.task, "inputs": request.inputs}, sort_keys=True),
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout_s) as client:
                resp = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException:
            return self._result("error", "provider_timeout")
        except httpx.HTTPError:
            return self._result("error", "provider_unreachable")

        if resp.status_code != 200:
            return self._result("error", "provider_http_error")
        try:
            parsed = _Completion.model_validate_json(resp.content)
        except (ValidationError, ValueError):
            return self._result("error", "provider_invalid_response")
        return ProviderResult(
            status="ok",
            model_version=parsed.model,
            output={"text": parsed.choices[0].message.content},
        )
