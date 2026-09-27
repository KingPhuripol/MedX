"""Slice s6: v1.2.0 care gold extension (S6-A08, S6-A09 audit part). Synthetic reference labels only."""

import hashlib
import json
import re
import shutil
from datetime import datetime

from data_factory import audit
from data_factory.generate import GENERATOR_VERSION, ITEM_VERSION

from .conftest import REPO_ROOT, load

TEMPLATES = REPO_ROOT / "data_factory" / "templates"
# Pinned from the v1.1.1 generator (commit ef4a3d2, seed 20260926): sha256 over every inputs/** file, and over every
# gold file with `label_version` and the new `care` key removed. v1.2.0 must reproduce both exactly.
V111_INPUTS_SHA256 = "d785e3a6ecc90fa80e5262be2384a1ebb68f7001a7109230fe3a428c2fb223c4"
V111_OLD_GOLD_SHA256 = "8b7aa1e8d584a4917949aef8c8124c660eca4633c41c3e60ca309f2009434b58"
REQUIRED = ["demographics.age", "demographics.sex", "chief_complaint", "duration", "allergy_status", "vitals.rr",
            "vitals.spo2", "vitals.on_oxygen", "vitals.temp_c", "vitals.sbp", "vitals.hr", "vitals.consciousness"]
CLAIMS = re.compile(r"diagnos|prescrib|treat|dose|dosage|วินิจฉัย|สั่งยา|ให้ยา|รักษา", re.IGNORECASE)


def inputs_sha256(root):
    h = hashlib.sha256()
    for p in sorted((root / "inputs").rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0"
                     + hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def old_gold_sha256(root):
    h = hashlib.sha256()
    for p in sorted((root / "gold").rglob("*.json")):
        g = load(p)
        g.pop("label_version")
        for r in g["decision_times"]:
            r.pop("care", None)
        h.update(p.relative_to(root).as_posix().encode() + b"\0"
                 + json.dumps(g, sort_keys=True, ensure_ascii=False).encode() + b"\n")
    return h.hexdigest()


def rows(dataset):
    for cid, c in sorted(dataset.cases.items()):
        for r in c["gold"]["decision_times"]:
            yield cid, c, r


def test_inputs_unchanged_vs_v111(dataset):
    assert GENERATOR_VERSION == "1.2.0" and ITEM_VERSION == "1.1.1"
    assert inputs_sha256(dataset.root) == V111_INPUTS_SHA256
    assert old_gold_sha256(dataset.root) == V111_OLD_GOLD_SHA256
    assert {c["gold"]["label_version"] for c in dataset.cases.values()} == {"1.2.0"}
    assert dataset.manifest["generator_version"] == "1.2.0"


def test_care_required_inputs_canonical(dataset):
    doc = load(TEMPLATES / "care_required_inputs.json")
    assert [r["input"] for r in doc["required_inputs"]] == REQUIRED
    refs = {r["ref_id"] for r in load(TEMPLATES / "references.json")}
    assert all(r["source_ref"] in refs for r in doc["required_inputs"])
    seen_abstain = set()
    for cid, c, r in rows(dataset):
        care = r["care"]
        missing = care["required_inputs_missing"]
        assert missing == [f for f in REQUIRED if f in missing]  # canonical order, exact strings
        assert care["expected_action"] == ("abstain" if missing else "suggest")
        for f in ("chief_complaint", "duration", "allergy_status"):
            assert (f in missing) == (r["required_fields"][f] == "MISSING")
        snap = c["snapshots"][r["decision_point"]]["items"]
        vit = [it for it in snap if it["data_type"] == "Vitals"]
        for p in ("rr", "spo2", "on_oxygen", "temp_c", "sbp", "hr", "consciousness"):
            assert (f"vitals.{p}" in missing) == all(v[p] is None for v in vit)
        seen_abstain |= set(missing)
    assert {"chief_complaint", "duration", "allergy_status", "vitals.temp_c"} <= seen_abstain


def test_care_gold_sources(dataset):
    refs = {r["ref_id"]: r for r in load(TEMPLATES / "references.json")}
    vocab = {c["code"]: c for c in load(TEMPLATES / "next_info_codes.json")["codes"]}
    paths = {c["code"]: c for c in load(TEMPLATES / "care_pathways.json")["pathways"]}
    cni = load(TEMPLATES / "care_next_info.json")
    complaints = [c["id"] for c in load(TEMPLATES / "complaints.json")]
    rule_ids = [r["rule_id"] for r in load(TEMPLATES / "red_flags.json")]
    assert sorted(cni["complaints"]) == sorted(complaints)
    assert sorted(cni["red_flag_rules"]) == sorted(rule_ids) == sorted(cni["rule_priority"])
    for e in [*cni["complaints"].values(), *cni["red_flag_rules"].values()]:
        if e.get("no_sourced_workup"):
            assert e["reason"] and set(e) == {"no_sourced_workup", "reason"}
        else:
            assert e["next_info"] and set(e["next_info"]) <= set(vocab) and e["pathway"] in paths and e["source_refs"]
    for c in vocab.values():
        assert c["kind"] in {"ask", "observe", "lab", "imaging", "ecg"} and c["display_th"] and c["display_en"]
        assert (c["kind"] == "lab") == bool(c.get("loinc")) and (not c.get("loinc") or re.fullmatch(r"\d{1,6}-\d", c["loinc"]))
        assert not CLAIMS.search(c["display_en"] + c["display_th"])
    for c in paths.values():
        assert not CLAIMS.search(c["display_en"] + c["display_th"]) and c["source_refs"]

    def good(ref_id):
        r = refs[ref_id]
        return bool(r.get("accessed")) and (bool(re.fullmatch(r"\d{7,8}", r.get("pmid", "")))
                                            or r.get("url", "").startswith("https://"))

    used_ni, used_cp = set(), set()
    for _, _, r in rows(dataset):
        care = r["care"]
        used_ni |= set(care["next_info"]) | set(care["ordered_after_T"])
        if care["pathway"]:
            used_cp.add(care["pathway"])
        assert set(care["next_info_sources"]) == set(care["next_info"])
        for code, srcs in care["next_info_sources"].items():
            assert srcs and any(good(s) for s in srcs), code
        if care["evaluable"]:
            assert care["next_info"] and care["reason"] == "sourced"
        else:
            assert care["next_info"] == [] and care["reason"] != "sourced"
    for code in used_ni:
        entry_refs = {s for e in [*cni["complaints"].values(), *cni["red_flag_rules"].values()]
                      if code in e.get("next_info", []) for s in e["source_refs"]}
        assert any(good(s) for s in entry_refs | set(vocab[code]["source_refs"])), code
    for code in used_cp:
        assert any(good(s) for s in paths[code]["source_refs"]), code
    assert len(used_cp) >= 10 and len(used_ni) >= 15


def test_care_gold_temporal(dataset):
    vocab = {c["code"]: c for c in load(TEMPLATES / "next_info_codes.json")["codes"]}
    loinc_code = {c["loinc"]: c["code"] for c in vocab.values() if c.get("loinc")}
    lab_code = {x["test"]: loinc_code[x["loinc"]] for x in load(TEMPLATES / "labs.json")}
    differ = 0
    for cid, c, r in rows(dataset):
        T = r["T"]
        snap = c["snapshots"][r["decision_point"]]["items"]
        resulted = {lab_code[x["test"]] for it in snap if it["data_type"] == "LabSeries" for x in it["results"]}
        care = r["care"]
        # nothing suggested is already resulted in snapshot_T; everything removed was really available at T
        assert not (set(care["next_info"]) & resulted)
        for code in care["already_available_at_T"]:
            assert code in resulted or (code == "NI-OBS-REPEAT-VITALS"
                                        and sum(it["data_type"] == "Vitals" for it in snap) >= 2)
        # proxy: lab items whose LabSeries event_time is after T (from the audit-only journey)
        later = {lab_code[x["test"]] for it in c["journey"]["items"] if it["data_type"] == "LabSeries"
                 and datetime.fromisoformat(it["event_time"]) > datetime.fromisoformat(T) for x in it["results"]}
        assert set(care["ordered_after_T"]) == later
    for cid, c in dataset.cases.items():
        t1, t2 = (r["care"] for r in c["gold"]["decision_times"])
        if t1["next_info"] != t2["next_info"] and set(t2["already_available_at_T"]) - set(t1["already_available_at_T"]):
            differ += 1
    assert differ >= 1


def test_audit_bans_care_gold_in_inputs(dataset, tmp_path):
    root = tmp_path / "ds"
    shutil.copytree(dataset.root, root)
    assert audit.run_audit(root, write_report=False)["status"] == "PASS"
    snap = next((root / "inputs" / "dev").glob("*/snapshot_T1.json"))
    doc = load(snap)
    doc["care"] = {"next_info": ["NI-ECG-12LEAD"]}
    snap.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    rep = audit.run_audit(root, write_report=False)
    assert rep["status"] == "FAIL" and rep["steps"]["gold_separation"].startswith("FAIL")
    errs = [e for e in rep["errors"] if str(snap) in e]
    assert any("'care'" in e for e in errs) and any("NI-ECG-12LEAD" in e for e in errs)


def test_care_docs_describe_labels(dataset):
    card = (dataset.root / "DATACARD.md").read_text("utf-8")
    readme = (dataset.root / "gold" / "README.md").read_text("utf-8")
    for text in (card, readme):
        assert "synthetic reference labels" in text and "not expert-reviewed" in text and "`care`" in text
