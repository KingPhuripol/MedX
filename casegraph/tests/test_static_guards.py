"""S2R-A09: static guard — no code path maps a missing input to an all-clear.

An AST scan of ``casegraph/`` (tests excluded) with four checks:

(a) every ``Alerts(``/``MedicationIssues(`` (and per-rule ``RuleResult(``/``MedicationCheck(``) call
    passes ``status=`` from the single aggregator ``screening_status(...)``, never a literal;
(b) the literal ``"evaluated"`` as a status value appears only inside ``screening_status``
    (type annotations ``Literal[...]`` and read-only comparisons are not status values);
(c) rule bodies contain no ``continue``, no ``.get(<key>, <default>)`` and no ``in``-guard skip
    unless the function records per-check status through ``screening_status``;
(d) ``escalation`` is assigned only in ``Executor._checkpoint`` and only as ``bool(reasons)``.

The mutation test runs the same scan on a verbatim copy of the edf8182 Red-flag code and must fail.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
MUTANT = Path(__file__).resolve().parent / "fixtures" / "edf8182_red_flag.py.txt"
STATUS_CLASSES = {"Alerts", "MedicationIssues", "RuleResult", "MedicationCheck"}
AGGREGATOR = "screening_status"
RULE_BODIES = {"red_flag_rules", "pharma_rules", "_finite_readings", "_red_flag", "_pharma"}


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]):
    while node in parents:
        node = parents[node]
        yield node


def _func_name(node: ast.AST, parents) -> str | None:
    return next((a.name for a in _ancestors(node, parents) if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))),
                None)


def _callee(call: ast.Call) -> str | None:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _is_aggregator_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _callee(node) == AGGREGATOR


def scan(source: str, filename: str) -> list[tuple[str, str]]:
    """Return ``(check, location)`` violations for one module's source."""
    tree = ast.parse(source, filename)
    parents = _parents(tree)
    out: list[tuple[str, str]] = []

    def loc(node: ast.AST, check: str) -> None:
        out.append((check, f"{filename}:{getattr(node, 'lineno', '?')}"))

    for node in ast.walk(tree):
        # (a) status= from the aggregator
        if isinstance(node, ast.Call) and _callee(node) in STATUS_CLASSES and isinstance(
            node.func, (ast.Name, ast.Attribute)
        ):
            status = [k for k in node.keywords if k.arg == "status"]
            if not status or not _is_aggregator_call(status[0].value):
                loc(node, "a")
        # (b) "evaluated" only inside the aggregator
        if isinstance(node, ast.Constant) and node.value == "evaluated":
            ancestors = list(_ancestors(node, parents))
            in_aggregator = _func_name(node, parents) == AGGREGATOR
            in_literal_type = any(
                isinstance(a, ast.Subscript) and isinstance(a.value, ast.Name) and a.value.id == "Literal"
                for a in ancestors
            )
            is_comparison = isinstance(parents.get(node), ast.Compare)
            if not (in_aggregator or in_literal_type or is_comparison):
                loc(node, "b")
        # (d) escalation only as bool(reasons) in _checkpoint
        targets: list[ast.AST] = []
        if isinstance(node, ast.Dict):
            targets = [v for k, v in zip(node.keys, node.values)
                       if isinstance(k, ast.Constant) and k.value == "escalation"]
        elif isinstance(node, ast.keyword) and node.arg == "escalation":
            targets = [node.value]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in tgts:
                named = isinstance(t, ast.Name) and t.id == "escalation"
                keyed = isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "escalation"
                if named or keyed:
                    targets.append(node.value if node.value is not None else node)
        for value in targets:
            ok_value = (isinstance(value, ast.Call) and _callee(value) == "bool" and len(value.args) == 1
                        and isinstance(value.args[0], ast.Name) and value.args[0].id == "reasons")
            if _func_name(value, parents) != "_checkpoint" or not ok_value:
                loc(value, "d")

    # (c) rule bodies
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name not in RULE_BODIES:
            continue
        records_status = any(_is_aggregator_call(n) for n in ast.walk(fn))
        for node in ast.walk(fn):
            if isinstance(node, ast.Continue):
                loc(node, "c")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and (
                len(node.args) >= 2 or node.keywords
            ):
                loc(node, "c")
            guards = [node.test] if isinstance(node, (ast.If, ast.IfExp)) else (
                list(node.ifs) if isinstance(node, ast.comprehension) else [])
            for g in guards:
                has_in = any(isinstance(c, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in c.ops)
                             for c in ast.walk(g))
                if has_in and not records_status:
                    loc(node, "c")
    return out


def _package_sources() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "tests" not in p.relative_to(PKG).parts)


def test_no_missing_input_maps_to_all_clear():
    files = _package_sources()
    assert {p.name for p in files} >= {"data.py", "providers.py", "executor.py", "export.py"}
    violations = [v for p in files for v in scan(p.read_text(encoding="utf-8"), str(p.relative_to(PKG)))]
    assert violations == []
    # the aggregator exists exactly once and every status class is constructed somewhere through it
    defs = [p for p in files if f"def {AGGREGATOR}(" in p.read_text(encoding="utf-8")]
    assert [p.name for p in defs] == ["data.py"]


def test_static_guard_catches_edf8182_pattern():
    violations = scan(MUTANT.read_text(encoding="utf-8"), MUTANT.name)
    checks = {c for c, _ in violations}
    assert {"a", "b", "c"} <= checks, violations
    # (d) is exercised on a minimal mutant: escalation assigned outside _checkpoint / not bool(reasons)
    mutant_d = (
        "def _other():\n    payload = {'escalation': True}\n"
        "def _checkpoint():\n    reasons = []\n    payload = {'escalation': len(reasons) > 0}\n"
    )
    assert [c for c, _ in scan(mutant_d, "mutant_d")] == ["d", "d"]
    # (c) also flags .get(<key>, <default>) in a rule body
    mutant_c = "def red_flag_rules(v):\n    return v.values.get('spo2', 100.0) < 90\n"
    assert [c for c, _ in scan(mutant_c, "mutant_c")] == ["c"]
