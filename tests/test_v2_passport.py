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


def test_internal_passport_carries_the_whole_journey_and_respects_time(client):
    c = client
    journey(c)
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    c.post('/v2/encounters/opd/events', headers=h('nurse'), json={'expected_revision': 7, 'idempotency_key': 'late', 'fact': {
        'event_id': 'late', 'kind': 'HISTORY', 'value': 'future note', 'observed_at': later, 'available_at_time': later}})
    p = c.get('/v2/encounters/opd/passport', headers=h('nurse')).json()
    assert p['physician']['reviewed_by'] == 'doctor' and p['physician']['summary']
    assert p['orders'][0]['dispense']['value']['outcome'] == 'DISPENSED'
    assert [f['value'] for f in p['return_precautions']] == ['หายใจเหนื่อย หรือไข้เกิน 3 วัน']
    assert 'late' not in {f['event_id'] for f in p['intake']}  # not yet available
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
    kinds = sorted(r['resourceType'] for r in resources)
    assert kinds == sorted(['Composition', 'Patient', 'Encounter', 'Observation', 'MedicationStatement',
                            'MedicationRequest', 'MedicationDispense', 'CarePlan'])
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
    allergy = next(s for s in composition['section'] if s['code']['coding'][0]['code'] == '48765-2')
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
