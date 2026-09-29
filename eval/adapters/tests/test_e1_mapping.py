"""E1-A01: the mapping table is complete, every row has a target or UNMAPPABLE, a rationale and a source."""

from __future__ import annotations

import json
from pathlib import Path

from eval.adapters import mapping

REPO = Path(__file__).resolve().parents[3]
TPL = REPO / "data_factory" / "templates"


def _sources(section: str) -> list[str]:
    return [r["source"] for r in mapping.rows(section)]


def test_mapping_complete():
    m = mapping.load()
    depts = [c["code"] for c in json.loads((TPL / "departments.json").read_text(encoding="utf-8"))["codes"]]
    assert len(depts) == 10
    assert sorted(_sources("department_s1r")) == sorted(depts + ["NOT_EVALUABLE"])
    s1r_rules = [r["rule_id"] for r in json.loads((TPL / "red_flags.json").read_text(encoding="utf-8"))]
    assert len(s1r_rules) == 7 and sorted(_sources("red_flag_s1r")) == sorted(s1r_rules)
    ccs = [c["id"] for c in json.loads((TPL / "complaints.json").read_text(encoding="utf-8"))]
    assert len(ccs) == 58 and sorted(_sources("chief_complaint_s1r_to_s3")) == sorted(ccs)
    icd = {c["id"]: c["icd10cm"] for c in json.loads((TPL / "complaints.json").read_text(encoding="utf-8"))}
    assert all(r["icd10cm"] == icd[r["source"]] for r in mapping.rows("chief_complaint_s1r_to_s3"))
    assert sorted(_sources("allergy_value")) == ["MISSING", "known", "no_known_allergy"]
    assert sorted(_sources("duration_unit")) == ["day", "hour", "minute", "month", "week", "year"]
    assert sorted(_sources("consciousness")) == ["A", "C", "P", "U", "V"]
    from app.triage.departments import CODES
    from app.voice.models import CHIEF_COMPLAINT_CODES

    rules = json.loads((REPO / "backend/app/triage/rules/redflag_rules_v1.json").read_text(encoding="utf-8"))
    assert len(CODES) == 10 and sorted(_sources("department_s4")) == sorted(CODES)
    assert len(rules["rules"]) == 16 and sorted(_sources("red_flag_s4")) == sorted(r["id"] for r in rules["rules"])
    assert len(CHIEF_COMPLAINT_CODES) == 16
    assert sorted(_sources("s3_cc_to_s4_symptom")) == sorted(CHIEF_COMPLAINT_CODES)
    for key, sec in m["sections"].items():  # every source code appears once
        src = [r["source"] for r in sec["rows"]]
        assert len(src) == len(set(src)), key
    # every S3 code named as an acceptable CC target exists in the S3 vocabulary
    for r in mapping.rows("chief_complaint_s1r_to_s3"):
        if r["target"] != mapping.UNMAPPABLE:
            assert r["target"] and set(r["target"]) <= set(CHIEF_COMPLAINT_CODES), r
    # the spec's examples and required targets
    assert mapping.table("chief_complaint_s1r_to_s3")["CC-RF-FAST"] == mapping.UNMAPPABLE
    assert mapping.table("red_flag_s1r")["RF-NEWS-AGG5"] == mapping.UNMAPPABLE
    assert mapping.table("department_s1r")["11"] == mapping.UNMAPPABLE
    assert mapping.outside_registry_s4_rules() == sorted(["RF-SUICIDE", "RF-GIBLEED", "RF-ECTOPIC", "RF-MENING",
                                                          "RF-HYPOGLY"])
    assert mapping.table("department_s4")["URO"] == "E-SURG" and mapping.table("department_s1r")["01"] == "E-MED"
    s4_rule_ids = {r["id"] for r in rules["rules"]}
    for tg in mapping.s1r_rule_targets().values():
        assert tg is None or set(tg) <= s4_rule_ids


def test_mapping_rows_have_rationale():
    m = mapping.load()
    n = 0
    for key, sec in m["sections"].items():
        assert sec["title"] and sec["scoring"], key
        for r in sec["rows"]:
            n += 1
            assert r["target"] == mapping.UNMAPPABLE or (r["target"] not in ("", None, [])), (key, r)
            assert isinstance(r["rationale"], str) and len(r["rationale"]) >= 5, (key, r)
            assert "\n" not in r["rationale"]
            assert isinstance(r["source_ref"], str) and r["source_ref"].strip(), (key, r)
    assert n >= 11 + 10 + 7 + 16 + 58 + 3 + 6 + 5 + 16
    assert isinstance(m["changelog"], list) and m["replay_deviations"] and m["known_disagreements"]
    for c in m["changelog"]:
        assert c["date"] and c["change"] and c["reason"]


def test_mapping_md_in_sync():
    assert mapping.MAPPING_MD_PATH.read_text(encoding="utf-8") == mapping.render_md()
