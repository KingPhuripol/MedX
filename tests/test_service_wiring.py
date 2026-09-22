"""Deployment wiring and the defects it hid.

`build_default_service()` and the environment variables that configure it had no test at
all, which is how a broken `FRONT_DOOR_AUDIT_LOG` survived: every test constructed the
pieces directly and never went through the path a deployment uses. These tests go through
that path.

Each test here corresponds to a defect found on 2026-09-02. They exist so the defects
cannot come back quietly.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from innovation.frontdoor import FrontDoorService
from innovation.gateway import ModelGateway
from innovation.gateway.audit import AuditLog, AuditRecord
from innovation.gateway.providers import MockProvider
from innovation.gateway.registry import is_external
from innovation.store import SqliteStore
from shared.contracts import PatientJourney

ROOT = Path(__file__).resolve().parents[1]
LATER = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)


@pytest.fixture
def journey() -> PatientJourney:
    return PatientJourney.model_validate(
        json.loads((ROOT / "tests/fixtures/patient_journey/valid.json").read_text())
    )


# ------------------------------------------------------------------ D1: audit log path


def test_the_service_builds_with_every_environment_variable_set(tmp_path, monkeypatch):
    """`FRONT_DOOR_AUDIT_LOG` could not be set at all.

    `api/app.py` imported `pathlib.Path` and then `fastapi.Path`, and the second won. The
    JSONL audit sink — one of the two durable destinations the design depends on — had
    therefore never worked through the API, and the app raised on startup rather than
    degrading.
    """
    module = importlib.import_module("innovation.api.app")
    monkeypatch.setenv("FRONT_DOOR_DB", str(tmp_path / "front_door.sqlite3"))
    monkeypatch.setenv("FRONT_DOOR_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    service = module.build_default_service()

    assert service.store is not None
    assert isinstance(service, FrontDoorService)


def test_the_jsonl_audit_sink_actually_receives_records(tmp_path, monkeypatch, journey):
    module = importlib.import_module("innovation.api.app")
    audit_path = tmp_path / "nested" / "audit.jsonl"
    monkeypatch.setenv("FRONT_DOOR_AUDIT_LOG", str(audit_path))
    monkeypatch.delenv("FRONT_DOOR_DB", raising=False)

    service = module.build_default_service()
    service.assess(journey, LATER)

    assert audit_path.exists(), "the JSONL sink was configured and wrote nothing"
    lines = [json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()]
    assert lines and lines[0]["journey_id"] == journey.journey_id


# --------------------------------------------------- D3/D7: undeclared dependencies


def test_every_import_the_app_needs_is_declared():
    """A clean `pip install -r requirements.txt` must produce an importable app.

    `httpx`, `jinja2` and `python-multipart` were imported and declared nowhere, so a
    fresh environment got an app that failed at `import innovation.ui`.
    """
    declared = (ROOT / "requirements.txt").read_text().lower()
    for package in ("httpx", "jinja2", "python-multipart", "fastapi", "pydantic", "uvicorn"):
        assert package in declared, f"{package} is imported by the app but not declared"


def test_the_app_imports_in_a_subprocess_with_no_test_fixtures_loaded():
    """Import-time failures — `Form(...)` without python-multipart is one — do not show up
    once something else in the session has already imported the module."""
    result = subprocess.run(
        [sys.executable, "-c", "import innovation.api.app; import innovation.ui.routes"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


# ------------------------------------------------- D6: the external-provider gate


def test_a_provider_registered_as_external_is_treated_as_external(monkeypatch):
    """There were two unrelated objects named `EXTERNAL_PROVIDERS`.

    The gateway's authorization check keyed off a hardcoded frozenset in `gateway.py`
    while adapters register in `registry.py`. An adapter registered under any name not in
    that frozenset was silently treated as local: no approval required, restricted
    classifications accepted, content free to leave the process.
    """
    from innovation.gateway import registry

    assert is_external("a_name_nobody_registered") is False

    class Vendor(MockProvider):
        name = "some_vendor"

    monkeypatch.setitem(registry.EXTERNAL_PROVIDERS, "some_vendor", Vendor)
    assert is_external("some_vendor") is True, (
        "registering an adapter as external must make the authorization check treat it "
        "as external, without also editing a second list"
    )


def test_a_contract_declared_external_name_is_external_before_any_adapter_exists():
    """`ProviderName` declares `external_prototype` in the contract. It has to be external
    from that moment, not from the moment someone writes the class."""
    assert is_external("external_prototype") is True


# --------------------------------------- D2: re-assessment used to erase human reviews


def test_re_assessing_the_same_question_keeps_the_human_review(journey):
    """Confirming a recommendation and re-assessing at the same decision time used to
    revert it to unconfirmed: the recommendation id was derived from journey and decision
    time only, and `assess` overwrote the entry with a fresh one whose reviews were empty.
    `/recommendations/{id}/effective` flipped from 200 back to 409 with nothing raised."""
    service = FrontDoorService(ModelGateway(MockProvider()))
    first = service.assess(journey, LATER)
    service.review(first.recommendation_id, reviewer_id="clinician-01", action="CONFIRM")
    assert service.get(first.recommendation_id).effective is True

    again = service.assess(journey, LATER)

    assert again.recommendation_id == first.recommendation_id
    assert again.effective is True, "a confirmed recommendation was silently unconfirmed"
    assert len(again.reviews) == 1
    assert len(service.history(journey.journey_id)) == 1, "history gained a duplicate"


def test_new_evidence_at_the_same_decision_time_is_a_new_question(journey):
    """The other half of the same fix: identity includes the snapshot checksum, so a
    genuinely different evidence set is a different recommendation rather than a silent
    replacement of the old one."""
    service = FrontDoorService(ModelGateway(MockProvider()))
    early = service.assess(journey, datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc))
    later = service.assess(journey, LATER)

    assert early.snapshot_checksum != later.snapshot_checksum
    assert early.recommendation_id != later.recommendation_id


# ------------------------------------------------- D4: the audit trail and restarts


def test_the_audit_trail_survives_a_restart(tmp_path, journey):
    """`AuditLog.find` scanned an in-memory list that rehydration never repopulated, so
    after a restart the audit endpoint answered 404 for every earlier call — while the
    rows sat in the database and `SqliteStore.audit_for` went uncalled."""
    db = tmp_path / "front_door.sqlite3"

    store = SqliteStore(db)
    service = FrontDoorService(
        ModelGateway(MockProvider(), audit_log=AuditLog(store=store)), store=store
    )
    recommendation = service.assess(journey, LATER)
    request_id = recommendation.response.request_id
    store.close()

    reopened = SqliteStore(db)
    restarted = FrontDoorService(
        ModelGateway(MockProvider(), audit_log=AuditLog(store=reopened)), store=reopened
    )

    trail = restarted.gateway.audit.find(request_id)
    assert trail, "the audit trail did not survive the restart"
    assert trail[0].request_id == request_id
    assert isinstance(trail[0], AuditRecord)
    reopened.close()


def test_a_review_is_durable_with_its_reviewer(tmp_path, journey):
    """The reviewer's identity used to be written by mutating a frozen dataclass in
    memory and was never persisted, so the durable row said `reviewer_id: null` forever —
    which is exactly the field `CLAUDE.md` requires the audit trail to carry."""
    db = tmp_path / "front_door.sqlite3"
    store = SqliteStore(db)
    service = FrontDoorService(
        ModelGateway(MockProvider(), audit_log=AuditLog(store=store)), store=store
    )
    recommendation = service.assess(journey, LATER)
    service.review(recommendation.recommendation_id, reviewer_id="clinician-42", action="CONFIRM")
    request_id = recommendation.response.request_id
    store.close()

    reopened = SqliteStore(db)
    trail = AuditLog(store=reopened).find(request_id)
    assert "clinician-42" in {r.reviewer_id for r in trail}
    reopened.close()


def test_a_stray_env_file_does_not_configure_the_suite(tmp_path, monkeypatch):
    from innovation.config import Settings

    (tmp_path / ".env").write_text("FRONT_DOOR_DB=leaked.sqlite3\n")
    monkeypatch.chdir(tmp_path)
    assert Settings().db is None

