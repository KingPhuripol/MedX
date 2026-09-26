"""S3-A08 no advice, S3-A10 fail-safe extraction, S3-A11 nurse-attention interrupt."""

import re
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.gateway import ProviderResult, build_provider
from app.config import Settings
from app.voice.db import voice_facts
from app.voice.policy import ATTENTION_SINGLE, nurse_attention_hit
from app.voice.utterances_th import UTTERANCES_TH

from ..conftest import REPO_ROOT
from .helpers import StubProvider, VoiceAPI, dict_keys_deep, load_fixtures, ok, simulate_all

FORBIDDEN_TH = ("ควรกิน", "ให้กินยา", "ทานยา", "แนะนำให้", "ไม่เป็นอันตราย", "ไม่ต้องกังวล", "น่าจะเป็นโรค", "วินิจฉัย")
FORBIDDEN_EN = re.compile(r"you should|take (?:a|this|your) medic|diagnos|prescrib|treat", re.IGNORECASE)
ADVICE = "ควรกินยาพาราทุก 4 ชั่วโมง ไม่ต้องกังวล you should take this medicine"


def _advice_hits(text: str) -> list[str]:
    hits = [p for p in FORBIDDEN_TH if p in text]
    if m := FORBIDDEN_EN.search(text):
        hits.append(m.group(0))
    return hits


def _web_intake_files() -> list[Path]:
    files = sorted((REPO_ROOT / "web" / "app" / "nurse" / "intake").rglob("*.ts*"))
    files += sorted((REPO_ROOT / "web" / "components" / "voice").rglob("*.ts*"))
    return files


def _agent_texts(runs) -> list[tuple[str, str]]:
    out = []
    for run in runs:
        for t in run.finish["evidence"][-1]["payload"]["turns"]:
            if t["speaker"] == "agent":
                out.append((t["turn_id"], t["text"]))
    return out


def test_no_patient_facing_advice_scan(app):
    utter_file = REPO_ROOT / "backend" / "app" / "voice" / "utterances_th.py"
    assert _advice_hits(utter_file.read_text(encoding="utf-8")) == []
    runs = simulate_all(app)
    agent = _agent_texts(runs)
    assert len(agent) >= 60
    assert [(tid, _advice_hits(text)) for tid, text in agent if _advice_hits(text)] == []
    web = _web_intake_files()
    assert web, "nurse intake page files not found"
    assert [(str(p), _advice_hits(p.read_text(encoding="utf-8"))) for p in web if _advice_hits(p.read_text())] == []


def test_utterances_from_allowlist_only(app):
    allow = set(UTTERANCES_TH.values())
    runs = simulate_all(app)
    for run in runs:
        for d in run.decisions:
            a = d["action"]
            assert UTTERANCES_TH[a["utterance_id"]] == a["utterance_th"]
    assert all(text in allow for _, text in _agent_texts(runs))


def _inject(req):
    """Advice text in every output field; spans cite the real patient turn so only content checks stop it."""
    tid = [t for t in req.inputs["turns"] if t["speaker"] != "agent"][-1]["turn_id"]
    fact = {"field": "chief_complaint", "state": "KNOWN", "value": ADVICE, "value_text": ADVICE,
            "span_turn_ids": [tid]}
    return ProviderResult(status="ok", model_version=ADVICE, output={
        "label": ADVICE, "extractor": ADVICE, "facts": [fact], "text": ADVICE, "utterance_th": ADVICE,
    })


def _grounded_inject(req):
    """The patient's own words contain advice text; the model echoes it into a grounded value_text."""
    tid = [t for t in req.inputs["turns"] if t["speaker"] != "agent"][-1]["turn_id"]
    fact = {"field": "chief_complaint", "state": "KNOWN", "value": "fever", "value_text": ADVICE,
            "span_turn_ids": [tid]}
    return ok({"label": "x", "extractor": "inject", "facts": [fact], "utterance_th": ADVICE})


@pytest.mark.parametrize("fn", [_inject, _grounded_inject], ids=["ungrounded", "grounded"])
def test_model_text_never_spoken(client, login, app, fn):
    app.state.provider = StubProvider(fn)
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    responses = [api.turn(ADVICE).json(), api.turn("มีไข้ค่ะ " + ADVICE).json()]
    for r in responses:
        assert ADVICE not in r["next_action"]["utterance_th"]
        assert r["next_action"]["utterance_th"] in UTTERANCES_TH.values()
    state = api.get().json()
    assert ADVICE not in state["next_action"]["utterance_th"]
    for t in state["turns"]:
        if t["speaker"] == "agent":
            assert ADVICE not in t["text"] and t["text"] in UTTERANCES_TH.values()


def _bad_span(req):
    agent = [t for t in req.inputs["turns"] if t["speaker"] == "agent"][-1]["turn_id"]
    return ok({"label": "x", "extractor": "stub", "facts": [
        {"field": "chief_complaint", "state": "KNOWN", "value": "fever", "value_text": "ไข้", "span_turn_ids": [agent]},
    ]})


def _unknown_span(req):
    return ok({"label": "x", "extractor": "stub", "facts": [
        {"field": "chief_complaint", "state": "KNOWN", "value": "fever", "value_text": "ไข้", "span_turn_ids": ["nope"]},
    ]})


def _bad_state(req):
    tid = req.inputs["turns"][-1]["turn_id"]
    return ok({"label": "x", "extractor": "stub", "facts": [
        {"field": "chief_complaint", "state": "MAYBE", "value": "fever", "value_text": "ไข้", "span_turn_ids": [tid]},
    ]})


def _bad_field(req):
    tid = req.inputs["turns"][-1]["turn_id"]
    return ok({"label": "x", "extractor": "stub", "facts": [
        {"field": "diagnosis", "state": "KNOWN", "value": "fever", "value_text": "ไข้", "span_turn_ids": [tid]},
    ]})


FAILURES = {
    "error": lambda req: ProviderResult(status="error", model_version="stub-1", reason="provider_timeout"),
    "rejected": lambda req: ProviderResult(status="rejected", model_version="stub-1", reason="policy"),
    "schema_invalid": lambda req: ok({"facts": "not-a-list"}),
    "bad_span": _bad_span,
    "bad_state": _bad_state,
    "unknown_span": _unknown_span,
    "unknown_field": _bad_field,
    "exception": lambda req: (_ for _ in ()).throw(RuntimeError("boom internals")),
}


@pytest.mark.parametrize("case", list(FAILURES))
def test_extraction_fail_safe(client, login, app, case):
    app.state.provider = StubProvider(FAILURES[case])
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    resp = api.turn("มีไข้ค่ะ")
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_facts"] == []
    assert body["extraction_error"] is True and body["session"]["extraction_error"] is True
    assert (body["next_action"]["action"], body["next_action"]["reason"]) == ("handoff", "extraction_unavailable")
    assert "boom internals" not in resp.text
    with app.state.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(voice_facts)).scalar_one() == 0
    # Sticky: later turns keep handing off; nothing crashes (no 5xx) and GET agrees.
    assert api.turn("สองวันค่ะ").json()["next_action"]["reason"] == "extraction_unavailable"
    assert api.get().json()["next_action"]["reason"] == "extraction_unavailable"
    assert api.finish().json()["handoff_reason"] == "extraction_unavailable"


UNIT_ATTENTION = ["เมื่อเช้าหมดสติไปค่ะ", "ลูกชักค่ะ", "เลือดออกมากไม่หยุดเลย", "ช่วงนี้อยากตายค่ะ", "คิดจะฆ่าตัวตาย"]


def test_nurse_attention_interrupt(client, login, app):
    login("nurse1")
    # Unit cases: every listed single phrase and the chest-pain + breathlessness combination.
    for phrase in ATTENTION_SINGLE:
        assert nurse_attention_hit(f"คุณยาย{phrase}ค่ะ")
    assert not nurse_attention_hit("เจ็บหน้าอกค่ะ") and not nurse_attention_hit("ไอค่ะ")
    assert nurse_attention_hit("หายใจไม่ออกด้วย", ["เจ็บหน้าอกค่ะ"])
    api = VoiceAPI(client, app)
    for i, text in enumerate(UNIT_ATTENTION):
        api.start(ref=f"SYN-S3-ATT{i}")
        body = api.turn(text).json()
        assert (body["next_action"]["action"], body["next_action"]["reason"]) == ("handoff", "nurse_attention_phrase")
        assert body["nurse_attention"] is True
        keys = {k.lower() for k in dict_keys_deep(body)}
        assert not any(w in k for k in keys for w in ("urgency", "triage", "department", "esi", "acuity"))
    api.start(ref="SYN-S3-COMBO")
    assert api.turn("เจ็บหน้าอกค่ะ").json()["next_action"]["action"] == "ask"
    assert api.turn("หายใจไม่ออกด้วยค่ะ").json()["next_action"]["reason"] == "nurse_attention_phrase"

    # Fixture runs: the interrupt fires on the same turn that contains the phrase, and only then.
    fixtures = load_fixtures()
    runs = simulate_all(app, fixtures)
    for fx, run in zip(fixtures, runs):
        prior: list[str] = []
        hit_any = False
        for post in run.posts:
            text = post["body"].text
            hit = nurse_attention_hit(text, prior)
            prior.append(text)
            reason = post["response"]["next_action"]["reason"]
            if hit:
                hit_any = True
                assert reason == "nurse_attention_phrase", fx["dialogue_id"]
            elif not hit_any:
                assert reason != "nurse_attention_phrase", fx["dialogue_id"]
        assert hit_any == fx["gold_nurse_attention"], fx["dialogue_id"]


def test_interrupt_independent_of_gateway(client, login, app):
    app.state.provider = StubProvider(FAILURES["error"])
    login("nurse1")
    api = VoiceAPI(client, app)
    for i, text in enumerate(UNIT_ATTENTION):
        api.start(ref=f"SYN-S3-IND{i}")
        body = api.turn(text).json()
        assert body["extraction_error"] is True
        assert body["next_action"]["reason"] == "nurse_attention_phrase"
    app.state.provider = build_provider("mock", Settings())
