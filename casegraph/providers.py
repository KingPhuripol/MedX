"""Providers for Case Graph nodes (PROPOSAL 3.1 Model Gateway, 1.3.4).

* Model-backed nodes call exactly one seam: ``GatewayClient.invoke(GatewayRequest) -> GatewayResponse``.
* ``LocalGateway`` is the in-process gateway. It reuses ``app.gateway.service`` (the same fail-safe
  logic as ``/api/gateway/invoke``) and writes exactly one audit record per call (hashes only).
* ``rules`` providers are in-process pure functions, versioned by a rule-set version.
  The rule sets here are tiny test rule sets: PLACEHOLDER — not clinical.
"""

from __future__ import annotations

import math
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from app.config import Settings
from app.gateway import build_provider
from app.gateway.contract import DataClass, GatewayRequest, GatewayResponse, canonical_sha256
from app.gateway.provider import Provider, ProviderResult
from app.gateway.service import audit_details, invoke_provider

from .data import (
    PLACEHOLDER_LABEL,
    Alert,
    LabSeries,
    MedicationCheck,
    MedicationIssue,
    MedicationList,
    RuleResult,
    Vitals,
    screening_status,
)

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


class _ExplicitReasoningKeys:
    """The s0 ``MockProvider`` plus explicit Reasoning keys ``department: null, care: []``.

    s2r: a Reasoning output *without* these keys is ``schema_invalid``; the mock states explicitly that
    it proposes no department and no care items instead of relying on an absent key.
    """

    def __init__(self, inner: Provider) -> None:
        self._inner = inner

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model_version(self) -> str:
        return self._inner.model_version  # type: ignore[attr-defined]

    @model_version.setter
    def model_version(self, value: str) -> None:
        self._inner.model_version = value  # type: ignore[attr-defined]

    def invoke(self, request: GatewayRequest, request_sha256: str) -> ProviderResult:
        result = self._inner.invoke(request, request_sha256)
        if request.task == "reasoning" and result.status == "ok" and result.output is not None:
            result = replace(result, output={"department": None, "care": [], **result.output})
        return result


def mock_provider(model_version: str) -> Provider:
    """The s0 deterministic ``MockProvider`` (via ``build_provider``) reporting ``model_version``."""
    provider = _ExplicitReasoningKeys(build_provider("mock", Settings()))
    provider.model_version = model_version
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


def _fmt(value: object) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def vitals_reader_rules(items: list[Vitals | LabSeries]) -> tuple[str, ...]:
    """Structured statements from vitals/labs. Pure; version ``placeholder-vitals-reader-0.1``."""
    out: list[str] = []
    for item in sorted(items, key=lambda i: i.item_id):
        if isinstance(item, Vitals):
            readings = item.readings()
            out += [f"{item.item_id}: {k}={_fmt(readings[k])}" for k in sorted(readings)]
        else:
            out += [f"{item.item_id}: {r.test}={r.value:g} {r.unit}" for r in item.results]
    return tuple(out)


@dataclass(frozen=True)
class RedFlagRule:
    """One placeholder threshold rule. ``required_inputs`` are declared per rule (s2r)."""

    rule_id: str
    key: str
    op: str
    threshold: float
    severity: str

    @property
    def required_inputs(self) -> tuple[str, ...]:
        return (f"Vitals.{self.key}",)

    def hit(self, value: float) -> bool:
        if self.op == "<":
            return value < self.threshold
        if self.op == ">":
            return value > self.threshold
        return value >= self.threshold


RED_FLAG_RULE_SET_VERSION = "placeholder-redflag-0.2"
RED_FLAG_RULES: tuple[RedFlagRule, ...] = (
    RedFlagRule("RF-PH-001", "spo2", "<", 90.0, "urgent"),
    RedFlagRule("RF-PH-002", "sbp", "<", 90.0, "urgent"),
    RedFlagRule("RF-PH-003", "hr", ">", 130.0, "urgent"),
    RedFlagRule("RF-PH-004", "temp_c", ">=", 39.5, "warning"),
)
RED_FLAG_RULE_IDS: tuple[str, ...] = tuple(r.rule_id for r in RED_FLAG_RULES)


def _finite_readings(vitals: list[Vitals], key: str) -> list[tuple[str, float]]:
    """(item_id, value) for ``key``; a non-finite value is treated as missing (defence in depth)."""
    return [
        (item.item_id, float(value))
        for item in sorted(vitals, key=lambda i: i.item_id)
        if isinstance(value := getattr(item, key, None), (int, float)) and not isinstance(value, bool)
        and math.isfinite(value)
    ]


def red_flag_rules(vitals: list[Vitals]) -> tuple[tuple[RuleResult, ...], tuple[Alert, ...]]:
    """Placeholder threshold rules over vitals. Pure; version ``placeholder-redflag-0.2``.

    Every declared rule yields a :class:`RuleResult`. A rule whose required input is absent or
    non-finite is ``not_evaluated`` with the exact missing input; it never reads as "did not fire".
    """
    results: list[RuleResult] = []
    alerts: list[Alert] = []
    for rule in RED_FLAG_RULES:
        readings = {inp: _finite_readings(vitals, inp.split(".", 1)[1]) for inp in rule.required_inputs}
        missing = tuple(sorted(inp for inp, found in readings.items() if not found))
        values = readings[rule.required_inputs[0]]
        hits = [(iid, v) for iid, v in values if rule.hit(v)] if not missing else []
        results.append(
            RuleResult(
                rule_id=rule.rule_id, missing_inputs=missing,
                status=screening_status([bool(found) for found in readings.values()], missing, allow_partial=False),
                evaluated_on=tuple(sorted({iid for found in readings.values() for iid, _ in found})) if not missing else (),
                fired=bool(hits) if not missing else None,
            )
        )
        alerts += [
            Alert(rule_id=rule.rule_id, severity=rule.severity,  # type: ignore[arg-type]
                  message=f"{PLACEHOLDER_LABEL}: {rule.key}={v:g} {rule.op} {rule.threshold:g} ({iid})")
            for iid, v in hits
        ]
    return tuple(results), tuple(alerts)


PHARMA_CHECKS = ("duplicate", "dose_mismatch")


def pharma_rules(lists: list[MedicationList]) -> tuple[tuple[MedicationCheck, ...], tuple[MedicationIssue, ...]]:
    """Placeholder duplicate/dose-mismatch check across lists. Pure; ``placeholder-pharma-0.2``.

    ``dose_mismatch`` is checked for every medication listed more than once; if any of those entries
    lacks a dose the check is ``not_evaluated`` (s2r: a missing dose never removes the check).
    """
    seen: dict[str, list[tuple[str | None, str]]] = {}
    for ml in sorted(lists, key=lambda i: i.item_id):
        for m in ml.entries:
            seen.setdefault(m.generic_name.strip().lower(), []).append((m.dose, ml.item_id))
    checks: list[MedicationCheck] = []
    issues: list[MedicationIssue] = []
    for name in sorted(seen):
        entries = seen[name]
        sources = tuple(sorted({iid for _, iid in entries}))
        duplicate = len(entries) > 1
        checks.append(MedicationCheck(medication=name, check="duplicate", missing_inputs=(), evaluated_on=sources,
                                      fired=duplicate, status=screening_status([True], (), allow_partial=False)))
        if duplicate:
            issues.append(MedicationIssue(kind="duplicate", medication=name,
                                          message=f"{PLACEHOLDER_LABEL}: listed {len(entries)} times"))
            missing = tuple(sorted({f"MedicationList.dose@{iid}" for d, iid in entries if not d}))
            doses = {d for d, _ in entries if d}
            differ = len(doses) > 1
            checks.append(MedicationCheck(
                medication=name, check="dose_mismatch", missing_inputs=missing,
                evaluated_on=sources if not missing else (), fired=differ if not missing else None,
                status=screening_status([not missing], missing, allow_partial=False),
            ))
            if differ:  # a mismatch among recorded doses is reported even when another dose is missing
                issues.append(MedicationIssue(kind="dose_mismatch", medication=name,
                                              message=f"{PLACEHOLDER_LABEL}: doses differ {sorted(doses)}"))
    return tuple(checks), tuple(issues)
