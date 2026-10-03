"""cg-l1 independent checker (own scenarios): all three kinds bad-time at once, bad-time KNOWN meds+allergy next to
valid facts, S5 never reads the bad fact, order/permutation of item arrival. Synthetic, mock only."""
import json
import pytest
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import Executor
from casegraph.staged import build_versions
from casegraph.types import NodeType
from casegraph.tests.conftest import Env
from casegraph.tests.fixtures import H, M
from casegraph.tests.staged_fixtures import T1, allergy, base, conv_meds, order

BAD = [None, "", "not-a-time", "2026-02-30T10:00:00+00:00", 12345, "MISSING"]


def _patch(mp, ids, bad):
    orig = Executor._conversation_facts
    def w(ctx):
        out = []
        for f in orig(ctx):
            if f.get("source_item") in ids:
                f = dict(f)
                if bad == "MISSING": f.pop("available_at_time", None)
                else: f["available_at_time"] = bad
            out.append(f)
        return tuple(out)
    mp.setattr(Executor, "_conversation_facts", staticmethod(w))


@pytest.mark.parametrize("mode", ["staged", "unstaged"])
@pytest.mark.parametrize("bad", BAD)
def test_all_kinds_bad_at_once(tmp_path, monkeypatch, mode, bad):
    p = "SYN-CHK"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * H, status="known"),
             conv_meds(p, f"{p}-ok", T1 - 20 * M, meds=("UNKNOWN", None), allergy_status=("KNOWN", "present"),
                       allergens=("UNKNOWN", None)),
             conv_meds(p, f"{p}-bad", T1 - 5 * M, meds=("KNOWN", ["warfarin"]), allergy_status=("KNOWN", "absent"),
                       allergens=("KNOWN", ["latexq"])),
             order(p, f"{p}-o", T1 if mode == "unstaged" else T1 + 30 * M)]
    _patch(monkeypatch, {f"{p}-bad"}, bad)
    ex = Env(tmp_path).executor()
    g = build_versions(ex, items, T1, T1 + 2 * H)[-1] if mode == "staged" else ex.run_sync(
        compile_graph(build_snapshot(items, T1, p), None, version=1, parent_version=None))
    n = g.by_type(NodeType.PHARMA_AGENT)
    mi = n.output["MedicationIssues"]
    assert n.status == "ok" and mi["status"] != "evaluated"
    for k in ("allergy_status", "allergens", "current_medications"):
        assert f"conversation.{k}:unparseable_time" in mi["missing_inputs"], k
    assert "conversation.current_medications=UNKNOWN" in mi["missing_inputs"]  # valid older UNKNOWN stays open
    assert "conversation.allergens=UNKNOWN" in mi["missing_inputs"]
    blob = json.dumps(mi["check_results"]).lower()
    assert "latexq" not in blob and "warfarin" not in blob  # bad-time facts never reach S5
    assert not any(c["status"] == "evaluated" and "unparseable_time" in json.dumps(c) for c in mi["check_results"])
