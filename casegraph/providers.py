"""Providers for Case Graph nodes (PROPOSAL 3.1 Model Gateway, 1.3.4).

* Model-backed nodes call exactly one seam: ``GatewayClient.invoke(GatewayRequest) -> GatewayResponse``.
* ``LocalGateway`` is the in-process gateway. It reuses ``app.gateway.service`` (the same fail-safe
  logic as ``/api/gateway/invoke``) and writes exactly one audit record per call (hashes only).
* ``rules`` providers are in-process pure functions, versioned by a rule-set version.
  The rule sets here are tiny test rule sets: PLACEHOLDER — not clinical.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from app.config import Settings
from app.gateway import build_provider
from app.gateway.contract import DataClass, GatewayRequest, GatewayResponse, canonical_sha256
from app.gateway.provider import Provider
from app.gateway.service import audit_details, invoke_provider

from .data import PLACEHOLDER_LABEL, Alert, MedicationIssue, MedicationList, Vitals, LabSeries

AuditSink = Callable[[dict[str, Any]], None]


class GatewayClient(Protocol):
    def invoke(self, request: GatewayRequest) -> GatewayResponse: ...


class LocalGateway:
    """In-process Model Gateway around one provider built by ``build_provider``."""

    def __init__(
        self,
        provider: Provider,
        *,
        audit_sink: AuditSink | None = None,
        synthetic_only: bool = False,
        actor_role: str = "system:casegraph",
    ) -> None:
        self._provider = provider
        self._audit = audit_sink or (lambda record: None)
        self._synthetic_only = synthetic_only
        self._actor_role = actor_role
        self._lock = threading.Lock()
        self.calls = 0

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        with self._lock:
            self.calls += 1
        if self._synthetic_only and request.data_class is not DataClass.SYNTHETIC:
            # Runtime twin of the compile-time policy: non-synthetic data never reaches this provider.
            response = GatewayResponse(
                status="rejected", provider=self._provider.name, model_version="unknown", output=None,
                reason="policy_non_synthetic", latency_ms=0.0, request_sha256=canonical_sha256(request),
            )
        else:
            response = invoke_provider(self._provider, request)
        self._audit(
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "actor_id": None,
                "actor_role": self._actor_role,
                "action": "gateway.invoke",
                "target": f"task/{request.task}",
                "outcome": response.status,
                "request_id": uuid.uuid4().hex,
                "details": audit_details(request, response),
            }
        )
        return response


def mock_provider(model_version: str) -> Provider:
    """The s0 deterministic ``MockProvider`` (via ``build_provider``) reporting ``model_version``."""
    provider = build_provider("mock", Settings())
    provider.model_version = model_version  # type: ignore[attr-defined]
    return provider


def mock_gateways(
    versions: dict[str, str] | None = None, *, audit_sink: AuditSink | None = None
) -> dict[str, LocalGateway]:
    """One mock-backed LocalGateway per model provider id; ``external_model`` is synthetic-only."""
    versions = versions or {
        "project_model": "proj-mock-0.1",
        "external_model": "ext-mock-0.1",
        "encoder_2d": "enc2d-mock-0.1",
        "encoder_3d": "enc3d-mock-0.1",
        "classifier": "cls-mock-0.1",
        "segmentation": "seg-mock-0.1",
    }
    return {
        pid: LocalGateway(mock_provider(v), audit_sink=audit_sink, synthetic_only=pid == "external_model")
        for pid, v in versions.items()
    }


# ------------------------------------------------------------------ rule sets: PLACEHOLDER — not clinical


def vitals_reader_rules(items: list[Vitals | LabSeries]) -> tuple[str, ...]:
    """Structured statements from vitals/labs. Pure; version ``placeholder-vitals-reader-0.1``."""
    out: list[str] = []
    for item in sorted(items, key=lambda i: i.item_id):
        if isinstance(item, Vitals):
            out += [f"{item.item_id}: {k}={item.values[k]:g}" for k in sorted(item.values)]
        else:
            out += [f"{item.item_id}: {r.name}={r.value:g} {r.unit}" for r in item.results]
    return tuple(out)


# (rule_id, vital key, comparison, threshold, severity)
_RED_FLAG_RULES: tuple[tuple[str, str, str, float, str], ...] = (
    ("RF-PH-001", "spo2", "<", 90.0, "urgent"),
    ("RF-PH-002", "sbp", "<", 90.0, "urgent"),
    ("RF-PH-003", "hr", ">", 130.0, "urgent"),
    ("RF-PH-004", "temp_c", ">=", 39.5, "warning"),
)


def red_flag_rules(vitals: list[Vitals]) -> tuple[Alert, ...]:
    """Placeholder threshold rules over vitals. Pure; version ``placeholder-redflag-0.1``."""
    alerts: list[Alert] = []
    for item in sorted(vitals, key=lambda i: i.item_id):
        for rule_id, key, op, threshold, severity in _RED_FLAG_RULES:
            if key not in item.values:
                continue
            v = item.values[key]
            hit = v < threshold if op == "<" else v > threshold if op == ">" else v >= threshold
            if hit:
                alerts.append(
                    Alert(
                        rule_id=rule_id, severity=severity,  # type: ignore[arg-type]
                        message=f"{PLACEHOLDER_LABEL}: {key}={v:g} {op} {threshold:g} ({item.item_id})",
                    )
                )
    return tuple(alerts)


def pharma_rules(lists: list[MedicationList]) -> tuple[MedicationIssue, ...]:
    """Placeholder duplicate/dose-mismatch check across lists. Pure; ``placeholder-pharma-0.1``."""
    seen: dict[str, list[tuple[str | None, str]]] = {}
    for ml in sorted(lists, key=lambda i: i.item_id):
        for m in ml.medications:
            seen.setdefault(m.name.strip().lower(), []).append((m.dose, ml.item_id))
    issues: list[MedicationIssue] = []
    for name in sorted(seen):
        entries = seen[name]
        if len(entries) > 1:
            issues.append(MedicationIssue(kind="duplicate", medication=name,
                                          message=f"{PLACEHOLDER_LABEL}: listed {len(entries)} times"))
            doses = {d for d, _ in entries if d}
            if len(doses) > 1:
                issues.append(MedicationIssue(kind="dose_mismatch", medication=name,
                                              message=f"{PLACEHOLDER_LABEL}: doses differ {sorted(doses)}"))
    return tuple(issues)
