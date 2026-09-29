"""S3-A03: the 15 synthetic Thai intake dialogues are valid and cover every required scenario."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIELDS = (
    "chief_complaint", "onset_duration", "severity", "allergy_status", "allergens",
    "current_medications", "relevant_history",
)
ASKED_FIELDS = tuple(f for f in FIELDS if f != "allergens")
REQUIRED_TAGS = {
    "allergy_none_denial": 1,
    "allergy_present": 1,
    "allergy_unknown": 1,
    "allergy_refused": 1,
    "meds_none": 1,
    "meds_multi_codeswitch": 1,
    "relative_speaker": 1,
    "correction": 1,
    "thai_number_words": 1,
    "volunteered_before_asked": 1,
    "field_never_answered": 1,
    "nurse_attention": 2,
}


class _Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(pattern=r"^t\d{2}$")
    speaker: Literal["agent", "patient", "relative", "nurse"]
    text: str = Field(min_length=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime


class _GoldFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal[FIELDS]  # type: ignore[valid-type]
    state: Literal["KNOWN", "UNKNOWN", "REFUSED"]
    value: str | int | None
    items: list[str] | None
    span_turn_ids: list[str] = Field(min_length=1)


class _Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dialogue_id: str
    synthetic: Literal[True]
    author: str = Field(min_length=1)
    scenario_tags: list[str]
    patient_ref: str = Field(pattern=r"^SYN-S3-\d{2}$")
    turns: list[_Turn] = Field(min_length=2)
    gold_facts: list[_GoldFact]
    answers_by_field: dict[str, list[str]]
    gold_nurse_attention: bool


def load_fixtures() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURE_DIR.glob("th_intake_*.json"))]


def test_fixtures_schema_and_coverage():
    paths = sorted(FIXTURE_DIR.glob("th_intake_*.json"))
    assert [p.name for p in paths] == [f"th_intake_{i:02d}.json" for i in range(1, 16)]
    tags: Counter[str] = Counter()
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fx = _Fixture.model_validate(raw)
        assert fx.dialogue_id == path.stem
        assert fx.patient_ref.startswith("SYN-")
        num = int(fx.dialogue_id[-2:])
        assert ("heldout" in fx.scenario_tags) == (num >= 11), fx.dialogue_id
        tags.update(set(fx.scenario_tags))
        assert fx.gold_nurse_attention == ("nurse_attention" in fx.scenario_tags)

        by_id = {t.turn_id: t for t in fx.turns}
        assert len(by_id) == len(fx.turns), "duplicate turn ids"
        prev_end: datetime | None = None
        for t in fx.turns:
            assert t.ended_at >= t.started_at
            if prev_end is not None:
                assert t.started_at >= prev_end, f"{fx.dialogue_id}/{t.turn_id} overlaps"
            prev_end = t.ended_at

        seen_fields = set()
        for g in fx.gold_facts:
            assert g.field not in seen_fields, f"{fx.dialogue_id}: duplicate gold {g.field}"
            seen_fields.add(g.field)
            for tid in g.span_turn_ids:
                assert tid in by_id and by_id[tid].speaker != "agent", f"{fx.dialogue_id}: bad span {tid}"
            is_list = g.field in {"allergens", "current_medications", "relevant_history"}
            if g.state == "KNOWN":
                assert (g.items is not None) if is_list else (g.value is not None)
            else:
                assert g.value is None and g.items is None

        # Every non-agent turn is reachable by the scripted-patient simulator exactly once.
        assert set(fx.answers_by_field) <= set(ASKED_FIELDS)
        listed = [tid for tids in fx.answers_by_field.values() for tid in tids]
        assert len(listed) == len(set(listed))
        non_agent = {t.turn_id for t in fx.turns if t.speaker != "agent"}
        assert set(listed) == non_agent, fx.dialogue_id

    for tag, minimum in REQUIRED_TAGS.items():
        assert tags[tag] >= minimum, f"coverage tag {tag}: {tags[tag]} < {minimum}"
    assert tags["heldout"] == 5 and tags["dev"] == 10
