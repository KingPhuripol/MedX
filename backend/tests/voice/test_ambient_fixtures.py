"""V2A-A13: the 15 ambient fixtures validate and are faithful conversions of th_intake_NN."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

FIXTURE_DIR = Path(__file__).parent / "fixtures"
AMBIENT_DIR = FIXTURE_DIR / "ambient"
ASK_FIELDS = (
    "chief_complaint", "onset_duration", "severity", "allergy_status", "current_medications", "relevant_history",
)
UNCHANGED_KEYS = ("gold_facts", "answers_by_field", "gold_nurse_attention")


class _Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(pattern=r"^t\d{2}$")
    speaker: Literal["unknown"]
    text: str = Field(min_length=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime


class _Ambient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dialogue_id: str
    mode: Literal["ambient"]
    source_dialogue_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    synthetic: Literal[True]
    author: str = Field(min_length=1)
    scenario_tags: list[str]
    patient_ref: str = Field(pattern=r"^SYN-V2A-\d{2}$")
    turns: list[_Turn] = Field(min_length=2)
    gold_question_turns: dict[str, Literal[ASK_FIELDS]]  # type: ignore[valid-type]
    gold_facts: list[dict]
    answers_by_field: dict[str, list[str]]
    gold_nurse_attention: bool


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ambient_fixtures_schema_and_source():
    paths = sorted(AMBIENT_DIR.glob("th_ambient_*.json"))
    assert [p.name for p in paths] == [f"th_ambient_{i:02d}.json" for i in range(1, 16)]
    dev_questions: set[str] = set()
    heldout_questions: dict[str, set[str]] = {f: set() for f in ASK_FIELDS}
    for path in paths:
        raw = _load(path)
        fx = _Ambient.model_validate(raw)
        num = int(fx.dialogue_id[-2:])
        assert fx.dialogue_id == path.stem and fx.source_dialogue_id == f"th_intake_{num:02d}"
        src_path = FIXTURE_DIR / f"{fx.source_dialogue_id}.json"
        assert hashlib.sha256(src_path.read_bytes()).hexdigest() == fx.source_sha256
        src = _load(src_path)
        for key in UNCHANGED_KEYS:
            assert json.dumps(raw[key], ensure_ascii=False) == json.dumps(src[key], ensure_ascii=False), key
        assert fx.scenario_tags == src["scenario_tags"]
        assert ("heldout" in fx.scenario_tags) == (num >= 11)

        # Same turn ids and times; former agent turns are exactly the gold question turns; other text unchanged.
        assert [t.turn_id for t in fx.turns] == [t["turn_id"] for t in src["turns"]]
        prev: datetime | None = None
        for t, s in zip(fx.turns, src["turns"]):
            assert (t.started_at, t.ended_at) == (datetime.fromisoformat(s["started_at"].replace("Z", "+00:00")),
                                                  datetime.fromisoformat(s["ended_at"].replace("Z", "+00:00")))
            assert prev is None or t.started_at >= prev
            prev = t.ended_at
            if s["speaker"] == "agent":
                assert t.turn_id in fx.gold_question_turns
                if num >= 11:
                    heldout_questions[fx.gold_question_turns[t.turn_id]].add(t.text)
                else:
                    dev_questions.add(t.text)
            else:
                assert t.turn_id not in fx.gold_question_turns and t.text == s["text"]
        assert len(fx.gold_question_turns) == sum(1 for s in src["turns"] if s["speaker"] == "agent")

    # Held-out wording novelty: for every field, one held-out question never appears verbatim in dev.
    for field, texts in heldout_questions.items():
        assert any(q not in dev_questions for q in texts), field
