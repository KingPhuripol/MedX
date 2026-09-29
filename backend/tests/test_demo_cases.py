"""U7: fixture demo cases served by the V2 demo router, with the real engines run at request time."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from app.demo import case_engines
from app.demo.case_engines import FIXTURE_PATH, SYMPTOM_TEXT, fixture_cases
from app.triage import redflags

from .conftest import REPO_ROOT
from .test_demo_api import create_run

VIEW_ONLY = "เคสตัวอย่างสำหรับดูข้อมูล — ยังไม่เปิดให้ดำเนินการ"
SYNTH = Path(os.environ.get("SYNTH_V1_DIR", REPO_ROOT / "data" / "synthetic" / "v1"))
FORBIDDEN_KEY = re.compile(r"gold|expected|label|injected|injection|target_department|red_flags|near_miss|medication_issues", re.I)


def _walk(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path + (k,), k
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, path)


def _times(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("available_at_time", "timestamp") and isinstance(v, str):
                yield k, v
            yield from _times(v)
    elif isinstance(node, list):
        for v in node:
            yield from _times(v)


# ---- A4: the fixture holds no gold or eval keys, nothing after T, only train-split ids ----------------


def test_fixture_has_six_cases_and_provenance():
    doc = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(doc["cases"]) == 6
    prov = doc["provenance"]
    assert prov["split"] == "train" and prov["decision_point"] == "T2" and prov["data_class"] == "synthetic"
    assert prov["dataset_seed"] and prov["source_dataset"] == "data/synthetic/v1"
    assert [s["case_id"] for s in prov["selection"]] == [c["case_id"] for c in doc["cases"]]


def test_fixture_contains_no_gold_or_eval_keys():
    doc = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    bad = [key for _, key in _walk(doc["cases"]) if FORBIDDEN_KEY.search(key)]
    assert bad == []
    assert not re.search(r"g2-heldout", FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_has_no_item_after_decision_time():
    for case in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]:
        t = datetime.fromisoformat(case["decision_time"])
        late = [(k, v) for k, v in _times(case) if datetime.fromisoformat(v) > t]
        assert late == [], case["case_id"]
        for lab in case["labs"]:
            assert datetime.fromisoformat(lab["resulted_at"]) <= t


@pytest.mark.skipif(not (SYNTH / "splits.json").exists(), reason="data/synthetic/v1 not generated (set SYNTH_V1_DIR)")
def test_fixture_ids_are_train_split_only_and_export_is_reproducible(tmp_path):
    splits = json.loads((SYNTH / "splits.json").read_text())
    for case in fixture_cases().values():
        assert splits[case["patient_ref"]] == "train", case["case_id"]
        assert (SYNTH / "inputs" / "train" / case["case_id"]).is_dir()
    out = tmp_path / "cases.json"
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "export_demo_cases.py"), "--data", str(SYNTH), "--out", str(out)],
                   check=True, capture_output=True, env=os.environ | {"PYTHONPATH": f"{REPO_ROOT / 'backend'}:{REPO_ROOT}"})
    assert out.read_bytes() == FIXTURE_PATH.read_bytes()


def test_fixture_covers_the_required_paths():
    cases = list(fixture_cases().values())
    flags = {c["case_id"]: case_engines.run_redflags(c) for c in cases}
    assert any(f["alerts"] for f in flags.values())  # vitals red flag
    assert any(c["allergies"] for c in cases)  # allergy recorded
    assert any(c["allergies"] is None for c in cases)  # null allergy status kept as null
    assert any(v.get(k) is None for c in cases for v in c["vitals"] for k in ("hr", "rr", "sbp", "dbp", "spo2", "temp_c"))


# ---- A1/A2 -----------------------------------------------------------------------------------------


def test_queue_lists_seven_cases_with_red_flags_first(client, login):
    run_id = create_run(client, login)
    rows = client.get(f"/api/demo/v1/runs/{run_id}/queue").json()["cases"]
    assert len(rows) == 7 and rows[0]["case_id"] == "SYN-2026-0017" and rows[0]["view_only"] is False
    levels = [r["safety_level"] for r in rows]
    assert levels == sorted(levels, key=lambda x: x != "critical")  # every critical row precedes every other row
    assert sum(r["view_only"] for r in rows) == 6
    for r in rows:
        if r["view_only"]:
            flags = case_engines.run_redflags(fixture_cases()[r["case_id"]])
            assert r["alert_count"] == len(flags["alerts"]) and r["not_evaluated_count"] == len(flags["not_evaluated"])


def test_every_fixture_case_matches_engine_output(client, login):
    run_id = create_run(client, login)
    for case_id, fx in fixture_cases().items():
        body = client.get(f"/api/demo/v1/runs/{run_id}/cases/{case_id}").json()
        flags = case_engines.run_redflags(fx)
        assert body["view_only"] is True and body["view_only_label"] == VIEW_ONLY
        assert body["engines"]["red_flag"] == flags
        assert body["engines"]["red_flag"]["ruleset_version"] == redflags.RULESET_VERSION
        assert (body["safety"]["level"] == "critical") == bool(flags["alerts"])
        meds = client.get(f"/api/demo/v1/runs/{run_id}/cases/{case_id}/medications").json()
        run = case_engines.run_pharma(fx, client.app.state.engine)
        assert len(meds["discrepancies"]) == len(run["issues"]) == body["engines"]["pharma"]["issue_count"]
        assert body["engines"]["pharma"]["rules_version"] == run["rules_version"]
        assert all(d["status"] == "pending" for d in meds["discrepancies"])
        assert len(client.get(f"/api/demo/v1/runs/{run_id}/cases/{case_id}/timeline").json()["items"]) >= 4


def test_no_alert_never_says_safe_and_symptom_rules_are_not_evaluated(client, login):
    run_id = create_run(client, login)
    quiet = next(c for c, fx in fixture_cases().items() if not case_engines.run_redflags(fx)["alerts"])
    body = client.get(f"/api/demo/v1/runs/{run_id}/cases/{quiet}").json()
    text = body["safety"]["label"] + body["safety"]["detail"]
    assert "ปลอดภัย" not in text and "safe" not in text.lower() and body["safety"]["level"] == "none"
    flags = body["engines"]["red_flag"]
    ids = {n["rule_id"] for n in flags["not_evaluated"]}
    assert {"RF-CHEST", "RF-STROKE", "RF-THUNDER"} <= ids  # symptom rules: unknown, never negative
    assert flags["not_evaluated_text"] == SYMPTOM_TEXT
    assert all(n["reason_th"] for n in flags["not_evaluated"])


def test_null_allergy_and_null_vital_stay_null_in_the_api(client, login):
    run_id = create_run(client, login)
    rows = {c: client.get(f"/api/demo/v1/runs/{run_id}/cases/{c}").json() for c in fixture_cases()}
    assert any(b["allergies"] is None for b in rows.values())
    assert any(v["temp_c"] is None for b in rows.values() for v in b["vitals"])


def test_unknown_case_is_404_everywhere(client, login):
    run_id = create_run(client, login)
    for suffix in ("", "/timeline", "/medications"):
        assert client.get(f"/api/demo/v1/runs/{run_id}/cases/SYNE-0007{suffix}").status_code == 404  # a dev-split id
        assert client.get(f"/api/demo/v1/runs/{run_id}/cases/nope{suffix}").status_code == 404


def test_fixture_cases_are_view_only_and_0017_is_unchanged(client, login):
    run_id = create_run(client, login)
    fx = next(iter(fixture_cases()))
    # workflow actions exist only for SYN-2026-0017's tasks and med review
    assert client.post(f"/api/demo/v1/tasks/{fx}/claim", json={"run_id": run_id, "version": 1}).status_code == 404
    assert client.post("/api/demo/v1/medication-reviews/" + fx + "-i01/confirm", json={"run_id": run_id, "version": 1}).status_code in (403, 404)
    orig = client.get(f"/api/demo/v1/runs/{run_id}/cases/SYN-2026-0017").json()
    assert orig["view_only"] is False and "engines" not in orig and orig["safety"]["label"] == "พบสัญญาณที่ต้องประเมินเร่งด่วน"
    assert client.get(f"/api/demo/v1/runs/{run_id}/cases/SYN-2026-0017/medications").json()["discrepancies"][0]["review_id"] == "med-review-017"
