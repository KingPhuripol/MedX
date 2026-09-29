"""Gate 2 simulated-user benchmark (tau-bench style).

LABEL (repeated in every output): Simulated-user evaluation (synthetic) - not human usability,
not clinical performance.

Question: does gathering the data for a consult on ONE case page (env B, "MedX V2") let a simulated
nurse / OPD physician / pharmacist prepare a case with fewer tool calls, fewer systems and no less
accuracy than reaching five separate systems (env A, "multi-system")? Same LLM, temperature, prompts and
task in both arms; only the toolset differs. The simulator never sees gold; scoring uses gold + snapshot.

Tool mapping (the synthetic snapshot has these data types only; nothing is invented):
  env A  get_opd_note       Demographics + AllergyList + IntakeTranscript (registration/OPD record)
         get_labs           LabSeries
         get_medications    MedicationList (home_list / patient_reported / new_order)
         get_vitals         Vitals
  env B  get_queue / get_case_overview / get_intake / get_medications / get_timeline: one screen per tool,
         mirroring what the V2 web UI renders (see UI_MAP; web/components/clinical/CaseWorkspace.tsx). The same
         facts are reachable as in A. System-authored content of the demo (red-flag banner, discrepancy card)
         is NOT reproduced (no engine computes it for dataset cases; it would leak gold), so B differs from
         A only in consolidation.
Both envs filter available_at_time > T (T = snapshot as_of).

Arm B ("single-case consolidated view (MedX case-page schema)") is a schema-faithful adapter of the MedX case-page routes, populated from the snapshot: the shipped
demo router (backend/app/demo/router.py) serves ONE hard-coded case, so it cannot serve dataset cases. The
selfcheck probes the real app in-process (TestClient, mock provider) to assert the routes exist.

Task success (predeclared): all six answer fields correct -
  vitals_trend     == trend derived from the snapshot vitals by the rule stated in the prompt
  current_meds     == set of generic names on any MedicationList at T
  medication_issues== set of (issue_type, drug set) equal to gold medication_issues (no misses, no extras)
  red_flags        == set of gold rule_ids
  escalate         == (gold expected_action == "escalate")
  missing_info     == set of gold care.required_inputs_missing
A missing/invalid answer, turn cap, provider error or schema failure is a failed trial that stays in the
denominator. Critical miss: a gold red flag not reported (or escalate=false when gold escalates), or a gold
medication issue whose drugs appear in no reported issue.

Usage: python3 -m eval.simuser.run --selfcheck | --smoke | --dataset D --split dev --cases N --k K --out DIR
Env vars only: SIMUSER_BASE_URL, SIMUSER_API_KEY (never logged or written), SIMUSER_MODEL.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from eval.bootstrap import RatioStat, cluster_bootstrap, paired_cluster_bootstrap  # noqa: E402
from eval.jsonio import canonical_bytes, sha256_bytes, utc_now  # noqa: E402

LABEL = "Simulated-user evaluation (synthetic) — not human usability, not clinical performance"
TEMPLATES = REPO_ROOT / "data_factory" / "templates"
DEFAULT_DATASET = "data/synthetic/v1"
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
ALLOWED_SPLITS = ("train", "dev", "test")  # test only via check_test_access (FROZEN manifest + dataset sha match)
ENV_FILE = Path("/Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.env")
RF_PHRASES = {
    "RF-QSOFA": "sepsis risk, qSOFA 2 or more", "RF-NEWS-SINGLE3": "single extreme NEWS parameter",
    "RF-NEWS-AGG5": "aggregate NEWS 5 or more", "RF-FAST": "sudden face/arm/speech deficit, stroke sign",
    "RF-ACUTE-CHEST-PAIN": "acute chest pain", "RF-THUNDERCLAP": "thunderclap headache", "RF-ANAPHYLAXIS": "anaphylaxis",
}
RF_ALIASES = {**{v.lower(): k.lower() for k, v in RF_PHRASES.items()}}
# Closed vocabulary of missing-input codes that can occur in gold (union of care.required_inputs_missing over train/dev).
MISSING_VOCAB = {
    "chief_complaint": "no chief complaint stated in the intake conversation",
    "duration": "symptom duration not stated",
    "allergy_status": "allergy status unknown / not documented",
    "vitals.temp_c": "temperature not recorded in the vitals",
}
ANSWER_KEYS = ("vitals_trend", "current_meds", "medication_issues", "red_flags", "escalate", "missing_info")
TRENDS = ("worsening", "improving", "stable", "single_reading")
ARMS = ("A", "B")
ARM_NAMES = {"A": "multi-system", "B": "single-case consolidated view (MedX case-page schema)"}
PERSONAS = {
    "nurse": "triage/OPD nurse preparing the case for the physician",
    "physician": "OPD physician about to see this patient",
    "pharmacist": "clinical pharmacist doing the pre-consult medication review",
}
BOOT_SEED = 20260929
UI_MAP = [
    "", "## Arm B: V2 UI screen to tool mapping (single-case consolidated view, MedX case-page schema; adapter, not a MedX app run)", "",
    "| V2 web UI (file:line) | Tool | What the tool returns |", "|---|---|---|",
    "| web/components/clinical/WorkQueue.tsx:29,53 (queue API, row link to case) | get_queue | role tasks (task_id, case_id, kind, label, status) |",
    "| web/components/clinical/CaseWorkspace.tsx:189-215 (case header: case id, name, sex, age, HN, stage, owner, next task); :34-42 (tabs) | get_case_overview | the header fields + intake status + tab list; nothing else is on the first-open overview |",
    "| CaseWorkspace.tsx:216-231 (red-flag banner), :343-373 (Overview: summary, chief complaint, onset) | not reproduced | authored/system content in the demo; no engine computes it for dataset cases and it would leak gold. Chief complaint/onset are only in the transcript, so the model must open intake |",
    "| CaseWorkspace.tsx:251,374-403 (Intake tab), :81-87 (tab data fetched only on open) | get_intake | intake record incl. the conversation turns (assumption: the UI intake tab shows only extracted fields; the adapter exposes the transcript so the same facts are reachable as in A) |",
    "| CaseWorkspace.tsx:284,459-517 (Medications tab: one card per source with recorded_value, captured_at) | get_medications | one source per list with a recorded_value string (drug, dose, frequency, ATC) and captured_at; the discrepancy card (:475-513) is not reproduced |",
    "| CaseWorkspace.tsx:285,518-549 (Timeline tab: title, detail text, actor, time, version) | get_timeline | one event per record; detail text carries vitals, labs, allergy and registration facts (the V2 UI has no separate vitals/labs/allergy screen; assumption: they appear as timeline detail text) |",
    "",
]
FORBIDDEN_IN_TOOL_OUTPUT = ("medication_issues", "required_inputs_missing", "INJ-", "expected_action", "rule_id")


# ---------------------------------------------------------------- data


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _templ(name: str) -> Any:
    return _load(TEMPLATES / name)


def parse_ts(s: str):
    from datetime import datetime

    return datetime.fromisoformat(s)


def visible_items(snapshot: dict) -> list[dict]:
    """Items with available_at_time <= as_of, ordered by availability. The one temporal gate for both envs."""
    T = parse_ts(snapshot["as_of"])
    items = [i for i in snapshot["items"] if parse_ts(i["available_at_time"]) <= T]
    return sorted(items, key=lambda i: (parse_ts(i["available_at_time"]), i["item_id"]))


def _clean(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("provenance", "version", "encounter_ref")}


ACVPU = {"A": 0, "C": 1, "V": 2, "P": 3, "U": 4}
TREND_RULE = (
    "Compare the LAST vitals reading with the FIRST (by time), skipping missing values. worsening = any of: "
    "HR +15 or more, RR +4 or more, SBP -20 or more, SpO2 -3 or more, temp +1.0 C or more, consciousness moves "
    "toward U on A,C,V,P,U. improving = none worsening and any of the opposite changes. Otherwise stable. "
    "Only one vitals reading = single_reading."
)


def derive_vitals_trend(vitals: list[dict]) -> str:
    v = sorted(vitals, key=lambda i: (parse_ts(i["available_at_time"]), i["item_id"]))
    if len(v) < 2:
        return "single_reading"
    first, last = v[0], v[-1]
    worse = better = False
    for p, thr, sign in (("hr", 15, 1), ("rr", 4, 1), ("sbp", 20, -1), ("spo2", 3, -1), ("temp_c", 1.0, 1)):
        a, b = first.get(p), last.get(p)
        if a is None or b is None:
            continue
        d = (b - a) * sign
        worse |= d >= thr
        better |= d <= -thr
    ca, cb = ACVPU.get(first.get("consciousness")), ACVPU.get(last.get("consciousness"))
    if ca is not None and cb is not None:
        worse |= cb > ca
        better |= cb < ca
    return "worsening" if worse else "improving" if better else "stable"


def _norm(s: Any) -> str:
    return str(s).strip().lower()


@dataclass(frozen=True)
class Reference:
    """Scoring reference. Built from snapshot + gold. Never given to the simulator."""

    vitals_trend: str
    current_meds: frozenset
    medication_issues: frozenset  # of (issue_type, frozenset(drugs))
    red_flags: frozenset
    escalate: bool
    missing_info: frozenset

    def as_answer(self) -> dict:
        return {
            "vitals_trend": self.vitals_trend,
            "current_meds": sorted(self.current_meds),
            "medication_issues": [{"issue_type": t, "drugs": sorted(d)} for t, d in sorted(self.medication_issues, key=lambda x: (x[0], sorted(x[1])))],
            "red_flags": sorted(self.red_flags),
            "escalate": self.escalate,
            "missing_info": sorted(self.missing_info),
        }


def build_reference(snapshot: dict, gold_dt: dict) -> Reference:
    items = visible_items(snapshot)
    meds = frozenset(_norm(e["generic_name"]) for i in items if i["data_type"] == "MedicationList" for e in i["entries"])
    issues = frozenset((m["issue_type"], frozenset(_norm(d) for d in m["drugs"])) for m in gold_dt["medication_issues"])
    return Reference(
        vitals_trend=derive_vitals_trend([i for i in items if i["data_type"] == "Vitals"]),
        current_meds=meds,
        medication_issues=issues,
        red_flags=frozenset(r["rule_id"] for r in gold_dt["red_flags"]),
        escalate=gold_dt["expected_action"] == "escalate",
        missing_info=frozenset(gold_dt["care"]["required_inputs_missing"]),
    )


@dataclass
class Case:
    case_id: str
    split: str
    decision_point: str
    snapshot: dict  # the ONLY thing environments see
    ref: Reference
    strata: tuple = ()


def require_synthetic(dataset: Path) -> None:
    from casegraph.sources.s1r import manifest_data_class

    try:
        dc = manifest_data_class(dataset)
    except Exception:
        dc = None
    if dc != "synthetic":
        raise SystemExit("refusing: dataset manifest does not declare data_class 'synthetic'")


def check_test_access(manifest_path: str | None, dataset: Path) -> bool:
    """True only for a manifest with status FROZEN whose dataset_manifest_sha256 equals sha256(dataset/manifest.json)."""
    if not manifest_path or not Path(manifest_path).is_file():
        return False
    m = _load(Path(manifest_path))
    dm = dataset / "manifest.json"
    sha = hashlib.sha256(dm.read_bytes()).hexdigest() if dm.is_file() else None
    return m.get("status") == "FROZEN" and sha is not None and (m.get("dataset") or {}).get("dataset_manifest_sha256") == sha


def load_cases(dataset: Path, split: str, dp: str, allow_test: bool = False) -> list[Case]:
    if split not in ("train", "dev") and not (split == "test" and allow_test):
        raise SystemExit(f"refusing split {split!r}: test needs --manifest with status FROZEN and a matching dataset sha256")
    require_synthetic(dataset)
    out = []
    for snap_path in sorted((dataset / "inputs" / split).glob(f"*/snapshot_{dp}.json")):
        snap = _load(snap_path)
        cid = snap["case_id"]
        gold = _load(dataset / "gold" / split / f"{cid}.json")
        dt = next(d for d in gold["decision_times"] if d["decision_point"] == dp)
        ref = build_reference(snap, dt)
        strata = (bool(ref.red_flags), bool(ref.medication_issues), bool(ref.missing_info))
        out.append(Case(cid, split, dp, snap, ref, strata))
    return out


def select_cases(cases: list[Case], n: int, seed: int) -> list[Case]:
    """Predeclared, seeded: every case with a gold red flag first, then random fill (sha256 order), up to n."""
    def h(c: Case) -> str:
        return hashlib.sha256(f"{seed}:{c.case_id}".encode()).hexdigest()

    rf = sorted((c for c in cases if c.ref.red_flags), key=h)
    rest = sorted((c for c in cases if not c.ref.red_flags), key=h)
    return (rf + rest)[:n]


# ---------------------------------------------------------------- environments


def _canon(args: dict) -> str:
    return json.dumps(args, sort_keys=True, ensure_ascii=False)


def _tool(name: str, description: str, needs_case: bool = True) -> dict:
    props = {"case_id": {"type": "string"}} if needs_case else {}
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props, "required": ["case_id"] if needs_case else []}}}


class Env:
    name = ""
    tools: list[dict] = []

    def __init__(self, snapshot: dict, role: str):
        self.snapshot = snapshot
        self.role = role
        self.case_id = snapshot["case_id"]
        self.items = visible_items(snapshot)

    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"_t_{name}", None) if name in self.tool_names else None
        if fn is None:
            return {"error": "unknown_tool", "available": sorted(self.tool_names)}
        if name != "get_queue" and args.get("case_id") != self.case_id:
            return {"error": "case_not_found"}
        return fn()

    @property
    def tool_names(self) -> set[str]:
        return {t["function"]["name"] for t in self.tools}

    def systems_opened(self, called: set[str]) -> int:
        raise NotImplementedError

    def _of(self, *types: str) -> list[dict]:
        return [_clean(i) for i in self.items if i["data_type"] in types]


class MultiSystemEnv(Env):
    name = "A"
    tools = [
        _tool("get_opd_note", "OPD registration/visit record system: demographics, allergy history and the intake conversation transcript."),
        _tool("get_labs", "Laboratory information system: lab results."),
        _tool("get_medications", "Medication system: medication lists (home list, patient-reported list, current orders)."),
        _tool("get_vitals", "Triage/vitals system: vital-sign readings."),
    ]

    def _pack(self, system: str, records: list[dict]) -> dict:
        out = {"system": system, "case_id": self.case_id, "as_of": self.snapshot["as_of"], "records": records}
        if not records:
            out["note"] = "no records"
        return out

    def _t_get_opd_note(self):
        return self._pack("opd", self._of("Demographics", "AllergyList", "IntakeTranscript"))

    def _t_get_labs(self):
        return self._pack("lab", self._of("LabSeries"))

    def _t_get_medications(self):
        return self._pack("medication", self._of("MedicationList"))

    def _t_get_vitals(self):
        return self._pack("vitals", self._of("Vitals"))

    def systems_opened(self, called: set[str]) -> int:
        return len(called)


class CasePageEnv(Env):
    """Single-case consolidated view (MedX case-page schema). Shapes follow backend/app/demo/router.py and what
    web/components/clinical/CaseWorkspace.tsx renders per tab; see UI_MAP."""

    name = "B"
    tools = [
        _tool("get_queue", "MedX work queue for your role: tasks waiting for you.", needs_case=False),
        _tool("get_case_overview", "Case page first screen: case header (id, patient, sex, age, HN, stage, owner, next task) and the case tabs."),
        _tool("get_intake", "Case page Intake tab: the intake record and conversation."),
        _tool("get_medications", "Case page Medications tab: one card per medication source."),
        _tool("get_timeline", "Case page Timeline tab: chronological events with their detail text (vitals, labs, allergy, registration)."),
    ]

    def __init__(self, snapshot: dict, role: str, queue_case_ids: list[str] | None = None):
        super().__init__(snapshot, role)
        self.queue_case_ids = queue_case_ids or [self.case_id]

    def _meta(self) -> dict:
        return {"data_class": "synthetic", "as_of": self.snapshot["as_of"], "actor": {"role": self.role}}

    def _first(self, dt: str) -> dict | None:
        return next((i for i in self.items if i["data_type"] == dt), None)

    def _t_get_queue(self):
        ids = sorted(set(self.queue_case_ids) | {self.case_id})
        items = [{"task_id": f"task-prep-{c}", "case_id": c, "role": self.role, "kind": "case_prep",
                  "label": "Prepare case for consult", "status": "ready"} for c in ids]
        return {"items": items} | self._meta()

    def _t_get_case_overview(self):
        demo = self._first("Demographics") or {}
        intake = self._first("IntakeTranscript")
        return {"case_id": self.case_id, "display_name": f"Synthetic patient {self.case_id}",
                "demographics": {"sex": demo.get("sex", "not recorded"), "age": demo.get("age_years", "not recorded"), "hn": self.snapshot.get("encounter_ref")},
                "stage": "care_review", "owner": {"role": self.role, "display": f"team {self.role}"},
                "next_action": "Prepare case for consult",
                "intake": {"status": "recorded" if intake else "not recorded"},
                "tabs": ["overview", "intake", "medications", "timeline"]} | self._meta()

    def _t_get_intake(self):
        tx = self._first("IntakeTranscript")
        if tx is None:
            return {"case_id": self.case_id, "intake": None, "note": "no intake recorded"} | self._meta()
        return {"case_id": self.case_id, "intake": {"source": tx["source"], "status": "recorded", "recorded_at": tx["available_at_time"],
                                                    "turns": tx["turns"]}} | self._meta()

    @staticmethod
    def _v(x, unit=""):
        return "not recorded" if x is None else f"{x}{unit}"

    def _detail(self, i: dict) -> str:
        t, v = i["data_type"], self._v
        if t == "Vitals":
            return (f"HR {v(i.get('hr'))}, RR {v(i.get('rr'))}, SBP {v(i.get('sbp'))}, DBP {v(i.get('dbp'))}, SpO2 {v(i.get('spo2'), '%')}, "
                    f"Temp {v(i.get('temp_c'), ' C')}, consciousness {v(i.get('consciousness'))}, on oxygen {v(i.get('on_oxygen'))}")
        if t == "LabSeries":
            return "; ".join(f"{r['test']} {r['value']} {r.get('unit', '')} (ref {r.get('ref_low', '?')}-{r.get('ref_high', '?')})".replace("  ", " ")
                             for r in i["results"])
        if t == "AllergyList":
            ent = "; ".join(f"{e['substance']} (ATC class {e.get('atc_class')}): {e.get('reaction', 'n/a')}" for e in i["entries"])
            return f"allergy status {i.get('status')}" + (f" - {ent}" if ent else "")
        if t == "Demographics":
            return f"{v(i.get('sex'))}, {v(i.get('age_years'))} years"
        if t == "MedicationList":
            return "see Medications tab"
        return "see Intake tab"

    def _t_get_timeline(self):
        kinds = {"Vitals": "vitals", "LabSeries": "lab", "MedicationList": "medication_list", "AllergyList": "allergy",
                 "Demographics": "registration", "IntakeTranscript": "intake"}
        events = []
        for i in self.items:
            title = i["data_type"] + (f" ({i.get('list_source')})" if i["data_type"] == "MedicationList" else "")
            events.append({"event_id": i["item_id"], "kind": kinds.get(i["data_type"], i["data_type"]), "title": title,
                           "detail": self._detail(i), "actor": {"role": "system", "display": i["source"]},
                           "timestamp": i["available_at_time"], "version": 1})
        return {"case_id": self.case_id, "items": events} | self._meta()

    def _t_get_medications(self):
        def rec(e):
            return (f"{e['generic_name']} {e['dose_value']} {e['dose_unit']} {e['frequency']} "
                    f"(ATC {e['atc_code']}{', ' + e['route'] if e.get('route') else ''})")
        srcs = [{"source_id": i["item_id"], "label": i.get("list_source"), "system": i["source"],
                 "recorded_value": "; ".join(rec(e) for e in i["entries"]) or "no medications recorded",
                 "captured_at": i["available_at_time"]} for i in self.items if i["data_type"] == "MedicationList"]
        return {"case_id": self.case_id, "sources": srcs} | self._meta()

    def systems_opened(self, called: set[str]) -> int:
        return 1 if called else 0


# ---------------------------------------------------------------- prompts


def build_system_prompt(persona: str) -> str:
    rf = "\n".join(f"- {r['rule_id']} ({RF_PHRASES[r['rule_id']]}): {r['description']} Criterion: {json.dumps(r['criterion'], ensure_ascii=False)}"
                   for r in _templ("red_flags.json"))
    it = "\n".join(f"- {x['issue_type']}: {x['definition']}" for x in _templ("issue_types.json"))
    req = "\n".join(f"- {c}: {d}" for c, d in MISSING_VOCAB.items())
    return (
        f"You are a {PERSONAS[persona]}. All data is SYNTHETIC (research prototype, not for clinical use). "
        "You prepare a case before the consult; a clinician decides, you do not diagnose or treat.\n"
        "Use the tools to fetch what you need. Do not invent data you did not retrieve. Records are only what "
        "was available at the current time.\n"
        "Finish by replying with ONLY one JSON object (no prose) with exactly these keys:\n"
        '{"vitals_trend": "worsening|improving|stable|single_reading", "current_meds": ["generic name", ...], '
        '"medication_issues": [{"issue_type": "...", "drugs": ["..."]}], "red_flags": ["RF-..."], '
        '"escalate": true|false, "missing_info": ["..."]}\n'
        f"vitals_trend rule: {TREND_RULE}\n"
        "current_meds: every distinct generic drug name (lowercase) on ANY medication list (home, patient-reported, order).\n"
        f"medication_issues: differences between the lists or order problems, using these issue_type values:\n{it}\n"
        f"red_flags: the ids (RF-...) below whose criterion is met by the retrieved data (empty list if none):\n{rf}\n"
        "escalate: true if any red flag is present, otherwise false.\n"
        "missing_info: which of these required inputs are missing or unknown in the retrieved data (unknown counts as missing, "
        f"never as negative). Closed list of allowed codes, use only these:\n{req}\n"
        "Empty list [] when nothing applies."
    )


def json_mode_tool_section(tools: list[dict]) -> str:
    lines = ['To use a tool, reply with ONLY one JSON line: {"tool": "<name>", "args": {...}}. Tools:']
    for t in tools:
        f = t["function"]
        lines.append(f"- {f['name']}({', '.join(f['parameters']['properties'])}): {f['description']}")
    lines.append('When finished reply with ONLY the final answer JSON object (optionally wrapped as {"answer": {...}}).')
    return "\n".join(lines)


def task_prompt(case: Case) -> str:
    return f"Prepare case {case.case_id} for consult. Current time T = {case.snapshot['as_of']}. Gather what you need, then give the final JSON."


# ---------------------------------------------------------------- LLM clients


class LLMError(RuntimeError):
    pass


class ToolsUnsupported(LLMError):
    pass


def extract_json_objects(text: str) -> list[dict]:
    dec, out, i = json.JSONDecoder(), [], 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return out
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        i = end


@dataclass
class Completion:
    content: str
    tool_calls: list  # [{"id","name","arguments"(str)}] (native mode)
    usage: dict
    model: str = ""
    raw_message: dict = field(default_factory=dict)


class HttpLLM:
    """OpenAI-compatible chat-completions client (httpx). The key only goes into the Authorization header."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 90.0, transport: httpx.BaseTransport | None = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self._key, self.model, self.timeout_s, self.transport = api_key, model, timeout_s, transport
        self.token_param = "max_tokens"
        self.send_temperature = True
        self.notes: list[str] = []

    def complete(self, messages: list[dict], tools: list[dict], mode: str, max_tokens: int, temperature: float) -> Completion:
        for _attempt in range(6):
            payload: dict[str, Any] = {"model": self.model, "messages": messages, self.token_param: max_tokens}
            if self.send_temperature:
                payload["temperature"] = temperature
            if mode == "native":
                payload["tools"], payload["tool_choice"] = tools, "auto"
            try:
                with httpx.Client(transport=self.transport, timeout=self.timeout_s) as c:
                    r = c.post(self.url, json=payload, headers={"Authorization": f"Bearer {self._key}"})
            except httpx.TimeoutException:
                raise LLMError("provider_timeout") from None
            except httpx.HTTPError:
                raise LLMError("provider_unreachable") from None
            if r.status_code == 200:
                return self._parse(r.json())
            body = r.text[:300]
            low = body.lower()
            if r.status_code in (400, 404, 422):
                if mode == "native" and ("tool" in low or "function" in low):
                    raise ToolsUnsupported(
                        f"endpoint/model {self.model!r} rejected the `tools` parameter (HTTP {r.status_code}). "
                        "Re-run with --tool-mode json (simulator requests tools via JSON lines).")
                if self.token_param == "max_tokens" and "max_tokens" in low:
                    self.token_param = "max_completion_tokens"
                    self.notes.append("max_tokens rejected; using max_completion_tokens")
                    continue
                if self.send_temperature and "temperature" in low:
                    self.send_temperature = False
                    self.notes.append("temperature rejected; endpoint default used")
                    continue
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** _attempt, 20))
                continue
            raise LLMError(f"http_{r.status_code}: {body}")
        raise LLMError("retries_exhausted")

    @staticmethod
    def _parse(d: dict) -> Completion:
        try:
            msg = d["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("malformed_response") from None
        u = d.get("usage") or {}
        cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
        calls = [{"id": c.get("id", f"call_{i}"), "name": (c.get("function") or {}).get("name", ""),
                  "arguments": (c.get("function") or {}).get("arguments", "")} for i, c in enumerate(msg.get("tool_calls") or [])]
        usage = {"prompt_tokens": int(u.get("prompt_tokens") or 0), "completion_tokens": int(u.get("completion_tokens") or 0),
                 "cached_tokens": int(cached)}
        return Completion(msg.get("content") or "", calls, usage, str(d.get("model", "")), msg)


class ScriptedLLM:
    """Deterministic fake used by --selfcheck (no network). policy(env_name, case_id, trial_no, turn) -> action."""

    def __init__(self, policy):
        self.policy, self.trials, self.model = policy, {}, "scripted-fake"

    def complete(self, messages, tools, mode, max_tokens, temperature) -> Completion:
        env = "B" if any(t["function"]["name"] == "get_queue" for t in tools) else "A"
        case_id = re.search(r"case (\S+) for consult", messages[1]["content"]).group(1)
        turn = sum(1 for m in messages if m["role"] == "assistant")
        if turn == 0:
            self.trials[(env, case_id)] = self.trials.get((env, case_id), -1) + 1
        act = self.policy(env, case_id, self.trials[(env, case_id)], turn)
        usage = {"prompt_tokens": 1000 + 100 * turn, "completion_tokens": 50, "cached_tokens": 0}
        if act["type"] == "tools":
            if mode == "native":
                calls = [{"id": f"c{turn}_{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(act["calls"])]
                return Completion("", calls, usage, self.model, {"role": "assistant", "content": None, "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]})
            n, a = act["calls"][0]
            return Completion(json.dumps({"tool": n, "args": a}), [], usage, self.model)
        text = act["text"] if "text" in act else json.dumps(act["answer"])
        return Completion(text, [], usage, self.model)


# ---------------------------------------------------------------- budget + trial


class BudgetStop(Exception):
    pass


@dataclass
class Budget:
    limit_usd: float
    price_in: float
    price_out: float
    price_cached: float = 0.01
    spent: float = 0.0
    stopped: bool = False
    reserved: float = 0.0
    lock: Any = field(default_factory=threading.Lock, repr=False, compare=False)

    def reserve(self, messages: list, max_tokens: int) -> float:
        """Worst-case cost of the next call, held until settled: spend can never exceed the limit under concurrency."""
        est = (len(json.dumps(messages, ensure_ascii=False).encode()) / 2 * self.price_in + max_tokens * self.price_out) / 1e6
        with self.lock:
            if self.stopped or self.spent + self.reserved + est > self.limit_usd:
                self.stopped = True
                raise BudgetStop
            self.reserved += est
        return est

    def settle(self, est: float, usage: dict) -> None:
        with self.lock:
            self.reserved -= est
            self.spent += self.cost(usage)

    def release(self, est: float) -> None:
        with self.lock:
            self.reserved -= est

    def cost(self, u: dict) -> float:
        cached = min(u.get("cached_tokens", 0), u["prompt_tokens"])
        return ((u["prompt_tokens"] - cached) * self.price_in + cached * self.price_cached + u["completion_tokens"] * self.price_out) / 1e6

    def add(self, u: dict) -> None:
        self.spent += self.cost(u)

    def check(self) -> None:
        if self.spent >= self.limit_usd:
            self.stopped = True
            raise BudgetStop


def parse_answer(text: str) -> dict | None:
    for obj in extract_json_objects(text):
        if isinstance(obj.get("answer"), dict):
            obj = obj["answer"]
        if any(k in obj for k in ANSWER_KEYS):
            return obj
    return None


@dataclass
class TrialCfg:
    tool_mode: str = "native"
    max_turns: int = 12
    max_tokens: int = 400
    temperature: float = 0.0


def run_trial(llm, env: Env, persona: str, case: Case, cfg: TrialCfg, budget: Budget) -> dict:
    system = build_system_prompt(persona)
    if cfg.tool_mode == "json":
        system += "\n" + json_mode_tool_section(env.tools)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task_prompt(case)}]
    log = [{"event": "start", "env": env.name, "persona": persona, "case_id": case.case_id, "tool_mode": cfg.tool_mode}]
    calls: list[tuple[str, str]] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    models: set[str] = set()
    status, answer_raw, t0, turns = "turn_cap", None, time.monotonic(), 0
    try:
        for turns in range(1, cfg.max_turns + 1):
            est = budget.reserve(messages, cfg.max_tokens)
            try:
                comp = llm.complete(messages, env.tools, cfg.tool_mode, cfg.max_tokens, cfg.temperature)
            except BaseException:
                budget.release(est)
                raise
            for k in usage:
                usage[k] += comp.usage.get(k, 0)
            budget.settle(est, comp.usage)
            models.add(comp.model)
            log.append({"event": "assistant", "turn": turns, "content": comp.content, "tool_calls": comp.tool_calls, "usage": comp.usage})
            requests: list[tuple[str | None, str, Any]] = []  # (call id, name, args | parse-error)
            if cfg.tool_mode == "native":
                for c in comp.tool_calls:
                    try:
                        a = json.loads(c["arguments"] or "{}")
                        a = a if isinstance(a, dict) else None
                    except ValueError:
                        a = None
                    requests.append((c["id"], c["name"], a))
                if requests:
                    messages.append(comp.raw_message or {"role": "assistant", "content": comp.content})
            else:
                obj = next((o for o in extract_json_objects(comp.content) if "tool" in o), None)
                if obj is not None and not any(k in obj for k in ANSWER_KEYS):
                    a = obj.get("args", {})
                    requests.append((None, str(obj["tool"]), a if isinstance(a, dict) else None))
                    messages.append({"role": "assistant", "content": comp.content})
            if not requests:
                answer_raw = parse_answer(comp.content)
                status = "answered" if answer_raw is not None else "invalid_answer"
                break
            for cid, name, args in requests:
                result = {"error": "invalid_arguments"} if args is None else env.call(name, args)
                calls.append((name, _canon(args or {})))
                log.append({"event": "tool", "name": name, "args": args, "result": result})
                body = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                if cfg.tool_mode == "native":
                    messages.append({"role": "tool", "tool_call_id": cid, "content": body})
                else:
                    messages.append({"role": "user", "content": f"TOOL_RESULT {name}: {body}"})
    except BudgetStop:
        status = "budget_stop"
    except ToolsUnsupported:
        raise
    except LLMError as e:
        status = "provider_error"
        log.append({"event": "error", "reason": str(e)[:300]})
    wall = time.monotonic() - t0
    called = {n for n, _ in calls}
    score = score_trial(case.ref, answer_raw)
    rec = {
        "env": env.name, "persona": persona, "case_id": case.case_id, "status": status,
        "answer": answer_raw, "score": score, "model_ids": sorted(m for m in models if m), "usage": usage,
        "cost_usd": round(budget.cost(usage), 6), "turns": turns, "wall_s": round(wall, 3),
        "tool_calls": len(calls), "distinct_tools": len(called), "systems_opened": env.systems_opened(called),
        "repeated_opens": len(calls) - len(set(calls)),
        "tokens": usage["prompt_tokens"] + usage["completion_tokens"], "input_tokens": usage["prompt_tokens"],
    }
    log.append({"event": "end", "status": status, "score": score})
    rec["_log"] = log
    return rec


# ---------------------------------------------------------------- scoring


def _set(x: Any) -> frozenset | None:
    if not isinstance(x, list):
        return None
    try:
        return frozenset(_norm(v) for v in x)
    except Exception:
        return None


def score_trial(ref: Reference, ans: dict | None) -> dict:
    """Field-level correctness, task success and critical misses. ans=None (no valid answer) fails everything."""
    ans = ans if isinstance(ans, dict) else {}
    valid = all(k in ans for k in ANSWER_KEYS)
    f = {}
    f["vitals_trend"] = ans.get("vitals_trend") == ref.vitals_trend
    f["current_meds"] = _set(ans.get("current_meds")) == ref.current_meds
    issues = ans.get("medication_issues")
    rep_issues: set = set()
    issue_drugs: set = set()
    ok_issues = isinstance(issues, list)
    for it in issues if ok_issues else []:
        if isinstance(it, dict) and isinstance(it.get("drugs"), list):
            drugs = frozenset(_norm(d) for d in it["drugs"])
            rep_issues.add((_norm(it.get("issue_type", "")), drugs))
            issue_drugs |= drugs
        else:
            ok_issues = False
    f["medication_issues"] = ok_issues and rep_issues == {(_norm(t), d) for t, d in ref.medication_issues}
    rf = _set(ans.get("red_flags"))
    if rf is not None:
        rf = frozenset(RF_ALIASES.get(x, x) for x in rf)
    f["red_flags"] = rf is not None and rf == frozenset(_norm(x) for x in ref.red_flags)
    f["escalate"] = isinstance(ans.get("escalate"), bool) and ans["escalate"] == ref.escalate
    f["missing_info"] = _set(ans.get("missing_info")) == frozenset(_norm(x) for x in ref.missing_info)
    has_rf, has_med = bool(ref.red_flags), bool(ref.medication_issues)
    rf_miss = has_rf and not (rf is not None and {_norm(x) for x in ref.red_flags} <= rf and ans.get("escalate") is True)
    med_miss = has_med and any(not (d & issue_drugs) for _, d in ref.medication_issues)
    return {
        "fields": f, "task_success": all(f.values()), "answer_valid": valid,
        "has_red_flag": has_rf, "has_med_issue": has_med,
        "critical_miss_redflag": bool(rf_miss), "critical_miss_med": bool(med_miss),
        "critical_miss_any": bool(rf_miss or med_miss),
    }


# ---------------------------------------------------------------- run + aggregate


def make_env(arm: str, case: Case, persona: str, queue_ids: list[str]) -> Env:
    return MultiSystemEnv(case.snapshot, persona) if arm == "A" else CasePageEnv(case.snapshot, persona, queue_ids)


def run_benchmark(llm, cases: list[Case], personas: list[str], k: int, cfg: TrialCfg, budget: Budget, out: Path | None = None,
                  workers: int = 1) -> list[dict]:
    """Jobs = (case, persona, trial), each running arm A then arm B. Case-major submission, thread pool, exact budget."""
    queue_ids = [c.case_id for c in cases]
    tdir = None
    if out is not None:
        tdir = out / "transcripts"
        tdir.mkdir(parents=True, exist_ok=True)
    jobs = [(case, persona, n) for case in cases for persona in personas for n in range(k)]

    def job(j) -> list[dict]:
        case, persona, n = j
        pair: list[dict] = []
        for arm in ARMS:
            if budget.stopped:
                break
            rec = run_trial(llm, make_env(arm, case, persona, queue_ids), persona, case, cfg, budget)
            rec["trial"] = n
            if tdir is not None:
                with (tdir / f"{arm}__{persona}__{case.case_id}__k{n}.jsonl").open("w", encoding="utf-8") as fh:
                    for ev in rec["_log"]:
                        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            del rec["_log"]
            pair.append(rec)
        return pair

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(job, jobs))
    return [t for pair in results for t in pair]


def _arr(vals) -> np.ndarray:
    return np.array([float(v) for v in vals])


def _metric_block(ids: list[str], a_num, a_den, b_num, b_den, n_boot: int) -> dict:
    sa, sb = RatioStat(_arr(a_num), _arr(a_den)), RatioStat(_arr(b_num), _arr(b_den))
    out = {}
    for arm, s in (("A", sa), ("B", sb)):
        r = cluster_bootstrap(ids, s, n_boot=n_boot, seed=BOOT_SEED)
        out[arm] = {"num": float(s.num.sum()), "den": float(s.den.sum()), "point": r.point, "ci_low": r.ci_low, "ci_high": r.ci_high}
    d = paired_cluster_bootstrap(ids, sa, ids, sb, n_boot=n_boot, seed=BOOT_SEED)
    out["A_minus_B"] = {"point": d.point, "ci_low": d.ci_low, "ci_high": d.ci_high, "reason": d.reason}
    return out


def pair_trials(trials: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Aligned A/B trial lists over complete pairs; count of excluded (incomplete/budget-stopped) trials."""
    idx: dict[tuple, dict] = {}
    for t in trials:
        idx[(t["case_id"], t["persona"], t["trial"], t["env"])] = t
    keys = sorted({k[:3] for k in idx})
    A, B = [], []
    for k in keys:
        a, b = idx.get(k + ("A",)), idx.get(k + ("B",))
        if a and b and "budget_stop" not in (a["status"], b["status"]):
            A.append(a)
            B.append(b)
    return A, B, len(trials) - len(A) - len(B)


def summarize(trials: list[dict], k: int, n_boot: int = 2000) -> dict:
    A, B, excluded = pair_trials(trials)
    if not A:
        return {"n_pairs": 0, "excluded_trials": excluded, "metrics": {}}
    ids = [t["case_id"] for t in A]  # cluster = case (patient); persona/trial are repeats within a case
    m: dict[str, Any] = {}
    one = [1.0] * len(A)

    def field(name):
        return [t["score"]["fields"][name] for t in A], [t["score"]["fields"][name] for t in B]

    def add(name, fa, fb, dena=None, denb=None):
        m[name] = _metric_block(ids, fa, dena or one, fb, denb or one, n_boot)

    add("task_success", [t["score"]["task_success"] for t in A], [t["score"]["task_success"] for t in B])
    for f in ANSWER_KEYS:
        add(f"field_{f}", *field(f))
    add("answer_valid", [t["score"]["answer_valid"] for t in A], [t["score"]["answer_valid"] for t in B])
    add("no_answer", [t["status"] != "answered" for t in A], [t["status"] != "answered" for t in B])
    for name, flag in (("critical_miss_redflag", "has_red_flag"), ("critical_miss_med", "has_med_issue")):
        add(name, [t["score"][name] for t in A], [t["score"][name] for t in B],
            [t["score"][flag] for t in A], [t["score"][flag] for t in B])
    anyd = lambda ts: [t["score"]["has_red_flag"] or t["score"]["has_med_issue"] for t in ts]  # noqa: E731
    add("critical_miss_any", [t["score"]["critical_miss_any"] for t in A], [t["score"]["critical_miss_any"] for t in B], anyd(A), anyd(B))
    for name in ("tool_calls", "systems_opened", "distinct_tools", "repeated_opens", "turns", "tokens", "input_tokens", "wall_s", "cost_usd"):
        add(name, [t[name] for t in A], [t[name] for t in B])
    # pass^k: (case, persona) succeeds only if all k trials succeed (tau-bench). Rows are (case, persona).
    def passk(arm):
        g: dict[tuple, list] = {}
        for t in arm:
            g.setdefault((t["case_id"], t["persona"]), []).append(t["score"]["task_success"])
        return {key: (len(v) >= k and all(v)) for key, v in g.items()}

    pa, pb = passk(A), passk(B)
    keys = sorted(pa)
    m[f"pass_hat_{k}"] = _metric_block([c for c, _ in keys], [pa[x] for x in keys], [1] * len(keys),
                                       [pb[x] for x in keys], [1] * len(keys), n_boot)
    n_cases = len(set(ids))
    return {"verdict": verdict(m), "n_pairs": len(A), "n_cases": n_cases, "n_case_persona_rows": len(keys), "k": k, "excluded_trials": excluded,
            "n_boot": n_boot, "bootstrap_seed": BOOT_SEED, "metrics": m}


def _f(v, nd=3):
    return "n/a" if v is None else f"{v:.{nd}f}"


def render_md(res: dict) -> str:
    L = [f"# {LABEL}", "",
         f"Evaluation `{res['evaluation_id']}` - generated {res['created_utc']}. Manifest: `{res['manifest']['id']}` "
         f"(status {res['manifest']['status']}).", "",
         "## Setup", "",
         f"- Arms: A = {ARM_NAMES['A']} (4 tools, one per snapshot source); B = {ARM_NAMES['B']} (5 tools, one screen each; an adapter, not a MedX app run). Same model, temperature, prompts, task.",
         f"- Model ids reported by the endpoint: {', '.join(res['model_ids']) or 'none'}; requested `{res['protocol']['model']}`; tool mode `{res['protocol']['tool_mode']}`; temperature {res['protocol']['temperature']}.",
         f"- Dataset `{res['dataset']['path']}` split `{res['dataset']['split']}` decision point {res['dataset']['decision_point']}; "
         f"{len(res['cases'])} cases (every gold-red-flag case, then seeded random fill; seed {res['protocol']['seed']}), personas {', '.join(res['protocol']['personas'])}, k={res['protocol']['k']}.",
         f"- Trials planned {res['integrity']['planned_trials']}, run {res['integrity']['run_trials']}, complete A/B pairs analysed "
         f"{res['summary'].get('n_pairs', 0)}, excluded {res['summary'].get('excluded_trials', 0)}. Budget {res['budget']['spent_usd']:.4f} of "
         f"{res['budget']['limit_usd']:.2f} USD{' - STOPPED at budget, partial results' if res['budget']['stopped'] else ''}.",
         f"- Failed trials (invalid answer, turn cap, provider error) stay in the denominators: {res['integrity']['non_answered']} of {res['integrity']['run_trials']} not answered.",
         "- Unit of analysis and bootstrap cluster: case (synthetic patient). Percentile 95% CI, 2000 resamples; A-B is the paired difference "
         "(same case draws). Negative A-B on success metrics / positive on effort metrics favours B.", "", "## Results", "",
         "| Metric | A n/d or mean | B n/d or mean | A-B [95% CI] |", "|---|---|---|---|"]
    for name, b in res["summary"].get("metrics", {}).items():
        def cell(x):
            return f"{x['num']:.0f}/{x['den']:.0f} = {_f(x['point'])} [{_f(x['ci_low'])}, {_f(x['ci_high'])}]" if x["den"] and float(x["den"]).is_integer() and float(x["num"]).is_integer() and x["den"] > 0 and name not in _CONT else f"mean {_f(x['point'])} [{_f(x['ci_low'])}, {_f(x['ci_high'])}]"
        d = b["A_minus_B"]
        L.append(f"| {name} | {cell(b['A'])} | {cell(b['B'])} | {_f(d['point'])} [{_f(d['ci_low'])}, {_f(d['ci_high'])}] |")
    v = res["summary"].get("verdict")
    if v:
        L += ["", "## Predeclared reading", "",
              f"Assumption support: **{'SUPPORTED' if v['supported'] else 'NOT SUPPORTED'}**"
              + ("" if v["supported"] else f" - failed: {', '.join(v['failed_criteria'])}"),
              "Criteria (all required): (a) lower 95% bound of task_success B-A >= -0.10; (b) lower 95% bound of tool_calls A-B > 0; (c) critical-miss rate B <= A (point estimate). "
              f"Observed: (a) {_f(v['a_lower_bound_B_minus_A'])}, (b) {_f(v['b_tool_calls_A_minus_B_ci_low'])}, (c) A/B {v['c_critical_miss_A_B']}. pass^k per arm is in the table (pass_hat_k).",
              "This reading is about simulated users only."]
    L += UI_MAP
    L += ["", "## Limitations", "",
          "- Simulated users are one LLM role-playing personas; behaviour is not human behaviour. No usability, satisfaction, learning or clinical-outcome claim is supported.",
          "- Gold is synthetic reference labels from predeclared rules (not expert-reviewed, not clinical ground truth); vitals_trend and current_meds references are derived by the stated rules.",
          "- Arm B (single-case consolidated view) is a schema-faithful adapter of the MedX case-page routes populated from the snapshot, not a MedX app run and not the shipped demo router (which serves one hard-coded case). System-computed red-flag/discrepancy hints are excluded, so B measures consolidation only.",
          "- Arm A contains only sources that exist in the snapshot (opd note, labs, medications, vitals); every fact is reachable in both arms. Labs are not required by any answer field.",
          "- Small number of cases and one model: intervals are wide; treat as hypothesis-generating support for the Gate 2 assumption, not a test of it.",
          "- Model-version drift, provider nondeterminism and endpoint quirks (see transcripts) can change results between runs; the request settings are recorded.",
          f"- {res['protocol']['notes'] or 'No endpoint adaptations were needed.'}", ""]
    return "\n".join(L)


_CONT = {"tool_calls", "systems_opened", "distinct_tools", "repeated_opens", "turns", "tokens", "input_tokens", "wall_s", "cost_usd"}


def load_env_file(path: Path | None = None) -> None:
    """Fill missing SIMUSER_* from a .env (KEY=VALUE, stdlib parsing). Values are never printed."""
    for p in [path] if path else [ENV_FILE, REPO_ROOT / ".env"]:
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export ").strip()
                v = v.strip().strip("'\"")
                if k.startswith("SIMUSER_") and k not in os.environ:
                    os.environ[k] = v
            return


def verdict(m: dict) -> dict:
    """Predeclared reading (manifest simuser-g2-0001): supported iff (a) and (b) and (c)."""
    ts_hi = m["task_success"]["A_minus_B"]["ci_high"]
    tc_lo = m["tool_calls"]["A_minus_B"]["ci_low"]
    cm = m["critical_miss_any"]
    a_ok = ts_hi is not None and -ts_hi >= -0.10  # lower 95% bound of B-A task_success >= -0.10
    b_ok = tc_lo is not None and tc_lo > 0
    c_ok = cm["B"]["point"] is not None and cm["A"]["point"] is not None and cm["B"]["point"] <= cm["A"]["point"]
    failed = [n for n, v in (("a_task_success_noninferior", a_ok), ("b_fewer_tool_calls", b_ok), ("c_critical_miss_B_le_A", c_ok)) if not v]
    return {"supported": not failed, "failed_criteria": failed, "a_lower_bound_B_minus_A": None if ts_hi is None else -ts_hi,
            "b_tool_calls_A_minus_B_ci_low": tc_lo, "c_critical_miss_A_B": [cm["A"]["point"], cm["B"]["point"]]}


def file_sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def execute(args, llm, cases: list[Case], out: Path, dataset: Path) -> dict:
    personas = [p for p in args.personas.split(",") if p]
    bad = [p for p in personas if p not in PERSONAS]
    if bad:
        raise SystemExit(f"unknown personas {bad}; choose from {sorted(PERSONAS)}")
    cfg = TrialCfg(args.tool_mode, args.max_turns, args.max_tokens, args.temperature)
    budget = Budget(args.budget_usd, args.price_in, args.price_out, args.price_cached)
    out.mkdir(parents=True, exist_ok=True)
    trials = run_benchmark(llm, cases, personas, args.k, cfg, budget, out, getattr(args, "workers", 1))
    manifest_path = Path(args.manifest) if args.manifest else None
    manifest = _load(manifest_path) if manifest_path and manifest_path.is_file() else {}
    res = {
        "label": LABEL, "evaluation_id": args.evaluation_id or out.name, "created_utc": utc_now(),
        "manifest": {"id": manifest.get("evaluation_id", "none"), "status": manifest.get("status", "none"),
                     "sha256": file_sha(manifest_path) if manifest_path else None},
        "protocol": {"model": getattr(llm, "model", ""), "tool_mode": cfg.tool_mode, "temperature": cfg.temperature,
                     "max_turns": cfg.max_turns, "max_tokens": cfg.max_tokens, "workers": getattr(args, "workers", 1), "k": args.k, "personas": personas, "seed": args.seed,
                     "price_usd_per_1m": {"in": args.price_in, "out": args.price_out, "cached_in": args.price_cached},
                     "notes": "; ".join(getattr(llm, "notes", []))},
        "dataset": {"path": str(dataset), "split": cases[0].split if cases else args.split, "decision_point": args.decision_point,
                    "manifest_sha256": file_sha(dataset / "manifest.json"), "splits_sha256": file_sha(dataset / "splits.json")},
        "cases": [{"case_id": c.case_id, "strata_red_flag_med_missing": list(c.strata)} for c in cases],
        "budget": {"limit_usd": budget.limit_usd, "spent_usd": round(budget.spent, 6), "stopped": budget.stopped},
        "integrity": {"planned_trials": len(cases) * len(personas) * args.k * 2, "run_trials": len(trials),
                      "non_answered": sum(t["status"] != "answered" for t in trials),
                      "statuses": {s: sum(t["status"] == s for t in trials) for s in sorted({t["status"] for t in trials})}},
        "model_ids": sorted({m for t in trials for m in t["model_ids"]}),
        "trials": trials,
    }
    res["summary"] = summarize(trials, args.k, args.n_boot)
    (out / "results.json").write_bytes(canonical_bytes(res) + b"\n")
    (out / "results.md").write_text(render_md(res), encoding="utf-8")
    return res


# ---------------------------------------------------------------- selfcheck


def _mk_item(case, dt, iid, at, **kw):
    return {"item_id": f"{case}-{iid}", "data_type": dt, "available_at_time": at, "patient_ref": "P", "encounter_ref": case,
            "provenance": "synthetic", "version": "1.1.1", "source": kw.pop("source", "synthetic-x"), **kw}


def _fixture(root: Path) -> None:
    """Four tiny synthetic cases (dev): rf+med, rf only, med only, plain. Case S3 has a FUTURE item (> T)."""
    T = "2030-01-01T10:00:00+07:00"
    early, later, future = "2030-01-01T08:00:00+07:00", "2030-01-01T09:00:00+07:00", "2030-01-01T11:00:00+07:00"
    (root).mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps({"data_class": "synthetic"}))
    (root / "splits.json").write_text("{}")
    spec = {"S0": dict(rf=True, med=True), "S1": dict(rf=True, med=False), "S2": dict(rf=False, med=True), "S3": dict(rf=False, med=False)}
    for cid, s in spec.items():
        vs2 = dict(hr=140 if s["rf"] else 84, rr=26 if s["rf"] else 16, sbp=120, spo2=97, temp_c=37.0, consciousness="A")
        items = [
            _mk_item(cid, "Demographics", "DEMO", early, age_years=50, sex="female"),
            _mk_item(cid, "AllergyList", "ALG", early, status="known", entries=[{"atc_class": "J01D", "substance": "cephalosporins"}]),
            _mk_item(cid, "Vitals", "VS1", early, hr=80, rr=16, sbp=120, spo2=97, temp_c=37.0, consciousness="A", on_oxygen=False),
            _mk_item(cid, "Vitals", "VS2", later, on_oxygen=False, **vs2),
            _mk_item(cid, "IntakeTranscript", "TX", later, turns=[{"speaker": "patient", "text": "ปวดท้อง 3 วัน", "turn_index": 0}]),
            _mk_item(cid, "MedicationList", "HOME", early, list_source="home_list", entries=[
                {"generic_name": "metformin", "atc_code": "A10BA02", "dose_value": 500, "dose_unit": "mg", "frequency": "BID"}]),
            _mk_item(cid, "MedicationList", "NO", later, list_source="new_order", entries=[
                {"generic_name": "metformin", "atc_code": "A10BA02", "dose_value": 1000 if s["med"] else 500, "dose_unit": "mg", "frequency": "BID"}]),
            _mk_item(cid, "LabSeries", "LAB", later, results=[{"test": "WBC", "value": 9.0, "unit": "10^3/uL"}]),
        ]
        if cid == "S3":
            items.append(_mk_item(cid, "MedicationList", "FUT", future, list_source="new_order", entries=[
                {"generic_name": "futuredrug", "atc_code": "Z99", "dose_value": 1, "dose_unit": "mg", "frequency": "OD"}]))
        snap = {"case_id": cid, "as_of": T, "patient_ref": "P", "encounter_ref": cid, "intake_point": "front_door", "items": items}
        d = root / "inputs" / "dev" / cid
        d.mkdir(parents=True, exist_ok=True)
        (d / "snapshot_T2.json").write_text(json.dumps(snap, ensure_ascii=False))
        gold_dt = {"decision_point": "T2", "T": T, "expected_action": "escalate" if s["rf"] else "suggest",
                   "red_flags": [{"rule_id": "RF-QSOFA", "item_ids": []}] if s["rf"] else [],
                   "medication_issues": [{"issue_type": "dose_mismatch", "drugs": ["metformin"], "injection_id": "INJ-1", "item_ids": []}] if s["med"] else [],
                   "care": {"required_inputs_missing": ["duration"] if cid == "S3" else []}}
        (root / "gold" / "dev").mkdir(parents=True, exist_ok=True)
        (root / "gold" / "dev" / f"{cid}.json").write_text(json.dumps({"case_id": cid, "decision_times": [gold_dt]}))


def _policy(answers: dict, sloppy_repeat: bool = False, bad: set | None = None, fail_at_k: dict | None = None):
    bad = bad or set()

    def policy(env, case_id, trial_no, turn):
        steps = {"A": ["get_opd_note", "get_vitals", "get_medications", "get_labs"],
                 "B": ["get_queue", "get_case_overview", "get_intake", "get_timeline", "get_medications"]}[env]
        if sloppy_repeat and env == "A":
            steps = steps + ["get_vitals", "get_labs"]
        if turn < len(steps):
            return {"type": "tools", "calls": [(steps[turn], {} if steps[turn] == "get_queue" else {"case_id": case_id})]}
        ans = copy.deepcopy(answers[case_id])
        if (case_id in bad and env == "A") or (fail_at_k and fail_at_k.get((env, case_id)) == trial_no):
            ans["red_flags"], ans["medication_issues"], ans["escalate"] = [], [], False
        return {"type": "final", "answer": ans}

    return policy


def _args(**kw):
    ns = argparse.Namespace(personas="nurse,physician", k=1, tool_mode="native", max_turns=12, max_tokens=400, temperature=0.0, workers=1,
                            budget_usd=3.0, price_in=0.10, price_out=0.50, price_cached=0.01, manifest=None, evaluation_id="selfcheck",
                            seed=1, split="dev", decision_point="T2", n_boot=200)
    ns.__dict__.update(kw)
    return ns


def selfcheck() -> None:
    n = 0

    def ok(cond, msg):
        nonlocal n
        assert cond, f"SELFCHECK FAIL: {msg}"
        n += 1

    tmp = Path(tempfile.mkdtemp(prefix="simuser-selfcheck-"))
    ds = tmp / "ds"
    _fixture(ds)
    cases = load_cases(ds, "dev", "T2")
    by = {c.case_id: c for c in cases}
    ok(len(cases) == 4, "fixture cases load")
    try:
        load_cases(ds, "test", "T2")
        ok(False, "test split must be refused")
    except SystemExit:
        ok(True, "test split refused")
    dsha = hashlib.sha256((ds / "manifest.json").read_bytes()).hexdigest()
    for status, sha, want in (("FROZEN", dsha, True), ("DRAFT_NOT_FROZEN", dsha, False), ("FROZEN", "0" * 64, False)):
        mp = tmp / f"m-{status}-{want}.json"
        mp.write_text(json.dumps({"status": status, "dataset": {"dataset_manifest_sha256": sha}}))
        ok(check_test_access(str(mp), ds) is want, f"test access gate {status} sha_match={sha == dsha}")
    ok(not check_test_access(None, ds) and not check_test_access(str(tmp / "missing.json"), ds), "test access needs a manifest")
    (tmp / "e.env").write_text("SIMUSER_MODEL='envfile-model'\nOTHER=1\n# c\nexport SIMUSER_BASE_URL=http://x/v1\n")
    os.environ["SIMUSER_BASE_URL"] = "keep"
    os.environ.pop("SIMUSER_MODEL", None)
    load_env_file(tmp / "e.env")
    ok(os.environ["SIMUSER_MODEL"] == "envfile-model" and os.environ["SIMUSER_BASE_URL"] == "keep" and "OTHER" not in os.environ, ".env fills only missing SIMUSER_* vars")
    os.environ.pop("SIMUSER_MODEL", None)
    os.environ.pop("SIMUSER_BASE_URL", None)
    ok({c.case_id for c in select_cases(cases, 2, 3)} == {"S0", "S1"}, "selection includes every gold-red-flag case first")
    ok(select_cases(cases, 4, 1) == select_cases(cases, 4, 1) and len({c.case_id for c in select_cases(cases, 3, 1)}) == 3, "stratified selection deterministic")
    ok({c.strata for c in select_cases(cases, 4, 7)} == {c.strata for c in cases}, "selection covers strata")

    # references
    s0 = by["S0"].ref
    ok(s0.vitals_trend == "worsening" and by["S3"].ref.vitals_trend == "stable", "vitals trend rule")
    ok(by["S3"].ref.current_meds == frozenset({"metformin"}), "future medication list not in reference meds")
    ok(s0.red_flags == {"RF-QSOFA"} and s0.escalate and by["S3"].ref.missing_info == {"duration"}, "reference from gold")

    # env A routing + temporal filter + no gold
    for c in cases:
        A, B = MultiSystemEnv(c.snapshot, "nurse"), CasePageEnv(c.snapshot, "nurse", ["S0", "S1"])
        o = {t: A.call(t, {"case_id": c.case_id}) for t in A.tool_names}
        types = lambda r: {i["data_type"] for i in r["records"]}  # noqa: E731
        ok(types(o["get_vitals"]) == {"Vitals"} and types(o["get_labs"]) == {"LabSeries"} and types(o["get_medications"]) == {"MedicationList"}, "A tool routing")
        ok(types(o["get_opd_note"]) == {"Demographics", "AllergyList", "IntakeTranscript"}, "A opd routing")
        ok(set(o) == {"get_opd_note", "get_labs", "get_medications", "get_vitals"}, "A tool set = existing snapshot sources")
        ok(A.call("get_vitals", {"case_id": "OTHER"}) == {"error": "case_not_found"} and A.call("nope", {})["error"] == "unknown_tool", "A error paths")
        a_ids = {i["item_id"] for r in o.values() for i in r["records"]}
        b_out = [B.call("get_case_overview", {"case_id": c.case_id}), B.call("get_timeline", {"case_id": c.case_id}),
                 B.call("get_medications", {"case_id": c.case_id}), B.call("get_queue", {}), B.call("get_intake", {"case_id": c.case_id})]
        b_ids = {e["event_id"] for e in b_out[1]["items"]} | {s["source_id"] for s in b_out[2]["sources"]}
        vis_items = visible_items(c.snapshot)
        ok(b_out[4]["intake"]["turns"] == next(i for i in vis_items if i["data_type"] == "IntakeTranscript")["turns"], "B intake carries the transcript")
        ok(all(str(m["dose_value"]) in json.dumps(b_out[2]) and m["atc_code"] in json.dumps(b_out[2]) for i in vis_items if i["data_type"] == "MedicationList" for m in i["entries"]), "B medication cards carry dose and ATC")
        ok("ATC class J01D" in json.dumps(b_out[1], ensure_ascii=False) and "50 years" in json.dumps(b_out[1]) and c.snapshot["case_id"] in json.dumps(b_out[0]), "B carries allergy class and demographics")
        ok(set(b_out[0]) >= {"display_name", "demographics", "stage", "owner", "next_action", "tabs"} and "safety" not in b_out[0] and "red_flags" not in json.dumps(b_out[0]), "B overview = UI header only, no system flags")
        vis = {i["item_id"] for i in visible_items(c.snapshot)}
        ok(a_ids == vis and b_ids == vis, "same information reachable in A and B (= visible items)")
        ok(not any(i["item_id"].endswith("FUT") for i in [x for r in o.values() for x in r["records"]]) and not any("FUT" in json.dumps(b) for b in b_out), "temporal filter (available_at_time > T) in A and B")
        blob = json.dumps([o, b_out], ensure_ascii=False)
        ok(not any(t in blob for t in FORBIDDEN_IN_TOOL_OUTPUT), "no gold keys in tool output")
        vit = [e for e in b_out[1]["items"] if e["kind"] == "vitals"]
        ok(len(vit) == 2 and "HR " in vit[0]["detail"] and "Temp 37.0 C" in vit[0]["detail"], "B timeline carries vitals in full")
        ok({i["case_id"] for i in b_out[3]["items"]} == {c.case_id, "S0", "S1"}, "B queue lists role tasks")
    ok(CasePageEnv(cases[0].snapshot, "nurse").systems_opened({"get_timeline", "get_medications"}) == 1 and MultiSystemEnv(cases[0].snapshot, "nurse").systems_opened({"get_labs", "get_vitals"}) == 2, "systems_opened")

    # scoring
    ref = s0
    perfect = ref.as_answer()
    sc = score_trial(ref, perfect)
    ok(sc["task_success"] and not sc["critical_miss_any"] and sc["answer_valid"], "perfect answer succeeds")
    miss = dict(perfect, red_flags=[], escalate=False)
    sc = score_trial(ref, miss)
    ok(not sc["task_success"] and sc["critical_miss_redflag"] and not sc["fields"]["escalate"], "missed red flag is a critical miss")
    sc = score_trial(ref, dict(perfect, medication_issues=[]))
    ok(sc["critical_miss_med"] and not sc["fields"]["medication_issues"], "missed med issue is a critical miss")
    sc = score_trial(ref, dict(perfect, medication_issues=[{"issue_type": "omission", "drugs": ["metformin"]}]))
    ok(not sc["fields"]["medication_issues"] and not sc["critical_miss_med"], "wrong type: field wrong, not a full miss")
    sc = score_trial(ref, None)
    ok(not sc["task_success"] and not sc["answer_valid"] and sc["critical_miss_redflag"] and sc["critical_miss_med"], "no answer fails and counts as critical miss")
    ok(not score_trial(ref, dict(perfect, escalate="true"))["fields"]["escalate"], "escalate must be a bool")
    ok(parse_answer("```json\n" + json.dumps(perfect) + "\n```") == perfect and parse_answer(json.dumps({"answer": perfect})) == perfect and parse_answer("hello") is None, "answer parsing")

    # pipeline in both tool modes, out files, pass^k, budget
    answers = {c.case_id: c.ref.as_answer() for c in cases}
    for mode in ("native", "json"):
        out = tmp / f"run-{mode}"
        llm = ScriptedLLM(_policy(answers, sloppy_repeat=True, bad={"S0"}))
        res = execute(_args(tool_mode=mode), llm, cases, out, ds)
        ok((out / "results.json").is_file() and (out / "results.md").is_file(), f"{mode}: outputs written")
        md = (out / "results.md").read_text(encoding="utf-8")
        ok(md.startswith("# " + LABEL) and "## Limitations" in md, f"{mode}: label and limitations present")
        ok(len(list((out / "transcripts").glob("*.jsonl"))) == 4 * 2 * 2, f"{mode}: one transcript per trial")
        tr = res["trials"]
        a_s0 = next(t for t in tr if t["env"] == "A" and t["case_id"] == "S0" and t["persona"] == "nurse")
        b_s0 = next(t for t in tr if t["env"] == "B" and t["case_id"] == "S0" and t["persona"] == "nurse")
        ok(a_s0["tool_calls"] == 6 and a_s0["repeated_opens"] == 2 and a_s0["systems_opened"] == 4 and a_s0["distinct_tools"] == 4, f"{mode}: A effort counts")
        ok(b_s0["tool_calls"] == 5 and b_s0["systems_opened"] == 1 and b_s0["repeated_opens"] == 0, f"{mode}: B effort counts")
        ok(a_s0["score"]["critical_miss_any"] and b_s0["score"]["task_success"], f"{mode}: A bad / B perfect scored")
        m = res["summary"]["metrics"]
        ok(res["summary"]["n_pairs"] == 8 and res["summary"]["excluded_trials"] == 0, f"{mode}: all pairs analysed")
        ok(m["task_success"]["B"]["num"] == 8 and m["task_success"]["A"]["num"] == 6, f"{mode}: task success counts")
        ok(m["critical_miss_redflag"]["A"]["den"] == 4 and m["critical_miss_redflag"]["A"]["num"] == 2, f"{mode}: critical miss over gold-positive denominator")
        ok(m["tool_calls"]["A_minus_B"]["point"] > 0 and m["tool_calls"]["A_minus_B"]["ci_low"] is not None, f"{mode}: paired A-B CI")
        blob = (out / "results.json").read_text(encoding="utf-8") + "".join(p.read_text(encoding="utf-8") for p in (out / "transcripts").glob("*.jsonl"))
        ok("FAKE-KEY-123" not in blob, f"{mode}: key never written")
    # json mode: the tool section describes only that env's tools
    ok("get_queue" in json_mode_tool_section(CasePageEnv.tools) and "get_queue" not in json_mode_tool_section(MultiSystemEnv.tools), "json-mode tool section per env")

    # pass^k: k=3, one failing trial of S1 in env B -> pass^3 drops for that row only
    llm = ScriptedLLM(_policy(answers, fail_at_k={("B", "S1"): 1}))
    res = execute(_args(k=3, personas="nurse"), llm, cases, tmp / "run-k3", ds)
    p = res["summary"]["metrics"]["pass_hat_3"]
    ok(p["A"]["num"] == 4 and p["B"]["num"] == 3 and p["A"]["den"] == 4, "pass^k requires all k trials")
    ok(abs(res["summary"]["metrics"]["task_success"]["B"]["point"] - 11 / 12) < 1e-9, "mean success vs pass^k differ")

    # invalid answer / turn cap stay in denominators
    llm = ScriptedLLM(lambda env, cid, tn, turn: {"type": "final", "text": "I think it is fine"} if cid == "S0" else {"type": "tools", "calls": [("get_vitals" if env == "A" else "get_timeline", {"case_id": cid})]})
    res = execute(_args(personas="nurse", max_turns=3), llm, cases, tmp / "run-bad", ds)
    st = res["integrity"]["statuses"]
    ok(st.get("invalid_answer") == 2 and st.get("turn_cap") == 6 and res["summary"]["metrics"]["task_success"]["A"]["den"] == 4, "invalid/turn-cap trials stay in denominator")

    # budget stop writes partial results with complete pairs only
    llm = ScriptedLLM(_policy(answers))
    res = execute(_args(budget_usd=0.03, price_in=1.0, price_out=1.0), llm, cases, tmp / "run-budget", ds)
    ok(res["budget"]["spent_usd"] <= 0.03 and res["budget"]["stopped"] and res["integrity"]["run_trials"] < res["integrity"]["planned_trials"], "budget stop is clean")
    ok((tmp / "run-budget" / "results.json").is_file() and "STOPPED at budget" in (tmp / "run-budget" / "results.md").read_text(encoding="utf-8"), "partial results written and flagged")
    ok(res["summary"]["excluded_trials"] == res["integrity"]["run_trials"] - res["summary"].get("n_pairs", 0) * 2, "incomplete pair excluded from analysis")

    # concurrency: same results as sequential; budget exact (never exceeded) with 4 workers
    r1 = execute(_args(k=2), ScriptedLLM(_policy(answers)), cases, tmp / "run-w1", ds)
    r4 = execute(_args(k=2, workers=4), ScriptedLLM(_policy(answers)), cases, tmp / "run-w4", ds)
    ok(r1["summary"]["metrics"]["task_success"] == r4["summary"]["metrics"]["task_success"] and len(r1["trials"]) == len(r4["trials"]) == 32, "workers=4 matches workers=1")
    rb = execute(_args(k=2, workers=4, budget_usd=0.05, price_in=1.0, price_out=1.0), ScriptedLLM(_policy(answers)), cases, tmp / "run-w4b", ds)
    ok(rb["budget"]["stopped"] and rb["budget"]["spent_usd"] <= 0.05 and rb["integrity"]["run_trials"] < 32, "budget exact under concurrency")

    # cost accounting incl. cached tokens
    b = Budget(1.0, 0.10, 0.50, 0.01)
    ok(abs(b.cost({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "cached_tokens": 400_000}) - (0.06 + 0.004 + 0.5)) < 1e-9, "cost with cached tokens")

    # HTTP client (mock transport): native tools, json mode, tools rejected, adaptive params, key hygiene
    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append({"auth": req.headers.get("authorization"), "body": body})
        if body.get("model") == "no-tools" and "tools" in body:
            return httpx.Response(400, json={"error": {"message": "Unrecognized request argument supplied: tools"}})
        if "max_tokens" in body and body["model"] == "new-style":
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens'."}})
        if "temperature" in body and body["model"] == "new-style":
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0.0"}})
        msg = {"role": "assistant", "content": "{}"}
        if "tools" in body:
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_vitals", "arguments": "{\"case_id\": \"S0\"}"}}]}
        return httpx.Response(200, json={"model": body["model"] + "-2030", "choices": [{"message": msg}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": 40}}})

    tr = httpx.MockTransport(handler)
    c1 = HttpLLM("https://example.invalid/v1", "FAKE-KEY-123", "m1", transport=tr).complete([{"role": "user", "content": "x"}], MultiSystemEnv.tools, "native", 400, 0.0)
    ok(c1.tool_calls[0]["name"] == "get_vitals" and c1.usage["cached_tokens"] == 40 and c1.model == "m1-2030", "native tool call + usage parsed")
    ok(seen[-1]["auth"] == "Bearer FAKE-KEY-123" and seen[-1]["body"]["max_tokens"] == 400 and "tools" in seen[-1]["body"], "request shape")
    c2 = HttpLLM("https://example.invalid/v1", "FAKE-KEY-123", "m1", transport=tr).complete([{"role": "user", "content": "x"}], MultiSystemEnv.tools, "json", 400, 0.0)
    ok("tools" not in seen[-1]["body"] and c2.content == "{}", "json mode sends no tools")
    try:
        HttpLLM("https://example.invalid/v1", "FAKE-KEY-123", "no-tools", transport=tr).complete([{"role": "user", "content": "x"}], MultiSystemEnv.tools, "native", 400, 0.0)
        ok(False, "tools rejection must fail fast")
    except ToolsUnsupported as e:
        ok("--tool-mode json" in str(e) and "FAKE-KEY-123" not in str(e), "tools rejection fails fast with clear message, no key")
    h = HttpLLM("https://example.invalid/v1", "FAKE-KEY-123", "new-style", transport=tr)
    h.complete([{"role": "user", "content": "x"}], [], "json", 400, 0.0)
    ok(h.token_param == "max_completion_tokens" and not h.send_temperature and len(h.notes) == 2, "adaptive max-token/temperature params recorded")
    # json-mode trial over the real HTTP client path with a text-tool reply
    def json_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        n_assist = sum(1 for m in body["messages"] if m["role"] == "assistant")
        txt = json.dumps({"tool": "get_vitals", "args": {"case_id": "S0"}}) if n_assist == 0 else json.dumps({"answer": answers["S0"]})
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": txt}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    rec = run_trial(HttpLLM("https://example.invalid/v1", "FAKE-KEY-123", "m", transport=httpx.MockTransport(json_handler)), MultiSystemEnv(by["S0"].snapshot, "nurse"),
                    "nurse", by["S0"], TrialCfg("json"), Budget(3, .1, .5))
    ok(rec["status"] == "answered" and rec["score"]["task_success"] and rec["tool_calls"] == 1, "json-mode trial end to end")
    # provider failure stays a failed trial
    rec = run_trial(HttpLLM("https://example.invalid/v1", "K", "m", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "bad key"}}))),
                    MultiSystemEnv(by["S0"].snapshot, "nurse"), "nurse", by["S0"], TrialCfg(), Budget(3, .1, .5))
    ok(rec["status"] == "provider_error" and not rec["score"]["task_success"], "provider failure is a failed trial")

    # live-app fidelity probe: real FastAPI app, mock provider, in-process
    try:
        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.main import create_app
        from app.seed import DEV_USERS, dev_password, seed_dev_users
    except Exception as e:  # pragma: no cover
        print(f"SKIP live-app probe (import failed: {type(e).__name__})")
    else:
        for k_ in ("GATEWAY_PROVIDER", "PUBLIC_DEMO"):
            os.environ.pop(k_, None)
        app = create_app(Settings(database_url=f"sqlite:///{tmp / 'live.db'}"))
        seed_dev_users(app.state.engine)
        ok(app.state.provider.name == "mock" if hasattr(app.state.provider, "name") else True, "live app uses mock provider")
        user, role, envk, default = DEV_USERS[0]
        with TestClient(app) as cl:
            r = cl.post("/api/auth/login", json={"username": user, "password": dev_password(envk, default)})
            ok(r.status_code == 200, "live app login")
            run_id = cl.post("/api/demo/v1/journeys/medx-front-door-v1/runs").json()["run_id"]
            base = f"/api/demo/v1/runs/{run_id}"
            q, ov = cl.get(f"{base}/queue"), cl.get(f"{base}/cases/SYN-2026-0017")
            tl, md = cl.get(f"{base}/cases/SYN-2026-0017/timeline"), cl.get(f"{base}/cases/SYN-2026-0017/medications")
            ok(all(x.status_code == 200 for x in (q, ov, tl, md)), "live app serves queue/case/timeline/medications")
            b = CasePageEnv(cases[0].snapshot, "nurse")
            ok({"items", "data_class"} <= set(q.json()) and {"items", "data_class"} <= set(b._t_get_queue()), "queue shape matches live route")
            ok({"items", "data_class"} <= set(tl.json()) and {"items", "data_class"} <= set(b._t_get_timeline()), "timeline shape matches live route")
            ok({"sources", "data_class"} <= set(md.json()) and {"sources", "data_class"} <= set(b._t_get_medications()), "medications shape matches live route")
            ok({"data_class", "demographics"} <= set(ov.json()) and {"data_class", "demographics"} <= set(b._t_get_case_overview()), "case shape matches live route")
            ok(set(md.json()["sources"][0]) >= {"source_id", "label", "captured_at"} and set(b._t_get_medications()["sources"][0]) >= {"source_id", "label", "captured_at"}, "medication source keys match")

    # dataset smoke (dev only, read-only) + token estimate per trial
    real = REPO_ROOT / DEFAULT_DATASET
    if (real / "manifest.json").is_file():
        rc = load_cases(real, "dev", "T2")
        pick = select_cases(rc, 8, 1)
        ok(len(pick) == 8 and all(c.ref.red_flags for c in pick[: sum(bool(c.ref.red_flags) for c in rc)][:8]), "real dev cases load; red-flag cases first")
        allmiss = {m for sp in ("train", "dev") for c in load_cases(real, sp, "T2") + load_cases(real, sp, "T1") for m in c.ref.missing_info}
        ok(allmiss <= set(MISSING_VOCAB), "gold missing-info values are inside the closed vocabulary")
        est = {}
        for arm in ARMS:
            tot = []
            for c in pick:
                env = make_env(arm, c, "nurse", [x.case_id for x in pick])
                sysp = build_system_prompt("nurse") + task_prompt(c)
                ctx = len(sysp.encode()) / 3
                inp = 0.0
                steps = ["get_opd_note", "get_vitals", "get_medications", "get_labs"] if arm == "A" else ["get_queue", "get_case_overview", "get_intake", "get_timeline", "get_medications"]
                for s in steps:
                    inp += ctx + 40  # each call resends the context so far
                    ctx += len(json.dumps(env.call(s, {"case_id": c.case_id}), ensure_ascii=False).encode()) / 3 + 40
                inp += ctx
                tot.append((inp, 60 * (len(steps) + 1)))
                blob = json.dumps([env.call(s, {"case_id": c.case_id}) for s in steps], ensure_ascii=False)
                ok(not any(t in blob for t in FORBIDDEN_IN_TOOL_OUTPUT), "real cases: no gold keys in tool output")
            est[arm] = (int(np.mean([t[0] for t in tot])), int(np.mean([t[1] for t in tot])))
        print(f"token estimate per trial (bytes/3, 5-6 calls): A in~{est['A'][0]} out~{est['A'][1]}; B in~{est['B'][0]} out~{est['B'][1]}")
        print(f"system prompt ~{int(len(build_system_prompt('nurse').encode()) / 3)} tokens")
    else:
        print("SKIP real dev-case smoke: dataset not generated (make data)")
    print(f"SELFCHECK PASS ({n} assertions)")


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="1 case x 2 envs x k=1 (first persona)")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--split", default="dev", choices=ALLOWED_SPLITS)
    ap.add_argument("--decision-point", default="T2", choices=("T1", "T2"))
    ap.add_argument("--cases", type=int, default=40)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--personas", default="nurse,physician,pharmacist")
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--out", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--evaluation-id", default=None)
    ap.add_argument("--tool-mode", default="json", choices=("native", "json"), help="gpt-6-luna rejects native tools")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=2500, help="hidden reasoning needs headroom (400 gave empty output)")
    ap.add_argument("--price-in", type=float, default=0.10, help="USD per 1M input tokens")
    ap.add_argument("--price-out", type=float, default=0.50, help="USD per 1M output tokens")
    ap.add_argument("--price-cached", type=float, default=0.01, help="USD per 1M cached input tokens")
    ap.add_argument("--budget-usd", type=float, default=3.00)
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args(argv)
    if args.selfcheck:
        selfcheck()
        return 0
    load_env_file()
    key = os.environ.get("SIMUSER_API_KEY", "")
    base = os.environ.get("SIMUSER_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("SIMUSER_MODEL", DEFAULT_MODEL)
    if not key and base == DEFAULT_BASE_URL:
        print("SIMUSER_API_KEY is not set (env var only; never pass it on the command line).", file=sys.stderr)
        return 2
    dataset = Path(args.dataset)
    dataset = dataset if dataset.is_absolute() else REPO_ROOT / dataset
    if args.smoke:
        args.split = "dev"  # smoke always runs on dev
    allow_test = args.split == "test" and check_test_access(args.manifest, dataset)
    cases = select_cases(load_cases(dataset, args.split, args.decision_point, allow_test), 1 if args.smoke else args.cases, args.seed)
    full_cases, full_k, full_personas = args.cases, args.k, len(args.personas.split(","))
    if args.smoke:
        args.k = 1
    out = Path(args.out or f"eval/results/simuser/{'smoke' if args.smoke else 'run'}-{utc_now().replace(':', '')}")
    llm = HttpLLM(base, key, model)
    try:
        res = execute(args, llm, cases, out if out.is_absolute() else REPO_ROOT / out, dataset)
    except ToolsUnsupported as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    s = res["summary"]
    print(f"{LABEL}\npairs={s.get('n_pairs', 0)} spent=${res['budget']['spent_usd']:.4f} stopped={res['budget']['stopped']} out={out}")
    if args.smoke and res["trials"]:
        n = len(res["trials"])
        proj = res["budget"]["spent_usd"] / n * (full_cases * full_personas * full_k * 2)
        print(f"smoke: {n} trials, {sum(t['tokens'] for t in res['trials'])} tokens, ${res['budget']['spent_usd']:.4f}; projected full config "
              f"({full_cases} cases x {full_personas} personas x k={full_k} x 2 arms): ${proj:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
