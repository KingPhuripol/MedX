"""Separately written synthetic vignettes; NOT expert-validated clinical cases.

Each record fixes a presentation, contextual fact state, and workflow challenge.
The deterministic expansion supplies IDs/time, not new medical ground truth.
Shared workflow patterns and related complaints remain a generalization limitation.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time import monotonic
from innovation.v2.models import (ScenarioSpec, ClinicalFact, EncounterCreate, EventRequest,
    TurnRequest, ReviewDecision, DraftContent, EvaluationRun)
from innovation.v2.service import Service, Principal
from innovation.v2.store import Store, digest
from innovation.v2.runtime import Runtime, POLICY
from innovation.v2.providers import MockProvider

DATA = Path(__file__).resolve().parents[2] / 'data/scenarios/v2/families-v2.tsv'
T = datetime(2026,9,12,tzinfo=timezone.utc)


def families():
    import json
    groups=json.loads(DATA.with_name("groups-v2.json").read_text())["groups"]
    result=[]
    for line in DATA.read_text().splitlines():
        if not line or line.startswith('#'):continue
        ident,presentation,kind,state,value,challenge=line.split('|')
        def fact(id, kind, value, state='KNOWN', time=T, old=None):
            return ClinicalFact(event_id=ident+'-'+id,kind=kind,state=state,value=value if state=='KNOWN' else None,
                observed_at=time,available_at_time=time,supersedes_event_id=old)
        first=fact('chief','CHIEF_COMPLAINT',presentation)
        context=fact('context',kind,value,state,T+timedelta(hours=1) if challenge=='future' else T)
        world=[first,context];visible=[first.event_id,context.event_id]
        if challenge=='future':visible.remove(context.event_id)
        if challenge=='correction':
            corrected=fact('corrected',kind,value+' (บุคลากรตรวจข้อความแก้ไขแล้ว)',old=context.event_id)
            world.append(corrected);visible=[first.event_id,corrected.event_id]
        if challenge=='conflict':
            other=fact('other',kind,'ข้อมูลอีกแหล่ง: ยังต้องตรวจข้อขัดแย้ง').model_copy(update={'conflicts_with_event_ids':[context.event_id]})
            world.append(other);visible.append(other.event_id)
        result.append(ScenarioSpec(family_id='family-'+ident,
            split=groups[str((int(ident)-1)//10+1)]['split'],
            scenario_group=groups[str((int(ident)-1)//10+1)]['group'], patient_age=24+(int(ident)*7)%62,
            behaviour='family:'+challenge,world=world,expected_evidence_ids=visible,
            decision_time=T,review_task=challenge if challenge in {'modify','reject'} else 'draft',
            simulator_version='authored-workflow-v2-explicit-conflicts'))
    if len(result)!=120 or len({r.family_id for r in result})!=120:
        raise ValueError('invalid family manifest')
    return result


def execute_family(case, design, seed, path, provider=None):
    began=monotonic();store=Store(path);s=Service(store,Runtime(provider or MockProvider()))
    actor=Principal('simulation-reviewer','physician');encounter=case.family_id+'-'+str(seed)
    checks={};run=None;conversation_runs=[]
    try:
        s.create(EncounterCreate(encounter_id=encounter,age=case.patient_age),'create',actor)
        from innovation.v2.models import ProposalAcceptance
        intake=s.turn(encounter,TurnRequest(expected_revision=0,idempotency_key='conversation-intake',
            text='อาการ: '+str(case.world[0].value),decision_time=case.decision_time,intent='conversation'),actor,design=design)
        conversation_runs.append(intake)
        checks['conversation_completed']=intake['status']=='COMPLETED'
        checks['conversation_does_not_confirm']=s.case(encounter)['case_revision']==0 and not intake['draft_id']
        proposals=[p for p in intake['proposals'] if p.get('proposal_id')]
        checks['proposal_extraction']=any(p['fact']['kind']=='CHIEF_COMPLAINT' and p['fact']['value']==case.world[0].value for p in proposals)
        if proposals:
            # Staff review supplies the authored fact; extraction quality is checked separately above.
            s.accept_proposal(intake['run_id'],proposals[0]['proposal_id'],ProposalAcceptance(
                expected_revision=0,idempotency_key='review-proposal',fact=case.world[0]),actor)
        else:
            s.append_event(encounter,EventRequest(expected_revision=0,idempotency_key='manual-fallback',fact=case.world[0]),actor)
        followup=s.turn(encounter,TurnRequest(expected_revision=1,idempotency_key='conversation-followup',
            text='ข้อมูลอะไรที่ยังไม่ได้รับการยืนยัน',decision_time=case.decision_time,intent='conversation'),actor,design=design)
        conversation_runs.append(followup)
        checks['followup_preserves_revision']=s.case(encounter)['case_revision']==1 and followup['draft_id'] is None
        for index,fact in enumerate(case.world[1:], start=1):
            s.append_event(encounter,EventRequest(expected_revision=index,idempotency_key=fact.event_id,fact=fact),actor)
        snapshot=s.snapshot(encounter,case.decision_time)
        expected=set(case.expected_evidence_ids)
        if {f.event_id for f in snapshot.evidence} != expected:
            return EvaluationRun(design=design,family_id=case.family_id,split=case.split,seed=seed,
                passed=False,valid_simulation=False,checks={'simulator_world_valid':False},
                elapsed_ms=(monotonic()-began)*1000,tool_calls=0,
                provenance={'error_code':'INVALID_SIMULATOR_EXPECTATION','simulator':case.simulator_version})
        checks['temporal_and_label_boundary']=True
        run=s.turn(encounter,TurnRequest(expected_revision=len(case.world),idempotency_key='run',
            text='ตรวจข้อมูลและเตรียมร่างจากหลักฐานที่พร้อมแล้ว',decision_time=case.decision_time),actor,design=design)
        checks['run_completed']=run['status']=='COMPLETED'
        checks['bounded_calls']=len(run['trace'])<=8
        checks['tool_order']=bool(run['trace']) and run['trace'][0]['tool']=='read_snapshot'
        content_report = {'semantic_verdict':'NO_DRAFT'}
        if run['draft_id']:
            draft=s.draft(run['draft_id'],actor)
            from innovation.v2.content import assess
            content_report=assess(DraftContent.model_validate(draft['content']),snapshot,extractive=provider is None)
            cited=set(draft['content']['evidence_ids'])
            checks['content_refs_valid']=cited<=expected
            checks['evidence_coverage']=cited==expected
            checks['pending_review']=not draft['effective']
            # Lexical extractive integrity applies only to the deterministic mock.
            if provider is None:
                checks['extractive_fidelity']=not content_report['unsupported_lines'] and not content_report['omitted_lines']
            if case.behaviour=='family:missing':
                checks['missing_information_detected']=bool(draft['content']['outstanding'])
            if case.behaviour=='family:conflict' and case.world[1].kind not in {'VITAL','LAB','REPORT'}:
                checks['conflict_detected']=any('ขัดแย้ง' in x for x in draft['content']['outstanding'])
            if case.review_task in {'modify','reject'}:
                def review(action,seq,key,dr=1,**kwargs):
                    return s.review(run['draft_id'],ReviewDecision(expected_revision=len(case.world),
                        idempotency_key=key,draft_revision=dr,expected_review_sequence=seq,action=action,**kwargs),actor)
                review('CONFIRM',0,'confirm')
                if case.review_task=='reject':
                    checks['rejection_revokes']=not review('REJECT',1,'reject',reason='ขอตรวจใหม่')['effective']
                else:
                    content=DraftContent.model_validate(draft['content'])
                    content.summary+='\nผู้ตรวจจัดรูปแบบข้อความแล้ว'
                    modified=review('MODIFY',1,'modify',reason='ปรับถ้อยคำ',content=content)
                    checks['modified_pending']=not modified['effective'] and modified['draft_revision']==2
                    checks['modified_confirmed']=review('CONFIRM',2,'confirm-new',dr=2)['effective']
        else:checks['draft_created']=False
        return EvaluationRun(design=design,family_id=case.family_id,split=case.split,seed=seed,
            passed=all(checks.values()),checks=checks,elapsed_ms=(monotonic()-began)*1000,
            tool_calls=sum(len(r['trace']) for r in [*conversation_runs,run]),provenance={'policy':POLICY,'case_hash':digest(case.model_dump(mode='json')),
                'simulator':case.simulator_version,'run':run,'runs':[*conversation_runs,run],'content_report':content_report,
                'content_verdict':'HUMAN_REVIEW_REQUIRED',
                'provider':run['provenance'],'seed_effect':'identifier only for deterministic simulator'})
    finally:store.close()
