"""Slice i2, condition C6 (int MEDIUM): one mock task registry and the MOCK label rule (I2-A03)."""

from __future__ import annotations

import ast

import pytest

import casegraph.single_prompt  # noqa: F401  (registers casegraph.single_prompt.v1)
import app.triage.department  # noqa: F401  (registers triage.department.v1)
import app.voice  # noqa: F401  (registers voice.intake_extract, voice.symptom_extract.v1)
from app.config import Settings
from app.gateway import MOCK_LABEL, GatewayRequest, build_provider, mock_tasks
from app.gateway.contract import canonical_sha256

from .conftest import REPO_ROOT

SAMPLE_INPUTS = {
    "voice.intake_extract": {"turns": [{"turn_id": "t1", "speaker": "patient", "text": "มีไข้ค่ะ", "ended_at": "x"}],
                             "last_asked_field": None},
    "voice.symptom_extract.v1": {"turns": [{"turn_index": 1, "speaker": "patient", "text": "เจ็บหน้าอกขึ้นมาทันที",
                                            "spoken_at": "2030-01-01T08:00:00+07:00"}]},
    "triage.department.v1": {"chief_complaint": {"fact_id": "X-1", "text": "ear pain"}, "symptoms_present": []},
}


def test_single_mock_registry():
    """Exactly one handler table; the old per-adapter table and register_task/register_mock_task are gone."""
    import sys

    import app.gateway as gw

    # The mock adapter module, reached through the gateway's public MockProvider: adapters stay private to
    # the gateway package (test_provider_isolation), so this test never names the adapter path.
    mock_adapter = sys.modules[gw.MockProvider.__module__]

    assert not hasattr(gw, "register_mock_task") and not hasattr(mock_adapter, "register_task")
    assert not hasattr(mock_adapter, "_TASK_HANDLERS")
    tables = []
    for path in sorted((REPO_ROOT / "backend" / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("register_task", "register_mock_task"):
                tables.append(f"{path}:{node.name}")
            if isinstance(node, (ast.AnnAssign, ast.Assign)):
                targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                for t in targets:
                    if isinstance(t, ast.Name) and t.id in ("_TASK_HANDLERS", "_REGISTRY"):
                        tables.append(f"{path.relative_to(REPO_ROOT)}:{t.id}")
    assert tables == ["backend/app/gateway/mock_tasks.py:_REGISTRY"]
    registered = mock_tasks.registered()
    for task in ("voice.intake_extract", "voice.symptom_extract.v1", "triage.department.v1",
                 "casegraph.single_prompt.v1"):
        assert task in registered, task


def test_reregister_different_handler_raises():
    def a(inputs):
        return {"n": 1}

    def b(inputs):
        return {"n": 2}

    mock_tasks.register("unit.i2.v1", a, version="t")
    mock_tasks.register("unit.i2.v1", a, version="t")  # idempotent
    with pytest.raises(ValueError):
        mock_tasks.register("unit.i2.v1", b, version="t")
    with pytest.raises(ValueError):
        mock_tasks.register("unit.i2.v1", a, version="t2")


def test_mock_label_every_task():
    provider = build_provider("mock", Settings())
    for task, version in mock_tasks.registered().items():
        if task.startswith("unit.") or task.startswith("test."):
            continue
        inputs = SAMPLE_INPUTS.get(task, {"snapshot": {"items": []}})
        req = GatewayRequest(task=task, inputs=inputs, data_class="synthetic")
        res = provider.invoke(req, canonical_sha256(req))
        assert res.status == "ok", task
        assert res.output["label"] == MOCK_LABEL, task
        assert res.model_version == f"mock-0.1.0+{version}", task
    req = GatewayRequest(task="unregistered.echo", inputs={}, data_class="synthetic")
    res = provider.invoke(req, canonical_sha256(req))
    assert res.output["label"] == MOCK_LABEL and res.model_version == "mock-0.1.0"
