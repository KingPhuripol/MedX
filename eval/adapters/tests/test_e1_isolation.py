"""E1-A15: adapters import only app.voice, app.triage, app.gateway and app.db (plus stdlib and eval core);
no module under eval/ imports data_factory.generate."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ADAPTERS = Path(__file__).resolve().parents[1]
EVAL_DIR = ADAPTERS.parent
APP_ALLOWED = ("app.voice", "app.triage", "app.gateway", "app.db")
NEVER = {"sklearn", "scipy", "socket", "urllib", "http", "requests", "httpx", "aiohttp", "backend", "casegraph",
         "web", "slices", "data_factory"}


def _imports(p: Path) -> list[tuple[str, int]]:
    out = []
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(a.name, 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level))
            if node.module in ("app", None) and node.level == 0:
                out += [(f"app.{a.name}", 0) for a in node.names]
    return out


def test_adapters_import_allowlist():
    runtime = sorted(p for p in ADAPTERS.rglob("*.py") if "tests" not in p.relative_to(ADAPTERS).parts)
    assert len(runtime) >= 10
    bad = []
    for p in runtime:
        for mod, level in _imports(p):
            if level > 0 or mod == "__future__":
                continue
            top = mod.split(".")[0]
            if top == "app":
                if mod == "app" or not mod.startswith(tuple(f"{a}" for a in APP_ALLOWED)):
                    bad.append(f"{p.name}: {mod}")
            elif top == "eval":
                if mod.startswith("eval.adapters"):
                    bad.append(f"{p.name}: {mod} (use relative imports)")
            elif top in NEVER or top not in sys.stdlib_module_names:
                bad.append(f"{p.name}: {mod}")
    assert bad == []
    # the adapter tests may use pytest and product vocabularies, never data_factory.generate or the network
    for p in sorted((ADAPTERS / "tests").rglob("*.py")):
        for mod, _ in _imports(p):
            assert not mod.startswith("data_factory"), (p.name, mod)
            assert mod.split(".")[0] not in {"socket", "urllib", "http", "requests", "httpx", "aiohttp"}, (p.name, mod)


def test_no_data_factory_generate_under_eval():
    for p in sorted(EVAL_DIR.rglob("*.py")):
        for mod, _ in _imports(p):
            assert not mod.startswith("data_factory.generate"), (p, mod)
