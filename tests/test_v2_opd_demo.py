"""DEC-0021 Phase 5: the seeded OPD demo, the hub page and per-endpoint free mode."""
import importlib.util
import json
from pathlib import Path
from fastapi.testclient import TestClient
from innovation.api.app import create_app
from innovation.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_seeded_demo_has_one_case_per_stage_and_links_every_station(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location('opd_demo', ROOT / 'scripts' / 'opd_demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    demo.seed(demo.principals())
    demo.seed(demo.principals())  # re-running is a no-op
    tokens = {p['role']: p['token'] for p in json.loads(demo.PRINCIPALS.read_text())['principals']}
    settings = Settings(auth_mode='token', principals_file=demo.PRINCIPALS, db=demo.DB)
    with TestClient(create_app(settings=settings)) as c:
        auth = lambda role: {'Authorization': f'Bearer {tokens[role]}'}
        items = c.get('/v2/encounters', headers=auth('pharmacist')).json()['items']
        assert {i['encounter_id']: i['journey_stage'] for i in items} == {
            'opd-001': 'INTAKE', 'opd-002': 'DOCTOR_REVIEW', 'opd-003': 'PHARMACY', 'opd-004': 'READY_HOME'}
        codes = {f['code'] for f in c.get('/v2/encounters/opd-003/pharmacy-check', headers=auth('pharmacist')).json()['findings']}
        assert {'ALLERGY_MATCH', 'INTERACTION'} <= codes
        assert c.get('/v2/dashboard', headers=auth('evaluator')).json()['total'] == 4
        hub = c.get('/')
        assert hub.status_code == 200
        for href in ['/nurse#/voice', '/platform#/pharmacy', '/platform#/dashboard', '/platform#/passport']:
            assert href in hub.text


def test_free_mode_applies_only_to_loopback_endpoints(tmp_path):
    settings = Settings(auth_mode='token', principals_file=_principals(tmp_path), allow_external=True,
                        v2_transport='openai_compatible', v2_local_free=True, v2_budget_db=tmp_path / 'budget.sqlite3',
                        v2_provider_url='https://llm.example/v1', v2_model='gpt-6-luna',
                        v2_speech_url='http://127.0.0.1:9100/v1')
    with TestClient(create_app(settings=settings)) as c:
        service = c.app.state.v2_service
        assert service.runtime.provider.adapter.local_free is False and service.runtime.provider.model_version == 'gpt-6-luna'


def _principals(tmp_path):
    path = tmp_path / 'p.json'
    path.write_text(json.dumps({'principals': [{'token': 't', 'subject': 's', 'role': 'physician'}]}))
    return path
