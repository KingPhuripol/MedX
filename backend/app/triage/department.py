"""Department suggestion (Reasoning Node, department part) via the Model Gateway.

Validates the snapshot before the provider (missing required fields abstain without a call) and
validates the provider output before use. Any gateway ``rejected``/``error`` or schema failure
returns no ranking. Nothing here can add, remove, or change red-flag alerts.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..gateway.contract import DataClass, GatewayRequest, GatewayResponse
from . import baseline  # noqa: F401  (registers the deterministic mock handler for TASK)
from .departments import BY_CODE, CODES
from .models import DepartmentEntry, DepartmentSuggestion, Snapshot

TASK = "triage.department.v1"
UNCERTAINTY_LABEL = "MOCK baseline — not calibrated"
InvokeFn = Callable[[GatewayRequest], GatewayResponse]


class _Ranked(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    score: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(max_length=64)


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None  # MOCK label rule (slice i2): every mock output carries it
    ranking: list[_Ranked] = Field(max_length=len(CODES))


def _empty(status: str, reason: str, missing: list[str], resp: GatewayResponse | None) -> DepartmentSuggestion:
    return DepartmentSuggestion(
        status=status,  # type: ignore[arg-type]
        top3=[],
        uncertainty=None,
        uncertainty_label=UNCERTAINTY_LABEL,
        missing_information=missing,
        reason=reason,
        provider=resp.provider if resp else None,
        model_version=resp.model_version if resp else None,
        contract_version=resp.contract_version if resp else None,
        request_sha256=resp.request_sha256 if resp else None,
    )


def build_request(snap: Snapshot) -> GatewayRequest:
    cc = snap.get("chief_complaint")
    present = sorted(
        (
            {"name": kind.removeprefix("symptom."), "fact_id": f.fact_id}
            for kind, f in snap.by_kind.items()
            if kind.startswith("symptom.") and f.value == "present"
        ),
        key=lambda s: s["name"],
    )
    return GatewayRequest(
        task=TASK,
        data_class=DataClass.SYNTHETIC,
        inputs={
            "chief_complaint": {"fact_id": cc.fact_id, "text": cc.value} if cc else None,
            "symptoms_present": present,
        },
    )


def _uncertainty(top: list[DepartmentEntry]) -> str:
    margin = top[0].score - (top[1].score if len(top) > 1 else 0.0)
    evidence = len(top[0].evidence_refs)
    if margin < 0.10:
        return "high"
    if margin < 0.30 or evidence < 2:
        return "medium"
    return "low"


def suggest(snap: Snapshot, invoke: InvokeFn) -> DepartmentSuggestion:
    missing = snap.missing_required()
    conflicts = snap.conflict_required()  # i2: a flagged same-timestamp conflict abstains too
    if missing or conflicts:  # validate before the provider: abstain and list what is missing
        reason = "required_information_missing" if missing else "conflicting_information"
        return _empty("abstained", reason, missing + conflicts, None)

    resp = invoke(build_request(snap))
    if resp.status == "rejected":
        return _empty("abstained", f"gateway_rejected:{resp.reason or 'unspecified'}", [], resp)
    if resp.status != "ok" or resp.output is None:
        return _empty("error", f"gateway_error:{resp.reason or 'unspecified'}", [], resp)
    try:
        output = _Output.model_validate(resp.output)
    except ValidationError:
        return _empty("error", "provider_output_schema_invalid", [], resp)
    codes = [r.code for r in output.ranking]
    refs_ok = all(set(r.evidence_refs) <= snap.fact_ids for r in output.ranking)
    if len(set(codes)) != len(codes) or not set(codes) <= set(CODES) or not refs_ok:
        return _empty("error", "provider_output_schema_invalid", [], resp)

    ranked = sorted(output.ranking, key=lambda r: (-r.score, r.code))
    top = [
        DepartmentEntry(
            code=r.code,
            label_th=BY_CODE[r.code].label_th,
            label_en=BY_CODE[r.code].label_en,
            score=round(r.score, 4),
            evidence_refs=sorted(set(r.evidence_refs)),
        )
        for r in ranked
        if r.score > 0 and r.evidence_refs
    ][:3]
    if not top:
        return _empty("abstained", "no_evidence_matched", [], resp)
    return DepartmentSuggestion(
        status="suggested",
        top3=top,
        uncertainty=_uncertainty(top),  # type: ignore[arg-type]
        uncertainty_label=UNCERTAINTY_LABEL,
        missing_information=[],
        reason=None,
        provider=resp.provider,
        model_version=resp.model_version,
        contract_version=resp.contract_version,
        request_sha256=resp.request_sha256,
    )
