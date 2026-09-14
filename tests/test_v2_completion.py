from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import datetime, timezone
import json
import httpx
import pytest
from innovation.v2.models import *
from innovation.v2.providers import MockProvider, ExternalConfig
from innovation.v2.compatible import CompatibleProvider, CompatibleSpeech
from innovation.v2.runtime import Runtime
from innovation.v2.service import Service, Principal
from innovation.v2.store import Store, DomainError

T = datetime(2026,9,12,tzinfo=timezone.utc)
P = Principal('doctor','physician')


def setup(provider=None, path=None):
    service=Service(Store(path),Runtime(provider or MockProvider()))
    service.create(EncounterCreate(encounter_id='case',age=40),'create',P)
    return service


def conversation(service, key='turn'):
    return service.turn('case',TurnRequest(expected_revision=0,idempotency_key=key,
        text='อาการ: ข้อความจำลอง',decision_time=T,intent='conversation'),P)


def test_conversation_proposal_acceptance_and_retry():
    s=setup();run=conversation(s)
    assert run['status']=='COMPLETED' and run['draft_id'] is None
    assert s.case('case')['case_revision']==0
    proposal=run['proposals'][0]
    body=ProposalAcceptance(expected_revision=0,idempotency_key='accept',
        fact=ClinicalFact.model_validate({**proposal['fact'],'value':'แก้โดยบุคลากร'}))
    result=s.accept_proposal(run['run_id'],proposal['proposal_id'],body,P)
    assert result['events'][0]['fact']['value']=='แก้โดยบุคลากร'
    assert s.accept_proposal(run['run_id'],proposal['proposal_id'],body,P)==result
    assert s.case('case')['case_revision']==1
    with pytest.raises(DomainError):
        s.accept_proposal(run['run_id'],proposal['proposal_id'],body,Principal('eval','evaluator'))
    s.store.close()


def test_provider_wait_does_not_lock_writes_and_stale_result_is_not_draft():
    entered,released=Event(),Event()
    class Slow(MockProvider):
        def infer(self,*args):
            entered.set();assert released.wait(5)
            return super().infer(*args)
    s=setup(Slow())
    with ThreadPoolExecutor(2) as pool:
        run=pool.submit(s.turn,'case',TurnRequest(expected_revision=0,idempotency_key='t',text='draft',decision_time=T),P)
        assert entered.wait(2)
        fact=ClinicalFact(event_id='a',kind='HISTORY',value='new',observed_at=T,available_at_time=T)
        write=pool.submit(s.append_event,'case',EventRequest(expected_revision=0,idempotency_key='e',fact=fact),P)
        try:
            assert write.result(timeout=2)['case_revision']==1
        finally:
            released.set()
        result=run.result(timeout=2)
    assert result['status']=='NEEDS_REVIEW' and result['draft_id'] is None
    s.store.close()


def test_recovery_does_not_replay_uncertain_provider_call(tmp_path):
    from innovation.v2.store import digest
    path=tmp_path/'db';s=setup(path=path)
    body=TurnRequest(expected_revision=0,idempotency_key='t',text='x',decision_time=T)
    ticket=digest([P.subject,'turn:case','t'])
    with s.store.transaction():
        s.store.append('ticket','case',{'ticket_id':ticket,'encounter_id':'case','checksum':'x'})
    s.store.close();s=Service(Store(path),Runtime(MockProvider()));s.recover_interrupted()
    with pytest.raises(DomainError,match='INTERRUPTED_RUN_USE_NEW_KEY'):
        s.turn('case',body,P)
    s.store.close()


def test_compatible_chat_and_speech_contract(monkeypatch):
    real=httpx.Client;requests=[]
    def handle(request):
        requests.append(request)
        if request.url.path.endswith('/audio/transcriptions'):
            assert b'name="file"' in request.content
            return httpx.Response(200,json={'text':'ข้อความถอดเสียง'})
        body=json.loads(request.content)
        assert body['model']=='configured-model' and body['max_tokens']==2048
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop',
            'message':{'content':json.dumps({'response':'กรุณาตรวจข้อมูล','facts':[],'evidence_ids':[]})}}]})
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    store=Store();provider=CompatibleProvider(ExternalConfig('http://localhost:9000/v1','','configured-model',0,0),store,['conversation'],local_free=True)
    s=setup(provider);assert conversation(s)['status']=='COMPLETED'
    assert not CompatibleSpeech(provider).transcribe(b'abc','audio/webm').confirmed
    assert len(requests)==2
    s.store.close();store.close()


def test_local_free_mode_cannot_target_remote():
    store=Store()
    with pytest.raises(ValueError):
        CompatibleProvider(ExternalConfig('https://remote.invalid','','m',0,0),store,[],local_free=True)
    store.close()


def test_authored_families_have_fixed_worlds_and_split():
    from collections import Counter
    from innovation.v2.families import families
    cases=families()
    assert len(cases)==120 and len({c.family_id for c in cases})==120
    assert Counter(c.split for c in cases)=={'development':60,'validation':30,'test':30}
    for case in cases:
        assert case.world and not case.clinical_reviewed
        assert set(case.expected_evidence_ids)<={f.event_id for f in case.world}
        if case.behaviour=='family:future':
            assert any(f.available_at_time>case.decision_time and f.event_id not in case.expected_evidence_ids for f in case.world)


@pytest.mark.parametrize('index',range(120))
def test_authored_family_fixed_workflow(index,tmp_path):
    from innovation.v2.families import families,execute_family
    from innovation.v2.runtime import DESIGNS
    result=execute_family(families()[index],DESIGNS['fixed'],0,tmp_path/'evaluation.sqlite3')
    assert result.passed,result.checks
    assert result.clinical_verdict=='NOT_REVIEWED'


def test_tool_registry_blocks_unauthorized_role():
    from innovation.v2.tools import invoke
    s=setup();snapshot=s.snapshot('case',T)
    with pytest.raises(DomainError,match='TOOL_FORBIDDEN'):
        invoke('read_snapshot',{'snapshot':snapshot,'text':'','role':'evaluator'},lambda:snapshot)
    s.store.close()


def test_invalid_world_is_not_counted_as_agent_failure(tmp_path):
    from innovation.v2.families import families,execute_family
    from innovation.v2.runtime import DESIGNS
    case=families()[0].model_copy(update={'expected_evidence_ids':['invented']})
    result=execute_family(case,DESIGNS['fixed'],0,tmp_path/'invalid.sqlite3')
    assert not result.valid_simulation and result.tool_calls==0


def test_content_report_detects_appended_invention():
    from innovation.v2.content import assess
    s=setup();snapshot=s.snapshot('case',T)
    report=assess(DraftContent(summary='invented clinical statement',evidence_ids=[]),snapshot,extractive=True)
    assert report['unsupported_lines']==['invented clinical statement']
    assert report['clinical_verdict']=='NOT_REVIEWED'
    s.store.close()


def test_invalid_designer_stops_at_budget_and_keeps_baseline():
    from innovation.v2.evaluation import search
    from innovation.v2.families import families
    class InvalidDesigner:
        calls=0
        def propose(self,feedback):
            assert feedback['remaining_designs']
            self.calls+=1
            raise ValueError('bad candidate')
    designer=InvalidDesigner()
    result=search([next(c for c in families() if c.split==split) for split in ['development','validation']],workers=0,designer=designer)
    assert designer.calls==12 and len(result['rejected_proposals'])==12
    assert result['selection_status']=='NO_VALID_CANDIDATE_KEEP_BASELINE'
