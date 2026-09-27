"""Arm B of the slice i2 comparison (PROPOSAL Table 3.2 "Case Graph"): one prompt over the whole snapshot.

One gateway call per decision point, task ``casegraph.single_prompt.v1``, with the whole snapshot serialized.
Its deterministic mock handler composes the **same registered handler versions** Arm A uses (S3
``voice.intake_extract``, ``voice.symptom_extract.v1`` and the S4 ``triage.department.v1`` baseline rank), called
in-process through the one mock registry, with the same Reader:Text reading logic (``read_clinical_text``) and
the same S4 Case adapter (latest wins). It has no graph-only steps: no Red-flag screen, no required-input gate,
no freshness check and no Human Checkpoint. It therefore produces no red-flag output by design.

MOCK — not clinical. System Evaluation on synthetic data — not clinical performance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.gateway import MOCK_LABEL, mock_tasks
from app.triage import department
from app.voice.models import EXTRACT_TASK

from . import reader_text, triage_bridge
from .data import dump_evidence, load_evidence, most_restrictive

TASK = "casegraph.single_prompt.v1"
VERSION = "sp-1.0"
COMPOSED_TASKS = (EXTRACT_TASK, reader_text.SYMPTOM_TASK, department.TASK)


def handler_versions() -> dict[str, str]:
    """The registered handler version of every composed task (the manifest records it for both arms)."""
    registered = mock_tasks.registered()
    return {t: registered[t] for t in COMPOSED_TASKS}


def _direct(task: str, inputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Call a registered mock handler in-process (inside the single prompt: no extra gateway call)."""
    found = mock_tasks.lookup(task)
    if found is None:
        raise reader_text.ReaderError(f"{task}: no registered handler")
    fn, version = found
    return {**fn(dict(inputs)), "label": MOCK_LABEL}, f"mock-0.1.0+{version}"


def request_inputs(patient_ref: str, T: datetime, items: list[Any]) -> dict[str, Any]:
    """The whole snapshot, serialized: the one prompt's input."""
    return {"snapshot": {"patient_ref": patient_ref, "T": T.isoformat(), "items": dump_evidence(items)}}


def answer(inputs: dict[str, Any]) -> dict[str, Any]:
    """Pure, offline handler: ``{"ranking": [...], "handler_versions": {...}}``."""
    snap = inputs.get("snapshot") or {}
    items = load_evidence(snap.get("items") or [])
    versions = handler_versions()
    if not items:
        return {"ranking": [], "handler_versions": versions}
    T = datetime.fromisoformat(snap["T"])
    intake, facts, _, _ = reader_text.read_clinical_text(items, T, _direct)
    findings = {"facts": [f.model_dump(mode="json") for f in facts],
                "intake": [v.model_dump(mode="json") for v in intake]}
    adapted = triage_bridge.build_case(snap["patient_ref"], T, items, [("single_prompt", findings, VERSION)],
                                       data_class=most_restrictive([i.data_class for i in items]))
    request = department.build_request(adapted.snapshot())
    output, _ = _direct(department.TASK, request.inputs)
    return {"ranking": output["ranking"], "handler_versions": versions}


mock_tasks.register(TASK, answer, version=VERSION)
