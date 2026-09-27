"""S5R2 (Pharma Agent v1.2): dose per administration, explicit unverifiable doses, frequency status,
inactive entries, allergy basis, atomic writes, versions, schema v2 and reassurance phrasing."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.gateway.provider import ProviderResult
from app.pharma.db import pharma_issue_decisions, pharma_issues, pharma_runs
from app.pharma.fixtures import get_fixture
from app.pharma.mock_rules import EXTRACT_TASK, MOCK_RULES_VERSION, extract_handler, parse_entry
from app.pharma.phrasing import TEMPLATE_VERSION, phrase_input, template_text, validate_text
from app.pharma.pipeline import PIPELINE_VERSION, issue_signature
from app.pharma.rules import RULE_VERSIONS, RULES_VERSION

from .conftest import PASSWORDS
from .pharma_helpers import notices, of_type, run, snapshot
from .test_pharma_pipeline import _scripted_invoke

REASONS = ("unverifiable", "not_recognised", "not_stated")

# ---------------------------------------------------------------- extraction (A05, A06, A14)

QUANTITY_FORMS = {
    "Warfarin 3 mg 2 tabs od": (2.0, "q24h"),
    "Warfarin 3 mg 1 tab od": (1.0, "q24h"),
    "เมทฟอร์มิน 500 มก. 2x2": (2.0, "q12h"),
    "เมทฟอร์มิน 500 มก. 1x2": (1.0, "q12h"),
    "Metformin 500 mg 2 tablets bid": (2.0, "q12h"),
    "Paracetamol 500 mg 2 เม็ด วันละ 3 ครั้ง": (2.0, "q8h"),
    "Warfarin 3 mg 1/2 tab od": (0.5, "q24h"),
    "วาร์ฟาริน 3 มก. ครึ่งเม็ด วันละ 1 ครั้ง": (0.5, "q24h"),
    "Warfarin 2 mg ½ เม็ด od": (0.5, "q24h"),
    "Warfarin 1 mg 1.5 tabs od": (1.5, "q24h"),
    "Warfarin 3 mg od": (None, "q24h"),
}


@pytest.mark.parametrize("text", list(QUANTITY_FORMS))
def test_extract_quantity_forms(text):
    quantity, freq = QUANTITY_FORMS[text]
    e = parse_entry(text)
    assert e["quantity"] == quantity  # exact: 0.5 / 1.5, never an integer read of a fraction, never a defaulted 1
    assert e["frequency_code"] == freq and e["frequency_status"] == "recognised"
    assert e["dose_status"] == "resolved" and e["dose_value"] is not None and e["dose_unverifiable_reason"] is None


UNVERIFIABLE_FORMS = {
    "Warfarin 3 mg od except 1.5 mg on Sunday": "variable_regimen",
    "วาร์ฟาริน 3 มก. วันละ 1 เม็ด ยกเว้นวันอาทิตย์ครึ่งเม็ด": "variable_regimen",
    "Warfarin 3 mg alternating with 1.5 mg daily": "variable_regimen",
    "Paracetamol syrup 250 mg/5 ml 10 ml q6h prn": "liquid_volume",
    "พาราเซตามอล น้ำเชื่อม 120 มก./5 มล. 5 มล. ทุก 6 ชั่วโมง": "liquid_volume",
    "Warfarin 3 mg + 1 mg od": "multiple_strengths",
    "Warfarin 3 mg and 2 mg tabs od": "multiple_strengths",
    "Metformin 500 mg 2 tabs 1x2": "ambiguous_quantity",
}


@pytest.mark.parametrize("text", list(UNVERIFIABLE_FORMS))
def test_extract_unverifiable_forms(text):
    e = parse_entry(text)
    assert (e["dose_status"], e["dose_unverifiable_reason"]) == ("unverifiable", UNVERIFIABLE_FORMS[text])
    assert e["dose_value"] is None and e["dose_unit"] is None and e["quantity"] is None  # no partial value


def test_combination_slash_keeps_gold():
    # "875/125 mg" keeps its s5/s5r reading: no dose read, not a multiple-strength entry.
    e = parse_entry("Augmentin 875/125 mg bid")
    assert (e["dose_value"], e["dose_status"], e["frequency_code"]) == (None, "not_stated", "q12h")


FREQ_NOT_RECOGNISED = {
    "q4h": "Metformin 500 mg q4h",
    "every_other_day": "Metformin 500 mg every other day",
    "3_times_a_week": "Metformin 500 mg 3 times a week",
    "วันเว้นวัน": "เมทฟอร์มิน 500 มก. วันเว้นวัน",
    "สัปดาห์ละ_1_ครั้ง": "เมทฟอร์มิน 500 มก. สัปดาห์ละ 1 ครั้ง",
}


@pytest.mark.parametrize("case", list(FREQ_NOT_RECOGNISED))
def test_extract_frequency_not_recognised(case):
    text = FREQ_NOT_RECOGNISED[case]
    e = parse_entry(text)
    assert (e["frequency_code"], e["frequency_status"]) == (None, "not_recognised")
    result = run(snapshot(home=["Metformin 500 mg bid"], orders=[text]))
    [mf] = of_type(result, "missing_field")
    assert (mf["field"], mf["detail"]["field_status"]) == ("frequency", "not_recognised")
    assert result["unchecked_by_reason"]["not_recognised"] == 1


def test_extract_frequency_not_stated_control():
    e = parse_entry("Amlodipine 5 mg")
    assert (e["frequency_code"], e["frequency_status"]) == (None, "not_stated")
    [mf] = of_type(run(snapshot(home=["Amlodipine 5 mg daily"], orders=["Amlodipine 5 mg"])), "missing_field")
    assert mf["detail"]["field_status"] == "not_stated"


# ---------------------------------------------------------------- dose per administration (A03, A04)

QUANTITY_MISMATCH = {
    "warfarin_en": ("Warfarin 3 mg 2 tabs od", "Warfarin 3 mg 1 tab od", {6.0, 3.0}),
    "metformin_th_2x2": ("เมทฟอร์มิน 500 มก. 2x2", "เมทฟอร์มิน 500 มก. 1x2", {1000.0, 500.0}),
    "stated_amount": ("Warfarin 3 mg od", "Warfarin 3 mg 2 tabs od", {3.0, 6.0}),
    "fraction": ("Warfarin 3 mg 1/2 tab od", "Warfarin 3 mg 1 tab od", {1.5, 3.0}),
}


@pytest.mark.parametrize("case", list(QUANTITY_MISMATCH))
def test_rule_dose_quantity_mismatch(case):
    home, order, per_admin = QUANTITY_MISMATCH[case]
    result = run(snapshot(home=[home], orders=[order]))
    assert [i["type"] for i in result["issues"]] == ["dose_mismatch"]
    [issue] = result["issues"]
    assert not issue["unverifiable"]
    srcs = issue["conflicting_sources"]
    assert {s["dose_per_administration"] for s in srcs} == per_admin
    for s in srcs:
        assert s["dose_basis"] == ("stated_amount" if s["quantity"] is None else "strength_x_quantity")
        assert (s["dose_status"], s["frequency_status"]) == ("resolved", "recognised")
    assert result["status"] == "complete" and result["unchecked_comparisons"] == 0


# Checker findings on v1.2: a mixed number lost its whole part (F1) and a quantity written straight after a Thai
# word was not read (F2). Each hid a >= 2-fold dose difference behind a "complete" run.
QUANTITY_FORMS_REGRESSION = {
    "Warfarin 3 mg 1 1/2 tab od": 1.5,
    "Warfarin 3 mg 1½ tab od": 1.5,
    "Warfarin 3 mg 2 1/2 เม็ด od": 2.5,
    "เมทฟอร์มิน 500 มก. ครั้งละ2เม็ด วันละ2ครั้ง": 2.0,
    "วาร์ฟาริน 3 มก. วันละครึ่งเม็ด": 0.5,
    "เมทฟอร์มิน500มก. 2x2": 2.0,
}


@pytest.mark.parametrize("text", list(QUANTITY_FORMS_REGRESSION))
def test_extract_quantity_mixed_number_and_thai_attached(text):
    e = parse_entry(text)
    assert e["quantity"] == QUANTITY_FORMS_REGRESSION[text] and e["dose_status"] == "resolved"


def test_extract_stray_number_before_quantity_is_unverifiable():
    # "1 0.5 tab" is not a known form: never drop the leading number and read 0.5.
    e = parse_entry("Warfarin 3 mg 1 0.5 tab od")
    assert (e["dose_status"], e["dose_unverifiable_reason"], e["quantity"]) == ("unverifiable", "ambiguous_quantity", None)


# Checker findings F3-F5 on v1.2 (fix 2): a mixed number joined by "-"/"and" lost its whole part (F3), Thai
# "N เม็ดครึ่ง" dropped the half (F4), and a range "1-2 tabs" was read as its upper end (F5).
QUANTITY_FORMS_REGRESSION_2 = {
    "Warfarin 3 mg 1-1/2 tab od": 1.5,
    "Warfarin 3 mg 1 and 1/2 tab od": 1.5,
    "Warfarin 3 mg 1 - 1/2 tab od": 1.5,
    "วาร์ฟาริน 3 มก. 1และ1/2 เม็ด วันละ 1 ครั้ง": 1.5,
    "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง": 1.5,
    "วาร์ฟาริน 3 มก. 2เม็ดครึ่ง วันละ 1 ครั้ง": 2.5,
}


@pytest.mark.parametrize("text", list(QUANTITY_FORMS_REGRESSION_2))
def test_extract_quantity_joined_mixed_number_and_thai_half(text):
    e = parse_entry(text)
    assert e["quantity"] == QUANTITY_FORMS_REGRESSION_2[text] and e["dose_status"] == "resolved"


AMBIGUOUS_QUANTITY_FORMS = [
    "พาราเซตามอล 500 มก. ครั้งละ 1-2 เม็ด ทุก 6 ชั่วโมง เวลาปวด",  # range
    "Paracetamol 500 mg 1-2 tabs q6h prn",
    "Paracetamol 500 mg 1 to 2 tabs q6h prn",
    "Paracetamol 500 mg 1 or 2 tabs q6h prn",
    "Warfarin 3 mg 1/2-1 tab od",
    "Warfarin 3 mg ½-1 tab od",
    "Metformin 500 mg 1-2x2",
    "Warfarin 3 mg one tab od",  # quantity word the pattern set cannot read
    "วาร์ฟาริน 3 มก. สองเม็ด วันละ 1 ครั้ง",
    "Warfarin 3 mg 1/0 tab od",
    "Warfarin 3 mg 1.5 เม็ดครึ่ง od",
]


@pytest.mark.parametrize("text", AMBIGUOUS_QUANTITY_FORMS)
def test_extract_range_or_unknown_quantity_is_unverifiable(text):
    e = parse_entry(text)
    assert (e["dose_status"], e["dose_unverifiable_reason"], e["quantity"], e["dose_value"]) == (
        "unverifiable", "ambiguous_quantity", None, None)


def test_range_quantity_raises_missing_dose_not_silent_pass():
    # F5: never guess the upper end of a range; the comparison is unchecked and visible.
    result = run(snapshot(home=["พาราเซตามอล 500 มก. ครั้งละ 1-2 เม็ด ทุก 6 ชั่วโมง เวลาปวด"],
                          orders=["Paracetamol 1000 mg q6h prn"]))
    [mf] = [i for i in of_type(result, "missing_field") if i["field"] == "dose"]
    assert (mf["detail"]["field_status"], mf["detail"]["unverifiable_reason"]) == ("unverifiable", "ambiguous_quantity")
    assert of_type(result, "dose_mismatch") == [] and result["unchecked_comparisons"] >= 1


REGRESSION_MISMATCH = {
    "mixed_number": ("Warfarin 3 mg 1 1/2 tab od", "Warfarin 1.5 mg od", {4.5, 1.5}),
    "thai_attached": ("เมทฟอร์มิน 500 มก. ครั้งละ2เม็ด วันละ2ครั้ง", "Metformin 500 mg 1 tab bid", {1000.0, 500.0}),
    "thai_attached_half": ("วาร์ฟาริน 3 มก. วันละครึ่งเม็ด", "Warfarin 3 mg 1 tab od", {1.5, 3.0}),
    "hyphen_mixed_number": ("Warfarin 3 mg 1-1/2 tab od", "Warfarin 1.5 mg od", {4.5, 1.5}),
    "and_mixed_number": ("Warfarin 3 mg 1 and 1/2 tab od", "Warfarin 1.5 mg od", {4.5, 1.5}),
    "thai_n_and_a_half": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง", "Warfarin 3 mg 1 tab od", {4.5, 3.0}),
}


@pytest.mark.parametrize("case", list(REGRESSION_MISMATCH))
def test_rule_dose_quantity_mismatch_regression(case):
    home, order, per_admin = REGRESSION_MISMATCH[case]
    result = run(snapshot(home=[home], orders=[order]))
    [issue] = of_type(result, "dose_mismatch")
    assert not issue["unverifiable"]
    assert {s["dose_per_administration"] for s in issue["conflicting_sources"]} == per_admin


def test_rule_dose_quantity_equivalent():
    result = run(snapshot(home=["Metformin 500 mg 2 tabs bid"], orders=["Metformin 1000 mg bid"]))
    assert of_type(result, "dose_mismatch") == [] and of_type(result, "missing_field") == []
    assert result["issues"] == [] and result["comparisons_made"] == 2 and result["unchecked_comparisons"] == 0
    # fraction x strength equals a stated amount too
    assert run(snapshot(home=["Warfarin 6 mg 1/2 tab od"], orders=["Warfarin 3 mg od"]))["issues"] == []


# ---------------------------------------------------------------- unverifiable is never a silent pass (A06)

UNVERIFIABLE_CASES = {
    "variable_en": ("Warfarin 3 mg od", "Warfarin 3 mg od except 1.5 mg on Sunday", "variable_regimen"),
    "variable_th": ("Warfarin 3 mg od", "วาร์ฟาริน 3 มก. วันละ 1 เม็ด ยกเว้นวันอาทิตย์ครึ่งเม็ด", "variable_regimen"),
    "liquid_en": ("Paracetamol 500 mg q6h", "Paracetamol syrup 250 mg/5 ml 10 ml q6h prn", "liquid_volume"),
    "liquid_th": ("Paracetamol 500 mg q6h", "พาราเซตามอล น้ำเชื่อม 120 มก./5 มล. 5 มล. ทุก 6 ชั่วโมง", "liquid_volume"),
    "multi_strength": ("Warfarin 4 mg od", "Warfarin 3 mg + 1 mg od", "multiple_strengths"),
    "ambiguous_quantity": ("Metformin 500 mg bid", "Metformin 500 mg 2 tabs 1x2", "ambiguous_quantity"),
    "single_source": (None, "Warfarin 3 mg od except 1.5 mg on Sunday", "variable_regimen"),
}


@pytest.mark.parametrize("case", list(UNVERIFIABLE_CASES))
def test_unverifiable_dose_explicit(case):
    home, order, reason = UNVERIFIABLE_CASES[case]
    result = run(snapshot(home=[home] if home else None, orders=[order]))
    order_rec = next(r for r in result["extraction"] if r["source_type"] == "new_order")
    [entry] = order_rec["entries"]
    assert (entry["dose_value"], entry["dose_unit"], entry["dose_status"], entry["dose_unverifiable_reason"]) == (
        None, None, "unverifiable", reason)
    dose_issues = [i for i in of_type(result, "missing_field") if i["field"] == "dose"]
    assert len(dose_issues) == 1
    [mf] = dose_issues
    assert mf["conflicting_sources"][0]["source_type"] == "new_order"
    assert (mf["detail"]["field_status"], mf["detail"]["unverifiable_reason"]) == ("unverifiable", reason)
    assert of_type(result, "dose_mismatch") == []  # never produced (nor suppressed) from that entry
    pairs = 1 if home else 0  # cross-source pairs holding the entry
    assert result["unchecked_comparisons"] == pairs == result["unchecked_by_reason"]["unverifiable"]
    assert sum(result["unchecked_by_reason"].values()) == result["unchecked_comparisons"]
    assert result["issues"] == [mf]  # frequency still compared: same code in both sources


def test_unchecked_by_reason_sums():
    result = run(snapshot(
        home=["Metformin 500 mg bid", "Warfarin 3 mg od"],
        reported=["Metformin bid"],                                          # dose not stated
        orders=["Metformin 500 mg + 250 mg bid", "Warfarin 3 mg every other day"],  # unverifiable; not recognised
    ))
    # metformin dose: home-reported not_stated; home-order unverifiable; reported-order (both null) -> unverifiable
    # warfarin frequency: home-order not_recognised. Made: metformin freq x3, warfarin dose x1.
    assert result["unchecked_by_reason"] == {"unverifiable": 2, "not_recognised": 1, "not_stated": 1}
    assert result["unchecked_comparisons"] == 4 == sum(result["unchecked_by_reason"].values())
    assert result["comparisons_made"] == 4
    statuses = sorted((i["ingredients"][0], i["field"], i["detail"]["field_status"]) for i in of_type(result, "missing_field"))
    assert statuses == [("metformin", "dose", "not_stated"), ("metformin", "dose", "unverifiable"),
                        ("warfarin", "frequency", "not_recognised")]


# ---------------------------------------------------------------- C1 inactive entries (A12)


def test_rule_missing_field_skips_inactive():
    for text, field in (("Metformin bid", "dose"), ("Metformin 500 mg", "frequency")):
        ended = {"text": text, "discontinue_intent": True, "reason": "synthetic: course completed"}
        inactive = run(snapshot(orders=[ended, "Amlodipine 5 mg daily"]))
        assert of_type(inactive, "missing_field") == []
        active = run(snapshot(orders=[text, "Amlodipine 5 mg daily"]))
        assert [(i["type"], i["field"]) for i in active["issues"]] == [("missing_field", field)]
    # an inactive entry still appears as another source on another entry's issue
    other = run(snapshot(home=["Metformin 500 mg"], orders=[{"text": "Metformin bid", "discontinue_intent": True,
                                                             "reason": "synthetic: held"}]))
    [mf] = of_type(other, "missing_field")
    assert mf["conflicting_sources"][0]["source_type"] == "home_list" and len(mf["conflicting_sources"]) == 2


# ---------------------------------------------------------------- C2 allergy basis (A13)

ALLERGY_BASIS = {
    "direct": ("แพ้ยา ซาร่า (ผื่น)", "Paracetamol 500 mg prn", "allergy_direct"),
    "class": ("Penicillin (rash)", "Amoxicillin 500 mg tid", "allergy_class"),
    "cross_reactivity": ("Penicillin (rash)", "Cephalexin 500 mg qid", "allergy_cross_reactivity"),
}


@pytest.mark.parametrize("case", list(ALLERGY_BASIS))
def test_allergy_issue_basis(case):
    allergy, order, subtype = ALLERGY_BASIS[case]
    result = run(snapshot(orders=[order], allergies=[allergy]))
    [issue] = of_type(result, subtype)
    detail = issue["detail"]
    assert detail["basis"]
    form_version = result["formulary_version"]
    if subtype == "allergy_direct":
        assert "acetaminophen" in detail["basis"] and "RxCUI" in detail["basis"] and detail["formulary_version"] == form_version
    elif subtype == "allergy_class":
        assert detail["class_name"] and detail["class_source"] and detail["formulary_version"] == form_version
        assert detail["class_name"] in detail["basis"]
    else:
        assert "doi:" in detail["citation"] and detail["clinical_review_status"] == "pending_pharmacist"
        assert "pending pharmacist sign-off" in detail["basis"]


# ---------------------------------------------------------------- C4 single-transaction writes (A15)


def _client(app) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/api/auth/login", json={"username": "pharmacist1", "password": PASSWORDS["pharmacist1"]}).status_code == 200
    return c


def _count(app, table) -> int:
    with app.state.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar()


def _boom(*args, **kwargs):
    raise RuntimeError("forced audit failure (test)")


def test_reconcile_atomic_with_audit(app, audit_rows, monkeypatch):
    with _client(app) as c:
        monkeypatch.setattr("app.pharma.router.insert_audit", _boom)
        resp = c.post("/api/pharma/reconcile", json={"fixture_ref": "demo-01"})
        assert resp.status_code >= 500
        assert _count(app, pharma_runs) == 0 and _count(app, pharma_issues) == 0
        assert not [r for r in audit_rows() if r["action"] == "pharma.reconcile"]
        monkeypatch.undo()
        ok = c.post("/api/pharma/reconcile", json={"fixture_ref": "demo-01"})
        assert ok.status_code == 200
        assert _count(app, pharma_runs) == 1 and _count(app, pharma_issues) == len(ok.json()["issues"])
        assert len([r for r in audit_rows() if r["action"] == "pharma.reconcile"]) == 1


def test_decision_atomic_with_audit(app, audit_rows, monkeypatch):
    with _client(app) as c:
        issue_id = c.post("/api/pharma/reconcile", json={"fixture_ref": "demo-01"}).json()["issues"][0]["issue_id"]
        decisions_before = [r for r in audit_rows() if r["action"].startswith("pharma.issue.")]
        monkeypatch.setattr("app.pharma.router.insert_audit", _boom)
        assert c.post(f"/api/pharma/issues/{issue_id}/confirm").status_code >= 500
        assert c.post(f"/api/pharma/issues/{issue_id}/dismiss", json={"reason": "synthetic"}).status_code >= 500
        assert _count(app, pharma_issue_decisions) == 0
        monkeypatch.undo()
        retry = c.post(f"/api/pharma/issues/{issue_id}/confirm")
        assert retry.status_code == 200  # no 409: the failed attempt left no decision row
        assert _count(app, pharma_issue_decisions) == 1
        after = [r for r in audit_rows() if r["action"].startswith("pharma.issue.")]
        assert len(after) == len(decisions_before) + 1 and after[-1]["details"]["issue_id"] == issue_id


# ---------------------------------------------------------------- C5 versions and schema v2 (A16)


def test_versions_bumped():
    assert MOCK_RULES_VERSION == "s5-mock-rules-1.2.0"
    assert TEMPLATE_VERSION == "template-1.1.0"
    assert RULES_VERSION == "s5-rules-2.1.0"
    assert RULE_VERSIONS["dose_mismatch"] == "1.2.0" and RULE_VERSIONS["missing_field"] == "2.1.0"
    assert {RULE_VERSIONS[t] for t in ("allergy_direct", "allergy_class", "allergy_cross_reactivity")} == {"1.1.0"}
    assert PIPELINE_VERSION == "s5-pipeline-2.1.0"
    assert EXTRACT_TASK == "pharma.extract.v2"
    r = run(get_fixture("demo-01"))
    assert (r["extract_mock_version"], r["template_version"], r["rules_version"], r["pipeline_version"]) == (
        MOCK_RULES_VERSION, TEMPLATE_VERSION, RULES_VERSION, PIPELINE_VERSION)
    assert r["rule_versions"] == RULE_VERSIONS and r["extract_task"] == "pharma.extract.v2"
    assert {c["task"] for c in r["gateway_calls"]} == {"pharma.extract.v2", "pharma.phrase.v1"}


NEW_FIELDS = ("quantity", "dose_status", "dose_unverifiable_reason", "frequency_status")


@pytest.mark.parametrize("missing", NEW_FIELDS)
def test_extract_v2_schema_required_fields(missing):
    good = extract_handler({"entries": ["Metformin 500 mg bid"]})
    bad = {"entries": [{k: v for k, v in e.items() if k != missing} for e in good["entries"]]}
    result = ProviderResult(status="ok", model_version="scripted-v1-shape", output=bad)
    r = run(snapshot(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg bid"]),
            invoke=_scripted_invoke(extract_result=result))
    assert r["status"] == "incomplete"
    assert {rec["failure_reason"] for rec in r["extraction"]} == {"schema_invalid"}
    assert len(notices(r, "source_unreadable")) == 2 and r["issues"] == []


def test_extract_v2_schema_rejects_partial_dose():
    good = extract_handler({"entries": ["Warfarin 3 mg od except 1.5 mg on Sunday"]})["entries"][0]
    partial = good | {"dose_value": 3.0, "dose_unit": "mg"}  # unverifiable must not carry a value
    result = ProviderResult(status="ok", model_version="m", output={"entries": [partial]})
    r = run(snapshot(orders=["Warfarin 3 mg od except 1.5 mg on Sunday"]), invoke=_scripted_invoke(extract_result=result))
    assert r["status"] == "incomplete" and r["extraction"][0]["failure_reason"] == "schema_invalid"


# ---------------------------------------------------------------- C6 reassurance phrasing (A17)

# One snapshot per issue type (synthetic).
TYPE_SNAPSHOTS = {
    "allergy_direct": dict(orders=["Brufen 400 mg tid"], allergies=["ibuprofen"]),
    "allergy_class": dict(orders=["Amoxicillin 500 mg tid"], allergies=["Penicillin (rash)"]),
    "allergy_cross_reactivity": dict(orders=["Cephalexin 500 mg qid"], allergies=["Penicillin (rash)"]),
    "duplication_ingredient": dict(orders=["Tylenol 500 mg prn", "Sara 500 mg prn"]),
    "duplication_class": dict(orders=["Simvastatin 20 mg daily", "Lipitor 40 mg daily"]),
    "dose_mismatch": dict(home=["Warfarin 3 mg 1 tab od"], orders=["Warfarin 3 mg 2 tabs od"]),
    "frequency_mismatch": dict(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg tid"]),
    "missing_field": dict(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg every other day"]),
    "omission": dict(home=["Losartan 50 mg daily", "Amlodipine 5 mg daily"], orders=["Amlodipine 5 mg daily"]),
}
REASSURANCE = {
    "allergy_direct": ("Patient tolerated it before.", "ไม่แพ้"),
    "allergy_class": ("The patient is not allergic.", "ไม่แพ้ยานี้"),
    "allergy_cross_reactivity": ("No allergy expected here.", "ไม่แพ้"),
    "duplication_ingredient": ("This is not a duplicate.", "ไม่ซ้ำ"),
    "duplication_class": ("There is no duplication.", "ไม่ซ้ำกัน"),
    "dose_mismatch": ("The doses match.", "ขนาดยาตรงกัน"),
    "frequency_mismatch": ("Same frequency in practice.", "ความถี่ตรงกัน"),
    "missing_field": ("The dose is stated elsewhere, record complete.", "ไม่มีปัญหา"),
    "omission": ("It was intentionally omitted.", "ปลอดภัย"),
}
PHRASE_CASES = [(t, lang) for t in REASSURANCE for lang in ("en", "th")]


@pytest.mark.parametrize("kind,lang", PHRASE_CASES, ids=[f"{t}-{lang}" for t, lang in PHRASE_CASES])
def test_phrasing_rejects_reassurance(kind, lang):
    phrase = REASSURANCE[kind][0 if lang == "en" else 1]

    def reassuring(inputs):
        return {"phrasings": [
            {"issue_id": i["issue_id"],
             "text": " ".join(["Mock phrasing.", *i["source_labels"], *i["ingredients"], phrase, "For pharmacist review."])}
            for i in inputs["issues"]]}

    snap = snapshot(**TYPE_SNAPSHOTS[kind])
    base = run(snap, mode="rules_only")
    r = run(snap, invoke=_scripted_invoke(phrase_output=reassuring))
    targets = of_type(r, kind)
    assert targets
    for issue in targets:
        assert issue["phrasing"]["source"] == "template_fallback"
        assert issue["phrasing"]["fallback_reason"] == "reassurance_phrase"
        assert phrase not in issue["phrasing"]["text"]
    assert [issue_signature(i) for i in r["issues"]] == [issue_signature(i) for i in base["issues"]]


def test_templates_pass_validation():
    snaps = [snapshot(**kw) for kw in TYPE_SNAPSHOTS.values()]
    snaps += [get_fixture(ref) for ref in ("demo-01", "demo-02", "demo-03", "demo-quantity", "demo-unverifiable")]
    snaps += [snapshot(home=[h] if h else None, orders=[o]) for h, o, _ in UNVERIFIABLE_CASES.values()]
    snaps += [snapshot(home=["Lantus 10 units hs"], orders=["Lantus 10 mg hs"]), snapshot(home=["Metformin bid"], orders=["Metformin 500 mg bid"])]
    seen = set()
    for snap in snaps:
        for issue in run(snap, mode="rules_only")["issues"]:
            item = phrase_input(issue)
            text = template_text(item)
            assert validate_text(text, item) is None, (issue["type"], text)
            assert "differs" not in text or not issue["unverifiable"]
            seen.add((issue["type"], issue["detail"].get("field_status"), issue["unverifiable"]))
    assert {t for t, _, _ in seen} == set(TYPE_SNAPSHOTS)
    assert {("missing_field", s, False) for s in REASONS} <= seen and ("dose_mismatch", None, True) in seen
