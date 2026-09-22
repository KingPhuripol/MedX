from datetime import datetime, timezone

import pytest

from innovation.v2.models import (ClinicalFact, EncounterCreate, EventRequest,
    ProposalBatchAcceptance, ReviewedProposal, TurnRequest)
from innovation.v2.providers import MockProvider
from innovation.v2.runtime import Runtime
from innovation.v2.service import Principal, Service
from innovation.v2.store import DomainError, Store

T = datetime(2026, 9, 12, tzinfo=timezone.utc)
P = Principal('reviewer', 'physician')


def service():
    s = Service(Store(), Runtime(MockProvider()))
    s.create(EncounterCreate(encounter_id='batch', age=40), 'create', P)
    return s


def fact(id, **kw):
    return ClinicalFact(event_id=id, kind='HISTORY', value='ข้อมูลจำลอง',
                        observed_at=T, available_at_time=T, **kw)


def prepare(s, facts):
    with s.store.transaction():
        s.store.append('run', 'batch', {'run_id': 'r', 'encounter_id': 'batch',
            'case_revision': 0, 'status': 'COMPLETED', 'proposals': [
                {'proposal_id': str(i), 'fact': f.model_dump(mode='json')}
                for i, f in enumerate(facts)]})
    return ProposalBatchAcceptance(expected_revision=0, idempotency_key='accept',
        proposals=[ReviewedProposal(proposal_id=str(i), fact=f) for i, f in enumerate(facts)])


def test_batch_commits_all_and_replays_without_duplicates():
    s = service()
    body = prepare(s, [fact('one'), fact('two')])
    first = s.accept_proposals('r', body, P)
    assert first['case_revision'] == 2
    assert s.accept_proposals('r', body, P) == first
    assert len(s.store.all('accepted')) == 2
    s.store.close()


def test_batch_rolls_back_earlier_fact_when_later_correction_invalid():
    s = service()
    body = prepare(s, [fact('one'), fact('two', supersedes_event_id='absent')])
    with pytest.raises(DomainError, match='INVALID_CORRECTION_TARGET'):
        s.accept_proposals('r', body, P)
    assert s.case('batch')['case_revision'] == 0
    assert s.store.all('accepted') == []
    s.store.close()


def test_batch_denies_evaluator_and_stale_case():
    s = service()
    body = prepare(s, [fact('one')])
    with pytest.raises(DomainError, match='ROLE_FORBIDDEN'):
        s.accept_proposals('r', body, Principal('evaluation', 'evaluator'))
    s.append_event('batch', EventRequest(expected_revision=0, idempotency_key='manual', fact=fact('manual')), P)
    with pytest.raises(DomainError, match='STALE_CASE_REVISION'):
        s.accept_proposals('r', body, P)
    s.store.close()


def test_draft_evidence_retains_superseded_fact():
    s = service()
    s.append_event('batch', EventRequest(expected_revision=0, idempotency_key='e', fact=fact('old')), P)
    run = s.turn('batch', TurnRequest(expected_revision=1, idempotency_key='t', text='draft', decision_time=T), P)
    s.append_event('batch', EventRequest(expected_revision=1, idempotency_key='fix',
        fact=fact('new', supersedes_event_id='old')), P)
    assert s.draft_evidence(run['draft_id'], 'old', P)['event_id'] == 'old'
    with pytest.raises(DomainError, match='EVIDENCE_NOT_AVAILABLE'):
        s.draft_evidence(run['draft_id'], 'other-case', P)
    s.store.close()


def test_session_csrf_and_workspace_isolation(tmp_path):
    import json
    from fastapi.testclient import TestClient
    from innovation.api.app import create_app
    from innovation.config import Settings
    principals = tmp_path / 'principals.json'
    principals.write_text(json.dumps({'principals': [
        {'subject': 'a', 'role': 'physician', 'token': 'secret-a', 'workspace': 'a'},
        {'subject': 'b', 'role': 'physician', 'token': 'secret-b', 'workspace': 'b'}]}))
    with TestClient(create_app(settings=Settings(auth_mode='token', principals_file=principals))) as c:
        login = c.post('/v2/session', json={'token': 'secret-a'})
        assert login.status_code == 200
        assert 'HttpOnly' in login.headers['set-cookie']
        csrf = login.json()['csrf']
        assert c.get('/v2/session').json()['subject'] == 'a'
        assert c.post('/v2/encounters', json={'encounter_id': 'private', 'age': 40},
                      headers={'Idempotency-Key': 'c'}).status_code == 403
        headers = {'X-CSRF-Token': csrf, 'Idempotency-Key': 'c'}
        assert c.post('/v2/encounters', json={'encounter_id': 'private', 'age': 40}, headers=headers).status_code == 201
        assert len(c.get('/v2/encounters').json()['items']) == 1
        r = c.post('/v2/encounters/private/turns', headers={'X-CSRF-Token': csrf}, json={
            'expected_revision': 0, 'idempotency_key': 'r', 'text': 'draft', 'decision_time': T.isoformat()}).json()
        other = {'Authorization': 'Bearer secret-b'}
        assert c.get('/v2/encounters', headers=other).json()['items'] == []
        for path in ['/encounters/private', '/encounters/private/snapshot',
                     '/encounters/private/turns', '/runs/' + r['run_id'],
                     '/drafts/' + r['draft_id']]:
            assert c.get('/v2' + path, headers=other).status_code == 404
        assert c.delete('/v2/session', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert c.get('/v2/session').status_code == 401


def test_cancel_running_job_never_creates_draft():
    from threading import Event
    from innovation.v2.jobs import Jobs
    entered, released = Event(), Event()
    class Slow(MockProvider):
        def infer(self, *args):
            entered.set()
            assert released.wait(5)
            return super().infer(*args)
    s = Service(Store(), Runtime(Slow()))
    s.create(EncounterCreate(encounter_id='batch', age=40), 'create', P)
    jobs = Jobs(s)
    body = TurnRequest(expected_revision=0, idempotency_key='slow', text='draft', decision_time=T)
    job = jobs.create('batch', body, P)
    assert entered.wait(2)
    jobs.cancel(job['job_id'])
    released.set()
    jobs.close()
    assert jobs.get(job['job_id'])['status'] == 'cancelled'
    assert s.drafts('batch', P) == []
    s.store.close()


def test_jobs_retry_only_executes_once():
    from innovation.v2.jobs import Jobs
    s = service()
    jobs = Jobs(s)
    body = TurnRequest(expected_revision=0, idempotency_key='job', text='draft', decision_time=T)
    one = jobs.create('batch', body, P)
    two = jobs.create('batch', body, P)
    jobs.close()
    assert one['job_id'] == two['job_id']
    assert jobs.get(one['job_id'])['status'] == 'completed'
    assert len(s.store.all('run')) == 1
    s.store.close()


def test_backup_restores_events_and_idempotency(tmp_path):
    from innovation.v2.backup import copy_database
    source=tmp_path/'source.sqlite3'
    s=Service(Store(source),Runtime(MockProvider()))
    s.create(EncounterCreate(encounter_id='batch',age=40),'create',P)
    request=EventRequest(expected_revision=0,idempotency_key='event',fact=fact('preserved'))
    before=s.append_event('batch',request,P)
    backup=copy_database(source,tmp_path/'backup.sqlite3')
    restored=Service(Store(backup),Runtime(MockProvider()))
    assert restored.case('batch')==before
    assert restored.append_event('batch',request,P)==before
    with pytest.raises(FileExistsError):copy_database(source,backup)
    restored.store.close();s.store.close()


def test_distinct_history_entries_are_not_assumed_contradictory():
    s=service()
    for index,id in enumerate(['one','two']):
        s.append_event('batch',EventRequest(expected_revision=index,idempotency_key=id,
            fact=fact(id).model_copy(update={'value':'history '+id})),P)
    result=s.turn('batch',TurnRequest(expected_revision=2,idempotency_key='draft',text='draft',decision_time=T,design_id='fixed'),P)
    assert not any('ขัดแย้ง' in x for x in s.draft(result['draft_id'],P)['content']['outstanding'])
    s.store.close()


def test_synthesis_contract_and_zero_budget(monkeypatch):
    import httpx
    from innovation.v2.compatible import CompatibleProvider,CompatibleSynthesis
    from innovation.v2.providers import ExternalConfig
    requests=[];real=httpx.Client
    def handler(request):
        requests.append(request)
        return httpx.Response(200,content=b'ID3synthetic',headers={'Content-Type':'audio/mpeg'})
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    store=Store()
    p=CompatibleProvider(ExternalConfig('http://localhost:9000/v1','secret','speech-model',0,0),store,[],local_free=True)
    assert CompatibleSynthesis(p,'configured-voice').synthesize('ข้อความจำลอง')==b'ID3synthetic'
    assert len(requests)==1
    paid=CompatibleProvider(ExternalConfig('https://example.invalid/v1','secret','speech-model',0,0),store,[])
    with pytest.raises(DomainError,match='PAID_BUDGET_EXCEEDED'):
        CompatibleSynthesis(paid,'configured-voice').synthesize('ข้อความจำลอง')
    assert len(requests)==1
    store.close()


def test_group_manifest_keeps_related_scenarios_together():
    from collections import Counter,defaultdict
    from innovation.v2.families import families
    cases=families();groups=defaultdict(set)
    for case in cases:groups[case.scenario_group].add(case.split)
    assert all(len(splits)==1 for splits in groups.values())
    assert Counter(c.split for c in cases)=={'development':60,'validation':30,'test':30}
    assert len({c.patient_age for c in cases})>10


def test_single_api_owner_and_release(tmp_path):
    from innovation.v2.ownership import ProcessOwnership
    first=ProcessOwnership(tmp_path/'owned.sqlite3')
    with pytest.raises(RuntimeError,match='already has an API owner'):
        ProcessOwnership(tmp_path/'owned.sqlite3')
    first.close()
    second=ProcessOwnership(tmp_path/'owned.sqlite3');second.close()


def test_disabled_v2_does_not_expose_sessions():
    from fastapi.testclient import TestClient
    from innovation.api.app import create_app
    from innovation.config import Settings
    with TestClient(create_app(settings=Settings(v2_enabled=False))) as c:
        assert c.get('/v2/session').status_code==404
        assert c.post('/v2/session',json={'token':'anything'}).status_code==404


def test_stale_revision_exposes_safe_diff_metadata():
    s=service()
    s.append_event('batch',EventRequest(expected_revision=0,idempotency_key='change',fact=fact('changed')),P)
    with pytest.raises(DomainError) as caught:
        s.ensure_revision('batch',0)
    assert caught.value.details=={
        'expected_revision':0,
        'current_revision':1,
        'changed_fact_types':['HISTORY'],
    }
    s.store.close()


def test_encounter_list_includes_attention_summary():
    from fastapi.testclient import TestClient
    from innovation.api.app import create_app
    from innovation.config import Settings
    with TestClient(create_app(settings=Settings())) as client:
        assert client.post('/v2/encounters',json={'encounter_id':'attention','age':40},
                           headers={'Idempotency-Key':'create'}).status_code==201
        before=client.get('/v2/encounters').json()['items'][0]
        assert before['attention']=={'pending_proposal_count':0,'active_job_status':None,
                                     'stale_draft':False,'needs_attention':False}
        run=client.post('/v2/encounters/attention/turns',json={
            'expected_revision':0,'idempotency_key':'turn','text':'อาการ: ไอ',
            'decision_time':T.isoformat(),'intent':'conversation'}).json()
        assert run['proposals']
        after=client.get('/v2/encounters').json()['items'][0]
        assert after['attention']['pending_proposal_count']==1
        assert after['attention']['needs_attention'] is True
        payload={'expected_revision':0,'idempotency_key':'event','fact':fact('manual').model_dump(mode='json')}
        assert client.post('/v2/encounters/attention/events',json=payload).status_code==201
        stale=client.post('/v2/encounters/attention/events',json={**payload,'idempotency_key':'stale'})
        assert stale.status_code==409
        body=stale.json()
        assert body['error']['code']=='STALE_CASE_REVISION'
        assert body['details']=={
            'expected_revision':0,'current_revision':1,'changed_fact_types':['HISTORY']}



def test_workspace_colors_are_tokenized_and_key_pairs_pass_aa():
    import re
    from pathlib import Path
    root=Path(__file__).parents[1]/'innovation'/'workspace'/'src'/'shared'
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b',(root/'style.css').read_text())
    tokens=(root/'tokens.css').read_text()
    values=dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})',tokens))
    def luminance(value):
        channels=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        channels=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
        return .2126*channels[0]+.7152*channels[1]+.0722*channels[2]
    def contrast(a,b):
        high,low=sorted((luminance(a),luminance(b)),reverse=True)
        return (high+.05)/(low+.05)
    for foreground,background in [
        ('primitive-white','primitive-black'),('primitive-white','primitive-brand-blue'),
        ('text-primary','primitive-white'),('text-muted','primitive-white'),
        ('text-info','surface-info'),('text-success','surface-success'),
        ('text-warning','surface-warning'),('text-danger','surface-danger')]:
        assert contrast(values[foreground],values[background])>=4.5,(foreground,background)


def test_five_concurrent_workspace_reads_are_fast(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from time import perf_counter
    import json
    from fastapi.testclient import TestClient
    from innovation.api.app import create_app
    from innovation.config import Settings
    principals=tmp_path/'principals.json'
    principals.write_text(json.dumps({'principals':[
        {'subject':f'user-{index}','role':'intake','token':f'token-{index}','workspace':'pilot'}
        for index in range(5)]}))
    with TestClient(create_app(settings=Settings(auth_mode='token',principals_file=principals))) as client:
        def read(index):
            start=perf_counter()
            response=client.get('/v2/encounters',headers={'Authorization':f'Bearer token-{index}'})
            return response.status_code,perf_counter()-start
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(read,range(5)))
    assert all(status==200 for status,_ in results)
    assert max(elapsed for _,elapsed in results)<.5
