"""e1 wrapper: manifests, hash-bound runs and the summary (slice e1). Research prototype - not for clinical use.

Run order (spec scope 6): dev iteration (unfrozen, scratch ledger, results under ``<out>/unfrozen``) ->
``python -m eval freeze`` of all 4 manifests -> one frozen dev run and one test run into ``<out>/<split>``.
A run refuses (exit 2, 0 files written) when a bound hash differs (dataset tree, splits, mapping, adapters),
when the ledger fails verification, when the test manifests are not frozen, or when outputs already exist.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from eval.errors import RunRefused
from eval.jsonio import canonical_bytes
from eval.ledger_chain import Ledger
from eval.manifest import load_manifest, manifest_sha256
from eval.runner import run as s8r_run

from . import baselines, protocol, score, summary, triage, voice
from .gold import load_split_gold
from .inputs import load_split
from .mapping import BANNER

KINDS = ("voice", "triage")
SPLITS = ("dev", "test")
OUT_ROOT = Path(__file__).resolve().parents[1] / "results" / "e1"
DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "v1"
NOT_RUN = ("the test split runs once, after all 4 e1 manifests are frozen and committed (spec scope 6)")


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_bytes(r) + b"\n" for r in rows)


def _sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r["task"], r.get("comparator", ""), r["patient_id"], r["decision_point_id"]))


# ---------------------------------------------------------------- system outputs (snapshots only)


def system_outputs(dataset: Path, split: str) -> list[dict[str, Any]]:
    """S3 + S4 outputs for every case of the split, built from snapshot inputs only (no gold, no journey)."""
    cases = load_split(dataset, split)
    s3 = voice.run_split(cases)
    s4 = triage.run_split(cases, s3)
    return [{"case_id": c.case_id, "patient_ref": c.patient_ref, "split": split, "voice": s3[c.case_id],
             "decision_points": s4[c.case_id]} for c in cases]


def score_split(dataset: Path, split: str, outputs: list[dict[str, Any]], s_star: dict[str, Any],
                majority: dict[str, Any]) -> tuple[dict[str, list], dict[str, list], dict[str, Any]]:
    gold = load_split_gold(dataset, split)
    snaps = {c.case_id: c.snapshots for c in load_split(dataset, split)}
    if sorted(gold) != sorted(o["case_id"] for o in outputs):
        raise ValueError(f"{split}: gold and inputs cover different cases")
    rows: dict[str, list] = {"voice": [], "triage": []}
    cmp_rows: dict[str, list] = {"voice": [], "triage": []}
    for o in outputs:
        g = gold[o["case_id"]]
        if g["patient_ref"] != o["patient_ref"]:
            raise ValueError(f"{o['case_id']}: patient_ref differs between gold and inputs")
        rows["voice"] += score.voice_rows(o["case_id"], o["patient_ref"], g, o["voice"])
        tr, tc = score.triage_rows(o["case_id"], o["patient_ref"], g, o["decision_points"], snaps[o["case_id"]],
                                   s_star["s_star"], majority["code"])
        rows["triage"] += tr
        cmp_rows["triage"] += tc
    expected = sorted((t, d) for cid, g in gold.items() for t, d in score.gold_tasks(cid, g))
    got = sorted((r["task"], r["decision_point_id"]) for k in KINDS for r in rows[k])
    if expected != got:
        raise AssertionError(f"{split}: scored records differ from the gold-derived task memberships")
    info = {
        "populations": score.populations(gold),
        "unmapped_counts": score.unmapped_counts(gold, {o["case_id"]: o["decision_points"] for o in outputs},
                                                 {o["case_id"]: o["voice"] for o in outputs}),
        "comparators": {"s_star": s_star, "always_answer_fallback": majority},
    }
    return {k: _sort(v) for k, v in rows.items()}, {k: _sort(v) for k, v in cmp_rows.items()}, info


# ---------------------------------------------------------------- manifests


def make_manifests(dataset: Path, manifest_dir: Path, n_boot: int = protocol.N_BOOT,
                   splits: tuple[str, ...] = SPLITS) -> list[Path]:
    s_star = baselines.select_shortcut(dataset)
    majority = baselines.train_majority_e(dataset)
    written = []
    for split in splits:
        members = protocol.memberships(dataset, split)
        for kind in KINDS:
            m = protocol.build_manifest(kind, split, dataset, members, s_star, majority, n_boot)
            p = protocol.manifest_path(manifest_dir, kind, split)
            protocol.write_manifest(p, m)
            written.append(p)
    return written


# ---------------------------------------------------------------- run


def _postprocess(out: Path) -> None:
    """Put the e1 banner above every table of results.md / results.html (results.json is untouched)."""
    md = out / "results.md"
    lines = md.read_text(encoding="utf-8").split("\n")
    res, prev = [], ""
    for line in lines:
        if line.startswith("| ") and not prev.startswith("|"):
            res += [f"> **{BANNER}**", ""]
        res.append(line)
        prev = line
    md.write_text(f"> **{BANNER}**\n\n" + "\n".join(res), encoding="utf-8")
    html = out / "results.html"
    h = html.read_text(encoding="utf-8")
    h = h.replace("<table>", f'<div class="banner">{BANNER}</div>\n<table>')
    h = h.replace("<body>", f'<body>\n<div class="banner">{BANNER}</div>', 1)
    html.write_text(h, encoding="utf-8")


def _frozen(ledger: Ledger, m: dict[str, Any]) -> bool:
    return any(e["sha256"] == manifest_sha256(m) for e in ledger.frozen(m["evaluation_id"]))


def run_split(split: str, dataset: Path = DEFAULT_DATASET, manifest_dir: Path = protocol.MANIFEST_DIR,
              out_root: Path = OUT_ROOT, ledger_dir: Path | None = None) -> Path:
    """Run one split end to end. Returns the output directory. Raises RunRefused (nothing written)."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    paths = {k: protocol.manifest_path(manifest_dir, k, split) for k in KINDS}
    manifests = {k: load_manifest(p) for k, p in paths.items()}
    for k, m in manifests.items():
        bad = protocol.hash_mismatches(m, dataset)
        if bad:
            raise RunRefused(f"{m['evaluation_id']}: current {', '.join(bad)} differ(s) from the manifest binding; "
                             "a frozen protocol cannot run on changed data, mapping or adapter code")
    ledger = Ledger(ledger_dir)
    ledger.verify()
    frozen = all(_frozen(ledger, m) for m in manifests.values())
    if split == "test" and not frozen:
        raise RunRefused("test split requires all e1 test manifests frozen in the ledger (python -m eval freeze)")
    out = Path(out_root) / (split if frozen else f"unfrozen/{split}")
    if out.exists() and any(out.iterdir()):
        raise RunRefused(f"{out} already has files; results are never overwritten")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        run_ledger = ledger
        if not frozen:  # exploratory dev iteration: never recorded in the committed ledger
            run_ledger = Ledger(Path(tmp) / "scratch-ledger")
            run_ledger.init()
        h = protocol.parse_hashes(manifests["triage"])
        s_star = baselines.select_shortcut(dataset)
        majority = baselines.train_majority_e(dataset)
        if s_star["s_star"] != h["s_star"] or majority["code"] != h["always_answer_fallback"]:
            raise RunRefused("train-derived comparators differ from the manifest binding")
        outputs = system_outputs(dataset, split)
        rows, cmp_rows, info = score_split(dataset, split, outputs, s_star, majority)
        stage.mkdir()
        (stage / "system_outputs.jsonl").write_bytes(_jsonl(outputs))
        (stage / "split_info.json").write_bytes(canonical_bytes(info) + b"\n")
        results = {}
        for k in KINDS:
            d = stage / k
            d.mkdir()
            (d / "predictions.jsonl").write_bytes(_jsonl(rows[k]))
            cmp_path = None
            if manifests[k]["comparators"]:
                cmp_path = d / "comparator.jsonl"
                cmp_path.write_bytes(_jsonl(cmp_rows[k]))
            results[k] = s8r_run(paths[k], d / "predictions.jsonl", d, cmp_path, run_ledger)
            _postprocess(d)
        split_sum = summary.split_summary(split, manifests, results, rows, cmp_rows, info)
        (stage / "split_summary.json").write_text(
            json.dumps(split_sum, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.rmdir()
        shutil.copytree(stage, out)
    write_summary(out.parent)
    return out


def write_summary(root: Path) -> dict[str, Any]:
    """(Re)build e1_summary.{json,md} under ``root`` from the per-split outputs present there."""
    splits: dict[str, dict[str, Any] | None] = {}
    for s in SPLITS:
        p = Path(root) / s / "split_summary.json"
        splits[s] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    s = summary.build(splits, NOT_RUN)
    summary.write(Path(root), s)
    return s
