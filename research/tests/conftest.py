"""Research tests run offline, on CPU, with no hub access (S9-A14)."""

from __future__ import annotations

import os

# Set before torch / transformers are imported by any test module.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = {
    "stage2": REPO_ROOT / "research" / "configs" / "stage2_connector.yaml",
    "stage3": REPO_ROOT / "research" / "configs" / "stage3_lora.yaml",
}
DRYRUN_MANIFESTS = {
    "stage2": REPO_ROOT / "research" / "manifests" / "dryrun-s2.json",
    "stage3": REPO_ROOT / "research" / "manifests" / "dryrun-s3.json",
}


def load_cfg(stage: str) -> dict:
    return yaml.safe_load(CONFIGS[stage].read_text(encoding="utf-8"))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _cpu_offline_env(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture
def ctrate_raw(tmp_path):
    from .ctrate_fixture import make_fixture

    return make_fixture(tmp_path / "raw")
