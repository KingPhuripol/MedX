"""DEC-0021 Phase 1: OPD journey facts, pharmacist role and the derived journey stage."""
from datetime import datetime, timezone
import json
import pytest
from fastapi.testclient import TestClient
from innovation.api.app import create_app
from innovation.config import Settings
from innovation.v2.models import ClinicalFact, EncounterCreate, EventRequest
from innovation.v2.providers import MockProvider
from innovation.v2.runtime import Runtime
from innovation.v2.safety import screen_case
from innovation.v2.service import Principal, Service
from innovation.v2.store import Store

T = datetime(2026, 9, 11, tzinfo=timezone.utc)
ACTOR = Principal('doctor-1', 'physician')
TOKENS = {'doctor': 'physician', 'nurse': 'intake', 'pharm': 'pharmacist'}
ORDER = {'drug': 'paracetamol', 'dose': '500 mg', 'route': 'PO', 'frequency': 'q6h prn', 'days': 3}


@pytest.fixture
def client(tmp_path):
    path = tmp_path / 'principals.json'
    path.write_text(json.dumps({'principals': [
        {'token': f'{name}-secret', 'subject': name, 'role': role} for name, role in TOKENS.items()]}))
    with TestClient(create_app(settings=Settings(auth_mode='token', principals_file=path))) as c:
        yield c


def h(who):
    return {'Authorization': f'Bearer {who}-secret', 'Idempotency-Key': who + '-create'}


def post_fact(c, who, id, kind, value, revision):
    fact = {'event_id': id, 'kind': kind, 'value': value, 'observed_at': T.isoformat(),
            'available_at_time': T.isoformat()}
    return c.post('/v2/encounters/opd/events', headers=h(who),
                  json={'expected_revision': revision, 'idempotency_key': f'{who}-{id}', 'fact': fact})


def stage(c, who='doctor'):
    [item] = c.get('/v2/encounters', headers=h(who)).json()['items']
    return item['journey_stage']


def test_fact_values_are_validated():
    fact = dict(event_id='x', observed_at=T, available_at_time=T)
    ClinicalFact(kind='MEDICATION_ORDER', value={'drug': 'amoxicillin'}, **fact)
    ClinicalFact(kind='DISPENSE', value={'order_event_id': 'o', 'outcome': 'DISPENSED'}, **fact)
    for kind, value in [('MEDICATION_ORDER', {'dose': '1 g'}), ('MEDICATION_ORDER', 'amoxicillin'),
                        ('DISPENSE', {'order_event_id': 'o', 'outcome': 'HELD'}),
                        ('DISPENSE', {'order_event_id': 'o', 'outcome': 'LOST'}),
                        ('RETURN_PRECAUTION', {'text': 'x'}), ('RETURN_PRECAUTION', '  ')]:
        with pytest.raises(ValueError):
            ClinicalFact(kind=kind, value=value, **fact)


def test_opd_context_is_in_scope():
    store = Store()
    try:
        service = Service(store, Runtime(MockProvider()))
        service.create(EncounterCreate(encounter_id='opd', age=40, care_context='OPD_ADULT_GENERAL'), 'opd', ACTOR)
        service.append_event('opd', EventRequest(expected_revision=0, idempotency_key='c', fact=ClinicalFact(
            event_id='c', kind='CHIEF_COMPLAINT', value='ไอ 3 วัน', observed_at=T, available_at_time=T)), ACTOR)
        screen = screen_case(service.snapshot('opd', T))
    finally:
        store.close()
    assert 'SCR-003-OUT-OF-SCOPE' not in screen.applied_rules
    assert all(flag.code != 'OUT_OF_SCOPE_PRESENTATION' for flag in screen.red_flags)


def test_roles_per_kind_order_reference_and_stage_progression(client):
    c = client
    assert c.post('/v2/encounters', headers=h('pharm'), json={'encounter_id': 'opd', 'age': 40}).status_code == 403
    assert c.post('/v2/encounters', headers=h('nurse'), json={
        'encounter_id': 'opd', 'age': 40, 'care_context': 'OPD_ADULT_GENERAL'}).status_code == 201
    assert post_fact(c, 'pharm', 'c', 'CHIEF_COMPLAINT', 'ไอ', 0).json()['error']['code'] == 'ROLE_FORBIDDEN'
    assert post_fact(c, 'nurse', 'c', 'CHIEF_COMPLAINT', 'ไอ 3 วัน', 0).status_code == 201
    assert stage(c) == 'INTAKE' and stage(c, 'pharm') == 'INTAKE'

    turn = c.post('/v2/encounters/opd/turns', headers=h('doctor'), json={
        'expected_revision': 1, 'idempotency_key': 't', 'text': 'สรุป', 'decision_time': T.isoformat()}).json()
    assert stage(c) == 'DOCTOR_REVIEW'

    for who, kind, value in [('nurse', 'MEDICATION_ORDER', ORDER), ('pharm', 'MEDICATION_ORDER', ORDER),
                             ('nurse', 'RETURN_PRECAUTION', 'กลับมาถ้าไข้สูง'),
                             ('doctor', 'DISPENSE', {'order_event_id': 'o1', 'outcome': 'DISPENSED'})]:
        response = post_fact(c, who, 'x', kind, value, 1)
        assert (response.status_code, response.json()['error']['code']) == (403, 'ROLE_FORBIDDEN')
    unknown = post_fact(c, 'pharm', 'd0', 'DISPENSE', {'order_event_id': 'nope', 'outcome': 'DISPENSED'}, 1)
    assert (unknown.status_code, unknown.json()['error']['code']) == (422, 'INVALID_ORDER_REFERENCE')

    assert post_fact(c, 'doctor', 'o1', 'MEDICATION_ORDER', ORDER, 1).status_code == 201
    assert post_fact(c, 'doctor', 'rp', 'RETURN_PRECAUTION', 'กลับมาถ้าหายใจเหนื่อย', 2).status_code == 201
    snapshot = c.get('/v2/encounters/opd/snapshot', headers=h('pharm')).json()
    assert [f['event_id'] for f in snapshot['evidence']] == ['c']  # journey facts are not model evidence
    review = {'expected_revision': 3, 'idempotency_key': 'r', 'draft_revision': 1,
              'expected_review_sequence': 0, 'action': 'CONFIRM'}
    assert c.post(f"/v2/drafts/{turn['draft_id']}/reviews", headers=h('pharm'), json=review).status_code == 403
    draft = c.post(f"/v2/drafts/{turn['draft_id']}/reviews", headers=h('doctor'), json=review).json()
    assert draft['effective'] and draft['status'] == 'CONFIRM'
    assert stage(c) == 'PHARMACY'

    held = post_fact(c, 'pharm', 'd1', 'DISPENSE', {'order_event_id': 'o1', 'outcome': 'HELD',
                                                    'reason': 'ตรวจสอบประวัติแพ้ยา'}, 3)
    assert held.status_code == 201 and stage(c, 'pharm') == 'PHARMACY_HOLD'
    assert post_fact(c, 'pharm', 'd2', 'DISPENSE', {'order_event_id': 'o1', 'outcome': 'DISPENSED'}, 4).status_code == 201
    assert stage(c, 'pharm') == 'READY_HOME'
    [item] = c.get('/v2/encounters?stage=READY_HOME', headers=h('pharm')).json()['items']
    assert item['handoff_status'] == 'CONFIRMED' and not item['attention']['stale_draft']
    assert c.get('/v2/encounters?stage=PHARMACY', headers=h('pharm')).json()['items'] == []
    assert c.get('/v2/encounters?stage=HOME', headers=h('pharm')).status_code == 422
    audit = c.get('/v2/encounters/opd/audit?limit=100', headers=h('pharm')).json()['items']
    assert [a['role'] for a in audit if a.get('fact_kind') == 'DISPENSE'] == ['pharmacist', 'pharmacist']

    # New intake evidence after confirmation still stales the draft and returns the case to the doctor.
    assert post_fact(c, 'nurse', 'c2', 'HISTORY', 'ข้อมูลใหม่', 5).status_code == 201
    assert stage(c) == 'DOCTOR_REVIEW'
