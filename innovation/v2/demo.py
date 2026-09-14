"""Reproducible offline vertical slice: python3 -m innovation.v2.demo."""
from datetime import datetime, timezone
import json
from innovation.v2.models import EncounterCreate, ClinicalFact, EventRequest, TurnRequest, ReviewDecision, ProposalAcceptance, DraftContent
from innovation.v2.providers import MockProvider
from innovation.v2.runtime import Runtime
from innovation.v2.service import Service, Principal
from innovation.v2.store import Store


def main():
    store = Store()
    service = Service(store, Runtime(MockProvider()))
    actor = Principal('demo-reviewer', 'physician')
    time = datetime(2026, 9, 12, tzinfo=timezone.utc)
    try:
        service.create(EncounterCreate(encounter_id='offline-demo', age=40), 'create', actor)
        conversation = service.turn('offline-demo', TurnRequest(expected_revision=0,
            idempotency_key='conversation', text='อาการ: ข้อมูลจำลองที่ต้องตรวจแก้',
            decision_time=time, intent='conversation'), actor)
        assert conversation['draft_id'] is None
        proposal = conversation['proposals'][0]
        corrected = ClinicalFact.model_validate({**proposal['fact'], 'event_id':'e0',
            'value':'ข้อความสังเคราะห์ที่บุคลากรตรวจแก้แล้ว'})
        service.accept_proposal(conversation['run_id'], proposal['proposal_id'],
            ProposalAcceptance(expected_revision=0, idempotency_key='accept', fact=corrected), actor)
        service.append_event('offline-demo', EventRequest(expected_revision=1,
            idempotency_key='correction', fact=corrected.model_copy(update={
                'event_id':'e1','supersedes_event_id':'e0','value':'ข้อมูลแก้ไขล่าสุดของเคสสังเคราะห์'})), actor)
        run = service.turn('offline-demo', TurnRequest(expected_revision=2, idempotency_key='turn',
            text='ช่วยตรวจข้อมูลที่ยังขาดและเตรียมร่าง', decision_time=time, design_id='fixed'), actor)
        assert run['status'] == 'COMPLETED'
        draft = service.review(run['draft_id'], ReviewDecision(expected_revision=2,
            idempotency_key='review', draft_revision=1, expected_review_sequence=0, action='CONFIRM'), actor)
        assert draft['effective'] and draft['content']['evidence_ids'] == ['e1']
        content = DraftContent.model_validate(draft['content'])
        content.summary += '\nผู้ตรวจจัดรูปแบบแล้ว'
        changed = service.review(run['draft_id'], ReviewDecision(expected_revision=2,
            idempotency_key='modify', draft_revision=1, expected_review_sequence=1,
            action='MODIFY', reason='ปรับถ้อยคำ', content=content), actor)
        assert not changed['effective'] and changed['draft_revision']==2
        draft = service.review(run['draft_id'], ReviewDecision(expected_revision=2,
            idempotency_key='confirm-revision-2', draft_revision=2, expected_review_sequence=2,
            action='CONFIRM'), actor)
        assert draft['effective']
        print(json.dumps({'profile': 'synthetic_intake_v1', 'case_revision': 2,
            'draft_status': draft['status'], 'effective': draft['effective'],
            'content': draft['content'], 'trace': run['trace'],
            'clinical_verdict': 'NOT_REVIEWED'}, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == '__main__':
    main()
