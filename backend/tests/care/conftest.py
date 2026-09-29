"""Care (s6) fixtures: the v1.2.0 synthetic dataset is generated once per session into a temp dir, so the
tests run from a clean checkout. Tests may read gold; the care engine never does."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.care import engine
from app.config import Settings
from app.gateway import build_provider
from app.gateway import service as gateway_service
from app.gateway.contract import GatewayRequest, GatewayResponse

REPO = Path(__file__).resolve().parents[3]

SEED = 20260926
SPLITS = ("train", "dev", "test")


class Dataset:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.rows: list[dict[str, Any]] = []  # one per (case, decision point), all splits
        for g in sorted((root / "gold").glob("*/*.json")):
            gold = json.loads(g.read_text("utf-8"))
            for row in gold["decision_times"]:
                self.rows.append({"split": gold["split"], "case_id": gold["case_id"],
                                  "patient_ref": gold["patient_ref"], "dp": row["decision_point"],
                                  "care": row["care"], "scenario": gold["scenario"]})

    def snapshot(self, split: str, case_id: str, dp: str) -> dict[str, Any]:
        return json.loads((self.root / "inputs" / split / case_id / f"snapshot_{dp}.json").read_text("utf-8"))

    def row_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        return self.snapshot(row["split"], row["case_id"], row["dp"])


def factory_generate(seed: int, out: Path, *, heldout: bool = False) -> None:
    """The factory CLI in a subprocess (no ``data_factory`` import under backend/, I2-A06)."""
    cmd = [sys.executable, "-m", "data_factory", "generate", "--seed", str(seed), "--out", str(out)]
    subprocess.run(cmd + (["--heldout"] if heldout else []), cwd=REPO, check=True, capture_output=True)


@pytest.fixture(scope="session")
def dataset(tmp_path_factory) -> Dataset:
    out = tmp_path_factory.mktemp("care_synthetic") / "v1"
    factory_generate(SEED, out)
    return Dataset(out)


@pytest.fixture(autouse=True)
def _care_dataset_env(monkeypatch, dataset):
    monkeypatch.setenv("CARE_DATASET", str(dataset.root))


_PROVIDER = build_provider("mock", Settings())


class CountingInvoke:
    """Gateway invoke through the real service with the offline mock provider; counts calls."""

    def __init__(self, provider=_PROVIDER) -> None:
        self.provider = provider
        self.calls = 0

    def __call__(self, req: GatewayRequest) -> GatewayResponse:
        self.calls += 1
        return gateway_service.invoke_provider(self.provider, req)


class FakeProvider:
    """A provider returning a fixed status/output, or computing output from the mock and then mutating it."""

    name = "fake"

    def __init__(self, status: str = "ok", output: Any = None, reason: str | None = None,
                 mutate: Callable[[dict], dict] | None = None, raises: Exception | None = None) -> None:
        self.status, self.output, self.reason, self.mutate, self.raises = status, output, reason, mutate, raises

    def invoke(self, request, sha):
        from app.gateway.provider import ProviderResult

        if self.raises:
            raise self.raises
        out = self.output
        if self.mutate is not None:
            base = _PROVIDER.invoke(request, sha).output
            out = self.mutate(copy.deepcopy(base))
        return ProviderResult(status=self.status, model_version="fake-1", output=out, reason=self.reason)


def run(doc: dict[str, Any], dp: str = "T2", provider=_PROVIDER, **kw):
    inv = CountingInvoke(provider)
    return engine.assess(doc, inv, decision_point=dp, **kw), inv.calls


def complete_dev_row(dataset: Dataset, *, lab: bool | None = None) -> dict[str, Any]:
    """A dev row with gold ``suggest`` and one transcript (optionally with / without a LabSeries)."""
    for row in dataset.rows:
        if row["split"] != "dev" or row["care"]["expected_action"] != "suggest":
            continue
        snap = dataset.row_snapshot(row)
        has_lab = any(it["data_type"] == "LabSeries" for it in snap["items"])
        if lab is None or lab == has_lab:
            return row
    raise AssertionError("no matching dev row")
