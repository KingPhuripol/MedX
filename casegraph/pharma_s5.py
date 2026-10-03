"""Real S5 Pharma Agent as the Case Graph Pharma provider (slice cg-t123, PROPOSAL 3.2.4). Research prototype.

Registers ``app.pharma.pipeline.reconcile`` (mode ``rules_plus_model``) on the ``pharma_agent`` hook under
``s5-pipeline-2.6.0`` (hook api 2). The adapter is the only place that knows both shapes:

* in:  ``MedicationList`` (home_list, patient_reported, new_order) + ``AllergyList`` + the Reader:Text allergy facts
  -> an S5 ``MedSnapshot`` with ``as_of = T``. Entry text is rendered from the typed fields; nothing is guessed.
* out: S5 issues -> ``MedicationIssue`` keeping rule id, severity, ingredients and conflicting sources (so the S5
  ``issue_signature`` is unchanged); notices, unchecked comparisons and unreadable sources -> ``not_evaluated``
  ``MedicationCheck`` rows (never a silent skip).

Every S5 extract/phrase call goes through the node's audited gateway (``PharmaInput.invoke``) and is counted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from app.gateway import DataClass
from app.pharma.models import AllergyRecord, MedEntry, MedSnapshot, MedSource
from app.pharma.pipeline import PIPELINE_VERSION, issue_signature, reconcile

from .conversation_meds import parse_medication_facts
from .data import AllergyList, MedicationCheck, MedicationEntry, MedicationIssue, MedicationList, screening_status
from .library import S5_PHARMA_VERSION
from .providers import PharmaInput, register_pharma_provider

assert PIPELINE_VERSION == S5_PHARMA_VERSION, "library.S5_PHARMA_VERSION must name the registered S5 pipeline"
S5_LABEL = "S5 Pharma Agent (rules primary; model phrasing supplementary; offline mock provider by default)"
SOURCE_TYPES = ("home_list", "patient_reported", "new_order")


def entry_text(entry: MedicationEntry) -> str:
    """One medication line from the typed fields: ``name [dose unit] [frequency] [route]``. Absent fields stay
    absent (S5 then reports the missing dose/frequency itself)."""
    parts = [entry.generic_name]
    if entry.dose is not None:
        parts.append(entry.dose)
    parts += [p for p in (entry.frequency, entry.route) if p]
    return " ".join(parts)[:500]


def _source(item: MedicationList) -> MedSource:
    if item.list_source not in SOURCE_TYPES:
        raise ValueError(f"{item.item_id}: list_source {item.list_source!r} has no S5 source type")
    return MedSource(
        source_type=item.list_source, evidence_ref=item.item_id[:128], available_at_time=item.available_at_time,
        provenance=item.provenance[:256], version=item.version[:64],
        entries=tuple(MedEntry(text=entry_text(e)) for e in item.entries),
    )


def _allergy_text(substance: str, reaction: str | None) -> str:
    return (f"{substance} ({reaction})" if reaction else substance)[:300]


def _allergy_records(inp: PharmaInput) -> tuple[AllergyRecord, ...]:
    """AllergyList entries, plus allergens the conversation named that no AllergyList entry already covers."""
    out: list[AllergyRecord] = []
    known: set[str] = set()
    for a in sorted(inp.allergies, key=lambda i: (i.available_at_time, i.item_id)):
        for n, e in enumerate(a.entries):
            known.add(e.substance.strip().lower())
            out.append(AllergyRecord(text=_allergy_text(e.substance, e.reaction), evidence_ref=f"{a.item_id}#{n}"[:128],
                                     available_at_time=a.available_at_time, provenance=a.provenance[:256],
                                     version=a.version[:64]))
    for fact in inp.facts:
        if fact["kind"] != "allergens" or fact["state"] != "KNOWN" or not isinstance(fact["value"], (list, tuple)):
            continue
        for n, name in enumerate(fact["value"]):
            if isinstance(name, str) and name.strip() and name.strip().lower() not in known:
                known.add(name.strip().lower())
                out.append(AllergyRecord(
                    text=name.strip()[:300], evidence_ref=f"conversation:allergens#{n}",
                    available_at_time=fact["available_at_time"], provenance="casegraph.reader_text",
                    version="1"))
    return tuple(out)


def _conversation_sources(inp: PharmaInput) -> tuple[MedSource, ...]:
    """Medications the patient named in the conversation (Reader:Text ``current_medications``, KNOWN) as
    ``patient_reported`` sources: each keeps its conversation evidence ref and available_at_time. An explicit empty
    list ("takes none") adds no source; UNKNOWN/REFUSED/unparseable facts are reported by the executor, not read."""
    return tuple(
        MedSource(source_type="patient_reported", evidence_ref=m.ref, available_at_time=m.fact["available_at_time"],
                  provenance="casegraph.reader_text", version="1", entries=tuple(MedEntry(text=n) for n in m.names))
        for m in parse_medication_facts(inp.facts) if m.names
    )


def build_med_snapshot(inp: PharmaInput, patient_ref: str) -> MedSnapshot:
    sources = tuple(_source(m) for m in sorted(inp.lists, key=lambda i: (i.available_at_time, i.item_id)))
    sources += _conversation_sources(inp)
    return MedSnapshot(patient_ref=patient_ref[:128], as_of=inp.T, data_class=DataClass(inp.data_class),
                       sources=sources, allergies=_allergy_records(inp))


def _run_id(snapshot: MedSnapshot) -> str:
    """Deterministic run id (S5 would otherwise draw a random one): the same snapshot gives the same output."""
    return hashlib.sha256(snapshot.model_dump_json().encode("utf-8")).hexdigest()[:16]


def _check(check: str, medication: str, missing: tuple[str, ...], read: tuple[str, ...], fired: bool | None
           ) -> MedicationCheck:
    return MedicationCheck(
        medication=medication[:200] or "*", check=check, missing_inputs=missing,
        evaluated_on=read if not missing else (), fired=fired if not missing else None,
        status=screening_status([not missing], missing, allow_partial=False), label=S5_LABEL,
    )


def to_graph_output(run: dict[str, Any]) -> tuple[tuple[MedicationCheck, ...], tuple[MedicationIssue, ...]]:
    """S5 run record -> (checks, issues). Gaps S5 reported become ``not_evaluated`` checks."""
    issues = tuple(
        MedicationIssue(
            kind=i["type"], medication=(", ".join(i["ingredients"]) or "unknown")[:200], message=i["phrasing"]["text"],
            rule_id=i["rule_id"], severity=i["severity"], severity_rank=i["severity_rank"],
            ingredients=tuple(i["ingredients"]), conflicting_sources=tuple(i["conflicting_sources"]),
            field=i.get("field"), unverifiable=i["unverifiable"], issue_id=i["issue_id"],
            phrasing_source=i["phrasing"]["source"],
        )
        for i in run["issues"]
    )
    read = tuple(sorted({r["evidence_ref"] for r in run["extraction"] if r["status"] == "ok"}))
    checks: list[MedicationCheck] = [_check("s5_rules", "*", () if read else ("MedicationList",), read,
                                            bool(run["issues"]))]
    for n in run["notices"]:
        ref = n["evidence_ref"] or n["source_type"] or "?"
        miss = {"source_unreadable": f"MedicationList.readable@{ref}", "unrecognised_drug": f"formulary@{ref}",
                "allergy_unmapped": f"allergen_mapping@{ref}", "source_missing": f"MedicationList.{ref}"}[n["type"]]
        checks.append(_check(n["type"], n.get("raw_span") or "*", (miss,), (), None))
    for reason, count in sorted(run["unchecked_by_reason"].items()):
        if count:
            checks.append(_check("comparison_unchecked", reason, (f"comparison_unchecked:{reason}={count}",), (), None))
    return tuple(checks), issues


def run_s5(inp: PharmaInput) -> tuple[tuple[MedicationCheck, ...], tuple[MedicationIssue, ...]]:
    """The Pharma hook (api 2): build the S5 snapshot at T, reconcile through the node's gateway, map the result."""
    snapshot = build_med_snapshot(inp, inp.lists[0].patient_ref if inp.lists else "unknown")
    run = reconcile(snapshot, inp.invoke, "rules_plus_model", run_id=_run_id(snapshot))
    return to_graph_output(run)


def reconcile_direct(snapshot: MedSnapshot, invoke: Callable) -> dict[str, Any]:
    """The same S5 call without the graph (for parity checks): same deterministic run id."""
    return reconcile(snapshot, invoke, "rules_plus_model", run_id=_run_id(snapshot))


register_pharma_provider(S5_PHARMA_VERSION, run_s5, label=S5_LABEL, api=2)

__all__ = ["S5_LABEL", "build_med_snapshot", "entry_text", "issue_signature", "reconcile_direct", "run_s5",
           "to_graph_output"]
