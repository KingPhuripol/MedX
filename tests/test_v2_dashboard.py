"""DEC-0021 Phase 4: journey dashboard (stage counts, waits, urgency, agent runs)."""
from test_v2_journey import client, h  # noqa: F401 (fixture)
from test_v2_passport import journey


def test_dashboard_counts_stages_waits_and_roles(client):
    c = client
    journey(c)  # one case through to the physician's HOME disposition
    c.post('/v2/encounters', headers={**h('nurse'), 'Idempotency-Key': 'w'}, json={'encounter_id': 'waiting', 'age': 30, 'care_context': 'OPD_ADULT_GENERAL'})
    c.post('/v2/encounters/opd/pharmacy-review', headers=h('pharm'))
    assert c.get('/v2/dashboard', headers=h('nurse')).status_code == 403
    d = c.get('/v2/dashboard', headers=h('pharm')).json()
    assert d['total'] == 2
    assert d['stages'] == {'INTAKE': 1, 'DOCTOR_REVIEW': 0, 'PHARMACY': 0, 'PHARMACY_HOLD': 0, 'AWAITING_DISPOSITION': 0,
                           'DISPOSITION_HOME': 1, 'DISPOSITION_REFER': 0, 'DISPOSITION_OBSERVE': 0}
    assert d['escalated'] == 1  # the OPD case is escalated by the out-of-scope screen
    assert {k: v['n'] for k, v in d['waits'].items()} == {'intake_to_draft': 1, 'draft_to_review': 1, 'review_to_dispense': 1}
    assert all(v['median_minutes'] >= 0 for v in d['waits'].values())
    assert sum(d['urgency_floor'].values()) == 1
    assert d['agent_runs'] == {'PHARMACY_AGENT_RUN:COMPLETED': 1}
