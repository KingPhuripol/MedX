"""Append-only persistence for care assessments and physician reviews (INSERT and SELECT only)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, select

from ..db import care_assessments, care_reviews
from .models import CareAssessment


def insert_assessment(engine: Engine, a: CareAssessment) -> None:
    with engine.begin() as conn:
        conn.execute(care_assessments.insert().values(
            assessment_id=a.assessment_id, case_id=a.case_id, decision_point=a.decision_point, as_of=a.as_of,
            created_at=a.created_at, created_by=a.created_by, rules_version=a.rules_version,
            payload_json=a.model_dump_json()))


def get_assessment(engine: Engine, assessment_id: str) -> CareAssessment | None:
    with engine.connect() as conn:
        row = conn.execute(select(care_assessments.c.payload_json)
                           .where(care_assessments.c.assessment_id == assessment_id)).first()
    return CareAssessment.model_validate_json(row.payload_json) if row else None


def newest_assessment_for_case(engine: Engine, case_id: str) -> CareAssessment | None:
    """Newest by clinical time ``as_of`` (parsed), then ``created_at``; review order never matters."""
    with engine.connect() as conn:
        rows = conn.execute(select(care_assessments.c.payload_json)
                            .where(care_assessments.c.case_id == case_id)).all()
    items = [CareAssessment.model_validate_json(r.payload_json) for r in rows]
    return max(items, key=lambda a: (datetime.fromisoformat(a.as_of), a.created_at), default=None)


def insert_review(engine: Engine, **values: Any) -> None:
    """Raises ``IntegrityError`` if the assessment already has a review (unique constraint)."""
    values["acknowledged_alert_ids_json"] = json.dumps(values.pop("acknowledged_alert_ids"))
    final = values.pop("final_codes")
    values["final_codes_json"] = None if final is None else json.dumps(final, sort_keys=True)
    values["screening_acknowledged"] = int(values["screening_acknowledged"])
    with engine.begin() as conn:
        conn.execute(care_reviews.insert().values(**values))


def get_review(engine: Engine, assessment_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(select(care_reviews).where(care_reviews.c.assessment_id == assessment_id)).first()
    if row is None:
        return None
    d = dict(row._mapping)
    d["acknowledged_alert_ids"] = json.loads(d.pop("acknowledged_alert_ids_json"))
    raw = d.pop("final_codes_json")
    d["final_codes"] = None if raw is None else json.loads(raw)
    d["screening_acknowledged"] = bool(d["screening_acknowledged"])
    d.pop("reason", None)  # reason text stays in the table, never echoed in API views or audit
    return d
