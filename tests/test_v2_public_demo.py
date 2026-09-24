"""DEC-0022 public demo: private synthetic sandboxes, role choice, limits, identifier guard."""
from fastapi.testclient import TestClient
from innovation.api.app import create_app
from innovation.config import Settings


def visitor(app):
    c = TestClient(app)
    assert c.get('/v2/session').status_code == 200  # first request issues the sandbox cookie
    return c


def test_each_visitor_gets_a_private_seeded_sandbox_and_picks_a_role(tmp_path):
    app = create_app(settings=Settings(auth_mode='public_demo', db=tmp_path / 'demo.sqlite3', v2_inline_jobs=True,
                                       public_calls_per_hour=3))
    with TestClient(app) as bootstrap:
        bootstrap.get('/health')
        a, b = visitor(app), visitor(app)
        assert a.get('/v2/session').json()['role'] == 'intake'
        assert a.post('/v2/demo/role', json={'role': 'pharmacist'}).json() == {'role': 'pharmacist', 'open': '/platform'}
        assert a.post('/v2/demo/role', json={'role': 'evaluator'}).status_code == 422
        mine = {i['encounter_id'] for i in a.get('/v2/encounters').json()['items']}
        theirs = {i['encounter_id'] for i in b.get('/v2/encounters').json()['items']}
        assert len(mine) == len(theirs) == 4 and not mine & theirs  # isolated copies of the four demo cases
        other = next(iter(theirs))
        assert a.get(f'/v2/encounters/{other}').status_code == 404
        pharmacy = next(e for e in mine if e.endswith('opd-003'))
        assert a.get(f'/v2/encounters/{pharmacy}/pharmacy-check').json()['status'] == 'NEEDS_PHARMACIST_REVIEW'
        assert a.post('/v2/experiments', json={}).status_code == 403
        assert a.get('/v1/health').status_code == 404 and a.get('/docs').status_code == 404
        # Model-backed calls are capped per sandbox.
        codes = [a.post(f'/v2/encounters/{pharmacy}/pharmacy-review').status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        # A job runs inside the request (serverless-safe) and identifier-looking text is refused.
        b.post('/v2/demo/role', json={'role': 'intake'})
        intake = next(e for e in theirs if e.endswith('opd-001'))
        revision = b.get(f'/v2/encounters/{intake}').json()['case_revision']
        job = b.post(f'/v2/encounters/{intake}/jobs', json={'expected_revision': revision, 'idempotency_key': 'k',
            'text': 'อาการ: ไอ', 'decision_time': '2026-09-23T00:00:00Z', 'intent': 'conversation', 'design_id': 'single'}).json()
        assert job['status'] == 'completed'
        leak = b.post(f'/v2/encounters/{intake}/events', json={'expected_revision': revision, 'idempotency_key': 'x', 'fact': {
            'event_id': 'x', 'kind': 'HISTORY', 'value': 'โทร 081-234-5678 เลขบัตร 1-1037-02345-67-8',
            'observed_at': '2026-09-23T00:00:00Z', 'available_at_time': '2026-09-23T00:00:00Z'}})
        assert leak.status_code == 422 and leak.json()['error']['code'] == 'POSSIBLE_REAL_IDENTIFIER'
        assert b.post('/v2/demo/reset').json() == {'reset': True}


def test_public_demo_refuses_a_model_provider_even_with_a_budget(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        Settings(auth_mode='public_demo', allow_external=True, v2_transport='openai_compatible',
                 v2_provider_url='https://llm.example/v1', v2_budget_db=tmp_path / 'b.sqlite3',
                 v2_paid_budget_usd=5, v2_call_reservation_usd=0.05)


def test_hospital_number_guard_ignores_ordinary_words():
    from innovation.v2.identifiers import guard
    guard('ปวดหลังตั้งแต่ Jan 2019 และ Plan 2026')  # must not raise
    import pytest
    from innovation.v2.store import DomainError
    for text in ('เลขHN6512345', 'HN: 6512345', 'mrn 12345'):
        with pytest.raises(DomainError):
            guard(text)


def test_public_demo_refuses_speech_and_guards_ids_and_review_text(tmp_path):
    import pytest
    for key in ('v2_speech_url', 'v2_synthesis_url'):
        with pytest.raises(ValueError):
            Settings(auth_mode='public_demo', allow_external=True, v2_budget_db=tmp_path / 'b.sqlite3',
                     **{key: 'https://speech.example/v1'})
    app = create_app(settings=Settings(auth_mode='public_demo', db=tmp_path / 'demo.sqlite3', v2_inline_jobs=True))
    with TestClient(app) as bootstrap:
        bootstrap.get('/health')
        a = visitor(app)
        for bad in ('1103702345678', 'HN6512345'):
            r = a.post('/v2/encounters', headers={'Idempotency-Key': bad}, json={'encounter_id': bad, 'age': 40})
            assert r.json()['error']['code'] == 'POSSIBLE_REAL_IDENTIFIER', bad
        a.post('/v2/demo/role', json={'role': 'physician'})
        case = next(i for i in a.get('/v2/encounters').json()['items'] if i['encounter_id'].endswith('opd-002'))
        draft = a.get(f"/v2/encounters/{case['encounter_id']}/drafts").json()[-1]
        content = {**draft['content'], 'summary': 'โทร 081.234.5678 เลขHN6512345'}
        r = a.post(f"/v2/drafts/{draft['draft_id']}/reviews", json={'expected_revision': case['case_revision'], 'idempotency_key': 'm',
            'draft_revision': 1, 'expected_review_sequence': 0, 'action': 'MODIFY', 'reason': 'แก้ถ้อยคำ', 'content': content})
        assert r.json()['error']['code'] == 'POSSIBLE_REAL_IDENTIFIER'
