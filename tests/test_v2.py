from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from innovation.api.app import create_app
from innovation.config import Settings
from innovation.v2.models import *
from innovation.v2.service import Service, Principal
from innovation.v2.runtime import Runtime, DESIGNS
from innovation.v2.providers import MockProvider, ProviderResult
from innovation.v2.store import Store, DomainError

T = datetime(2026, 9, 11, tzinfo=timezone.utc)
ACTOR = Principal('doctor-1', 'physician')

@pytest.fixture
def service():
    store = Store()
    yield Service(store, Runtime(MockProvider()))
    store.close()


def create(s, name='case-1'):
    return s.create(EncounterCreate(encounter_id=name, age=40), name, ACTOR)


def add(s, id='a', revision=0, kind='HISTORY', value='ประวัติจำลอง', state='KNOWN', time=T, old=None, case='case-1', key=None):
    return s.append_event(case, EventRequest(expected_revision=revision,idempotency_key=key or id,
        fact=ClinicalFact(event_id=id,kind=kind,state=state,value=value,observed_at=time,
        available_at_time=time,supersedes_event_id=old)),ACTOR)


def turn(s, revision=1, key='turn', time=T, design='fixed'):
    return s.turn('case-1',TurnRequest(expected_revision=revision,idempotency_key=key,
        text='ช่วยสรุป',decision_time=time,design_id=design),ACTOR)


def review(s, id, action='CONFIRM', revision=1, dr=1, seq=0, key='review', **kwargs):
    return s.review(id,ReviewDecision(expected_revision=revision,idempotency_key=key,
        draft_revision=dr,expected_review_sequence=seq,action=action,**kwargs),ACTOR)


def test_correction_time_and_resolver(service):
    create(service);add(service)
    add(service,id='b',revision=1,value='แก้ข้อมูล',time=T+timedelta(hours=1),old='a')
    assert [f.event_id for f in service.snapshot('case-1',T).evidence]==['a']
    assert [f.event_id for f in service.snapshot('case-1',T+timedelta(hours=2)).evidence]==['b']
    add(service,id='gold',revision=2,kind='LABEL',value='answer')
    assert 'gold' not in [f.event_id for f in service.snapshot('case-1',T).evidence]
    for ref in ['file:///etc/passwd','https://example.com','gold','b']:
        with pytest.raises(DomainError):service.resolve('case-1',ref,T)


def test_review_latest_modification_and_stale(service):
    create(service);add(service);r=turn(service);id=r['draft_id']
    assert not service.draft(id,ACTOR)['effective']
    assert review(service,id)['effective']
    assert not review(service,id,'REJECT',seq=1,key='reject',reason='ตรวจใหม่')['effective']
    # Retrying an old CONFIRM cannot render the now-rejected draft effective.
    assert not review(service,id)['effective']
    d=service.draft(id,ACTOR)
    content=DraftContent(**{**d['content'],'summary':'ร่างที่แก้แล้ว'})
    changed=review(service,id,'MODIFY',seq=2,key='modify',reason='แก้ข้อความ',content=content)
    assert changed['draft_revision']==2 and not changed['effective']
    assert changed['versions'][0]['content']['summary']!=changed['content']['summary']
    assert review(service,id,dr=2,seq=3,key='confirm-new')['effective']
    add(service,id='new',revision=1)
    assert service.draft(id,ACTOR)['status']=='STALE'
    with pytest.raises(DomainError):review(service,id,revision=2,dr=2,seq=4,key='stale')


def test_idempotency_atomic_across_connections(tmp_path):
    path=tmp_path/'data.sqlite'
    a,b=Service(Store(path),Runtime(MockProvider())),Service(Store(path),Runtime(MockProvider()))
    create(a)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda s:add(s,key='same'),[a,b]))
    assert results[0]==results[1]
    assert a.case('case-1')['case_revision']==1
    with pytest.raises(DomainError,match='IDEMPOTENCY_CONFLICT'):add(a,value='different',key='same')
    a.store.close();b.store.close()


def test_restart_and_append_only(tmp_path):
    path=tmp_path/'data.sqlite';s=Service(Store(path),Runtime(MockProvider()))
    create(s);add(s);r=turn(s);review(s,r['draft_id']);s.store.close()
    s=Service(Store(path),Runtime(MockProvider()))
    assert s.draft(r['draft_id'],ACTOR)['effective']
    with pytest.raises(sqlite3.IntegrityError):s.store.conn.execute('DELETE FROM v2_records')
    s.store.close()


@pytest.mark.parametrize('state',['UNKNOWN','REFUSED','NOT_AVAILABLE'])
def test_missing_states(service,state):
    create(service);add(service,state=state,value=None)
    r=turn(service)
    assert state in service.draft(r['draft_id'],ACTOR)['content']['summary']


def test_cross_case_correction(service):
    create(service);create(service,'other');add(service,case='other')
    with pytest.raises(DomainError):add(service,id='b',old='a')


@pytest.mark.parametrize('design',['single','fixed','form'])
def test_every_design_validates_provider_output(service,design):
    class Bad(MockProvider):
        def infer(self,*args):
            return ProviderResult(content=DraftContent(summary='bad',evidence_ids=['not-authorized']),model_version='bad',provider_version='bad')
    service.runtime.provider=Bad();create(service);add(service)
    r=turn(service,design=design)
    assert r['status']=='FAILED_SAFE' and not r['draft_id']


def test_timeout_and_turn_budget(service):
    class Timeout(MockProvider):
        def infer(self,*args):raise DomainError(504,'PROVIDER_TIMEOUT')
    create(service);add(service);service.runtime.provider=Timeout()
    assert turn(service)['error_code']=='PROVIDER_TIMEOUT'
    service.runtime.provider=MockProvider()
    for i in range(20):r=turn(service,key=f'turn-{i}')
    assert r['status']=='BUDGET_EXCEEDED'
    assert sum(len(r['trace']) for r in service.store.all('run'))<=30


def test_revision_race_and_event_reuse(service):
    create(service);add(service)
    with pytest.raises(DomainError,match='STALE_CASE'):add(service,id='b',revision=0)
    with pytest.raises(DomainError,match='DUPLICATE_EVENT'):add(service,revision=1,key='different')


def test_api_workflow_and_access(tmp_path):
    principals=tmp_path/'principals.json'
    principals.write_text(json.dumps({'principals':[
        {'token':'doctor-secret','subject':'doctor','role':'physician'},
        {'token':'nurse-secret','subject':'nurse','role':'intake'},
        {'token':'eval-secret','subject':'eval','role':'evaluator'}]}))
    app=create_app(settings=Settings(auth_mode='token',principals_file=principals))
    with TestClient(app) as c:
        for path in ('/platform', '/nurse', '/workspace'):
            assert c.get(path).status_code == 200
        assert c.get('/v2/encounters/a').status_code==401
        assert c.get('/v1/journeys/a/history').status_code==401
        h={'Authorization':'Bearer doctor-secret','Idempotency-Key':'a'}
        assert c.post('/v2/encounters',headers=h,json={'encounter_id':'a','age':40}).status_code==201
        assert c.post('/v2/encounters',headers={**h,'Authorization':'Bearer eval-secret'},json={'encounter_id':'b','age':40}).status_code==403
        body={'expected_revision':0,'idempotency_key':'t','text':'hello','decision_time':T.isoformat()}
        r=c.post('/v2/encounters/a/turns',headers=h,json=body).json()
        body={'expected_revision':0,'idempotency_key':'r','draft_revision':1,'expected_review_sequence':0,'action':'CONFIRM'}
        assert c.post(f"/v2/drafts/{r['draft_id']}/reviews",headers={**h,'Authorization':'Bearer nurse-secret'},json=body).status_code==403
        body['reviewer_id']='forged'
        assert c.post(f"/v2/drafts/{r['draft_id']}/reviews",headers=h,json=body).status_code==422
        body.pop('reviewer_id')
        d=c.post(f"/v2/drafts/{r['draft_id']}/reviews",headers=h,json=body).json()
        assert d['reviews'][0]['actor']=='doctor'
        audit=c.get('/v2/encounters/a/audit',headers=h).json()['items']
        assert [item['event'] for item in audit][-1]=='HUMAN_REVIEW_RECORDED'
        assert audit[-1]['actor']=='doctor'
        assert c.get('/ui/v2').status_code==200


def test_separate_platform_and_nurse_entrypoints():
    """DEC-0017: each path serves its own bundle; /workspace is only a redirect."""
    with TestClient(create_app()) as c:
        for path, title in (('/platform', 'Pratu Console'), ('/nurse', 'Pratu Intake')):
            response = c.get(path)
            assert response.status_code == 200
            assert '<div id="root"></div>' in response.text
            assert f'<title>{title} · Clinical Front Door</title>' in response.text
        assert c.get('/platform').text != c.get('/nurse').text
        legacy = c.get('/workspace', follow_redirects=False)
        assert legacy.status_code == 308 and legacy.headers['location'] == '/platform'


def test_speech_failure_is_not_text_failure():
    with TestClient(create_app()) as c:
        r=c.post('/v2/speech/transcriptions',files={'file':('a.webm',b'abc','audio/webm')})
        assert r.status_code==503
        assert c.post('/v2/encounters',headers={'Idempotency-Key':'x'},json={'encounter_id':'x','age':40}).status_code==201


def test_v2_disabled_and_schema_boundaries():
    with TestClient(create_app(settings=Settings(v2_enabled=False))) as c:
        assert c.get('/v2/capabilities').status_code==404
        assert c.get('/health').status_code==200
    with pytest.raises(ValueError):EncounterCreate(encounter_id='x',age=17)
    with pytest.raises(ValueError):EncounterCreate(encounter_id='x',age=40,classification='REAL')
    with pytest.raises(ValueError):DesignSpec(design_id='bad',nodes=['verify','draft'])


def test_audio_codec_mime_is_accepted():
    with TestClient(create_app()) as c:
        response = c.post('/v2/speech/transcriptions', files={
            'file': ('a.webm', b'abc', 'audio/webm;codecs=opus')})
        assert response.status_code == 503  # adapter absent, not unsupported MIME


def test_auth_stays_enabled_when_v2_disabled(tmp_path):
    path = tmp_path / 'principals.json'
    path.write_text(json.dumps({'principals': [
        {'token': 'secret', 'subject': 'doctor', 'role': 'physician'}]}))
    with TestClient(create_app(settings=Settings(v2_enabled=False, auth_mode='token', principals_file=path))) as c:
        assert c.get('/v1/journeys/a/history').status_code == 401
        assert c.get('/health').status_code == 200


def test_deterministic_screen_reaches_the_v2_draft(service):
    """SCR-001/SCR-002 must run on the /workspace path, not only on the v1 gateway.

    This is the regression for the gap found on 16 Sep 2026: `innovation/v2` shipped with
    no reference to the safety layer at all, so every draft the default UI produced
    carried no red flags and no urgency floor. Deleting the `screen=` argument in
    `Service.turn` fails this test.
    """
    create(service); add(service)
    draft = service.draft(turn(service)['draft_id'], ACTOR)

    screen = draft['screen']
    assert screen['policy_version'] == 'safety-policy-v2-pilot'
    # Only a HISTORY fact exists, so both required Front Door types are absent.
    assert sorted(screen['missing_required']) == ['CHIEF_COMPLAINT', 'VITAL']
    assert screen['urgency_floor'] == 'URGENT_REVIEW'
    assert [f['code'] for f in screen['red_flags']] == ['REQUIRED_INFORMATION_INCOMPLETE']
    assert screen['applied_rules'] == ['SCR-001-REQUIRED_INFORMATION_INCOMPLETE']


def test_screen_reports_unread_complaint_as_limitation_without_structural_escalation(service):
    create(service)
    add(service, id='c', kind='CHIEF_COMPLAINT', value='ไอสองวัน เป็นข้อมูลสังเคราะห์')
    draft = service.draft(turn(service, revision=1)['draft_id'], ACTOR)

    # The previous structural rule escalated every complaint-bearing case regardless of
    # content. The pilot policy states the limitation without manufacturing a red flag.
    assert 'COMPLAINT_NOT_EVALUATED_BY_RULE' not in {
        item['code'] for item in draft['screen']['red_flags']
    }
    assert any('does not evaluate free-text complaint severity' in item
               for item in draft['screen']['limitations'])

    # A physician MODIFY replaces `content`. It must not be able to drop the screen:
    # a finding a reviewer can overwrite is not a safety control.
    edited = DraftContent(**{**draft['content'], 'summary': draft['content']['summary'] + '\nแก้ไข'})
    after = review(service, draft['draft_id'], 'MODIFY', content=edited, reason='ตรวจแก้ร่าง')
    assert after['draft_revision'] == 2
    assert after['screen'] == draft['screen']


def test_t0_t1_drafts_keep_separate_snapshots_and_extended_output(service):
    create(service)
    add(service, id='c', kind='CHIEF_COMPLAINT', value='อาการจำลอง')
    add(service, id='v', revision=1, kind='VITAL',
        value={'name': 'temperature', 'value': 37.0, 'unit': 'C'})
    t0 = service.draft(turn(service, revision=2, key='t0')['draft_id'], ACTOR)
    assert t0['snapshot']['timepoint'] == 'T0'
    assert t0['content']['urgency']['level'] == 'INSUFFICIENT_INFORMATION'
    assert t0['content']['uncertainty']['abstained'] is True
    assert t0['content']['care_pathways'][0]['code'] == 'CLINICIAN_ASSESSMENT'

    add(service, id='lab', revision=2, kind='LAB',
        value={'name': 'synthetic result', 'value': 1.0, 'unit': 'unit'})
    t1 = service.draft(turn(service, revision=3, key='t1', time=T+timedelta(hours=1))['draft_id'], ACTOR)
    assert t1['snapshot']['timepoint'] == 'T1'
    assert t0['snapshot']['timepoint'] == 'T0'
    assert {item['event_id'] for item in t1['snapshot']['evidence']} == {'c', 'v', 'lab'}


def test_explicit_audit_trail_records_versions_provider_and_human_action(service):
    create(service)
    add(service)
    result = turn(service)
    review(service, result['draft_id'], action='REQUEST_INFORMATION',
           reason='ต้องมีข้อมูลเพิ่ม', key='request-info')
    events = service.store.all('audit', 'case-1')
    assert [event['event'] for event in events] == [
        'ENCOUNTER_CREATED', 'EVIDENCE_APPENDED', 'MODEL_RUN_STARTED',
        'MODEL_RUN_COMPLETED', 'HUMAN_REVIEW_RECORDED'
    ]
    completed = next(event for event in events if event['event'] == 'MODEL_RUN_COMPLETED')
    assert completed['model'] == 'deterministic-extractive-v1'
    assert completed['provider'] == 'mock-v2'
    reviewed = events[-1]
    assert reviewed['action'] == 'REQUEST_INFORMATION'
    assert reviewed['reason_code'] == 'OTHER'


def test_out_of_scope_context_abstains_and_escalates_before_provider_claim(service):
    service.create(EncounterCreate(encounter_id='trauma-case', age=40,
        care_context='TRAUMA'), 'trauma-case', ACTOR)
    add(service, case='trauma-case', id='c', kind='CHIEF_COMPLAINT', value='อาการจำลอง')
    add(service, case='trauma-case', id='v', revision=1, kind='VITAL',
        value={'name': 'pulse', 'value': 80, 'unit': 'bpm'})
    result = service.turn('trauma-case', TurnRequest(expected_revision=2,
        idempotency_key='draft', text='ช่วยสรุป', decision_time=T, design_id='fixed'), ACTOR)
    draft = service.draft(result['draft_id'], ACTOR)
    assert draft['screen']['urgency_floor'] == 'URGENT_REVIEW'
    assert draft['screen']['red_flags'][0]['code'] == 'OUT_OF_SCOPE_PRESENTATION'
    assert draft['content']['uncertainty']['abstained'] is True
    assert draft['content']['uncertainty']['escalation_required'] is True


def test_a_review_body_cannot_carry_its_own_screen(service):
    with pytest.raises(Exception):
        ReviewDecision(expected_revision=1, idempotency_key='k', draft_revision=1,
                       expected_review_sequence=0, action='CONFIRM',
                       screen={'policy_version': 'forged', 'urgency_floor': 'ROUTINE_REVIEW'})
