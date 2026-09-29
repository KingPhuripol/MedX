"""Gate 2 simulated-user harness: selfcheck (scripted fake LLM, no network) plus its own import allowlist.

eval/simuser is excluded from the s8 isolation rule in test_runner.py because it needs an HTTP client (httpx) for
the simulator endpoint, the synthetic-manifest check (casegraph) and, in the selfcheck only, the in-process app.
It still may not use raw sockets, urllib, requests, aiohttp, slices, web or heavy ML libraries.
"""

import ast
from pathlib import Path

from eval.simuser.run import selfcheck

SIMUSER = Path(__file__).resolve().parents[1] / "simuser"
BANNED = {"socket", "urllib", "requests", "aiohttp", "slices", "web", "sklearn", "scipy", "torch"}


def test_simuser_import_allowlist():
    bad = []
    for p in SIMUSER.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else []
            bad += [f"{p.name}: {m}" for m in mods if m.split(".")[0] in BANNED]
    assert bad == []


def test_simuser_selfcheck():
    selfcheck()
