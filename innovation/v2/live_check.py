"""One synthetic live conversation and draft through the shared runtime.

Requires configured credentials and an explicit budget (or free loopback mode).
python -m innovation.v2.live_check --output artifacts/v2/live-check.json
This checks integration, not clinical quality. Output never includes credentials.
"""
import argparse
import json
from pathlib import Path
from innovation.v2.evaluation import provider_from_environment, manifest
from innovation.v2.models import EncounterCreate, TurnRequest, now
from innovation.v2.runtime import Runtime
from innovation.v2.service import Service, Principal
from innovation.v2.store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Refusing to overwrite previous evidence')
    provider=provider_from_environment()
    service=Service(Store(),Runtime(provider))
    actor=Principal('live-smoke','physician')
    try:
        service.create(EncounterCreate(encounter_id='synthetic-live-smoke',age=40),'create',actor)
        results=[]
        for intent,text in [('conversation','อาการ: ไอสองวัน เป็นข้อมูลสังเคราะห์'),('draft','เตรียมร่างจากข้อมูลที่ยืนยันแล้วเท่านั้น')]:
            results.append(service.turn('synthetic-live-smoke',TurnRequest(expected_revision=0,
                idempotency_key=intent,text=text,decision_time=now(),intent=intent),actor))
        from innovation.config import Settings
        from innovation.v2.readiness import fingerprint
        report={'checked_at':now().isoformat(),'configuration_fingerprint':fingerprint(Settings()),'manifest':manifest('external'),
                'connectivity_and_smoke_passed':all(r['status']=='COMPLETED' for r in results),
                'clinical_evaluation':'NOT_REVIEWED','speech_evaluation':'NOT_TESTED','runs':results}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
        print(json.dumps({k:v for k,v in report.items() if k not in {'runs','manifest'}}))
        return 0 if report['connectivity_and_smoke_passed'] else 1
    finally:
        service.store.close();provider.budget.close()

if __name__=='__main__':raise SystemExit(main())
