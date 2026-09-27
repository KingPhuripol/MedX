"""Append-only persistence for assessments and reviews (INSERT and SELECT only)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, select

from ..db import triage_assessments, triage_reviews
from .models import TriageAssessment


def insert_assessment(engine: Engine, a: TriageAssessment) -> None:
    with engine.begin() as conn:
        conn.execute(
            triage_assessments.insert().values(
                assessment_id=a.assessment_id,
                case_ref=a.case_ref,
                as_of=a.as_of.isoformat(),
                created_at=a.created_at,
                created_by=a.created_by,
                ruleset_version=a.ruleset_version,
                payload_json=a.model_dump_json(),
            )
        )


def get_assessment(engine: Engine, assessment_id: str) -> TriageAssessment | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(triage_assessments.c.payload_json).where(triage_assessments.c.assessment_id == assessment_id)
        ).first()
    return TriageAssessment.model_validate_json(row.payload_json) if row else None


def insert_review(engine: Engine, **values: Any) -> None:
    """Raises ``IntegrityError`` if the assessment already has a review (unique constraint)."""
    values["acknowledged_alert_ids_json"] = json.dumps(values.pop("acknowledged_alert_ids"))
    with engine.begin() as conn:
        conn.execute(triage_reviews.insert().values(**values))


def get_review(engine: Engine, assessment_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(select(triage_reviews).where(triage_reviews.c.assessment_id == assessment_id)).first()
    return _review_dict(row) if row else None


def newest_assessment_for_case(engine: Engine, case_ref: str) -> TriageAssessment | None:
    """The assessment that reflects the most recent information for a case.

    Ordered by clinical time ``as_of`` (parsed, so UTC offsets compare correctly), then ``created_at``.
    Review insert order is deliberately ignored: reviewing an older snapshot never makes it current.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(triage_assessments.c.payload_json).where(triage_assessments.c.case_ref == case_ref)
        ).all()
    items = [TriageAssessment.model_validate_json(r.payload_json) for r in rows]
    return max(items, key=lambda a: (a.as_of, a.created_at), default=None)


def _review_dict(row: Any) -> dict[str, Any]:
    d = dict(row._mapping)
    d["acknowledged_alert_ids"] = json.loads(d.pop("acknowledged_alert_ids_json"))
    d.pop("reason", None)  # reason text is kept in the table, not echoed in API views
    return d
