"""S5 pipeline tests: gateway use, determinism, isolation, extraction, normalisation, phrasing,
fail-safe behaviour and temporal gating (A02-A04, A07, A08, A12, A13)."""

import ast
import json
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.gateway import build_provider
from app.gateway.contract import GatewayRequest
from app.gateway.provider import ProviderResult
from app.pharma.fixtures import get_fixture
from app.pharma.formulary import load_formulary
from app.pharma.mock_rules import EXTRACT_TASK, PHRASE_TASK, extract_handler
from app.pharma.pipeline import issue_signature

from .conftest import REPO_ROOT
from .pharma_helpers import AFTER, allergy, mem_engine, mock_invoke, notices, of_type, run, snapshot, source

PHARMA_DIR = REPO_ROOT / "backend" / "app" / "pharma"
PATIENTS = json.loads((PHARMA_DIR / "fixtures" / "patients.json").read_text(encoding="utf-8"))["patients"]
FIELDS = ("drug_name_raw", "dose_value", "dose_unit", "quantity", "dose_status", "route", "frequency_code", "frequency_status")


def test_pipeline_uses_gateway(client, login, audit_rows):
    login("pharmacist1")
    before = len(audit_rows())
    resp = client.post("/api/pharma/reconcile", json={"fixture_ref": "demo-01"})
    assert resp.status_code == 200, resp.text
    run_data = resp.json()
    rows = [r for r in audit_rows()[before:] if r["action"] == "gateway.invoke"]
    present = len(run_data["extraction"])
    assert present == 3
    assert EXTRACT_TASK == "pharma.extract.v2"  # the pipeline calls only v2
    assert [r["target"] for r in rows].count(f"task/{EXTRACT_TASK}") == present
    assert not [r for r in rows if r["target"] == "task/pharma.extract.v1"]
    assert [r["target"] for r in rows].count(f"task/{PHRASE_TASK}") == 1
    assert {r["details"]["provider"] for r in rows} == {"mock"}
    assert [r["details"]["request_sha256"] for r in rows] == [c["request_sha256"] for c in run_data["gateway_calls"]]
    assert all(r["actor_role"] == "pharmacist" for r in rows)


def test_reconcile_deterministic():
    snap = get_fixture("demo-01")

    def strip(r):
        return json.dumps(
            [{k: v for k, v in i.items() if k not in ("issue_id", "run_id")} for i in r["issues"]],
            sort_keys=True, ensure_ascii=False,
        ).encode()

    a = run(snap)
    b = run(get_fixture("demo-01"), invoke=mock_invoke(mem_engine()))
    assert strip(a) == strip(b)
    assert a["snapshot_sha256"] == b["snapshot_sha256"]


def test_pharma_provider_isolation():
    needle = ".".join(["gateway", "adapters"])
    sdks = {"openai", "anthropic", "google.generativeai", "litellm", "langchain", "httpx", "requests"}
    files = [p for p in PHARMA_DIR.rglob("*") if p.is_file() and p.suffix in {".py", ".json"}]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert needle not in text, path
        if path.suffix == ".py":
            for node in ast.walk(ast.parse(text)):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for mod in mods:
                    assert "adapters" not in mod, path
                    assert not any(mod == s or mod.startswith(s + ".") for s in sdks), (path, mod)
    assert Settings.from_env().gateway_provider == "mock"


def _extraction_accuracy(patients):
    total = correct = fabricated = 0
    for p in patients:
        r = run(get_fixture(p["patient_ref"]))
        for rec in r["extraction"]:
            assert rec["status"] == "ok"
            for ext, gold in zip(rec["entries"], p["gold"][rec["source_type"]], strict=True):
                for f in FIELDS:
                    total += 1
                    correct += ext[f] == gold[f]
                    fabricated += gold[f] is None and ext[f] is not None
    return correct / total, fabricated


def test_extraction_fields():
    acc, fabricated = _extraction_accuracy([p for p in PATIENTS if p["split"] == "test"])
    assert acc >= 0.98 and fabricated == 0
    out = extract_handler({"entries": ["Metformin วันละ 2 ครั้ง", "Norvasc", "ซาร่า 500 มก. เวลาปวด", "Augmentin 1 g PO bid"]})
    e = out["entries"]
    assert (e[0]["dose_value"], e[0]["dose_unit"], e[0]["frequency_code"], e[0]["route"]) == (None, None, "q12h", None)
    assert (e[1]["drug_name_raw"], e[1]["dose_value"], e[1]["frequency_code"]) == ("Norvasc", None, None)
    assert (e[2]["drug_name_raw"], e[2]["dose_value"], e[2]["dose_unit"], e[2]["frequency_code"]) == ("ซาร่า", 500.0, "mg", "prn")
    assert (e[3]["dose_value"], e[3]["dose_unit"], e[3]["route"], e[3]["frequency_code"]) == (1.0, "g", "oral", "q12h")


def test_normalise_fixture_mentions():
    form = load_formulary()
    kinds = set()
    for p in PATIENTS:
        for gl in p["gold"].values():
            for g in gl:
                ings = form.resolve_name(g["drug_name_raw"])
                assert list(ings) == g["ingredients"], g["drug_name_raw"]
                assert list(form.rxcuis(ings)) == g["ingredient_rxcuis"]
                kinds.add(g["drug_name_raw"])
    # every mention class is exercised: generic, EN brand, Thai brand (Latin), Thai script
    assert {"Amlodipine", "Norvasc"} & kinds and {"Sara", "Miracid", "Orfarin", "Berlontin"} & kinds
    assert any(any("฀" <= ch <= "๿" for ch in k) for k in kinds)


def test_unknown_drug_notice():
    names = ["Qelvadrine 10 mg daily", "Zorbitrax 5 mg bid", "ฟ้าทะลายโจร 2 แคปซูล วันละ 3 ครั้ง"]
    r = run(snapshot(home=names, orders=["Amlodipine 5 mg daily"]))
    found = notices(r, "unrecognised_drug")
    assert len(found) == 3
    assert [n["raw_span"] for n in found] == names  # never dropped
    home = next(rec for rec in r["extraction"] if rec["source_type"] == "home_list")
    assert len(home["entries"]) == 3 and not any(e["recognised"] for e in home["entries"])
    assert of_type(r, "omission") == []  # unrecognised names are not silently checked


class _Scripted:
    """Delegates extraction to the mock; returns scripted phrasing output."""

    name = "scripted"

    def __init__(self, phrase_output=None, extract_result=None):
        self._mock = build_provider("mock", Settings())
        self._phrase_output = phrase_output
        self._extract_result = extract_result

    def invoke(self, request: GatewayRequest, sha: str) -> ProviderResult:
        if request.task == EXTRACT_TASK and self._extract_result is not None:
            result = self._extract_result
            if isinstance(result, Exception):
                raise result
            return result
        if request.task == PHRASE_TASK and self._phrase_output is not None:
            out = self._phrase_output(request.inputs) if callable(self._phrase_output) else self._phrase_output
            return ProviderResult(status="ok", model_version="scripted-1", output=out)
        return self._mock.invoke(request, sha)


def _scripted_invoke(**kw):
    return mock_invoke(mem_engine(), _Scripted(**kw))


def test_phrasing_cannot_change_issues():
    snap = get_fixture("demo-01")
    base = run(snap, mode="rules_only")

    def hostile(inputs):
        items = inputs["issues"]
        out = [{"issue_id": i["issue_id"], "text": f"All clear for {', '.join(i['ingredients'])}"} for i in items[::-1]]
        out.append({"issue_id": "made-up", "text": "New issue: warfarin"})
        return {"phrasings": out[1:], "extra": "retype everything"}

    for invoke in (_scripted_invoke(phrase_output=hostile), mock_invoke()):
        r = run(snap, mode="rules_plus_model", invoke=invoke)
        assert [issue_signature(i) for i in r["issues"]] == [issue_signature(i) for i in base["issues"]]
    ok = run(snap, mode="rules_plus_model")
    assert {i["phrasing"]["source"] for i in ok["issues"]} == {"model"}
    assert {i["phrasing"]["source"] for i in base["issues"]} == {"template"}


def _valid_but(bad):
    def build(inputs):
        out = []
        for item in inputs["issues"]:
            text = "Mock phrasing. " + " ".join(item["source_labels"] + item["ingredients"]) + " noted for pharmacist review."
            out.append({"issue_id": item["issue_id"], "text": bad(text, item)})
        return {"phrasings": out}

    return build


FALLBACKS = {
    "schema": ({"phrasings": [{"issue_id": 1}]}, "schema_invalid"),
    "missing_source": (_valid_but(lambda t, item: t.replace(item["source_labels"][0], "somewhere")), "missing_source"),
    "banned_phrase": (_valid_but(lambda t, item: t + " Please stop this medicine."), "banned_phrase"),
}


@pytest.mark.parametrize("case", list(FALLBACKS))
def test_phrasing_validation_fallback(case):
    output, reason = FALLBACKS[case]
    snap = get_fixture("demo-01")
    r = run(snap, invoke=_scripted_invoke(phrase_output=output))
    assert r["issues"]
    for issue in r["issues"]:
        assert issue["phrasing"]["source"] == "template_fallback"
        assert issue["phrasing"]["fallback_reason"] == reason
        assert issue["phrasing"]["text"].endswith("For pharmacist review.")
    assert r["phrase_raw_output"]["output"] is not None  # original model output stored raw
    good = run(snap, invoke=_scripted_invoke(phrase_output=_valid_but(lambda t, item: t)))
    assert {i["phrasing"]["source"] for i in good["issues"]} == {"model"}


def test_issue_sources_complete():
    from app.pharma.phrasing import phrase_input, validate_text

    snaps = [get_fixture(ref) for ref in ("demo-01", "demo-03")]
    snaps.append(snapshot(
        home=["Metformin 500 mg bid", "Losartan 50 mg daily"], reported=["เมทฟอร์มิน 500 มก. วันละ 3 ครั้ง"],
        orders=["Metformin 1000 mg bid", "Brufen 400 mg tid", "Naprosyn 250 mg bid"], allergies=["Aspirin"],
    ))
    seen = 0
    for snap in snaps:
        for issue in run(snap)["issues"]:
            seen += 1
            srcs = issue["conflicting_sources"]
            assert len(srcs) >= (1 if issue["type"] == "omission" else 2)
            for s in srcs:
                assert s["source_type"] and s["evidence_ref"] and s["available_at_time"] and "raw_span" in s
            if issue["type"].startswith("allergy_"):
                assert srcs[0]["source_type"] == "allergy_record" and len({s["source_type"] for s in srcs}) >= 2
            if issue["phrasing"]["source"] == "model":
                assert validate_text(issue["phrasing"]["text"], phrase_input(issue)) is None
    assert seen >= 8


def _timeout_result():
    return ProviderResult(status="error", model_version="m", output=None, reason="provider_timeout")


EXTRACT_FAILURES = {
    "error": RuntimeError("boom"),
    "timeout": _timeout_result(),
    "rejected": ProviderResult(status="rejected", model_version="m", output=None, reason="policy_non_synthetic"),
    "schema_invalid": ProviderResult(status="ok", model_version="m", output={"entries": [{"name": "x"}]}),
}


@pytest.mark.parametrize("mode", list(EXTRACT_FAILURES))
def test_extract_fail_safe(mode):
    snap = get_fixture("demo-01")
    r = run(snap, invoke=_scripted_invoke(extract_result=EXTRACT_FAILURES[mode]))
    assert r["status"] == "incomplete"
    assert len(r["extraction"]) == 3
    for rec in r["extraction"]:
        assert rec["status"] == "extraction_failed" and rec["entries"] is None and rec["failure_reason"]
    assert len(notices(r, "source_unreadable")) == 3
    assert of_type(r, "omission") == []  # an unreadable order list never floods omissions


def test_missing_new_order_source():
    r = run(snapshot(home=["Metformin 500 mg bid", "Amlodipine 5 mg daily"], reported=["เมทฟอร์มิน วันละ 2 ครั้ง"]))
    assert len(notices(r, "source_missing")) == 1
    assert of_type(r, "omission") == []
    assert r["status"] == "complete"


def test_pharma_non_synthetic_rejected(settings):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "x"}}]})

    s = replace(settings, external_enabled=True, external_base_url="http://external.invalid/v1")
    provider = build_provider("openai_compatible", s, transport=httpx.MockTransport(handler))
    engine = mem_engine()
    for data_class in ("mimic", "hospital", "real", "unknown"):
        snap = snapshot(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg bid"], data_class=data_class)
        r = run(snap, invoke=mock_invoke(engine, provider))
        assert r["status"] == "incomplete"
        assert {rec["failure_reason"] for rec in r["extraction"]} == {"policy_non_synthetic"}
        assert r["issues"] == []
    assert requests == []


def test_future_items_excluded():
    future_order = source("new_order", ["Metformin 1000 mg tid", "Tylenol 500 mg prn", "Sara 500 mg prn"], at=AFTER, ref="t/new_order/2")
    snap = snapshot(
        home=["Metformin 500 mg bid"],
        orders=["Metformin 500 mg bid"],
        allergies=["Aspirin", allergy("Metformin (rash)", at=AFTER, ref="t/allergy/future")],
        extra_sources=[future_order],
    )
    r = run(snap)
    assert r["excluded_future_items"] == 2
    assert r["issues"] == []
    refs = {s["evidence_ref"] for i in r["issues"] for s in i["conflicting_sources"]}
    assert "t/new_order/2" not in refs and "t/allergy/future" not in refs
    assert [rec["evidence_ref"] for rec in r["extraction"]] == ["t/home_list/1", "t/new_order/1"]
