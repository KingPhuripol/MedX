"""i2 wrapper: manifests, hash-bound runs and the summary. Research prototype - not for clinical use.

Order (spec scope 9): iterate on train/dev only (unfrozen dev runs use a scratch ledger and write to
``<out>/unfrozen/dev``; they are exploratory evidence, never the frozen result and never in eval/ledger) -> ``python -m eval freeze`` both manifests -> one frozen dev
run and one test run into ``<out>/<split>``. A run refuses (nothing written) when a bound hash differs, the ledger
fails verification, the test manifest is not frozen, or frozen outputs already exist. The test split is compiled
and executed only inside the frozen run.
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

from eval.adapters.gold import load_split_gold
from . import arms, protocol, summary
from .score import gold_tasks, rows_for

OUT_ROOT = protocol.ROOT / "eval" / "results" / "i2"
DEFAULT_DATASET = protocol.ROOT / "data" / "synthetic" / "v1"
NOT_RUN = "the test split runs once, inside the frozen run after both i2 manifests are frozen and committed"


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_bytes(r) + b"\n" for r in rows)


def _sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r["task"], r.get("comparator", ""), r["patient_id"], r["decision_point_id"]))


def make_manifests(dataset: Path, manifest_dir: Path, n_boot: int = protocol.N_BOOT,
                   splits: tuple[str, ...] = protocol.SPLITS) -> list[Path]:
    written = []
    for split in splits:
        p = protocol.manifest_path(manifest_dir, split)
        protocol.write_manifest(p, protocol.build_manifest(split, dataset, n_boot))
        written.append(p)
    return written


def score_split(dataset: Path, split: str, records: list[dict[str, Any]]
                ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    gold = load_split_gold(dataset, split)
    if sorted(gold) != sorted({r["case_id"] for r in records}):
        raise ValueError(f"{split}: gold and inputs cover different cases")
    rows, cmp_rows = [], []
    for rec in records:
        g = gold[rec["case_id"]]
        if g["patient_ref"] != rec["patient_ref"]:
            raise ValueError(f"{rec['case_id']}: patient_ref differs between gold and inputs")
        s, c = rows_for(rec, g)
        rows += s
        cmp_rows += c
    expected = sorted(m for g in gold.values() for m in gold_tasks(g))
    if expected != sorted((r["task"], r["decision_point_id"]) for r in rows):
        raise AssertionError(f"{split}: scored records differ from the gold-derived task memberships")
    return _sort(rows), _sort(cmp_rows), gold


def _postprocess(out: Path) -> None:
    """Banner and circularity note above every table of the runner's results.md / results.html."""
    note = f"> **{summary.BANNER}**\n>\n> {summary.CIRCULARITY}\n"
    md = out / "results.md"
    lines, res, prev = md.read_text(encoding="utf-8").split("\n"), [], ""
    for line in lines:
        if line.startswith("| ") and not prev.startswith("|"):
            res += [note, ""]
        res.append(line)
        prev = line
    md.write_text(note + "\n" + "\n".join(res), encoding="utf-8")
    html = out / "results.html"
    div = f'<div class="banner">{summary.BANNER}</div>\n<p class="banner">{summary.CIRCULARITY}</p>\n'
    h = html.read_text(encoding="utf-8").replace("<table>", div + "<table>")
    html.write_text(h.replace("<body>", "<body>\n" + div, 1), encoding="utf-8")


def _frozen(ledger: Ledger, m: dict[str, Any]) -> bool:
    return any(e["sha256"] == manifest_sha256(m) for e in ledger.frozen(m["evaluation_id"]))


def run_split(split: str, dataset: Path = DEFAULT_DATASET, manifest_dir: Path = protocol.MANIFEST_DIR,
              out_root: Path = OUT_ROOT, ledger_dir: Path | None = None) -> Path:
    if split not in protocol.SPLITS:
        raise ValueError(f"split must be one of {protocol.SPLITS}")
    path = protocol.manifest_path(manifest_dir, split)
    manifest = load_manifest(path)
    bad = protocol.hash_mismatches(manifest, dataset)
    if bad:
        raise RunRefused(f"{manifest['evaluation_id']}: current {', '.join(bad)} differ(s) from the manifest "
                         "binding; a frozen protocol cannot run on changed data, mapping or code")
    ledger = Ledger(ledger_dir)
    ledger.verify()
    frozen = _frozen(ledger, manifest)
    if split == "test" and not frozen:
        raise RunRefused("the test split requires i2-cg-vs-sp-test-v1 frozen in the ledger (python -m eval freeze)")
    out = Path(out_root) / (split if frozen else f"unfrozen/{split}")
    if frozen and out.exists() and any(out.iterdir()):
        raise RunRefused(f"{out} already has files; frozen results are never overwritten")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        run_ledger = ledger
        if not frozen:  # exploratory dev iteration: never recorded in the committed ledger
            run_ledger = Ledger(Path(tmp) / "scratch-ledger")
            run_ledger.init()
        records, wall = arms.run_split(dataset, split)
        rows, cmp_rows, gold = score_split(dataset, split, records)
        stage.mkdir()
        (stage / "system_outputs.jsonl").write_bytes(_jsonl(records))
        (stage / "predictions.jsonl").write_bytes(_jsonl(rows))
        (stage / "comparator.jsonl").write_bytes(_jsonl(cmp_rows))
        results = s8r_run(path, stage / "predictions.jsonl", stage, stage / "comparator.jsonl", run_ledger)
        _postprocess(stage)
        hv = protocol.parse_hashes(manifest)["handler_versions"]
        split_sum = summary.split_summary(split, manifest, results, records, rows, cmp_rows, gold, hv)
        (stage / "split_summary.json").write_text(
            json.dumps(split_sum, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8")
        (stage / "timing.json").write_text(json.dumps(summary.timing(split, wall), sort_keys=True, indent=1) + "\n",
                                           encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():  # frozen: empty (checked above); unfrozen: exploratory scratch, replaced as a whole
            shutil.rmtree(out)
        shutil.copytree(stage, out)
    write_summary(out.parent)
    return out


def write_summary(root: Path) -> dict[str, Any]:
    splits: dict[str, dict[str, Any] | None] = {}
    for s in protocol.SPLITS:
        p = Path(root) / s / "split_summary.json"
        splits[s] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    s = summary.build(splits, NOT_RUN)
    summary.write(Path(root), s)
    return s
