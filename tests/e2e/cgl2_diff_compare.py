"""manual evidence: compares two differential dumps (base c6a7a92 vs head); companion of cgl2_differential.py"""
import json, sys, collections
b = json.load(open(sys.argv[1])); h = json.load(open(sys.argv[2]))
assert b.keys() == h.keys()
OLD13 = None
unexpected = []; changed = collections.Counter(); rows_total = 0; sup_rows = collections.Counter(); sup_used_in_head = 0
stale_used_in_base = 0
for key in sorted(b):
    variant = key.split("|")[0]
    for stage in b[key]:
        bm, hm = b[key][stage]["mi"], h[key][stage]["mi"]
        if b[key][stage]["other"] != h[key][stage]["other"]: unexpected.append((key, stage, "other-nodes"))
        if bm is None or hm is None:
            if bm != hm: unexpected.append((key, stage, "mi-presence"))
            continue
        bu, hu = bm["conversation_fact_use"], hm["conversation_fact_use"]
        if len(bu) != len(hu): unexpected.append((key, stage, "row-count")); continue
        for i, (x, y) in enumerate(zip(bu, hu)):
            rows_total += 1
            if y["use"] == "superseded":
                sup_rows[y["kind"]] += 1
                if y["used"]: sup_used_in_head += 1
            diff = {k for k in set(x) | set(y) if x.get(k) != y.get(k)}
            if diff == {"used"} and x["use"] == "superseded" and x["used"] is True and y["used"] is False:
                changed[(variant, x["kind"])] += 1
            elif diff:
                unexpected.append((key, stage, i, sorted(diff), x, y))
        strip = lambda m: {k: v for k, v in m.items() if k != "conversation_fact_use"}
        if strip(bm) != strip(hm): unexpected.append((key, stage, "rest-of-MedicationIssues"))
print("rows compared", rows_total, "superseded rows at head by kind", dict(sup_rows), "head superseded with used=True:", sup_used_in_head)
print("changed rows True->False on superseded, by (variant,kind):", {f"{k[0]}/{k[1]}": v for k, v in sorted(changed.items())}, "total", sum(changed.values()))
print("unexpected diffs:", len(unexpected)); [print(u) for u in unexpected[:10]]
