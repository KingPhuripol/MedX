"""S9-A01, A03, A04, A05: selection matrix provenance, benchmark hygiene, pre-declared rubric."""

from __future__ import annotations

import copy
import re
import subprocess
from datetime import date
from urllib.parse import urlparse

from research.base_model import render as R

from .conftest import REPO_ROOT

COLUMNS = ["param_count", "architecture", "vision_encoder", "image_tokens", "context_length", "license",
           "finetune_permitted", "redistribution", "hf_repo", "medical_benchmarks", "eval_overlap", "support_3d",
           "library_support"]


def _allowed(url: str, allow: dict[str, list[str]]) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and u.netloc in allow and any(u.path.startswith(p) for p in allow[u.netloc])


def _iso(d: str) -> bool:
    try:
        date.fromisoformat(d)
        return True
    except ValueError:
        return False


def _all_sources(cell: dict) -> list[tuple[str, str]]:
    out = [(cell["source_url"], cell["retrieved_on"])]
    out += [(s["source_url"], s["retrieved_on"]) for s in cell.get("additional_sources", [])]
    return out


def test_matrix_every_cell_cited():
    m = R.load_matrix()
    allow = m["source_domain_allowlist"]
    assert [c["id"] for c in m["columns"]] == COLUMNS
    assert {r["candidate_id"] for r in m["rows"]} == {"medgemma-27b-it", "qwen3.8-27b", "lingshu-32b"}
    bad, n = [], 0
    for row in m["rows"]:
        assert set(row["cells"]) == set(COLUMNS), row["candidate_id"]
        for col, cell in row["cells"].items():
            n += 1
            assert set(cell) >= {"value", "source_url", "retrieved_on", "note"}, (row["candidate_id"], col)
            if cell["value"] is None:
                assert cell["note"], f"{row['candidate_id']}.{col}: null value needs a note"
            for url, when in _all_sources(cell):
                if not (_allowed(url, allow) and _iso(when)):
                    bad.append((row["candidate_id"], col, url, when))
    assert n == 39
    assert bad == []


def test_benchmark_cells_complete():
    m = R.load_matrix()
    allow = m["source_domain_allowlist"]
    keys = {"benchmark", "split", "metric", "value", "setting", "comparable_group", "source_url", "retrieved_on"}
    for row in m["rows"]:
        cell = row["cells"]["medical_benchmarks"]
        assert isinstance(cell["value"], list)
        if not cell["value"]:
            assert "not reported" in cell["note"].lower()
        for e in cell["value"]:
            assert set(e) >= keys, e
            assert all(e[k] not in (None, "") for k in keys), e
            assert isinstance(e["value"], (int, float))
            assert _allowed(e["source_url"], allow) and _iso(e["retrieved_on"]), e


def _fixture_two_groups() -> dict:
    m = copy.deepcopy(R.load_matrix())
    rows = {r["candidate_id"]: r for r in m["rows"]}

    def e(bench, value, group):
        return {"benchmark": bench, "split": "test", "metric": "accuracy", "value": value, "setting": "s",
                "comparable_group": group, "source_url": "https://arxiv.org/abs/0000.00000", "retrieved_on": "2026-09-26"}

    rows["medgemma-27b-it"]["cells"]["medical_benchmarks"]["value"] = [e("X", 50.0, "G1"), e("Y", 99.0, "G2")]
    rows["qwen3.8-27b"]["cells"]["medical_benchmarks"]["value"] = [e("X", 60.0, "G1")]
    rows["lingshu-32b"]["cells"]["medical_benchmarks"]["value"] = [e("X", 70.0, "G2")]
    return m


def test_render_no_cross_group_ranking():
    m = _fixture_two_groups()
    ranked = R.rankings(m)
    # Only G1/X has two candidates in the same group; the G2 value for X (70.0) must not be ranked with G1.
    assert [(r["group"], r["benchmark"]) for r in ranked] == [("G1", "X")]
    assert [v for _, v in ranked[0]["order"]] == [60.0, 50.0]
    md = R.render(m)
    rank_lines = [ln for ln in md.splitlines() if ln.startswith("- [")]
    assert rank_lines == ["- [G1] X / accuracy / s: Qwen3.8-27B (Qwen/Qwen3.8-27B) (60.0) > "
                          "MedGemma 27B multimodal (google/medgemma-27b-it) (50.0)"]
    # Real matrix: every ranking stays inside one group.
    for r in R.rankings(R.load_matrix()):
        groups = {g for g, entries in R.benchmark_groups(R.load_matrix()).items()
                  for e in entries if e["candidate"] in {c for c, _ in r["order"]} and e["benchmark"] == r["benchmark"]}
        assert r["group"] in groups


def test_selection_matrix_md_regenerates():
    committed = (REPO_ROOT / "research" / "base_model" / "SELECTION_MATRIX.md").read_text(encoding="utf-8")
    assert R.render(R.load_matrix()) == committed


def _first_commit_time(path: str) -> int | None:
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ct", "--", path], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=30, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(out[-1]) if out else None


def test_rubric_predeclared_no_winner():
    m = R.load_matrix()
    assert m["final_selection"] is None
    assert m["status"] == "pending_preliminary_experiments"
    rub = m["rubric"]
    assert rub["declared_before_results"] is True
    assert abs(sum(c["weight"] for c in rub["criteria"]) - 1.0) < 1e-9
    assert all(c["weight"] > 0 for c in rub["criteria"])
    assert rub["hard_constraints"] and rub["tie_breaks"]
    assert "test" in rub["selection_data"] and "validation" in rub["selection_data"]
    md = (REPO_ROOT / "research" / "base_model" / "SELECTION_MATRIX.md").read_text(encoding="utf-8")
    assert "Final selection: `null`" in md and "No winner is declared" in md
    assert not re.search(r"Final selection: `(?!null`)", md)
    results = REPO_ROOT / "research" / "results"
    result_files = [p for p in results.rglob("*") if p.is_file()] if results.exists() else []
    if result_files:
        rubric_t = _first_commit_time("research/base_model/selection_matrix.json")
        assert rubric_t is not None, "rubric must be committed before any result file exists"
        for p in result_files:
            t = _first_commit_time(p.relative_to(REPO_ROOT).as_posix())
            assert t is None or rubric_t <= t, f"{p} committed before the rubric"


def test_license_and_overlap_cells_present():
    m = R.load_matrix()
    decisions = {d["id"]: d for d in m["decisions_needed"]}
    for row in m["rows"]:
        cells = row["cells"]
        for col in ("finetune_permitted", "redistribution"):
            assert cells[col]["value"] is not None or cells[col]["note"]
            assert cells[col]["note"]
        overlap = cells["eval_overlap"]["value"]
        assert set(overlap) == {"MIMIC-CXR", "MIMIC-IV", "CT-RATE"}
        assert all(v for v in overlap.values())
    # A license that restricts the open-weight release is escalated to humans.
    mg = next(r for r in m["rows"] if r["candidate_id"] == "medgemma-27b-it")
    assert "conditions" in mg["cells"]["redistribution"]["value"].lower()
    assert "medgemma-27b-it" in decisions["medgemma-release-terms"]["candidates"]
    assert "lingshu-32b" in decisions["lingshu-true-scale"]["candidates"]


def test_medgemma_vqa_rad_split_matches_card():
    # S9-A02 regression: the card footnote on the VQA-RAD row names the "balanced split" of Yang (2024,
    # arXiv 2405.03162); the split is stated, so it must not be recorded as "not stated on card".
    m = R.load_matrix()
    mg = next(r for r in m["rows"] if r["candidate_id"] == "medgemma-27b-it")
    vqa = [e for e in mg["cells"]["medical_benchmarks"]["value"] if e["benchmark"].startswith("VQA-RAD")]
    assert len(vqa) == 1
    assert vqa[0]["value"] == 46.7
    assert "balanced split" in vqa[0]["split"] and "2405.03162" in vqa[0]["split"]
