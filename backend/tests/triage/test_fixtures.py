import hashlib
import inspect
import json
import re
import subprocess
from collections import Counter

import pytest
from pydantic import ValidationError

from app.triage import department, engine, redflags
from app.triage.departments import CODES
from app.triage.fixtures import CASES_PATH, engine_cases, load_entries
from app.triage.models import Case

from ..conftest import REPO_ROOT

# Pinned after the fixture commit; the fixtures are frozen before the engine was written.
FIXTURES_SHA256 = "a757aa00872831d20be1b80e8d0235b60ed2f72b27ffad2020ccdf28c155fe8c"
RULE_IDS = [r["id"] for r in redflags.rules()]
THAI = re.compile(r"[฀-๿]")


def test_fixture_composition():
    assert hashlib.sha256(CASES_PATH.read_bytes()).hexdigest() == FIXTURES_SHA256
    doc = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert doc["data_class"] == "synthetic"
    entries = load_entries()
    assert len(entries) == 40
    assert len({e.case.case_ref for e in entries}) == 40
    assert all(e.case.data_class == "synthetic" for e in entries)
    assert Counter(e.split for e in entries) == {"dev": 20, "holdout": 20}

    red = [e for e in entries if e.gold.red_flag_rules]
    assert len(red) >= 16
    assert set(RULE_IDS) - {"RF-NEWS-AGG5"} <= {r for e in red for r in e.gold.red_flag_rules}
    assert sum(1 for e in red if len(e.gold.red_flag_rules) > 1) >= 3

    missing = [e for e in entries if e.gold.missing_required]
    assert len(missing) >= 6
    assert sum(1 for e in missing if e.gold.red_flag_rules) >= 2

    assert sum(1 for e in entries if e.gold.near_miss and not e.gold.red_flag_rules) >= 10
    assert sum(1 for e in entries if e.gold.temporal) >= 2

    complete = Counter(e.gold.department for e in entries if not e.gold.missing_required)
    assert set(complete) == set(CODES)
    assert min(complete.values()) >= 3

    thai = [e for e in entries for f in e.case.facts if f.kind == "chief_complaint" and THAI.search(f.value)]
    assert len(thai) >= 20
    # Every fact carries time, source, provenance, and version.
    for e in entries:
        for f in e.case.facts:
            assert f.available_at_time.tzinfo is not None and f.source and f.provenance and f.version


def test_fixture_commit_precedes_engine():
    def first_commit(path: str) -> str:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", path],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip().splitlines()[-1] if out.returncode == 0 and out.stdout.strip() else ""

    fixture_commit = first_commit("backend/app/triage/fixtures/cases_v1.json")
    engine_commit = first_commit("backend/app/triage/redflags.py")
    if not fixture_commit or not engine_commit:
        pytest.skip("git history unavailable or engine not committed yet")
    order = subprocess.run(["git", "merge-base", "--is-ancestor", fixture_commit, engine_commit],
                           cwd=REPO_ROOT, timeout=30)
    assert order.returncode == 0 and fixture_commit != engine_commit


def test_gold_not_in_engine_input():
    assert "gold" not in Case.model_fields
    entry = load_entries()[0]
    with pytest.raises(ValidationError):
        Case.model_validate(entry.case.model_dump(mode="json") | {"gold": entry.gold.model_dump(mode="json")})
    with pytest.raises(ValidationError):
        Case.model_validate(entry.case.model_dump(mode="json") | {"split": "dev"})
    # The API case source hands out Case objects only.
    assert all(type(c) is Case for c in engine_cases().values())
    # The engine modules never read gold.
    for mod in (engine, redflags, department):
        assert "gold" not in inspect.getsource(mod).lower()
