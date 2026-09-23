"""Synthetic OPD demo cases (DEC-0021): four encounters, one per journey stage.

Shared by `scripts/opd_demo.py` (local demo) and the public sandbox, which seeds a fresh
copy into every visitor's own workspace. Nothing here resembles a real patient.
"""
from datetime import datetime, timezone
from innovation.v2.models import ClinicalFact, EncounterCreate, EventRequest, ReviewDecision, TurnRequest
from innovation.v2.service import Principal

CASES = {  # encounter: (age, intake facts, orders, dispense outcomes, return precautions, confirm?)
    'opd-001': (34, [('CHIEF_COMPLAINT', 'ปวดศีรษะ 2 วัน')], [], [], [], False),
    'opd-002': (61, [('CHIEF_COMPLAINT', 'ไอ มีเสมหะ 5 วัน'), ('ALLERGY', 'ไม่มี'), ('MEDICATION', 'ไม่มี'),
                     ('VITAL', {'name': 'temperature', 'value': 37.9, 'unit': 'Cel'})], [], [], [], False),
    'opd-003': (72, [('CHIEF_COMPLAINT', 'เจ็บคอ ไข้ 3 วัน'), ('ALLERGY', 'แพ้ penicillin ผื่นลมพิษ'),
                     ('MEDICATION', 'warfarin 3 mg วันละครั้ง')],
                [{'drug': 'amoxicillin', 'dose': '500 mg', 'route': 'PO', 'frequency': 'วันละ 3 ครั้ง', 'days': 7},
                 {'drug': 'ibuprofen', 'dose': '400 mg', 'route': 'PO', 'frequency': 'เมื่อปวด', 'days': 3}], [], [], True),
    'opd-004': (45, [('CHIEF_COMPLAINT', 'ไข้ ปวดเมื่อยตัว 1 วัน'), ('ALLERGY', 'ไม่มี'), ('MEDICATION', 'ไม่มี'),
                     ('VITAL', {'name': 'temperature', 'value': 38.4, 'unit': 'Cel'})],
                [{'drug': 'paracetamol', 'dose': '500 mg', 'route': 'PO', 'frequency': 'ทุก 6 ชม. เมื่อมีไข้', 'days': 3}],
                ['DISPENSED'], ['ไข้เกิน 3 วัน หายใจเหนื่อย หรือซึมลง'], True),
}


def seed_cases(service, workspace, prefix=''):
    """Create the demo cases in `workspace`; existing ones are left untouched.

    Encounter ids are global in the store, so each public sandbox gets its own `prefix`.
    """
    # Seeded decisions are attributed to a script identity, never to a login people use.
    who = {role: Principal(f'seed-script-{role}', role, workspace) for role in ('intake', 'physician', 'pharmacist')}
    for base, (age, intake, orders, outcomes, precautions, confirm) in CASES.items():
        eid = prefix + base
        if service.store.all('encounter', eid):
            continue
        now = datetime.now(timezone.utc)
        service.create(EncounterCreate(encounter_id=eid, age=age, care_context='OPD_ADULT_GENERAL'), eid, who['intake'])
        revision = 0

        def add(kind, value, actor, suffix):
            nonlocal revision
            fact = ClinicalFact(event_id=f'{eid}-{suffix}', kind=kind, value=value, observed_at=now, available_at_time=now)
            service.append_event(eid, EventRequest(expected_revision=revision, idempotency_key=f'{eid}-{suffix}', fact=fact), actor)
            revision += 1

        for i, (kind, value) in enumerate(intake):
            add(kind, value, who['intake'], f'i{i}')
        if base == 'opd-001':  # stays at intake: no draft yet
            continue
        run = service.turn(eid, TurnRequest(expected_revision=revision, idempotency_key=f'{eid}-draft',
                           text='เตรียมร่างส่งต่อ', decision_time=now, design_id='fixed'), who['physician'])
        if confirm:
            service.review(run['draft_id'], ReviewDecision(expected_revision=revision, idempotency_key=f'{eid}-ok',
                           draft_revision=1, expected_review_sequence=0, action='CONFIRM'), who['physician'])
        for i, order in enumerate(orders):
            add('MEDICATION_ORDER', order, who['physician'], f'o{i}')
        for text in precautions:
            add('RETURN_PRECAUTION', text, who['physician'], 'rp')
        for i, outcome in enumerate(outcomes):
            add('DISPENSE', {'order_event_id': f'{eid}-o{i}', 'outcome': outcome}, who['pharmacist'], f'd{i}')
        if outcomes:  # the physician, not the system, records where the patient goes
            add('DISPOSITION', {'decision': 'HOME', 'reason': 'อาการคงที่ ได้รับยาแล้ว'}, who['physician'], 'dp')
