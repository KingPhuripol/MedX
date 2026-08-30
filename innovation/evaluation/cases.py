"""Loading the frozen synthetic case set.

See `tests/fixtures/cases/README.md`: `expected_minimum_urgency` is an author-declared
property of a synthetic fixture, written before any result was measured. It is not
clinical ground truth and no clinical claim may rest on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from innovation.frontdoor.intake import IntakeItem

CASE_DIR = Path(__file__).resolve().parents[2] / "tests/fixtures/cases"


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    scenario: str
    description: str
    journey_id: str
    encounter_start: datetime
    decision_time: datetime
    intake: tuple[IntakeItem, ...]
    appended: tuple[IntakeItem, ...]
    expected_minimum_urgency: str
    provider_behaviour: str
    notes: str | None = None


def _item(raw: dict) -> IntakeItem:
    return IntakeItem(
        information_type=raw["information_type"],
        state=raw["state"],
        value=raw.get("value"),
        observed_at=datetime.fromisoformat(raw["observed_at"]) if raw.get("observed_at") else None,
        available_at_time=(
            datetime.fromisoformat(raw["available_at_time"]) if raw.get("available_at_time") else None
        ),
    )


def load_cases(directory: Path | None = None) -> tuple[EvaluationCase, ...]:
    """Load every case, in a stable order so a run is reproducible."""
    directory = directory or CASE_DIR
    cases = []
    for path in sorted(directory.glob("case-*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        cases.append(
            EvaluationCase(
                case_id=raw["case_id"],
                scenario=raw["scenario"],
                description=raw["description"],
                journey_id=raw["journey_id"],
                encounter_start=datetime.fromisoformat(raw["encounter_start"]),
                decision_time=datetime.fromisoformat(raw["decision_time"]),
                intake=tuple(_item(i) for i in raw["intake"]),
                appended=tuple(_item(i) for i in raw["appended"]),
                expected_minimum_urgency=raw["expected_minimum_urgency"],
                provider_behaviour=raw["provider_behaviour"],
                notes=raw.get("notes"),
            )
        )
    return tuple(cases)
