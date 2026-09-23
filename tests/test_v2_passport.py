"""DEC-0021 Phase 3: Universal Med Passport (internal hand-off + FHIR R4 document Bundle)."""
from datetime import datetime, timedelta, timezone
from test_v2_journey import T, client, h, post_fact  # noqa: F401 (fixture)


def journey(c):
    c.post('/v2/encounters', headers=h('nurse'), json={'encounter_id': 'opd', 'age': 52, 'care_context': 'OPD_ADULT_GENERAL'})
    post_fact(c, 'nurse', 'c', 'CHIEF_COMPLAINT', 'ไอ มีไข้ 3 วัน', 0)
    post_fact(c, 'nurse', 'a', 'ALLERGY', 'ไม่มี', 1)
    post_fact(c, 'nurse', 'v', 'VITAL', {'name': 'temperature', 'value': 38.2, 'unit': 'Cel'}, 2)
    post_fact(c, 'nurse', 'm', 'MEDICATION', 'amlodipine 5 mg', 3)
    turn = c.post('/v2/encounters/opd/turns', headers=h('doctor'), json={
        'expected_revision': 4, 'idempotency_key': 't', 'text': 'สรุป', 'decision_time': T.isoformat()}).json()
    c.post(f"/v2/drafts/{turn['draft_id']}/reviews", headers=h('doctor'), json={
        'expected_revision': 4, 'idempotency_key': 'r', 'draft_revision': 1, 'expected_review_sequence': 0, 'action': 'CONFIRM'})
    post_fact(c, 'doctor', 'o1', 'MEDICATION_ORDER', {'drug': 'paracetamol', 'dose': '500 mg', 'frequency': 'q6h prn', 'days': 3}, 4)
    post_fact(c, 'doctor', 'rp', 'RETURN_PRECAUTION', 'หายใจเหนื่อย หรือไข้เกิน 3 วัน', 5)
    post_fact(c, 'pharm', 'd1', 'DISPENSE', {'order_event_id': 'o1', 'outcome': 'DISPENSED'}, 6)
    post_fact(c, 'doctor', 'dp', 'DISPOSITION', {'decision': 'HOME', 'reason': 'ไข้ลดลง ทบทวนแล้ว'}, 7)


def test_internal_passport_carries_the_whole_journey_and_respects_time(client):
    c = client
    journey(c)
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    c.post('/v2/encounters/opd/events', headers=h('nurse'), json={'expected_revision': 8, 'idempotency_key': 'late', 'fact': {
        'event_id': 'late', 'kind': 'HISTORY', 'value': 'future note', 'observed_at': later, 'available_at_time': later}})
    p = c.get('/v2/encounters/opd/passport', headers=h('nurse')).json()
    assert p['physician']['reviewed_by'] == 'doctor' and p['physician']['summary']
    assert p['orders'][0]['dispense']['value']['outcome'] == 'DISPENSED'
    assert [f['value'] for f in p['return_precautions']] == ['หายใจเหนื่อย หรือไข้เกิน 3 วัน']
    assert 'late' not in {f['event_id'] for f in p['intake']}  # not yet available
    assert {f['kind'] for f in p['intake']} == {'CHIEF_COMPLAINT', 'ALLERGY', 'VITAL', 'MEDICATION'}
    assert p['disposition']['value']['decision'] == 'HOME'
    assert c.get(f'/v2/encounters/opd/passport?as_of={later.replace("+", "%2B")}', headers=h('pharm')).json()['intake'][-1]['event_id'] == 'late'
    earlier = c.get('/v2/encounters/opd/passport?as_of=2020-01-01T00:00:00Z', headers=h('doctor')).json()
    assert earlier['orders'] == [] and earlier['physician'] is None and earlier['intake'] == []


def test_fhir_bundle_is_a_closed_ips_shaped_document(client):
    c = client
    journey(c)
    response = c.get('/v2/encounters/opd/passport/fhir', headers=h('pharm'))
    assert response.headers['content-type'].startswith('application/fhir+json')
    bundle = response.json()
    assert bundle['type'] == 'document' and bundle['identifier'] and bundle['timestamp']
    resources = [e['resource'] for e in bundle['entry']]
    assert resources[0]['resourceType'] == 'Composition'
    kinds = {r['resourceType'] for r in resources}
    assert kinds == {'Composition', 'Patient', 'Encounter', 'Observation', 'MedicationStatement',
                     'MedicationRequest', 'MedicationDispense', 'CarePlan', 'Flag'}
    flags = [r['code']['text'] for r in resources if r['resourceType'] == 'Flag']
    assert any('OUT_OF_SCOPE_PRESENTATION' in f for f in flags)  # escalation travels with the passport
    assert resources[0]['status'] == 'final'  # physician confirmed and recorded a disposition
    urls = [e['fullUrl'] for e in bundle['entry']]
    assert len(set(urls)) == len(urls) and all(u.startswith('urn:uuid:') for u in urls)

    def refs(node):
        if isinstance(node, dict):
            yield from ([node['reference']] if 'reference' in node else [])
            for value in node.values():
                yield from refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from refs(value)

    def empty(node):
        return node in ([], {}, '', None) or (isinstance(node, dict) and any(empty(v) for v in node.values())) \
            or (isinstance(node, list) and any(empty(v) for v in node))

    assert set(refs(bundle)) <= set(urls)  # every reference resolves inside the document
    assert not empty(bundle)  # FHIR forbids empty elements
    assert all(r['meta']['security'][0]['code'] == 'HTEST' for r in resources)
    composition = resources[0]
    allergy = next(s for s in composition['section'] if s.get('code', {}).get('coding', [{}])[0].get('code') == '48765-2')
    assert allergy['emptyReason']['coding'][0]['code'] == 'nilknown'  # "ไม่มี" = asked, none known
    vital = next(r for r in resources if r['resourceType'] == 'Observation')
    assert vital['code']['coding'][0]['code'] == '8310-5'
    dispense = next(r for r in resources if r['resourceType'] == 'MedicationDispense')
    assert dispense['status'] == 'completed'
    encounter = next(r for r in resources if r['resourceType'] == 'Encounter')
    assert encounter['class']['code'] == 'AMB' and encounter['status'] == 'finished'


def test_passport_agent_proposes_but_physician_confirms(client):
    c = client
    journey(c)
    assert c.post('/v2/encounters/opd/passport-assist', headers=h('pharm')).status_code == 403
    run = c.post('/v2/encounters/opd/passport-assist', headers=h('doctor')).json()
    assert run['status'] == 'COMPLETED' and 'paracetamol' in run['patient_summary']
    assert run['proposed_return_precautions'] == []  # physician already confirmed one
    assert [t['tool'] for t in run['trace']] == ['get_physician_summary', 'get_medications', 'get_return_precautions']
    audit = c.get('/v2/encounters/opd/audit?limit=100', headers=h('doctor')).json()['items']
    assert any(a['event'] == 'PASSPORT_AGENT_RUN' for a in audit)


def test_review_fixes_dispense_gate_replaced_orders_and_exports(client):  # clinical safety review M1, M4, minors
    c = client
    c.post('/v2/encounters', headers=h('nurse'), json={'encounter_id': 'opd', 'age': 40, 'care_context': 'OPD_ADULT_GENERAL'})
    post_fact(c, 'nurse', 'a', 'ALLERGY', 'ไม่มี', 0)
    post_fact(c, 'nurse', 'm', 'MEDICATION', 'ไม่มี', 1)
    post_fact(c, 'doctor', 'o1', 'MEDICATION_ORDER', {'drug': 'ibuprofen', 'dose': '400 mg', 'frequency': 'prn'}, 2)
    early = post_fact(c, 'pharm', 'd0', 'DISPENSE', {'order_event_id': 'o1', 'outcome': 'DISPENSED'}, 3)
    assert (early.status_code, early.json()['error']['code']) == (409, 'HANDOFF_NOT_CONFIRMED')
    turn = c.post('/v2/encounters/opd/turns', headers=h('doctor'), json={
        'expected_revision': 3, 'idempotency_key': 't', 'text': 'สรุป', 'decision_time': T.isoformat()}).json()
    c.post(f"/v2/drafts/{turn['draft_id']}/reviews", headers=h('doctor'), json={
        'expected_revision': 3, 'idempotency_key': 'r', 'draft_revision': 1, 'expected_review_sequence': 0, 'action': 'CONFIRM'})
    assert post_fact(c, 'pharm', 'd1', 'DISPENSE', {'order_event_id': 'o1', 'outcome': 'DISPENSED'}, 3).status_code == 201
    history = c.get('/v2/encounters/opd/history', headers=h('pharm')).json()['items']
    assert history[-1]['pharmacy_check']['status'] == 'NO_RULE_FINDINGS'  # verdict stored with the dispense
    # Replacing a dispensed order must not erase what the patient received.
    c.post('/v2/encounters/opd/events', headers=h('doctor'), json={'expected_revision': 4, 'idempotency_key': 'o2', 'fact': {
        'event_id': 'o2', 'kind': 'MEDICATION_ORDER', 'value': {'drug': 'paracetamol', 'dose': '500 mg', 'frequency': 'q6h'},
        'supersedes_event_id': 'o1', 'observed_at': T.isoformat(), 'available_at_time': T.isoformat()}})
    orders = c.get('/v2/encounters/opd/passport', headers=h('doctor')).json()['orders']
    assert {(o['value']['drug'], bool(o['dispense']), o.get('replaced', False)) for o in orders} == {
        ('paracetamol', False, False), ('ibuprofen', True, True)}
    bad = c.post('/v2/encounters/opd/events', headers=h('pharm'), json={'expected_revision': 5, 'idempotency_key': 'u', 'fact': {
        'event_id': 'u', 'kind': 'DISPENSE', 'state': 'UNKNOWN', 'value': None, 'observed_at': T.isoformat(), 'available_at_time': T.isoformat()}})
    assert bad.status_code == 422
    assert c.get('/v2/encounters/opd/passport?as_of=2026-09-11T00:00:00', headers=h('doctor')).status_code == 422
    c.get('/v2/encounters/opd/passport/fhir', headers=h('pharm'))
    audit = c.get('/v2/encounters/opd/audit?limit=100', headers=h('doctor')).json()['items']
    assert any(a['event'] == 'PASSPORT_EXPORTED' for a in audit)


def test_second_order_of_a_pair_and_draftless_escalation_are_gated(client):  # re-review MAJOR-2, MAJOR-3
    c = client
    c.post('/v2/encounters', headers=h('nurse'), json={'encounter_id': 'opd', 'age': 60})  # ED context
    post_fact(c, 'nurse', 'c', 'CHIEF_COMPLAINT', 'เจ็บหน้าอก', 0)
    # No draft yet: the deterministic screen still escalates (vitals missing), so HOME needs a reason.
    early = post_fact(c, 'doctor', 'dp0', 'DISPOSITION', {'decision': 'HOME'}, 1)
    assert (early.status_code, early.json()['error']['code']) == (422, 'DISPOSITION_REASON_REQUIRED')
    assert c.get('/v2/encounters/opd/passport', headers=h('doctor')).json()['escalation']
    post_fact(c, 'nurse', 'a', 'ALLERGY', 'ไม่มี', 1)
    post_fact(c, 'nurse', 'm', 'MEDICATION', 'ไม่มี', 2)
    turn = c.post('/v2/encounters/opd/turns', headers=h('doctor'), json={
        'expected_revision': 3, 'idempotency_key': 't', 'text': 'สรุป', 'decision_time': T.isoformat()}).json()
    c.post(f"/v2/drafts/{turn['draft_id']}/reviews", headers=h('doctor'), json={
        'expected_revision': 3, 'idempotency_key': 'r', 'draft_revision': 1, 'expected_review_sequence': 0, 'action': 'CONFIRM'})
    post_fact(c, 'doctor', 'w', 'MEDICATION_ORDER', {'drug': 'warfarin', 'dose': '3 mg', 'frequency': 'od'}, 3)
    post_fact(c, 'doctor', 'i', 'MEDICATION_ORDER', {'drug': 'ibuprofen', 'dose': '400 mg', 'frequency': 'prn'}, 4)
    second = post_fact(c, 'pharm', 'd', 'DISPENSE', {'order_event_id': 'i', 'outcome': 'DISPENSED'}, 5)
    assert (second.status_code, second.json()['error']['code']) == (422, 'OVERRIDE_REASON_REQUIRED')
    assert 'INTERACTION' in second.json()['details']['findings']
