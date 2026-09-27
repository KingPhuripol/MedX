"""Slice i2, condition C3 (S4 HIGH): the assess endpoint bounds ``as_of`` by the case evidence (I2-A11).

Synthetic S4 author fixtures only. Research prototype — not for clinical use.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.triage.fixtures import load_entries

from .helpers import AS_OF_SKEW

BY_REF = {e.case.case_ref: e for e in load_entries()}
REF = "SYN-S4-002"
ONE_S = timedelta(seconds=1)


def _bounds(ref=REF):
    times = [f.available_at_time for f in BY_REF[ref].case.facts]
    return min(times), max(times)


def _assess(client, as_of, ref=REF):
    return client.post(f"/api/triage/cases/{ref}/assess", json={"as_of": as_of.isoformat()})


def test_as_of_ceiling(client, login):
    login("nurse1")
    _, latest = _bounds()
    ok = _assess(client, latest + AS_OF_SKEW)
    assert ok.status_code == 201, ok.text
    late = _assess(client, latest + AS_OF_SKEW + ONE_S)
    assert (late.status_code, late.json()["detail"]) == (422, "as_of_beyond_evidence")


def test_as_of_floor(client, login):
    login("nurse1")
    earliest, _ = _bounds()
    ok = _assess(client, earliest)
    assert ok.status_code == 201, ok.text
    early = _assess(client, earliest - ONE_S)
    assert (early.status_code, early.json()["detail"]) == (422, "as_of_before_evidence")


@pytest.mark.parametrize("which,reason", [("late", "as_of_beyond_evidence"), ("early", "as_of_before_evidence")])
def test_as_of_rejection_audited(client, login, audit_rows, which, reason):
    login("nurse1")
    earliest, latest = _bounds()
    as_of = latest + AS_OF_SKEW + ONE_S if which == "late" else earliest - ONE_S
    before = len(audit_rows())
    resp = _assess(client, as_of)
    assert resp.status_code == 422
    rows = audit_rows()[before:]
    assert [(r["action"], r["outcome"], r["details"]["reason"]) for r in rows] == [
        ("triage.assess.rejected", "denied", reason)
    ]
    d = rows[0]["details"]
    assert d["status"] == 422 and d["skew_s"] == AS_OF_SKEW.total_seconds()
    assert d["latest_evidence"] == latest.isoformat() and d["earliest_evidence"] == earliest.isoformat()


def test_as_of_skew_is_configurable(settings, tmp_path):
    """D-I2-2: the skew is a setting (``TRIAGE_AS_OF_SKEW_S``), 300 s by default."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.seed import seed_dev_users

    from ..conftest import PASSWORDS

    assert settings.triage_as_of_skew_s == 300.0
    app = create_app(replace(settings, triage_as_of_skew_s=0.0))
    seed_dev_users(app.state.engine)
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"username": "nurse1", "password": PASSWORDS["nurse1"]})
        _, latest = _bounds()
        assert _assess(c, latest).status_code == 201
        assert _assess(c, latest + ONE_S).status_code == 422
