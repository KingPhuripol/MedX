"""S9R-A02..A06, A15: explicit, scope-bound Tier-3/4 approval records in docs/DECISIONS.md.

All approval fixtures live in tmp_path; the real docs/DECISIONS.md is only read (never written).
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys

import pytest

from research.manifest_validation import (APPROVAL_SCHEMA_PATH, DECISIONS_PATH, approval_sha256, load_decision_log,
                                          parse_decision_log, validate_manifest)
from research.train import launcher, models

from .conftest import CONFIGS, REPO_ROOT, load_json

BASE = REPO_ROOT / "research" / "manifests" / "smoke-s3-lora-qwen3.8-27b.json"
HEADING = "2026-10-01 — Approve smoke-s3 LoRA scale-up (fixture only)"
OTHER_HEADING = "2026-10-02 — Unrelated decision (fixture only)"
RESET_HEADING = "2026-09-26 — Reset to Proposal v8"
OWNER = "project owner"


def _manifest(tier=3, gpus=8, minutes=600, gpu_hours=80.0, cost=640.0, heading=HEADING, approver=OWNER, date="2026-10-01"):
    m = copy.deepcopy(load_json(BASE))
    m["run_tier"] = tier
    m["resources"].update(gpu_count=gpus, max_minutes=minutes, devices=f"{gpus}x NVIDIA B200 (team-controlled)")
    m["resources"]["budget"].update(gpu_hours=gpu_hours, cost_usd_max=cost)
    m["approval"] = {"decision_ref": heading, "approved_by": approver, "date": date,
                     "budget": f"{gpu_hours} GPU-hours, USD {cost}", "run_id": m["experiment_id"]}
    return m


def _record(m, *, sha=False, **over):
    rec = {"experiment_id": m["experiment_id"], "tier": m["run_tier"], "gpu_count": m["resources"]["gpu_count"],
           "max_minutes": m["resources"]["max_minutes"], "gpu_hours": m["resources"]["budget"]["gpu_hours"],
           "cost_usd_max": m["resources"]["budget"]["cost_usd_max"], "approved_by": m["approval"]["approved_by"],
           "date": m["approval"]["date"], "scope": "one controlled LoRA run on 8x B200, fixture only"}
    if sha:
        rec["manifest_sha256"] = approval_sha256(m)
    rec.update(over)
    return rec


def _block(rec) -> str:
    return "```approval\n" + json.dumps(rec, ensure_ascii=False, indent=2) + "\n```\n"


def _log(tmp_path, sections: list[tuple[str, str]]):
    text = "# Decisions\n\nDated approvals and material decisions.\n\n"
    text += "".join(f"## {heading}\n- **What:** fixture decision.\n\n{body}\n" for heading, body in sections)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "DECISIONS.md"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------------------ A02


def test_approval_record_parsing(tmp_path):
    m = _manifest()
    rec = _record(m)
    json_text = json.dumps(_record(m, experiment_id="prose-run"))
    text = (
        "# Decisions\n\n"
        f"## {HEADING}\n- approved in chat\n\n{_block(rec)}\n"
        f"The record below is prose, not a block: {json_text}\n\n"
        "<!--\n" + _block(_record(m, experiment_id="comment-run")) + "-->\n\n"
        "```json\n" + json.dumps(_record(m, experiment_id="json-fence-run")) + "\n```\n\n"
        "## Notes (undated)\n\n" + _block(_record(m, experiment_id="undated-run"))
    )
    log = parse_decision_log(text)
    assert [(b.section, b.record["experiment_id"]) for b in log.blocks] == [(HEADING, m["experiment_id"])]
    assert log.headings == {HEADING}
    schema = json.loads(APPROVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"experiment_id", "manifest_sha256", "tier", "gpu_count", "max_minutes",
                                         "gpu_hours", "cost_usd_max", "approved_by", "date", "scope"}
    assert set(schema["required"]) == set(schema["properties"]) - {"manifest_sha256"}


# ------------------------------------------------------------------------------------------------ A03


def _case_reset_heading_no_record(tmp_path):
    m = _manifest(heading=RESET_HEADING, date="2026-09-26")
    return m, [_log(tmp_path, [(RESET_HEADING, "- **Approved by:** project owner (chat, 2026-09-26).\n")])]


def _case_record_other_experiment(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path, [(HEADING, _block(_record(m, experiment_id="smoke-s3-lora-medgemma-27b-it")))])]


def _case_record_in_prose(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path, [(HEADING, "Approval: " + json.dumps(_record(m)) + "\n")])]


def _case_record_in_other_section(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path, [(HEADING, ""), (OTHER_HEADING, _block(_record(m, date="2026-10-02")))])]


def _case_tier_mismatch(tmp_path):
    m = _manifest(tier=4)
    return m, [_log(tmp_path, [(HEADING, _block(_record(m, sha=True, tier=3)))])]


def _case_gpu_count_exceeds(tmp_path):
    m = _manifest(gpus=8)
    return m, [_log(tmp_path, [(HEADING, _block(_record(m, gpu_count=4)))])]


def _case_minutes_exceed(tmp_path):
    m = _manifest(minutes=600)
    return m, [_log(tmp_path, [(HEADING, _block(_record(m, max_minutes=300)))])]


def _case_budget_exceeds(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path / "a", [(HEADING, _block(_record(m, gpu_hours=40.0)))]),
               _log(tmp_path / "b", [(HEADING, _block(_record(m, cost_usd_max=100.0)))])]


def _case_approver_mismatch(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path, [(HEADING, _block(_record(m, approved_by="advisor")))])]


def _case_agent_self_approval(tmp_path):
    variants = []
    for i, who in enumerate(("research-lead", "Claude", "Training Engineer", "builder bot")):
        m = _manifest(approver=who)
        variants.append((m, _log(tmp_path / str(i), [(HEADING, _block(_record(m)))])))
    return variants


def _case_date_mismatch(tmp_path):
    m = _manifest()
    m2 = _manifest(date="2026-10-02")
    return [(m, _log(tmp_path / "a", [(HEADING, _block(_record(m, date="2026-10-02")))])),
            (m2, _log(tmp_path / "b", [(HEADING, _block(_record(m2)))]))]


def _case_sha_mismatch_or_missing_tier4(tmp_path):
    m = _manifest(tier=4)
    return m, [_log(tmp_path / "a", [(HEADING, _block(_record(m)))]),
               _log(tmp_path / "b", [(HEADING, _block(_record(m, manifest_sha256="0" * 64)))])]


def _case_duplicate_record(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path / "a", [(HEADING, _block(_record(m))), (OTHER_HEADING, _block(_record(m, date="2026-10-02")))]),
               _log(tmp_path / "b", [(HEADING, _block(_record(m)) + "\n" + _block(_record(m)))])]


def _case_record_schema_invalid(tmp_path):
    m = _manifest()
    return m, [_log(tmp_path / "a", [(HEADING, _block(_record(m, gpus=8)))]),
               _log(tmp_path / "b", [(HEADING, _block(_record(m, tier="3")))])]


FORGERIES = {
    "reset_heading_no_record": (_case_reset_heading_no_record, "contains no fenced ```approval record"),
    "record_other_experiment": (_case_record_other_experiment, "approves only other experiments"),
    "record_in_prose": (_case_record_in_prose, "only in prose or a comment"),
    "record_in_other_section": (_case_record_in_other_section, "not under decision_ref"),
    "tier_mismatch": (_case_tier_mismatch, "approval record tier 3 != manifest run_tier 4"),
    "gpu_count_exceeds": (_case_gpu_count_exceeds, "resources.gpu_count 8 != approved gpu_count 4"),
    "minutes_exceed": (_case_minutes_exceed, "max_minutes 600 exceeds approved max_minutes 300"),
    "budget_exceeds": (_case_budget_exceeds, "exceeds approved"),
    "approver_mismatch": (_case_approver_mismatch, "!= record approved_by 'advisor'"),
    "agent_self_approval": (_case_agent_self_approval, "is an agent identity"),
    "date_mismatch": (_case_date_mismatch, "approval date mismatch"),
    "sha_mismatch_or_missing_tier4": (_case_sha_mismatch_or_missing_tier4, "manifest_sha256"),
    "duplicate_record": (_case_duplicate_record, "duplicate approval records"),
    "record_schema_invalid": (_case_record_schema_invalid, "approval record schema"),
}


def _variants(built):
    if isinstance(built, list):
        return built
    m, logs = built
    return [(m, log) for log in logs]


@pytest.mark.parametrize("case", list(FORGERIES))
def test_validator_rejects_forged_approval(case, tmp_path):
    build, message = FORGERIES[case]
    variants = _variants(build(tmp_path))
    assert variants
    for manifest, log in variants:
        errors = validate_manifest(manifest, decisions_path=log)
        assert errors, (case, log.read_text())
        assert all(message in e for e in errors), (case, errors)  # one specific reason, nothing incidental


def test_forgery_messages_are_distinct():
    messages = [msg for _, msg in FORGERIES.values()]
    assert len(set(messages)) == len(messages) == 14


def test_validator_rejects_real_reset_heading():
    """The HIGH finding: citing the real reset heading must not approve an 8-GPU run."""
    log = load_decision_log(DECISIONS_PATH)
    assert RESET_HEADING in log.headings
    for tier in (3, 4):
        m = _manifest(tier=tier, heading=RESET_HEADING, date="2026-09-26")
        errors = validate_manifest(m)
        assert any("contains no fenced ```approval record" in e for e in errors), errors


def test_no_committed_approval_records():
    """S9R-A15: this slice adds no approval record to the real log."""
    assert load_decision_log(DECISIONS_PATH).blocks == ()


# ------------------------------------------------------------------------------------------------ A04


@pytest.mark.parametrize("case", ["tier3_id", "tier3_sha", "tier4_sha"])
def test_validator_accepts_explicit_approval(case, tmp_path):
    m = _manifest(tier=4 if case == "tier4_sha" else 3)
    log = _log(tmp_path, [(OTHER_HEADING, _block(_record(_manifest(), experiment_id="another-run", date="2026-10-02"))),
                          (HEADING, _block(_record(m, sha=case.endswith("_sha"))))])
    assert validate_manifest(m, decisions_path=log) == []


def _pinned_tier4():
    m = _manifest(tier=4)
    m["code"]["revision"] = "a" * 40
    for ds in m["data"]["datasets"]:
        ds.update(dataset_version=f"{ds['name']}-v1", split_version="patient-split-v1")
    return m


def test_approval_sha_status_invariant(tmp_path):
    m = _pinned_tier4()
    log = _log(tmp_path, [(HEADING, _block(_record(m, sha=True)))])
    for status in ("planned", "approved", "running"):
        m["status"] = status
        assert validate_manifest(m, decisions_path=log) == [], status


def _set_gpus(m):
    m["resources"]["gpu_count"] = 4


def _set_config_sha(m):
    m["code"]["config_sha256"] = "1" * 64


def _set_split(m):
    m["data"]["datasets"][1]["split_version"] = "patient-split-v2"


@pytest.mark.parametrize("change", [_set_gpus, _set_config_sha, _set_split], ids=["gpu_count", "config_sha", "split_version"])
def test_approval_sha_binds_content(change, tmp_path):
    m = _pinned_tier4()
    log = _log(tmp_path, [(HEADING, _block(_record(m, sha=True)))])
    m["status"] = "approved"
    assert validate_manifest(m, decisions_path=log) == []
    change(m)
    errors = validate_manifest(m, decisions_path=log)
    assert any("manifest_sha256 does not match the manifest content" in e for e in errors), errors


# ------------------------------------------------------------------------------------------------ A06


def test_approval_sha_cli(tmp_path):
    paths = [REPO_ROOT / "research" / "manifests" / "dryrun-s3.json", tmp_path / "tier4.json"]
    paths[1].write_text(json.dumps(_manifest(tier=4), ensure_ascii=False), encoding="utf-8")
    digests = []
    for path in paths:
        out = subprocess.run([sys.executable, "scripts/validate_manifest.py", "--approval-sha", str(path)], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr
        digest = out.stdout.strip()
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
        assert digest == approval_sha256(load_json(path))
        digests.append(digest)
    assert digests[0] != digests[1]


# ------------------------------------------------------------------------------------------------ A05


def test_launcher_rejects_forged_approval(tmp_path, monkeypatch, capsys):
    built = []
    monkeypatch.setattr(models, "build_model", lambda *a, **k: built.append(a) or pytest.fail("model built"))
    m = _manifest(tier=3, heading=RESET_HEADING, date="2026-09-26")
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    out_root = tmp_path / "out"
    rc = launcher.main(["--config", str(CONFIGS["stage3"]), "--manifest", str(path), "--output-root", str(out_root)])
    assert rc == launcher.EXIT_INVALID == 2
    assert built == []
    assert not out_root.exists()
    assert "contains no fenced ```approval record" in capsys.readouterr().err
