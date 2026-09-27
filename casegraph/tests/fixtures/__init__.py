"""Hand-written synthetic fixtures F1-F6 (SYN-* patients). Not derived from any real record or s1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from casegraph.data import (
    ClinicalText,
    Demographics,
    VoiceFact,
    VoiceIntakeFacts,
    CTVolume,
    CXRImage,
    LabResult,
    LabSeries,
    MedicationEntry,
    MedicationList,
    MRIVolume,
    Vitals,
)

UTC = timezone.utc
DAY = datetime(2026, 1, 1, tzinfo=UTC)
H = timedelta(hours=1)
M = timedelta(minutes=1)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _common(pid: str, item_id: str, event, avail, data_class="synthetic"):
    return dict(
        item_id=item_id, patient_ref=pid, event_time=event, available_at_time=avail,
        source="synthetic-fixture", provenance="casegraph/tests/fixtures", version="1", data_class=data_class,
    )


def text(pid, iid, event, avail, body="Synthetic note: cough for 3 days.", **kw):
    return ClinicalText(**_common(pid, iid, event, avail, **kw), text=body)


def vitals(pid, iid, event, avail, **values):
    # i2: consciousness "A" added so the S4 department's required vitals are complete
    values = values or {"hr": 88.0, "sbp": 124.0, "spo2": 97.0, "rr": 16.0, "temp_c": 37.2, "consciousness": "A"}
    return Vitals(**_common(pid, iid, event, avail), **values)


def s4_intake(pid, prefix, t):
    """i2: Demographics + extracted intake facts (chief complaint, onset) available at ``t``.

    Added to F1, F2 and F5 so the S4 department (Reasoning) has its REQUIRED_FIELDS and the s2/s2r
    executor tests keep a Reasoning node that runs. Facts pass through Reader:Text with 0 calls.
    """
    facts = tuple(
        VoiceFact(field=k, state="KNOWN", value=v, value_text=v, event_time=t, available_at_time=t)
        for k, v in (("chief_complaint", "synthetic: cough and fever"), ("onset_duration", "3 days"))
    )
    return [
        Demographics(**_common(pid, f"{prefix}-demo", t, t), age_years=45, sex="female"),
        VoiceIntakeFacts(**_common(pid, f"{prefix}-intake", t, t), facts=facts),
    ]


def labs(pid, iid, event, avail):
    return LabSeries(**_common(pid, iid, event, avail),
                     results=(LabResult(test="wbc", value=9.1, unit="10^9/L"), LabResult(test="crp", value=12, unit="mg/L")))


def cxr(pid, iid, event, avail):
    return CXRImage(**_common(pid, iid, event, avail), uri=f"synthetic://{pid}/{iid}.png", shape=(1024, 1024), sha256=SHA_A)


def ct(pid, iid, event, avail):
    return CTVolume(**_common(pid, iid, event, avail), uri=f"synthetic://{pid}/{iid}.nii", shape=(512, 512, 120), sha256=SHA_B)


def mri(pid, iid, event, avail):
    return MRIVolume(**_common(pid, iid, event, avail), uri=f"synthetic://{pid}/{iid}.nii", shape=(256, 256, 60), sha256=SHA_C)


def medlist(pid, iid, event, avail):
    # i2: s1 MedicationEntry shape (the s2 ``Medication``/``list_source`` per entry is retired)
    meds = (
        MedicationEntry(generic_name="Paracetamol", dose_value=500, dose_unit="mg", frequency="q6h"),
        MedicationEntry(generic_name="paracetamol", dose_value=1, dose_unit="g", frequency="q6h"),
        MedicationEntry(generic_name="Amlodipine", dose_value=5, dose_unit="mg", frequency="daily"),
    )
    return MedicationList(**_common(pid, iid, event, avail), list_source="home_list", entries=meds)


# F1: T1 has text + vitals; T2 adds CXR + medication list (Fig. 3.2).
F1_T1 = DAY + 8 * H + 30 * M
F1_T2 = DAY + 10 * H


def f1():
    p = "SYN-F1"
    return [
        text(p, "f1-text", DAY + 8 * H, DAY + 8 * H + 5 * M),
        vitals(p, "f1-vitals", DAY + 8 * H + 10 * M, DAY + 8 * H + 10 * M),
        cxr(p, "f1-cxr", DAY + 9 * H, DAY + 9 * H + 15 * M),
        medlist(p, "f1-meds", DAY + 9 * H + 30 * M, DAY + 9 * H + 30 * M),
        *s4_intake(p, "f1", DAY + 8 * H + 5 * M),
    ]


F2_T = DAY + 12 * H


def f2():
    p = "SYN-F2"
    return [
        text(p, "f2-text", DAY + 8 * H, DAY + 8 * H),
        vitals(p, "f2-vitals", DAY + 8 * H, DAY + 8 * H + M),
        labs(p, "f2-labs", DAY + 8 * H, DAY + 9 * H),
        ct(p, "f2-ct", DAY + 9 * H, DAY + 10 * H),
        mri(p, "f2-mri", DAY + 10 * H, DAY + 11 * H),
        *s4_intake(p, "f2", DAY + 8 * H),
    ]


F3_T = DAY + 12 * H


def f3():
    return [text("SYN-F3", "f3-text", DAY + 8 * H, DAY + 8 * H)]


# F4: mixed availability around T, including one item available exactly at T.
F4_T = DAY + 12 * H


def f4():
    p = "SYN-F4"
    return [
        text(p, "f4-text", DAY + 9 * H, F4_T - H),
        vitals(p, "f4-vitals-at-T", F4_T - 2 * H, F4_T),  # boundary: included
        labs(p, "f4-labs-future", F4_T - 3 * H, F4_T + timedelta(seconds=1)),  # event before T, available after
        cxr(p, "f4-cxr-future", F4_T + H, F4_T + 24 * H),
    ]


F5_T = DAY + 12 * H


def f5():
    """Full-input Red-flag case: all four placeholder rule keys present.

    s2r: ``temp_c=37.0`` added (the only fixture change allowed by slices/s2r/SPEC.md). Without it F5
    is correctly ``partially_evaluated`` (RF-PH-004 needs ``Vitals.temp_c``).
    """
    p = "SYN-F5"
    return [
        text(p, "f5-text", DAY + 9 * H, DAY + 9 * H),
        vitals(p, "f5-vitals", DAY + 9 * H, DAY + 9 * H + M, hr=118.0, sbp=84.0, spo2=86.0, temp_c=37.0,
               rr=16.0, consciousness="A"),  # i2: rr + consciousness for the S4 department's required fields
        *s4_intake(p, "f5", DAY + 9 * H),
    ]


F6_T = DAY + 12 * H


def f6():
    p = "SYN-F6"
    return [
        text(p, "f6-text-mimic", DAY + 9 * H, DAY + 9 * H, data_class="mimic"),
        vitals(p, "f6-vitals", DAY + 9 * H, DAY + 9 * H + M),
    ]


FIXTURES = {"F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5, "F6": f6}
# Primary decision time per fixture (F1 has two: T1 and T2).
CASES = [
    ("F1", F1_T1), ("F1", F1_T2), ("F2", F2_T), ("F3", F3_T), ("F4", F4_T), ("F5", F5_T), ("F6", F6_T),
]


def sweep_times(name: str) -> list[datetime]:
    """>=3 decision times per fixture: before, around and after every availability time."""
    items = FIXTURES[name]()
    times = {i.available_at_time for i in items}
    out = {DAY + 7 * H, DAY + 30 * H}
    for t in times:
        out |= {t - timedelta(microseconds=1), t, t + timedelta(microseconds=1)}
    return sorted(out)
