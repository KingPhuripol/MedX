"""Hand fixtures F-* for the staged Case Graph versions (slice cg-t123). Synthetic, offline, mock only.

Timeline anchor: ``T1`` (the nurse assessment time) = DAY + 09:00. Items are deliberately simple: the S4 intake
(demographics + extracted facts) passes through Reader:Text with 0 gateway calls.
"""

from __future__ import annotations

from datetime import timedelta

from casegraph.data import AllergyEntry, AllergyList, MedicationEntry, MedicationList, VoiceFact, VoiceIntakeFacts
from casegraph.stages import plan_stages

from .fixtures import DAY, H, M, _common, cxr, labs, s4_intake, vitals

T1 = DAY + 9 * H
FRESH = {"hr": 80.0, "sbp": 124.0, "spo2": 97.0, "rr": 16.0, "temp_c": 37.2, "consciousness": "A"}
URGENT = {**FRESH, "spo2": 85.0}  # RF-SPO2 (urgent)


def order(pid, iid, avail, *, event=None):
    entries = (MedicationEntry(generic_name="Amoxicillin", dose_value=500, dose_unit="mg", frequency="q8h"),)
    t = event or avail
    return MedicationList(**_common(pid, iid, t, avail), list_source="new_order", entries=entries)


def home(pid, iid, avail):
    entries = (MedicationEntry(generic_name="Paracetamol", dose_value=500, dose_unit="mg", frequency="q6h"),)
    return MedicationList(**_common(pid, iid, avail - H, avail), list_source="home_list", entries=entries)


def allergy(pid, iid, avail, status="known"):
    entries = (AllergyEntry(substance="penicillin", atc_class="J01CE", reaction="rash"),) if status == "known" else ()
    return AllergyList(**_common(pid, iid, avail - H, avail), status=status, entries=entries)


def conv_allergy(pid, iid, t, *, status=("KNOWN", "present"), allergens=None):
    """Conversation allergy facts (Reader:Text intake): ``status`` / ``allergens`` are (state, value) or None."""
    facts = []
    for field, spec in (("allergy_status", status), ("allergens", allergens)):
        if spec is not None:
            facts.append(VoiceFact(field=field, state=spec[0], value=spec[1], value_text=str(spec[1] or spec[0]),
                                   event_time=t, available_at_time=t))
    return VoiceIntakeFacts(**_common(pid, iid, t, t), facts=tuple(facts))


def base(pid, *, vs=FRESH, with_allergy=True):
    """The T1 snapshot: intake facts, one fresh vitals, a home list and (optionally) an allergy record."""
    items = [*s4_intake(pid, pid, T1 - 20 * M),
             vitals(pid, f"{pid}-vs1", T1 - 10 * M, T1 - 9 * M, **vs),
             home(pid, f"{pid}-home", T1 - 24 * H)]
    if with_allergy:
        items.append(allergy(pid, f"{pid}-allergy", T1 - 48 * H))
    return items


def f_cxr():
    """Figure 3.2: T1 nurse; CXR at t1+40 (T2 physician); a new order at t1+70 (T3 pharmacist)."""
    p = "SYN-CXR"
    return p, [*base(p), cxr(p, f"{p}-cxr", T1 + 35 * M, T1 + 40 * M), order(p, f"{p}-order", T1 + 70 * M)], T1 + 2 * H


def f_t3only():
    """No results; a new order at t1+30; no AllergyList (the conversation states an unnamed allergy)."""
    p = "SYN-T3ONLY"
    return p, [*base(p, with_allergy=False), conv_allergy(p, f"{p}-conv", T1 - 15 * M),
               order(p, f"{p}-order", T1 + 30 * M)], T1 + 2 * H


def f_same():
    """A lab and a new order share one available_at_time: T2 then T3 at the same T."""
    p = "SYN-SAME"
    e = T1 + 45 * M
    return p, [*base(p), labs(p, f"{p}-labs", e - 20 * M, e), order(p, f"{p}-order", e)], T1 + 2 * H


def f_pre():
    """A historical lab and a prior-encounter order, both available before t1: only T1."""
    p = "SYN-PRE"
    return p, [*base(p), labs(p, f"{p}-labs", T1 - 30 * H, T1 - 29 * H), order(p, f"{p}-order", T1 - 5 * H)], T1 + 2 * H


def f_future():
    """An order and a result after the horizon: no version."""
    p = "SYN-FUTURE"
    horizon = T1 + 2 * H
    return p, [*base(p), order(p, f"{p}-order", horizon + M), labs(p, f"{p}-labs", horizon, horizon + 5 * M)], horizon


def f_red(vs_each=True):
    """Urgent (RF-SPO2) vitals fresh at every stage time: lab at t1+30 (T2), order at t1+60 (T3)."""
    p = "SYN-RED"
    items = [*s4_intake(p, p, T1 - 20 * M),
             vitals(p, f"{p}-vs1", T1 - 5 * M, T1 - 4 * M, **URGENT),
             vitals(p, f"{p}-vs2", T1 + 25 * M, T1 + 26 * M, **URGENT),
             vitals(p, f"{p}-vs3", T1 + 55 * M, T1 + 56 * M, **URGENT),
             home(p, f"{p}-home", T1 - 24 * H), allergy(p, f"{p}-allergy", T1 - 48 * H),
             labs(p, f"{p}-labs", T1 + 20 * M, T1 + 30 * M), order(p, f"{p}-order", T1 + 60 * M)]
    return p, items, T1 + 2 * H


def f_stale():
    """VS1 is the only vitals (60-min window); the order arrives at t1+90, so Red-flag at T3 sees it stale."""
    p = "SYN-STALE"
    return p, [*base(p), order(p, f"{p}-order", T1 + 90 * M)], T1 + 2 * H


FIXTURES_STAGED = {"F-CXR": f_cxr, "F-T3ONLY": f_t3only, "F-SAME": f_same, "F-PRE": f_pre, "F-FUTURE": f_future,
                   "F-RED": f_red, "F-STALE": f_stale}
GOLD_STAGES = {"F-CXR": ["T1", "T2", "T3"], "F-T3ONLY": ["T1", "T3"], "F-SAME": ["T1", "T2", "T3"],
               "F-PRE": ["T1"], "F-FUTURE": ["T1"], "F-RED": ["T1", "T2", "T3"], "F-STALE": ["T1", "T3"]}


def stage_list(items, horizon):
    return [p.stage for p in plan_stages(items, T1, horizon)]
