"""Three-step Pharma Agent pipeline: extract (gateway) -> normalise + rules -> phrase (gateway).

``reconcile(snapshot, invoke, mode)`` is the callable S2 can wrap later. ``invoke`` is the
in-process gateway function (audited); pharma never touches provider adapters. The snapshot is
read-only: the agent never edits, creates, or mutates orders.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from ..gateway import GatewayRequest, GatewayResponse
from .formulary import Formulary, load_formulary
from .mock_rules import DOSE_GRAMMAR_VERSION, EXTRACT_TASK, MOCK_RULES_VERSION, PHRASE_TASK
from .models import ExtractOutput, Issue, MedSnapshot, Mode, Notice
from .phrasing import TEMPLATE_VERSION, parse_phrase_output, phrase_input, template_text, validate_text
from .rules import NOTICE_RANK, RULE_VERSIONS, RULES_VERSION, AllergyItem, MedItem, count_comparisons, run_rules

Invoke = Callable[[GatewayRequest], GatewayResponse]
PIPELINE_VERSION = "s5-pipeline-2.3.0"


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_sha256(snapshot: MedSnapshot) -> str:
    return hashlib.sha256(canonical_json(snapshot.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _iso(dt) -> str:
    return dt.isoformat()


def _call_record(task: str, resp: GatewayResponse) -> dict:
    return {
        "task": task,
        "status": resp.status,
        "reason": resp.reason,
        "provider": resp.provider,
        "model_version": resp.model_version,
        "contract_version": resp.contract_version,
        "request_sha256": resp.request_sha256,
    }


def _extract_source(
    snapshot: MedSnapshot, index: int, invoke: Invoke, form: Formulary, calls: list[dict]
) -> tuple[dict, list[MedItem]]:
    source = snapshot.sources[index]
    request = GatewayRequest(
        task=EXTRACT_TASK,
        inputs={"source_type": source.source_type, "entries": [e.text for e in source.entries]},
        data_class=snapshot.data_class,
    )
    resp = invoke(request)
    calls.append(_call_record(EXTRACT_TASK, resp))
    record = {
        "source_index": index,
        "source_type": source.source_type,
        "evidence_ref": source.evidence_ref,
        "available_at_time": _iso(source.available_at_time),
        "provenance": source.provenance,
        "version": source.version,
        "request_sha256": resp.request_sha256,
        "provider": resp.provider,
        "model_version": resp.model_version,
    }
    failure = None
    parsed: ExtractOutput | None = None
    if resp.status != "ok":
        failure = resp.reason or resp.status
    else:
        try:
            parsed = ExtractOutput.model_validate(resp.output)
        except ValidationError:
            failure = "schema_invalid"
        else:
            if len(parsed.entries) != len(source.entries):
                failure = "schema_invalid_entry_count"
    if failure is not None:
        # Fail safe: no silent empty list; the source is visibly unreadable.
        return record | {"status": "extraction_failed", "failure_reason": failure, "entries": None}, []

    entries_out, items = [], []
    for j, (entry, ext) in enumerate(zip(source.entries, parsed.entries)):  # type: ignore[union-attr]
        ingredients = form.resolve_name(ext.drug_name_raw)
        entries_out.append(
            ext.model_dump()
            | {
                "source_text": entry.text,
                "ingredients": list(ingredients),
                "ingredient_rxcuis": list(form.rxcuis(ingredients)),
                "recognised": bool(ingredients),
                "discontinue_intent": entry.discontinue_intent,
                "discontinue_reason": entry.reason,
            }
        )
        items.append(
            MedItem(
                key=f"{index}:{j}",
                source_type=source.source_type,
                evidence_ref=source.evidence_ref,
                available_at_time=_iso(source.available_at_time),
                raw_span=entry.text,  # verbatim evidence text, not the model's copy
                drug_name_raw=ext.drug_name_raw,
                dose_value=ext.dose_value,
                dose_unit=ext.dose_unit,
                route=ext.route,
                frequency_code=ext.frequency_code,
                ingredients=ingredients,
                discontinue_intent=entry.discontinue_intent,
                quantity=ext.quantity,
                dose_status=ext.dose_status,
                dose_unverifiable_reason=ext.dose_unverifiable_reason,
                frequency_status=ext.frequency_status,
            )
        )
    return record | {"status": "ok", "failure_reason": None, "entries": entries_out}, items


def _phrase(
    issues: list[dict], snapshot: MedSnapshot, invoke: Invoke, mode: Mode, calls: list[dict]
) -> tuple[list[dict], dict | None]:
    items = [phrase_input(i) for i in issues]
    templates = {it["issue_id"]: template_text(it) for it in items}
    if mode == "rules_only":
        return [
            {"text": templates[it["issue_id"]], "source": "template", "provider": "none",
             "model_version": TEMPLATE_VERSION, "fallback_reason": None}
            for it in items
        ], None

    request = GatewayRequest(task=PHRASE_TASK, inputs={"issues": items}, data_class=snapshot.data_class)
    resp = invoke(request)
    calls.append(_call_record(PHRASE_TASK, resp))
    raw = {"status": resp.status, "reason": resp.reason, "output": resp.output}
    texts, call_failure = (None, resp.reason or resp.status) if resp.status != "ok" else parse_phrase_output(resp.output)
    out = []
    for it in items:
        text = (texts or {}).get(it["issue_id"])
        reason = call_failure or (None if text is not None else "missing_issue")
        if reason is None:
            reason = validate_text(text, it)  # type: ignore[arg-type]
        if reason is None:
            out.append({"text": text, "source": "model", "provider": resp.provider,
                        "model_version": resp.model_version, "fallback_reason": None})
        else:
            out.append({"text": templates[it["issue_id"]], "source": "template_fallback",
                        "provider": resp.provider, "model_version": resp.model_version, "fallback_reason": reason})
    return out, raw


def reconcile(
    snapshot: MedSnapshot, invoke: Invoke, mode: Mode = "rules_plus_model", run_id: str | None = None
) -> dict:
    """Run the pipeline on a read-only snapshot and return the run record (JSON-serialisable)."""
    form = load_formulary()
    run_id = run_id or uuid.uuid4().hex
    calls: list[dict] = []
    notices: list[dict] = []

    # Temporal gate: only evidence available at as_of is used.
    present = [i for i, s in enumerate(snapshot.sources) if s.available_at_time <= snapshot.as_of]
    allergies_ok = [a for a in snapshot.allergies if a.available_at_time <= snapshot.as_of]
    excluded = (len(snapshot.sources) - len(present)) + (len(snapshot.allergies) - len(allergies_ok))

    extraction, items = [], []
    for index in present:
        record, source_items = _extract_source(snapshot, index, invoke, form, calls)
        extraction.append(record)
        items.extend(source_items)
        if record["status"] == "extraction_failed":
            notices.append({"type": "source_unreadable", "source_type": record["source_type"],
                            "evidence_ref": record["evidence_ref"],
                            "detail": f"extraction failed ({record['failure_reason']}); this source was not checked"})
    for item in items:
        if not item.ingredients:
            notices.append({"type": "unrecognised_drug", "source_type": item.source_type,
                            "evidence_ref": item.evidence_ref, "raw_span": item.raw_span,
                            "detail": f"'{item.drug_name_raw}' is not in the formulary; kept for review, not checked"})

    order_records = [r for r in extraction if r["source_type"] == "new_order"]
    if not order_records:
        notices.append({"type": "source_missing", "source_type": "new_order", "evidence_ref": None,
                        "detail": "no new_order source available at as_of; omission was not evaluated"})
    readable_orders = [r for r in order_records if r["status"] == "ok"]

    allergy_items = []
    for n, a in enumerate(allergies_ok):
        res = form.resolve_allergen(a.text)
        allergy_items.append(AllergyItem(n, a.text, a.evidence_ref, _iso(a.available_at_time), res))
        if not res.mapped:
            notices.append({"type": "allergy_unmapped", "source_type": "allergy_record",
                            "evidence_ref": a.evidence_ref, "raw_span": a.text,
                            "detail": "allergen not mapped to the formulary; not checked automatically"})

    # A dose or frequency without a value (not stated, not recognised, unverifiable) is never read as
    # agreement: each such active entry is a missing_field issue (run_rules), and every comparison
    # skipped because of it is counted here, by reason.
    comparisons = count_comparisons(items)

    drafts = run_rules(items, allergy_items, form, readable_orders)
    issues = []
    for n, d in enumerate(drafts, start=1):
        issues.append({
            "issue_id": f"{run_id}-i{n:02d}",
            "run_id": run_id,
            "type": d.type,
            "severity": d.severity,
            "severity_rank": d.severity_rank,
            "rule_id": d.rule_id,
            "ingredients": list(d.ingredients),
            "ingredient_rxcuis": list(form.rxcuis(d.ingredients)),
            "conflicting_sources": d.sources,
            "unverifiable": d.unverifiable,
            "possible_substitution": d.possible_substitution,
            "notes": d.notes,
            "detail": d.detail,
            "field": d.field,
        })

    phrasings, phrase_raw = _phrase(issues, snapshot, invoke, mode, calls)
    for issue, phrasing in zip(issues, phrasings):
        issue["phrasing"] = phrasing
        issue["status"] = "open"
        Issue.model_validate(issue)  # contract check

    notice_out = []
    for n, notice in enumerate(notices, start=1):
        full = {"notice_id": f"{run_id}-n{n:02d}", "severity_rank": NOTICE_RANK, "source_type": None,
                "evidence_ref": None, "raw_span": None} | notice
        Notice.model_validate(full)
        notice_out.append(full)

    return {
        "run_id": run_id,
        "patient_ref": snapshot.patient_ref,
        "as_of": _iso(snapshot.as_of),
        "data_class": snapshot.data_class.value,
        "mode": mode,
        "status": "incomplete" if any(r["status"] != "ok" for r in extraction) else "complete",
        "snapshot_sha256": snapshot_sha256(snapshot),
        "pipeline_version": PIPELINE_VERSION,
        "formulary_version": form.version,
        "rules_version": RULES_VERSION,
        "cross_reactivity_version": form.cross_version,
        "excluded_future_items": excluded,
        "comparisons_made": comparisons["comparisons_made"],
        "unchecked_comparisons": comparisons["unchecked_comparisons"],
        "unchecked_by_reason": comparisons["unchecked_by_reason"],
        "extract_task": EXTRACT_TASK,
        "extract_mock_version": MOCK_RULES_VERSION,
        "dose_grammar_version": DOSE_GRAMMAR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "rule_versions": dict(RULE_VERSIONS),
        "extraction": extraction,
        "issues": issues,
        "notices": notice_out,
        "gateway_calls": calls,
        "phrase_raw_output": phrase_raw,
        "attribution": form.metadata["attribution"],
        "label": "Rules primary; model phrasing supplementary; default provider is the offline mock.",
    }


def issue_signature(issue: dict) -> tuple:
    """Mode-independent identity of an issue: type, rule, ingredients, sources, severity."""
    return (
        issue["type"],
        issue["rule_id"],
        tuple(issue["ingredients"]),
        tuple((s["source_type"], s["evidence_ref"], s["raw_span"], s.get("presence")) for s in issue["conflicting_sources"]),
        issue["severity"],
        issue["severity_rank"],
        issue.get("field"),
    )
