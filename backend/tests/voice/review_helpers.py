"""Slice v2d test helpers: drive an ambient session through the API, then build the nurse's review.

Dev ambient fixtures 01-10 only (11-15 are v2a held-out and are never read here). Synthetic data, offline.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.db import triage_assessments
from app.voice.db import voice_review_decisions, voice_reviews

from .helpers import FIXTURE_DIR, Clock

ASK = ("chief_complaint", "onset_duration", "severity", "allergy_status", "current_medications", "relevant_history")
RESPONSE_KEYS = {
    "review_id", "session_id", "patient_ref", "case_ref", "submitted_at", "red_flag", "triage_path",
    "evidence_item_ids", "confirmed_fields", "missing_fields", "department_suggestion",
}
SUGGESTION_KEYS = {
    "status", "assessment_id", "as_of", "reason", "top3", "missing_information", "alert_rule_ids",
    "escalation_required", "label",
}
UNKNOWN_TH = "ผู้ป่วยไม่ทราบ"
REFUSED_TH = "ผู้ป่วยไม่ตอบ"
NONE_TH = "ไม่มีประวัติแพ้ยา"
UNCLEAR_TH = "ข้อมูลแพ้ยายังไม่ชัด ตรวจในหน้าตรวจทาน"


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def ambient_fixture(n: int) -> dict:
    assert 1 <= n <= 10, "held-out ambient fixtures 11-15 are not used by v2d tests"
    return json.loads((FIXTURE_DIR / "ambient" / f"th_ambient_{n:02d}.json").read_text(encoding="utf-8"))


# ---- test-local port of SPEC 3.3 (mirrors mobile/lib/voice.ts rows()/knownValue()), from the GET payload ----


def _latest(facts: list[dict], field: str) -> dict | None:
    return next((f for f in reversed(facts) if f["field"] == field), None)


def _text(f: dict | None) -> str:
    if not f:
        return ""
    if isinstance(f.get("value_text"), str) and f["value_text"].strip():
        return f["value_text"].strip()
    if isinstance(f["value"], list):
        return ", ".join(f["value"])
    return "" if f["value"] is None else str(f["value"])


def display(get: dict) -> dict[str, str | None]:
    s, facts = get["session"], get["facts"]
    statuses = {x["field"]: x["status"] for x in get["field_statuses"]}
    out: dict[str, str | None] = {}
    for field in ASK:
        st = statuses[field]
        if st == "MISSING":
            out[field] = None
        elif st == "UNKNOWN":
            out[field] = UNKNOWN_TH
        elif st == "REFUSED":
            out[field] = REFUSED_TH
        elif field != "allergy_status":
            out[field] = _text(_latest(facts, field)) or "ยังไม่มี"
        else:
            f, al = _latest(facts, "allergy_status"), _latest(facts, "allergens")
            if f and f["state"] == "KNOWN" and f["value"] == "none" and not s["allergy_conflict"] \
                    and not s["extraction_error"]:
                out[field] = NONE_TH
            elif s["allergy_conflict"] or not f or f["value"] != "present":
                out[field] = UNCLEAR_TH
            else:
                t = (_text(al) if al and al["state"] == "KNOWN" else "") or _text(f)
                out[field] = UNCLEAR_TH if not t or re.search("ไม่แพ้|ไม่มีประวัติแพ้", t) else t
    return out


def build_decisions(get: dict, overrides: dict[str, tuple[str, str | None]] | None = None) -> list[dict]:
    """Default: confirm every captured row, ``unknown`` on every MISSING row. ``overrides``: field -> (action, value)."""
    shown = display(get)
    out = []
    for field in ASK:
        action, value = (overrides or {}).get(field) or (
            ("unknown", None) if shown[field] is None else ("confirm", shown[field]))
        original = shown[field] if action in ("confirm", "edit", "reject") else None
        out.append({"field": field, "action": action, "value": value, "original": original})
    return out


class Intake:
    """One ambient session of a dev fixture, driven through /api/voice with a fixed server clock."""

    def __init__(self, client, app, n: int | dict, patient_ref: str | None = None, shift: timedelta = timedelta(0)):
        self.c, self.app = client, app
        self.fx = n if isinstance(n, dict) else ambient_fixture(n)
        self.ref = patient_ref or self.fx["patient_ref"]
        self.shift = shift
        self.clock = Clock(dt(self.fx["turns"][0]["started_at"]) + shift - timedelta(seconds=1))
        app.state.voice_clock = self.clock
        resp = client.post("/api/voice/sessions", json={"patient_ref": self.ref, "data_class": "synthetic",
                                                        "mode": "ambient"})
        assert resp.status_code == 201, resp.text
        self.sid = resp.json()["session"]["session_id"]
        for t in self.fx["turns"]:
            start, end = dt(t["started_at"]) + shift, dt(t["ended_at"]) + shift
            self.clock.t = end + timedelta(milliseconds=100)
            r = client.post(f"/api/voice/sessions/{self.sid}/turns", json={
                "speaker": "unknown", "text": t["text"], "started_at": start.isoformat(), "ended_at": end.isoformat(),
                "source": "asr", "asr_model": "fixture-text"})
            assert r.status_code == 200, r.text
        self.first_start = dt(self.fx["turns"][0]["started_at"]) + shift
        self.last_end = dt(self.fx["turns"][-1]["ended_at"]) + shift
        self.clock.t = self.last_end + timedelta(seconds=30)

    def get(self) -> dict:
        r = self.c.get(f"/api/voice/sessions/{self.sid}")
        assert r.status_code == 200, r.text
        return r.json()

    def finish(self, expect: int = 200):
        r = self.c.post(f"/api/voice/sessions/{self.sid}/finish")
        assert r.status_code == expect, r.text
        return r

    def payload(self, overrides=None, **changes) -> dict:
        get = self.get()
        body = {
            "session_id": self.sid, "patient_ref": self.ref, "decisions": build_decisions(get, overrides),
            "consent_acknowledged_at": (self.first_start - timedelta(seconds=5)).isoformat(),
            "red_flag_acknowledged_at": self.last_end.isoformat() if get["session"]["nurse_attention"] else None,
        }
        body.update(changes)
        return body

    def review(self, body: dict | None = None, expect: int | None = 201, overrides=None):
        r = self.c.post(f"/api/voice/sessions/{self.sid}/review", json=body if body is not None else self.payload(overrides))
        if expect is not None:
            assert r.status_code == expect, r.text
        return r

    def submit(self, overrides=None) -> dict:
        self.finish()
        return self.review(overrides=overrides).json()


def counts(app) -> tuple[int, int, int]:
    with app.state.engine.connect() as conn:
        return tuple(conn.execute(select(func.count()).select_from(t)).scalar_one()  # type: ignore[return-value]
                     for t in (voice_reviews, voice_review_decisions, triage_assessments))


def stored_evidence(app, review_id: str) -> list[dict]:
    with app.state.engine.connect() as conn:
        row = conn.execute(select(voice_reviews.c.evidence_json).where(voice_reviews.c.review_id == review_id)).one()
    return json.loads(row.evidence_json)


def stored_case_facts(app, review_id: str) -> list[dict]:
    with app.state.engine.connect() as conn:
        row = conn.execute(select(voice_reviews.c.case_facts_json).where(voice_reviews.c.review_id == review_id)).one()
    return json.loads(row.case_facts_json)


def voice_facts_of(app, review_id: str) -> dict[str, dict]:
    facts = next(e for e in stored_evidence(app, review_id) if e["data_type"] == "VoiceIntakeFacts")["facts"]
    return {f["field"]: f for f in facts}


def hand_turns(ref: str, texts: list[str], day: int = 20) -> dict:
    """A hand-authored ambient dialogue (synthetic): 3 s turns, 2 s apart."""
    base = datetime.fromisoformat(f"2026-01-{day:02d}T02:00:00+00:00")
    turns = [{"turn_id": f"h{i}", "text": t, "started_at": (base + timedelta(seconds=5 * i)).isoformat(),
              "ended_at": (base + timedelta(seconds=5 * i + 3)).isoformat()} for i, t in enumerate(texts)]
    return {"patient_ref": ref, "turns": turns}


ALLERGY_CONFLICT_TURNS = ["มาด้วยอาการอะไรคะ", "ปวดหัวค่ะ", "แพ้ยาอะไรไหมคะ", "แพ้เพนิซิลลินค่ะ",
                          "แพ้ยาอะไรไหมคะ", "ไม่แพ้ค่ะ"]
