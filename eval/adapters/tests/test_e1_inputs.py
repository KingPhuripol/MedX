"""E1-A03: model inputs are snapshot-only and time-valid."""

from __future__ import annotations

import builtins
import io
import json
import pathlib
from pathlib import Path

import pytest

from eval.adapters import inputs, pipeline, voice
from eval.adapters.inputs import InputIntegrityError, t
from eval.jsonio import canonical_bytes

from .conftest import hand_case


def _spy(monkeypatch) -> list[str]:
    seen: list[str] = []
    real_open, real_io_open = builtins.open, io.open
    real_read_text, real_read_bytes, real_path_open = pathlib.Path.read_text, pathlib.Path.read_bytes, pathlib.Path.open

    def rec(p):
        seen.append(str(p))

    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (rec(f), real_open(f, *a, **k))[1])
    monkeypatch.setattr(io, "open", lambda f, *a, **k: (rec(f), real_io_open(f, *a, **k))[1])
    monkeypatch.setattr(pathlib.Path, "read_text", lambda self, *a, **k: (rec(self), real_read_text(self, *a, **k))[1])
    monkeypatch.setattr(pathlib.Path, "read_bytes", lambda self: (rec(self), real_read_bytes(self))[1])
    monkeypatch.setattr(pathlib.Path, "open", lambda self, *a, **k: (rec(self), real_path_open(self, *a, **k))[1])
    return seen


def _forbidden(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith("journey.json") or "/gold/" in p.replace("\\", "/")]


def test_inputs_snapshot_only(ds, monkeypatch):
    seen = _spy(monkeypatch)
    cases = inputs.load_split(ds, "dev")
    assert cases and all(set(c.snapshots) == {"T1", "T2"} for c in cases)
    snaps = [p for p in seen if p.endswith(".json")]
    assert snaps and all(Path(p).name.startswith("snapshot_T") for p in snaps)
    seen.clear()
    outputs = pipeline.system_outputs(ds, "dev")  # the whole S3 + S4 system-output builder
    assert len(outputs) == len(cases)
    assert _forbidden(seen) == []
    assert any(Path(p).name.startswith("snapshot_T") for p in seen)


def _plant(ds: Path, split: str) -> int:
    n = 0
    for jp in sorted((ds / "inputs" / split).glob("*/journey.json")):
        j = json.loads(jp.read_text(encoding="utf-8"))
        for it in j["items"]:
            if it["data_type"] == "IntakeTranscript":
                for turn in it["turns"]:
                    if turn["speaker"] == "patient":
                        turn["text"] = "SENTINEL จู่ ๆ ก็หน้าเบี้ยวและเจ็บหน้าอกรุนแรงทันที"
            if it["data_type"] == "Vitals":
                it.update(spo2=70, rr=40, sbp=70, consciousness="U")
        jp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
        n += 1
    for gp in sorted((ds / "gold" / split).glob("*.json")):
        g = json.loads(gp.read_text(encoding="utf-8"))
        for d in g["decision_times"]:
            d["red_flags"] = [{"rule_id": "RF-FAST", "item_ids": ["SENTINEL"]}]
            d["target_department"] = "SENTINEL"
        gp.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
        n += 1
    return n


def test_planted_sentinel_no_effect(ds, ds_copy, dev_outputs):
    assert _plant(ds_copy, "dev") > 0
    planted = pipeline.system_outputs(ds_copy, "dev")
    before = b"".join(canonical_bytes(o) + b"\n" for o in dev_outputs)
    after = b"".join(canonical_bytes(o) + b"\n" for o in planted)
    assert before == after


def test_facts_time_valid(ds, dev_outputs):
    n_facts = n_turns = 0
    cases = {c.case_id: c for c in inputs.load_split(ds, "dev")}
    for o in dev_outputs:
        c = cases[o["case_id"]]
        T1 = t(c.snapshots["T1"]["as_of"])
        for f in o["voice"]["facts"].values():
            assert t(f["available_at_time"]) <= T1
        for _, _, start, end in voice.turn_windows(inputs.transcript(c.snapshots["T1"])):
            assert start <= end <= T1
            n_turns += 1
        for dp in o["decision_points"]:
            T = t(dp["T"])
            assert dp["T"] == c.snapshots[dp["dp"]]["as_of"]
            for f in dp["facts"]:
                assert t(f["available_at_time"]) <= T, (o["case_id"], dp["dp"], f)
                n_facts += 1
    assert n_facts > 500 and n_turns == 12 * len(dev_outputs)


def test_late_item_refused():
    c = hand_case("LATE", ["ปวดหัวค่ะ"], vitals={})
    snap = json.loads(json.dumps(c.snapshots["T1"]))
    snap["items"][1]["available_at_time"] = "2030-01-01T10:00:01+07:00"
    with pytest.raises(InputIntegrityError):
        inputs.check_time_valid(snap, "LATE")
