import json
from pathlib import Path

import pytest

from data_factory.generate import generate

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 20260926


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


class Dataset:
    def __init__(self, root: Path):
        self.root = root
        self.manifest = load(root / "manifest.json")
        self.splits = load(root / "splits.json")
        self.cases = {}
        for jp in sorted((root / "inputs").glob("*/*/journey.json")):
            cid = jp.parent.name
            self.cases[cid] = {
                "split": jp.parent.parent.name,
                "journey": load(jp),
                "snapshots": {sp.stem.split("_")[1]: load(sp) for sp in sorted(jp.parent.glob("snapshot_*.json"))},
                "gold": load(root / "gold" / jp.parent.parent.name / f"{cid}.json"),
            }
        self.injections = [json.loads(line) for line in (root / "gold" / "injection_log.jsonl").read_text("utf-8").splitlines()]


@pytest.fixture(scope="session")
def dataset(tmp_path_factory) -> Dataset:
    out = tmp_path_factory.mktemp("synthetic") / "v1"
    generate(SEED, out)
    return Dataset(out)
