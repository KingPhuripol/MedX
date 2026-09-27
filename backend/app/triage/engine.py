"""Assessment pipeline: snapshot -> red flags (first, independent) -> department via gateway."""

from __future__ import annotations

import uuid
from datetime import datetime

from ..audit import utc_now_iso
from . import department, redflags
from .models import Case, Snapshot, TriageAssessment


def assess(case: Case, as_of: datetime, invoke: department.InvokeFn, *, actor_id: int) -> TriageAssessment:
    snap = Snapshot(case, as_of)
    # Red-flag Node runs first and never sees gateway output, so a model cannot suppress an alert.
    alerts, not_evaluable = redflags.evaluate(snap)
    suggestion = department.suggest(snap, invoke)
    return TriageAssessment(
        assessment_id=uuid.uuid4().hex,
        case_ref=case.case_ref,
        as_of=as_of,
        ruleset_version=redflags.RULESET_VERSION,
        alerts=alerts,
        not_evaluable=not_evaluable,
        escalation_required=bool(alerts),
        department=suggestion,
        conflicts=snap.conflicts,  # i2 (C4): same-timestamp conflicts, shown at review
        created_at=utc_now_iso(),
        created_by=actor_id,
    )
