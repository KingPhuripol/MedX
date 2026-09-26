"""Fixed department list v1 (adult OPD granularity). PROVISIONAL until clinical experts confirm it.

There is deliberately no emergency code: urgency travels only through red-flag alerts.
``mimic_services`` aligns each code with the MIMIC-IV ``services`` proxy label (proposal 3.6).
"""

from __future__ import annotations

from dataclasses import dataclass

DEPARTMENT_LIST_VERSION = "dept-1.0.0-provisional"


@dataclass(frozen=True)
class Department:
    code: str
    label_th: str
    label_en: str
    mimic_services: tuple[str, ...]


DEPARTMENTS: tuple[Department, ...] = (
    Department("MED", "อายุรกรรม", "Internal medicine", ("MED", "OMED")),
    Department("CARD", "อายุรกรรมหัวใจ", "Cardiology", ("CMED",)),
    Department("NEURO", "ประสาทวิทยา", "Neurology", ("NMED",)),
    Department("SURG", "ศัลยกรรมทั่วไป", "General surgery", ("SURG", "VSURG", "TSURG", "PSURG", "CSURG")),
    Department("ORTHO", "ศัลยกรรมกระดูกและข้อ", "Orthopedics", ("ORTHO", "TRAUM")),
    Department("URO", "ศัลยกรรมระบบทางเดินปัสสาวะ", "Urology", ("GU",)),
    Department("OBGYN", "สูติ-นรีเวชกรรม", "Obstetrics & gynecology", ("OBS", "GYN")),
    Department("EYE", "จักษุ", "Ophthalmology", ("EYE",)),
    Department("ENT", "โสต ศอ นาสิก", "ENT", ("ENT",)),
    Department("PSY", "จิตเวช", "Psychiatry", ("PSYCH",)),
)
BY_CODE: dict[str, Department] = {d.code: d for d in DEPARTMENTS}
CODES: tuple[str, ...] = tuple(BY_CODE)
