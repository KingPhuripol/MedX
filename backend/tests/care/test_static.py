"""Static and isolation checks for app/care (s6): provider isolation, no gold/data_factory access, pinned rules,
snapshot-only input, claim terms in rule/template/web copy."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.care import ruleset

from ..conftest import REPO_ROOT
from .test_api import CLAIMS

CARE_DIR = REPO_ROOT / "backend" / "app" / "care"
# The evaluator joins predictions with gold labels; it is the harness, not the care engine.
HARNESS = {"evaluate.py"}
ADAPTERS = ".".join(["gateway", "adapters"])  # built so the s0 hygiene scan does not self-match
FORBIDDEN_IMPORTS = ("app." + ADAPTERS, "httpx", "requests", "socket", "urllib", "data_factory")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # resolve relative imports inside app.care
                pkg = ["app", "care"][: 3 - node.level] if node.level <= 2 else []
                base = ".".join([*pkg, base] if base else pkg)
            mods.add(base)
            mods |= {f"{base}.{a.name}" for a in node.names}
    return mods


def _care_files() -> list[Path]:
    return sorted(CARE_DIR.rglob("*.py"))


def test_care_provider_isolation():
    bad = [(p.name, m) for p in _care_files() for m in _imports(p)
           if any(m == f or m.startswith(f + ".") or m.endswith("." + ADAPTERS) for f in FORBIDDEN_IMPORTS)]
    assert bad == []
    assert "adapters" not in " ".join(p.read_text("utf-8") for p in _care_files())


def test_care_no_data_factory_import():
    for p in _care_files():
        assert not any(m.split(".")[0] == "data_factory" for m in _imports(p)), p
        src = p.read_text("utf-8")
        assert "data_factory" not in src.replace("must not import ``data_factory``", ""), p
        if p.name not in HARNESS:
            assert "journey.json" not in src.replace("(``journey.json``, ``gold/``) is read here", "")
            assert '"gold"' not in src and "'gold'" not in src and "/gold" not in src, p


def test_rules_hash_pinned_to_version(tmp_path):
    assert ruleset.file_sha256() == ruleset.CARE_RULES_SHA256
    doc = ruleset.load()
    assert doc["version"] == ruleset.CARE_RULES_VERSION
    changed = tmp_path / "rules.json"
    changed.write_text(ruleset.RULES_PATH.read_text("utf-8").replace(ruleset.CARE_RULES_VERSION, "care-rules-9.9.9"), "utf-8")
    with pytest.raises(RuntimeError, match="without a CARE_RULES_VERSION bump"):
        ruleset.load(changed)
    with pytest.raises(RuntimeError, match="version does not match"):
        ruleset.load(changed, pinned_sha256=ruleset.file_sha256(changed))


def test_rules_vocabulary_matches_gold_vocabulary():
    """Rule codes are a subset of the gold's closed vocabularies with the same displays and sources."""
    r = ruleset.rules()
    tpl = REPO_ROOT / "data_factory" / "templates"
    ni = {c["code"]: c for c in json.loads((tpl / "next_info_codes.json").read_text("utf-8"))["codes"]}
    cp = {c["code"]: c for c in json.loads((tpl / "care_pathways.json").read_text("utf-8"))["pathways"]}
    assert set(r["vocabulary"]["next_info"]) == set(ni) and set(r["vocabulary"]["pathways"]) == set(cp)
    for code, v in [*r["vocabulary"]["next_info"].items(), *r["vocabulary"]["pathways"].items()]:
        g = ni.get(code) or cp[code]
        assert (v["display_en"], v["display_th"]) == (g["display_en"], g["display_th"])
        assert r["source_refs"][code], code
    refs = {x["ref_id"] for x in json.loads((tpl / "references.json").read_text("utf-8"))}
    assert {x for v in r["source_refs"].values() for x in v} <= refs


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_care_claim_scan_files():
    hits = [s for s in _strings(ruleset.rules()) if CLAIMS.search(s)]
    tpl = REPO_ROOT / "data_factory" / "templates"
    for name, key in (("next_info_codes.json", "codes"), ("care_pathways.json", "pathways")):
        for c in json.loads((tpl / name).read_text("utf-8"))[key]:
            hits += [c[k] for k in ("display_en", "display_th") if CLAIMS.search(c[k])]
    web = REPO_ROOT / "web" / "app" / "physician" / "care"
    files = [p for p in web.rglob("*") if p.is_file()] + [
        REPO_ROOT / "web" / "components" / n for n in ("CareCaseList.tsx", "CareReview.tsx", "CareReviewLoader.tsx")]
    files.append(REPO_ROOT / "web" / "lib" / "care.ts")
    assert all(p.exists() for p in files) and len(files) >= 5
    hits += [f"{p.name}: {m.group(0)}" for p in files if (m := CLAIMS.search(p.read_text("utf-8")))]
    assert hits == []


PRINT_ALL = """
import json, sys
from app.care import dataset, engine
from app.config import Settings
from app.gateway import build_provider
from app.gateway.service import invoke_provider
p = build_provider("mock", Settings())
out = []
for cid in dataset.case_ids("dev"):
    for dp in dataset.DECISION_POINTS:
        r = engine.assess(dataset.load_snapshot("dev", cid, dp), lambda q: invoke_provider(p, q), decision_point=dp)
        out.append(json.loads(r.model_dump_json()))
sys.stdout.write(json.dumps(out, sort_keys=True))
"""


def test_care_reads_snapshots_only(dataset, tmp_path):
    """Remove journey.json, gold/ and data_factory (templates included): care outputs are byte-identical."""
    stripped = tmp_path / "ds"
    shutil.copytree(dataset.root, stripped, ignore=shutil.ignore_patterns("journey.json"))
    shutil.rmtree(stripped / "gold")
    assert not list(stripped.rglob("journey.json"))
    code = tmp_path / "code"
    shutil.copytree(REPO_ROOT / "backend" / "app", code / "app", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO_ROOT / "casegraph", code / "casegraph", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    assert not (code / "data_factory").exists()

    def dump(paths: list[Path], ds: Path) -> bytes:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CARE_DATASET")}
        env["CARE_DATASET"] = str(ds)
        res = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path[:0] = {[str(p) for p in paths]!r}\n"
                              + PRINT_ALL], capture_output=True, env=env, cwd=tmp_path, check=False)
        assert res.returncode == 0, res.stderr.decode()
        return res.stdout

    full = dump([REPO_ROOT / "backend", REPO_ROOT], dataset.root)
    assert json.loads(full) and dump([code], stripped) == full
