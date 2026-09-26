import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime

import pytest
from pydantic import BaseModel

import casegraph
from data_factory import audit
from data_factory.generate import QUOTAS, generate

from .conftest import REPO_ROOT, SEED, load

TEMPLATES = REPO_ROOT / "data_factory" / "templates"
DEPT_CODES = {"01", "02", "03", "04", "06", "07", "08", "09", "11", "12"}
RULES = ("RF-QSOFA", "RF-NEWS-SINGLE3", "RF-FAST", "RF-ACUTE-CHEST-PAIN", "RF-THUNDERCLAP", "RF-ANAPHYLAXIS")
ISSUE_TYPES = ("duplicate_therapy", "dose_mismatch", "frequency_mismatch", "omission", "allergy_conflict")


def t(s):
    return datetime.fromisoformat(s)


def run_cli(*args, hashseed="0"):
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONHASHSEED": hashseed}
    return subprocess.run([sys.executable, *args], cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def leakage_module():
    spec = importlib.util.spec_from_file_location("tla", REPO_ROOT / "scripts" / "temporal_leakage_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def transcript(items):
    return next(i for i in items if i["data_type"] == "IntakeTranscript")


# ------------------------------------------------------------------ determinism and split
def test_determinism_same_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_cli("-m", "data_factory", "generate", "--seed", str(SEED), "--out", str(a), hashseed="0").returncode == 0
    assert run_cli("-m", "data_factory", "generate", "--seed", str(SEED), "--out", str(b), hashseed="12345").returncode == 0
    assert load(a / "manifest.json")["tree_sha256"] == load(b / "manifest.json")["tree_sha256"]
    ta = tree_bytes(a)
    assert ta == tree_bytes(b)
    # no wall-clock values: every timestamp is synthetic (2028-2031); manifest has no time fields
    years = {int(y) for data in ta.values() for y in re.findall(rb"\b(\d{4})-\d{2}-\d{2}T", data)}
    assert years and years <= {2028, 2029, 2030, 2031}
    assert not {"generated_at", "created_at", "timestamp"} & set(load(a / "manifest.json"))


def test_different_seed_differs(tmp_path, dataset):
    generate(SEED + 1, tmp_path / "x")
    assert load(tmp_path / "x" / "manifest.json")["tree_sha256"] != dataset.manifest["tree_sha256"]


def test_counts_and_split_ratio(dataset):
    c = dataset.manifest["counts"]
    assert c["cases"] == len(dataset.cases) == 200
    assert c["patients"] == len(dataset.splits) == 180
    assert c["revisit_patients"] == 20
    assert c["patients_per_split"] == {"dev": 36, "test": 36, "train": 108}
    per = {s: sum(1 for x in dataset.cases.values() if x["split"] == s) for s in ("train", "dev", "test")}
    assert abs(per["train"] / 200 - 0.60) <= 0.03
    assert abs(per["dev"] / 200 - 0.20) <= 0.03 and abs(per["test"] / 200 - 0.20) <= 0.03


def test_revisit_same_split(dataset):
    by_patient = {}
    for c in dataset.cases.values():
        by_patient.setdefault(c["journey"]["patient_ref"], set()).add(c["split"])
        assert all(i["patient_ref"] == c["journey"]["patient_ref"] for i in c["journey"]["items"])
    revisit = [p for p in by_patient if sum(1 for c in dataset.cases.values() if c["journey"]["patient_ref"] == p) == 2]
    assert len(revisit) == 20
    assert all(len(s) == 1 for s in by_patient.values())
    assert all(by_patient[p] == {dataset.splits[p]} for p in by_patient)


def test_split_precedes_generation(tmp_path, dataset):
    assert run_cli("-m", "data_factory", "generate", "--seed", str(SEED), "--out", str(tmp_path / "s"),
                   "--splits-only").returncode == 0
    assert sorted(p.name for p in (tmp_path / "s").iterdir()) == ["splits.json"]
    full = (dataset.root / "splits.json").read_bytes()
    assert (tmp_path / "s" / "splits.json").read_bytes() == full
    changed = {**QUOTAS, "red_flag": "1/3", "missing_info": "1/4", "injected_of_medication": "1/2"}
    generate(SEED, tmp_path / "q", quotas=changed)
    assert (tmp_path / "q" / "splits.json").read_bytes() == full
    assert load(tmp_path / "q" / "manifest.json")["tree_sha256"] != dataset.manifest["tree_sha256"]


# ------------------------------------------------------------------ schema
def test_all_items_schema_valid(dataset):
    n = 0
    for c in dataset.cases.values():
        for doc in (c["journey"], *c["snapshots"].values()):
            for it in doc["items"]:
                obj = casegraph.evidence_adapter.validate_python(it)
                assert isinstance(obj, casegraph.TimedEvidence) and type(obj).model_config["extra"] == "forbid"
                assert it["provenance"] == "synthetic" and it["source"] and it["version"]
                assert it["item_id"] and it["encounter_ref"] == c["journey"]["case_id"]
                assert all(t(it[f]).tzinfo is not None for f in ("event_time", "observed_at", "available_at_time"))
                assert t(it["event_time"]) <= t(it["observed_at"]) <= t(it["available_at_time"])
                n += 1
    assert n > 4000
    assert audit.schema_check(dataset.root)[0] == []


def test_adults_only(dataset):
    ages = [i["age_years"] for c in dataset.cases.values() for i in c["journey"]["items"] if i["data_type"] == "Demographics"]
    assert len(ages) == 200 and all(18 <= a <= 95 for a in ages)


def test_no_identity_fields(dataset):
    banned = {"name", "first_name", "last_name", "full_name", "patient_name", "dob", "date_of_birth", "birth_date",
              "birthdate", "address", "phone", "national_id", "hn", "an"}

    def fields(model):
        out = set(model.model_fields)
        for f in model.model_fields.values():
            for arg in getattr(f.annotation, "__args__", ()) or (f.annotation,):
                inner = getattr(arg, "__args__", (arg,))
                for a in inner:
                    if isinstance(a, type) and issubclass(a, BaseModel):
                        out |= fields(a)
        return out

    for model in (casegraph.IntakeTranscript, casegraph.Demographics, casegraph.Vitals, casegraph.LabSeries,
                  casegraph.MedicationList, casegraph.AllergyList):
        assert not fields(model) & banned, model
    keys = set(re.findall(r'"([a-z_]+)":', "".join(json.dumps(c["journey"]) for c in dataset.cases.values())))
    assert not keys & banned


# ------------------------------------------------------------------ time
def test_decision_times(dataset):
    for cid, c in dataset.cases.items():
        ts = c["journey"]["decision_times"]
        assert len(ts) >= 2 and all(t(a) < t(b) for a, b in zip(ts, ts[1:]))
        s1 = {i["item_id"] for i in c["snapshots"]["T1"]["items"]}
        s2 = {i["item_id"] for i in c["snapshots"]["T2"]["items"]}
        assert s1 < s2, cid
        assert t(ts[0]) >= t(transcript(c["journey"]["items"])["available_at_time"])
        assert c["journey"]["intake_point"] == "front_door"


def test_new_order_not_at_T1(dataset):
    for c in dataset.cases.values():
        assert not [i for i in c["snapshots"]["T1"]["items"] if i.get("list_source") == "new_order"]


def test_future_items_exist_and_excluded(dataset):
    with_future = 0
    for c in dataset.cases.values():
        tmax = max(t(x) for x in c["journey"]["decision_times"])
        future = {i["item_id"] for i in c["journey"]["items"] if t(i["available_at_time"]) > tmax}
        with_future += bool(future)
        for s in c["snapshots"].values():
            assert not future & {i["item_id"] for i in s["items"]}
    assert with_future >= 0.2 * len(dataset.cases)


# ------------------------------------------------------------------ audit
def test_leakage_audit_passes_generated(dataset, tmp_path):
    report = tmp_path / "audit_report.json"
    r = run_cli("scripts/temporal_leakage_audit.py", "--dataset", str(dataset.root), "--report", str(report))
    assert r.returncode == 0, r.stdout + r.stderr
    rep = load(report)
    assert rep["status"] == "PASS" and rep["case_x_T"] == rep["case_x_T_pass"] >= 400


def _plant(kind, root):
    first = lambda split: sorted((root / "inputs" / split).iterdir())[0]  # noqa: E731
    case = first("test")
    if kind == "future_item":
        j = load(case / "journey.json")
        s = load(case / "snapshot_T1.json")
        s["items"].append(j["items"][-1])
        (case / "snapshot_T1.json").write_text(json.dumps(s, ensure_ascii=False))
    elif kind == "cross_split":
        pref = load(case / "journey.json")["patient_ref"]
        shutil.copytree(case, root / "inputs" / "train" / "SYNE-9999")
        j = load(root / "inputs" / "train" / "SYNE-9999" / "journey.json")
        j["patient_ref"] = pref
        (root / "inputs" / "train" / "SYNE-9999" / "journey.json").write_text(json.dumps(j, ensure_ascii=False))
    elif kind == "patient_mismatch":
        j = load(case / "journey.json")
        j["items"][0]["patient_ref"] = "SYNP-9999"
        (case / "journey.json").write_text(json.dumps(j, ensure_ascii=False))
    elif kind == "gold_in_input":
        s = load(case / "snapshot_T2.json")
        s["expected_action"] = "suggest"
        (case / "snapshot_T2.json").write_text(json.dumps(s, ensure_ascii=False))
    elif kind == "T_mismatch":
        gp = root / "gold" / "test" / f"{case.name}.json"
        g = load(gp)
        g["decision_times"][0]["T"] = "2030-12-31T23:59:59+07:00"
        gp.write_text(json.dumps(g, ensure_ascii=False))


@pytest.mark.parametrize("kind", ["future_item", "cross_split", "patient_mismatch", "gold_in_input", "T_mismatch"])
def test_audit_detects_planted(kind, dataset, tmp_path):
    root = tmp_path / "ds"
    shutil.copytree(dataset.root, root)
    assert leakage_module().main(["--dataset", str(root)]) == 0
    _plant(kind, root)
    assert leakage_module().main(["--dataset", str(root)]) != 0


def test_audit_legacy_as_of_mode(dataset):
    cid, c = next((k, v) for k, v in dataset.cases.items() if any(i["item_id"].endswith("-LATE") for i in v["journey"]["items"]))
    path = dataset.root / "inputs" / c["split"] / cid
    T2 = c["journey"]["decision_times"][-1]
    r = run_cli("scripts/temporal_leakage_audit.py", str(path / "journey.json"), "--as-of", T2)
    assert r.returncode == 1 and f"{cid}-LATE" in r.stdout
    assert run_cli("scripts/temporal_leakage_audit.py", str(path / "snapshot_T2.json"), "--as-of", T2).returncode == 0


# ------------------------------------------------------------------ gold
def test_gold_separation(dataset):
    names = [c["display_th"] for c in load(TEMPLATES / "departments.json")["codes"]]
    for p in sorted((dataset.root / "inputs").rglob("*")):
        if p.is_file():
            assert p.name == "journey.json" or p.name.startswith("snapshot_")
            text = p.read_text("utf-8")
            for tok in (*audit.GOLD_KEYS, *names, "gold/"):
                assert tok not in text, (p, tok)
    assert audit.gold_separation(dataset.root) == []
    assert not list((dataset.root / "inputs").rglob("*gold*"))


def _rows(dataset):
    return [(cid, c, r) for cid, c in dataset.cases.items() for r in c["gold"]["decision_times"]]


def test_red_flag_subset(dataset):
    refs = {r["ref_id"]: r for r in load(TEMPLATES / "references.json")}
    rules = {r["rule_id"]: r for r in load(TEMPLATES / "red_flags.json")}
    rf_cases = {cid for cid, _, r in _rows(dataset) if r["red_flags"]}
    assert len(rf_cases) >= 0.2 * len(dataset.cases)
    for split in ("train", "dev", "test"):
        ids = [cid for cid, c in dataset.cases.items() if c["split"] == split]
        assert sum(cid in rf_cases for cid in ids) >= 0.2 * len(ids), split
    uses = {r: {cid for cid, _, row in _rows(dataset) for f in row["red_flags"] if f["rule_id"] == r} for r in RULES}
    assert all(len(v) >= 5 for v in uses.values()), {k: len(v) for k, v in uses.items()}
    for _, _, row in _rows(dataset):
        for f in row["red_flags"]:
            assert refs[rules[f["rule_id"]]["source_ref"]].get("pmid")


def test_red_flag_evolves_at_T2(dataset):
    evolving = [cid for cid, c in dataset.cases.items()
                if not c["gold"]["decision_times"][0]["red_flags"] and c["gold"]["decision_times"][1]["red_flags"]]
    assert len(evolving) >= 5
    for cid in evolving:
        rows = dataset.cases[cid]["gold"]["decision_times"]
        assert rows[0]["target_department"] != "12" and rows[1]["target_department"] == "12"


def test_department_labels(dataset):
    dep = load(TEMPLATES / "departments.json")
    assert dep["system"] == "https://terms.sil-th.org/core/CodeSystem/cs-chi-clinic" and dep["version"] == "0.1.2"
    assert {c["code"] for c in dep["codes"]} == DEPT_CODES
    per_code = {}
    for cid, _, r in _rows(dataset):
        assert r["target_department"] in DEPT_CODES
        per_code.setdefault(r["target_department"], set()).add(cid)
        if r["red_flags"]:
            assert r["target_department"] == "12"
    assert set(per_code) == DEPT_CODES and all(len(v) >= 5 for v in per_code.values())


def test_required_fields_gold(dataset):
    missing = {"chief_complaint": set(), "duration": set(), "allergy_status": set()}
    for cid, c, r in _rows(dataset):
        rf = r["required_fields"]
        assert set(rf) == set(missing)
        text = " ".join(x["text"] for x in transcript(c["snapshots"][r["decision_point"]]["items"])["turns"])
        for k, v in rf.items():
            if v == "MISSING":
                missing[k].add(cid)
            else:
                assert v["th_text"] in text, (cid, k)
    any_missing = set().union(*missing.values())
    assert len(any_missing) >= 30 and len(any_missing) >= 0.15 * len(dataset.cases)
    assert all(len(v) >= 8 for v in missing.values())
    rf = {cid for cid, _, r in _rows(dataset) if r["red_flags"]}
    assert len(rf & any_missing) >= 5


def test_missing_info_really_missing(dataset):
    complaints = [c["th"] for c in load(TEMPLATES / "complaints.json")]
    for cid, c, r in _rows(dataset):
        items = c["snapshots"][r["decision_point"]]["items"]
        text = " ".join(x["text"] for x in transcript(items)["turns"] if x["speaker"] == "patient")
        rf = r["required_fields"]
        if rf["chief_complaint"] == "MISSING":
            assert not any(cc in text for cc in complaints), cid
        if rf["duration"] == "MISSING":
            assert not re.search(r"\d+\s*(ชั่วโมง|วัน|สัปดาห์|เดือน)", text), cid
        if rf["allergy_status"] == "MISSING":
            assert "แพ้" not in text, cid
            statuses = {i["status"] for i in items if i["data_type"] == "AllergyList"}
            assert statuses <= {"unknown"} and "no_known_allergy" not in statuses, cid


def test_expected_action_precedence(dataset):
    for cid, _, r in _rows(dataset):
        missing = any(v == "MISSING" for v in r["required_fields"].values())
        want = "escalate" if r["red_flags"] else ("abstain" if missing else "suggest")
        assert r["expected_action"] == want, cid


# ------------------------------------------------------------------ medication
def test_medication_sources(dataset):
    atc = {f["atc_code"] for f in load(TEMPLATES / "formulary.json")}
    with_meds = 0
    for cid, c in dataset.cases.items():
        lists = {i["list_source"]: i for i in c["journey"]["items"] if i["data_type"] == "MedicationList"}
        if not lists:
            continue
        with_meds += 1
        assert set(lists) == {"home_list", "patient_reported", "new_order"}, cid
        assert lists["patient_reported"]["derived_from"] == transcript(c["journey"]["items"])["item_id"]
        for lst in lists.values():
            for e in lst["entries"]:
                assert e["generic_name"] and e["atc_code"] in atc and e["dose_value"] > 0 and e["dose_unit"]
                assert e["frequency"] in {"OD", "BID", "TID", "QID", "HS"} and e["route"]
    assert with_meds >= 0.85 * len(dataset.cases)


def test_injection_counts(dataset):
    for itype in ISSUE_TYPES:
        recs = [r for r in dataset.injections if r["issue_type"] == itype]
        test_recs = [r for r in recs if dataset.cases[r["case_id"]]["split"] == "test"]
        assert len(recs) >= 10 and len(test_recs) >= 2, itype
    med_cases = [cid for cid, c in dataset.cases.items()
                 if any(i["data_type"] == "MedicationList" for i in c["journey"]["items"])]
    injected = {r["case_id"] for r in dataset.injections}
    assert sum(cid not in injected for cid in med_cases) >= 0.3 * len(med_cases)


def test_injection_log_one_to_one(dataset):
    keys = {"injection_id", "case_id", "issue_type", "drugs", "item_ids", "list_sources", "field", "value_before",
            "value_after"}
    log = {r["injection_id"]: r for r in dataset.injections}
    assert len(log) == len(dataset.injections) and all(set(r) == keys for r in dataset.injections)
    gold = {}
    for cid, c in dataset.cases.items():
        rows = c["gold"]["decision_times"]
        assert rows[0]["medication_issues"] == []  # new order not yet available at T1
        for issue in rows[-1]["medication_issues"]:
            gold[issue["injection_id"]] = (cid, issue)
    assert set(gold) == set(log)
    for iid, (cid, issue) in gold.items():
        assert log[iid]["case_id"] == cid and log[iid]["issue_type"] == issue["issue_type"]
        assert log[iid]["drugs"] == issue["drugs"]
    allergy = [r for r in dataset.injections if r["issue_type"] == "allergy_conflict"]
    for r in allergy:
        c = dataset.cases[r["case_id"]]
        T2 = t(c["journey"]["decision_times"][-1])
        al = [i for i in c["journey"]["items"] if i["data_type"] == "AllergyList"]
        assert al and al[0]["status"] == "known" and t(al[0]["available_at_time"]) <= T2


# ------------------------------------------------------------------ text and safety
def test_transcripts_wellformed(dataset):
    drugs = sorted((f["generic_name"] for f in load(TEMPLATES / "formulary.json")), key=len, reverse=True)
    used = set()
    for cid, c in dataset.cases.items():
        tx = transcript(c["journey"]["items"])
        turns = tx["turns"]
        arrival, T1 = t(c["journey"]["arrival_time"]), t(c["journey"]["decision_times"][0])
        assert len(turns) >= 6 and turns[0]["speaker"] == "nurse"
        assert all(x["speaker"] in {"nurse", "patient"} for x in turns)
        times = [t(x["spoken_at"]) for x in turns]
        assert all(a < b for a, b in zip(times, times[1:])) and arrival <= times[0] and times[-1] <= T1
        for x in turns:
            assert unicodedata.normalize("NFC", x["text"]) == x["text"]
            s = x["text"]
            for d in drugs:
                s = s.replace(d, "")
            letters = [ch for ch in s if ch.isalpha()]
            assert letters and sum("฀" <= ch <= "๿" for ch in letters) / len(letters) >= 0.7, (cid, x["text"])
        used.add(c["gold"]["scenario"]["complaint_id"])
    assert len(used) >= 20


def test_identifier_scan_clean(dataset):
    assert audit.identifier_scan([dataset.root / "inputs", dataset.root / "gold", TEMPLATES]) == []


def test_identifier_scanner_self_test():
    result = audit.identifier_self_test()
    assert set(result) == set(audit.IDENTIFIER_PATTERNS) and all(result.values())
    assert audit.scan_text("ปวดหัว 3 วัน SYNE-0001 2030-01-05T10:00:00+07:00 120 มิลลิกรัม") == []


GUARD = r"""
import json, sys
from pathlib import Path
from data_factory.generate import generate
generate(1, Path(sys.argv[1]))  # warm imports before the hook
events = []
def hook(ev, args):
    if ev == "open":
        events.append(["open", str(args[0])])
    elif ev.startswith("socket."):
        events.append([ev, ""])
sys.addaudithook(hook)
generate(20260926, Path(sys.argv[2]))
print(json.dumps(events))
"""


def test_generator_reads_only_templates(tmp_path):
    out = (tmp_path / "out").resolve()
    r = run_cli("-c", GUARD, str(tmp_path / "warm"), str(out))
    assert r.returncode == 0, r.stderr
    events = json.loads(r.stdout.strip().splitlines()[-1])
    assert not [e for e in events if e[0].startswith("socket.")]
    allowed = (str((REPO_ROOT / "data_factory").resolve()), str(out))
    opens = [e[1] for e in events if e[0] == "open"]
    assert opens and not [p for p in opens if not os.path.realpath(p).startswith(allowed)]


def test_no_real_data_refs():
    needles = re.compile("|".join(["mi" + "mic", "physio" + "net", "hospital" + r"[_/ -]?data", "/data" + "/raw"]), re.I)
    for p in sorted((REPO_ROOT / "data_factory").rglob("*.py")):
        assert not needles.search(p.read_text("utf-8")), p


def test_templates_have_source_ref():
    refs = {r["ref_id"]: r for r in load(TEMPLATES / "references.json")}
    assert all(r.get("pmid") or r.get("doi") or r.get("url") for r in refs.values())
    vb = load(TEMPLATES / "vitals_bands.json")
    dep = load(TEMPLATES / "departments.json")
    records = [*load(TEMPLATES / "complaints.json"), *load(TEMPLATES / "red_flags.json"), *vb["normal"],
               *vb["red_flag_variants"], *vb["near_miss_variants"], vb["anaphylaxis_host"],
               *load(TEMPLATES / "formulary.json"), *load(TEMPLATES / "allergy_classes.json"), dep, *dep["codes"],
               *load(TEMPLATES / "issue_types.json"), *load(TEMPLATES / "labs.json")]
    unresolved = [r for r in records if r.get("source_ref") not in refs]
    unresolved += [r for r in load(TEMPLATES / "complaints.json") if r.get("department_source_ref") not in refs]
    assert unresolved == []


# ------------------------------------------------------------------ integrity
def test_manifest_detects_tamper(dataset, tmp_path):
    root = tmp_path / "ds"
    shutil.copytree(dataset.root, root)
    assert audit.run_audit(root, write_report=False)["status"] == "PASS"
    m = dataset.manifest
    assert {"seed", "generator_version", "source_code_sha256", "counts", "files", "tree_sha256"} <= set(m)
    assert m["seed"] == SEED and len(m["files"]) == len([p for p in dataset.root.rglob("*") if p.is_file()]) - 1
    gp = next((root / "gold" / "test").iterdir())
    gp.write_bytes(gp.read_bytes().replace(b'"suggest"', b'"escalate"', 1).replace(b'"abstain"', b'"escalate"', 1)
                   + b" ")
    rep = audit.run_audit(root, write_report=False)
    assert rep["status"] == "FAIL" and rep["steps"]["manifest"].startswith("FAIL")


def test_datacard_present(dataset):
    text = (dataset.root / "DATACARD.md").read_text("utf-8")
    assert "synthetic, not for clinical use, not expert-reviewed, system evaluation only" in text
