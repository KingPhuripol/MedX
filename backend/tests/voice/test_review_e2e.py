"""V2D-D9: the v2c mobile submitFlow end to end (login -> ambient start -> ASR turns -> GET -> finish -> review)."""

from __future__ import annotations

from .review_helpers import RESPONSE_KEYS, Intake


def _flow(client, app, login, finish_twice: bool) -> None:
    login("nurse1")
    it = Intake(client, app, 1)  # start {mode:"ambient"}, turns speaker "unknown", source "asr", asr_model
    body = it.payload()  # decisions from GET via the test-local port of SPEC 3.3
    it.finish(200)
    if finish_twice:
        it.finish(409)  # submitFlow treats 409 as "already finished"
    r = client.post(f"/api/voice/sessions/{it.sid}/review", json=body)
    assert r.status_code == 201 and set(r.json()) == RESPONSE_KEYS, r.text
    retry = client.post(f"/api/voice/sessions/{it.sid}/review", json=body)
    assert (retry.status_code, retry.json()["detail"]) == (409, "review_exists")


def test_mobile_submit_flow(client, app, login):
    _flow(client, app, login, finish_twice=False)


def test_mobile_submit_flow_finish_409_variant(client, app, login):
    _flow(client, app, login, finish_twice=True)
