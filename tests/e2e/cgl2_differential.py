"""cg-l2 checker: run the conversation-fact sweep in ONE tree and dump every Pharma MedicationIssues as JSON.
usage: python cgl2_differential.py <tree> <dataset> <variants.json|-> <out.json> ; tree on sys.path first."""
import sys, json, pathlib, tempfile
from datetime import timedelta, timezone
tree, dataset, vfile, out = sys.argv[1:5]
sys.path[:0] = [tree + "/backend", tree]
from casegraph.tests.conftest import Env
from casegraph.sources import s1r
from casegraph.staged import build_versions
from casegraph.types import NodeType
from casegraph.tests.staged_fixtures import FIXTURES_STAGED, T1, conv_meds
from casegraph.tests.fixtures import M
import casegraph.tests.test_cgt123_conversation_meds as tm
BKK = timezone(timedelta(hours=7))
import ast, re, os
_src = open(os.environ.get("VARIANTS_SRC", tm.__file__)).read()
_m = re.search(r"^VARIANTS = (\{.*?^\})", _src, re.S | re.M)
V = ast.literal_eval(_m.group(1))  # variant defs always from VARIANTS_SRC (the head test file) so both trees run the same 17
if vfile != "-":
    names = json.load(open(vfile)); V = {k: V[k] for k in names}
else:
    json.dump(sorted(V), open(out + ".variants", "w"))
dataset = pathlib.Path(dataset)
res = {}
cases = []
for name, fx in sorted(FIXTURES_STAGED.items()):
    p, items, horizon = fx(); cases.append((name, p, items, T1, horizon))
for path in s1r.snapshot_paths(dataset, "dev"):
    if path.name == "snapshot_T1.json":
        sc = s1r.load_staged_case(dataset, "dev", path.parent.name, "T2")
        cases.append((path.parent.name, sc.items[0].patient_ref, sc.items, sc.t1, sc.horizon))
tmp = pathlib.Path(tempfile.mkdtemp())
for variant, specs in sorted(V.items()):
    for n, (name, p, items, t1, horizon) in enumerate(cases):
        items = list(items)
        for k, spec in enumerate(specs if isinstance(specs, list) else ([specs] if specs else [])):
            kw = dict(spec); t = t1 - kw.pop("minus", 15) * M
            items.append(conv_meds(p, f"{p}-cm-{variant}-{k}", t.astimezone(BKK) if kw.pop("tz", False) else t, **kw))
        env = Env(tmp / variant / str(n))
        graphs = build_versions(env.executor(), items, t1, horizon)
        rec = {}
        for g in graphs:
            ph = g.by_type(NodeType.PHARMA_AGENT)
            rec[g.stage] = {"mi": ph.output["MedicationIssues"] if ph and ph.output else None,
                            "other": {t.value if hasattr(t, 'value') else str(t): (g.by_type(t).output if g.by_type(t) else None)
                                      for t in (NodeType.RED_FLAG, NodeType.HUMAN_CHECKPOINT)}}
        res[f"{variant}|{name}"] = rec
json.dump(res, open(out, "w"), default=str, sort_keys=True)
print(len(res), "runs")
