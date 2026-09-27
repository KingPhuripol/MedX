"""Builders for small synthetic cases used by unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.triage.models import Case, Snapshot

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
SCREEN = (
    "acute_chest_pain", "sudden_facial_droop", "sudden_limb_weakness", "sudden_speech_disturbance",
    "sudden_vision_disturbance", "thunderclap_headache", "allergen_exposure", "airway_breathing_compromise",
    "suicidal_ideation", "self_harm", "hematemesis", "melena", "fever", "neck_stiffness",
    "non_blanching_rash", "abdominal_pain", "vaginal_bleeding",
)
BASE = {
    "age": 40, "sex": "male", "chief_complaint": "synthetic complaint", "onset_duration": "1 day",
    "vital.hr": 80, "vital.rr": 16, "vital.sbp": 125, "vital.dbp": 78, "vital.spo2": 98, "vital.temp_c": 36.8,
    "vital.avpu": "A", "vital.new_confusion": False, "vital.capillary_glucose_mg_dl": 100,
} | {f"symptom.{s}": "absent" for s in SCREEN}
DROP = object()


def fact(case_ref: str, i: int, kind: str, value, minutes: int = 0) -> dict:
    return {
        "fact_id": f"{case_ref}-F{i:02d}", "kind": kind, "value": value,
        "available_at_time": (T0 + timedelta(minutes=minutes)).isoformat(),
        "source": "unit-test", "provenance": "synthetic unit test", "version": "t1",
    }


def make_case(overrides: dict | None = None, *, base: dict | None = None, case_ref: str = "UT-1",
              late: list[tuple[str, object, int]] | None = None) -> Case:
    values = (BASE if base is None else base) | (overrides or {})
    facts = [fact(case_ref, i + 1, k, v) for i, (k, v) in enumerate(values.items()) if v is not DROP]
    for j, (kind, value, minutes) in enumerate(late or []):
        facts.append(fact(case_ref, 90 + j, kind, value, minutes))
    return Case(case_ref=case_ref, data_class="synthetic", facts=facts)


def snap(overrides: dict | None = None, **kw) -> Snapshot:
    return Snapshot(make_case(overrides, **kw), T0 + timedelta(hours=1))
