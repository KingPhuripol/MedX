"""External prototype model provider for the Model Gateway.

Adheres to DEC-0003 and DEC-0006:
- Only prototype models behind the stable Model Gateway.
- Never sends non-synthetic or unauthorized patient data to external APIs.
- Translates responses strictly into the Model API Contract v1.0.0 (ProviderOutput).
- Raises ProviderTimeout and ProviderFailure on communication defects so the Gateway
  circuit breaker and fail-safe policy handle them deterministically.
"""

from __future__ import annotations

import json
import os
from typing import Any
import httpx
from pydantic import ValidationError

from shared.contracts.model_api import (
    CarePathway,
    GatewayRequest,
    NextInformation,
    RedFlag,
    Uncertainty,
    Urgency,
)
from innovation.gateway.providers.base import ProviderFailure, ProviderOutput, ProviderTimeout

DEFAULT_EXTERNAL_URL = "https://api.openai.com/v1"
DEFAULT_EXTERNAL_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 15.0


class ExternalPrototypeProvider:
    """Gateway provider adapter connecting to external LLMs (OpenAI-compatible / Gemini)."""

    name = "external_prototype"

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        provider_version: str = "external-prototype-v1",
        config_version: str = "external-prototype-config-v1",
        fail_with: Exception | None = None,
        modalities: frozenset[str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = (
            url
            or os.environ.get("FRONT_DOOR_EXTERNAL_URL")
            or DEFAULT_EXTERNAL_URL
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("FRONT_DOOR_EXTERNAL_API_KEY") or ""
        self.model_version = (
            model_name
            or os.environ.get("FRONT_DOOR_EXTERNAL_MODEL")
            or DEFAULT_EXTERNAL_MODEL
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(
                os.environ.get(
                    "FRONT_DOOR_EXTERNAL_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)
                )
            )
        )
        self.provider_version = provider_version
        self.config_version = config_version
        self._fail_with = fail_with
        self._client = client
        self._modalities = modalities if modalities is not None else frozenset(
            {"TEXT", "STRUCTURED", "IMAGE_2D", "REFERENCE"}
        )

    def supported_modalities(self) -> frozenset[str]:
        return self._modalities

    def infer(self, request: GatewayRequest) -> ProviderOutput:
        if self._fail_with is not None:
            raise self._fail_with

        # DEC-0006 guard: Refuse non-synthetic patient data without explicit recorded approval
        if request.authorization.data_classification != "SYNTHETIC":
            if (
                not request.authorization.external_provider_allowed
                or not request.authorization.approval_id
            ):
                raise ProviderFailure(
                    f"External provider refused: {request.authorization.data_classification} "
                    "requires explicit recorded authorization (DEC-0006)."
                )

        usable = [e for e in request.evidence if e.modality in self._modalities]
        unsupported = tuple(
            e.evidence_id for e in request.evidence if e.modality not in self._modalities
        )
        evidence_ids = [e.evidence_id for e in usable]

        # Calculate effective timeout from request constraints and provider setting
        timeout_limit = min(
            self.timeout_seconds,
            request.provider_constraints.timeout_ms / 1000.0,
        )

        # Build prompt & request payload
        payload = self._build_payload(request, usable)

        # If a client is provided or API key is set, call the external API
        if self._client is not None or self.api_key:
            return self._call_external_api(
                payload=payload,
                timeout=timeout_limit,
                evidence_ids=evidence_ids,
                unsupported=unsupported,
                request=request,
            )

        # Fallback when no network/key is configured (allows offline contract testing)
        return self._build_default_output(
            request=request,
            evidence_ids=evidence_ids,
            unsupported=unsupported,
            note="External prototype offline fallback: no API key configured.",
        )

    def _build_payload(
        self, request: GatewayRequest, usable_evidence: list[Any]
    ) -> dict[str, Any]:
        evidence_summary = [
            {
                "evidence_id": e.evidence_id,
                "event_type": e.event_type,
                "modality": e.modality,
                "available_at_time": str(e.available_at_time),
            }
            for e in usable_evidence
        ]
        return {
            "model": self.model_version,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an AI Clinical Front Door prototype decision-support model. "
                        "Given patient evidence available at decision time, return a JSON proposal. "
                        "Never claim definitive autonomous diagnosis. "
                        "The JSON must have keys: urgency (level, confidence, evidence_ids), "
                        "red_flags (list of {code, state, evidence_ids}), "
                        "care_pathways (list of {code, rank, confidence, evidence_ids}), "
                        "next_information (list of {information_type, rank, reason_code}), "
                        "uncertainty (method, limitations, out_of_distribution, abstention_reason)."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": request.task,
                            "decision_time": str(request.decision_time),
                            "evidence": evidence_summary,
                            "missing_information": request.missing_information,
                            "requested_outputs": request.requested_outputs,
                        }
                    ),
                },
            ],
            "temperature": 0.0,
        }

    def _call_external_api(
        self,
        payload: dict[str, Any],
        timeout: float,
        evidence_ids: list[str],
        unsupported: tuple[str, ...],
        request: GatewayRequest,
    ) -> ProviderOutput:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.url}/chat/completions"

        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, headers=headers, timeout=timeout)
            else:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(url, json=payload, headers=headers)

            if response.status_code >= 400:
                raise ProviderFailure(
                    f"External API returned HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            content_str = data["choices"][0]["message"]["content"]
            parsed = json.loads(content_str)
            return self._parse_provider_output(parsed, evidence_ids, unsupported, request)

        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"External API timed out after {timeout}s") from exc
        except (httpx.RequestError, KeyError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderFailure(f"External API call failed: {exc}") from exc

    def _parse_provider_output(
        self,
        parsed: dict[str, Any],
        evidence_ids: list[str],
        unsupported: tuple[str, ...],
        request: GatewayRequest,
    ) -> ProviderOutput:
        try:
            urgency_raw = parsed.get("urgency", {})
            level = urgency_raw.get("level", "ROUTINE_REVIEW")
            if level not in {
                "IMMEDIATE_REVIEW",
                "URGENT_REVIEW",
                "ROUTINE_REVIEW",
                "INSUFFICIENT_INFORMATION",
            }:
                level = "ROUTINE_REVIEW" if evidence_ids else "INSUFFICIENT_INFORMATION"

            urgency = Urgency(
                level=level,
                confidence=urgency_raw.get("confidence"),
                evidence_ids=[
                    eid for eid in urgency_raw.get("evidence_ids", evidence_ids) if eid in evidence_ids
                ],
            )

            raw_flags = parsed.get("red_flags", [])
            red_flags = tuple(
                RedFlag(
                    code=str(f.get("code", "UNKNOWN_FLAG")),
                    state=f.get("state", "UNKNOWN")
                    if f.get("state") in {"TRIGGERED", "NOT_TRIGGERED", "UNKNOWN"}
                    else "UNKNOWN",
                    evidence_ids=[
                        eid for eid in f.get("evidence_ids", evidence_ids) if eid in evidence_ids
                    ],
                )
                for f in raw_flags
            )

            raw_pathways = parsed.get("care_pathways", [])
            care_pathways = tuple(
                CarePathway(
                    code=str(p.get("code", "CLINICIAN_ASSESSMENT")),
                    rank=int(p.get("rank", idx)),
                    confidence=p.get("confidence"),
                    evidence_ids=[
                        eid for eid in p.get("evidence_ids", evidence_ids) if eid in evidence_ids
                    ],
                )
                for idx, p in enumerate(raw_pathways, start=1)
            ) or (
                CarePathway(
                    code="CLINICIAN_ASSESSMENT",
                    rank=1,
                    confidence=None,
                    evidence_ids=evidence_ids,
                ),
            )

            raw_next = parsed.get("next_information", [])
            next_information = tuple(
                NextInformation(
                    information_type=str(n.get("information_type", "VITAL")),
                    rank=int(n.get("rank", idx)),
                    reason_code=str(n.get("reason_code", "EVALUATION_REQUEST")),
                )
                for idx, n in enumerate(raw_next, start=1)
            )

            raw_unc = parsed.get("uncertainty", {})
            uncertainty = Uncertainty(
                method=str(raw_unc.get("method", "external-llm-structured")),
                limitations=raw_unc.get("limitations") or [
                    "External prototype proposal: requires mandatory clinician review."
                ],
                out_of_distribution=raw_unc.get("out_of_distribution"),
                abstention_reason=raw_unc.get("abstention_reason"),
            )

            return ProviderOutput(
                urgency=urgency,
                red_flags=red_flags,
                care_pathways=care_pathways,
                next_information=next_information,
                uncertainty=uncertainty,
                model_version=self.model_version,
                provider_version=self.provider_version,
                config_version=self.config_version,
                graph_id=f"graph-{request.request_id}",
                graph_ref=f"external://graph-{request.request_id}",
                graph_schema_version="1.0.0",
                unsupported_evidence_ids=unsupported,
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ProviderFailure(f"Failed to validate external provider response schema: {exc}") from exc

    def _build_default_output(
        self,
        request: GatewayRequest,
        evidence_ids: list[str],
        unsupported: tuple[str, ...],
        note: str,
    ) -> ProviderOutput:
        return ProviderOutput(
            urgency=Urgency(
                level="ROUTINE_REVIEW" if evidence_ids else "INSUFFICIENT_INFORMATION",
                confidence=0.8 if evidence_ids else None,
                evidence_ids=evidence_ids,
            ),
            red_flags=(),
            care_pathways=(
                CarePathway(
                    code="CLINICIAN_ASSESSMENT",
                    rank=1,
                    confidence=0.8 if evidence_ids else None,
                    evidence_ids=evidence_ids,
                ),
            ),
            next_information=tuple(
                NextInformation(
                    information_type=item,
                    rank=i,
                    reason_code="DECLARED_INFORMATION_GAP",
                )
                for i, item in enumerate(request.missing_information, start=1)
            ),
            uncertainty=Uncertainty(
                method="external-prototype-standin",
                limitations=[note],
                out_of_distribution=None,
                abstention_reason=None if evidence_ids else "No evidence available",
            ),
            model_version=self.model_version,
            provider_version=self.provider_version,
            config_version=self.config_version,
            graph_id=f"graph-{request.request_id}",
            graph_ref=f"external://graph-{request.request_id}",
            graph_schema_version="1.0.0",
            unsupported_evidence_ids=unsupported,
        )


__all__ = ["ExternalPrototypeProvider", "ProviderTimeout", "ProviderFailure"]
