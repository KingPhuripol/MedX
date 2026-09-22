"""Process-isolated simulation/search CLI. Search never accepts test cases.

python -m innovation.v2.evaluation regression --output artifacts/v2/regression.json
python -m innovation.v2.evaluation search --output artifacts/v2/search.json
python -m innovation.v2.evaluation freeze --input artifacts/v2/search.json --design fixed --output artifacts/v2/selection.json
python -m innovation.v2.evaluation heldout --input artifacts/v2/selection.json --output artifacts/v2/heldout.json
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
import json
from pathlib import Path
import random
import subprocess
import tempfile
from innovation.v2.models import DesignSpec, ScenarioSpec
from innovation.v2.runtime import DESIGNS, POLICY
from innovation.v2.simulation import regression, factorial, execute_scenario
from innovation.v2.store import digest, DomainError
from innovation.v2.families import families, execute_family


def provider_from_environment():
    from innovation.config import Settings
    from innovation.v2.providers import HttpProvider, ExternalConfig
    from innovation.v2.store import Store
    settings=Settings()
    if not settings.v2_provider_url or not settings.allow_external or settings.auth_mode!='token':
        raise ValueError('external evaluation requires explicitly configured authorized provider')
    config = ExternalConfig(settings.v2_provider_url,settings.v2_provider_token,settings.v2_model,
        settings.v2_paid_budget_usd,settings.v2_call_reservation_usd)
    budget = Store(settings.v2_budget_db)
    if settings.v2_transport == 'openai_compatible':
        from innovation.v2.compatible import CompatibleProvider
        return CompatibleProvider(config,budget,settings.v2_capabilities,local_free=settings.v2_local_free,
            json_mode=settings.v2_json_mode,max_tokens=settings.v2_max_tokens)
    return HttpProvider(config,budget,settings.v2_capabilities)


def worker(job):
    design,case,seed,mode=job
    provider=provider_from_environment() if mode=='external' else None
    try:
        with tempfile.TemporaryDirectory(prefix='frontdoor-eval-') as directory:
            execute = execute_family if case['behaviour'].startswith('family:') else execute_scenario
            result=execute(ScenarioSpec.model_validate(case),DesignSpec.model_validate(design),seed,
                path=Path(directory)/'evaluation.sqlite',provider=provider)
            return result.model_dump(mode='json')
    finally:
        if provider:provider.budget.close()


def evaluate(design,cases,seeds=(0,),workers=1,provider_mode='mock'):
    jobs=[(design.model_dump(),c.model_dump(),seed,provider_mode) for c in cases for seed in seeds]
    if workers==0:return [worker(j) for j in jobs]  # test-only in-process path
    with ProcessPoolExecutor(max_workers=max(1,min(workers,4))) as executor:
        return list(executor.map(worker,jobs))


def summary(results):
    valid=[r for r in results if r['valid_simulation']]
    failures={}
    families={}
    for r in valid:
        families.setdefault(r['family_id'],[]).append(r['passed'])
        for check,passed in r['checks'].items():
            if not passed:failures[check]=failures.get(check,0)+1
    five=[values for values in families.values() if len(values)==5]
    latency=sorted(r['elapsed_ms'] for r in valid)
    reserved = sum(run.get('provenance',{}).get('reserved_cost_usd',0) for r in results
        for run in r.get('provenance',{}).get('runs', [r.get('provenance',{}).get('run',{})]))
    return {'runs':len(results),'valid_runs':len(valid),'invalid_runs':len(results)-len(valid),
        'success_rate':sum(r['passed'] for r in valid)/len(valid) if valid else None,
        'pass_5':sum(all(v) for v in five)/len(five) if five else None,
        'pass_5_eligible_families':len(five),
        'pass_5_excluded_families':len({r['family_id'] for r in results})-len(five),
        'mean_tool_calls':sum(r['tool_calls'] for r in valid)/len(valid) if valid else None,
        'reserved_cost_usd':reserved,'actual_billed_cost_usd':None,
        'p95_ms':latency[min(len(latency)-1,int(.95*len(latency)))] if latency else None,
        'failures':failures,'clinical_verdict':'NOT_REVIEWED'}


def candidates():
    pool=[]
    for count in range(4):
        for optional in combinations(['intake','check','verify'],count):
            nodes=[n for n in ['intake','check'] if n in optional]+['draft']+(['verify'] if 'verify' in optional else [])
            for prompt in ['grounded-v1','concise-v1']:
                pool.append(DesignSpec(design_id='candidate-'+str(len(pool)+1),nodes=nodes,prompt_version=prompt))
    return pool


def score(item):
    # Clinical metrics are never optimized here. Hard software violations disqualify.
    critical={'temporal_and_label_boundary','content_refs_valid','pending_review','rejection_revokes',
        'stale_not_effective','bounded_calls','cross_case_blocked','modified_pending','modified_confirmed','tool_order'}
    s=item['summary']
    safe=s['invalid_runs']==0 and not any(k in critical for k in s['failures'])
    return (safe,s['success_rate'] or 0,-(s['mean_tool_calls'] or 0),-len(item['design']['nodes']))


def search(cases=None,workers=1,mode='feedback',provider_mode='mock',designer=None):
    cases=[c for c in families() if c.split != 'test'] if cases is None else cases
    if any(c.split not in {'development','validation'} for c in cases):
        # Default callers pass a filtered list; a test suite cannot be accidentally consumed.
        raise ValueError('search accepts development/validation only')
    dev=[c for c in cases if c.split=='development'];val=[c for c in cases if c.split=='validation']
    if not dev or not val:raise ValueError('both development and validation required')
    pool=candidates();random.Random(11).shuffle(pool)
    tested=[]
    rejected=[]
    for index in range(min(12,len(pool))):
        if mode=='feedback':
            failures=tested[-1]['summary']['failures'] if tested else {}
            if designer:
                try:
                    proposal=designer.propose({'iteration':index,'failures':failures,
                        'remaining_designs':[p.model_dump() for p in pool]})
                    if not any(p.nodes==proposal.nodes and p.prompt_version==proposal.prompt_version for p in pool):
                        raise ValueError('out of space')
                except (ValueError, DomainError):
                    rejected.append({'iteration':index,'reason':'INVALID_OR_UNAVAILABLE_DESIGN_PROPOSAL'})
                    continue
                candidate=next(p for p in pool if p.nodes==proposal.nodes and p.prompt_version==proposal.prompt_version)
            else:
                # Explicit deterministic fallback; never label this an LLM designer.
                need_check=bool(failures.get('missing_information_detected') or failures.get('conflict_detected'))
                need_intake=bool(failures.get('question_proposed'))
                candidate=max(pool,key=lambda p:(int(need_check and 'check' in p.nodes)+int(need_intake and 'intake' in p.nodes),-len(p.nodes)))
        else:candidate=pool[0]
        pool.remove(candidate)
        results=evaluate(candidate,dev,seeds=(0,1),workers=workers,provider_mode=provider_mode)
        tested.append({'design':candidate.model_dump(),'summary':summary(results),'results':results})
    finalists=sorted(tested,key=score,reverse=True)[:3]
    validation=[]
    for f in finalists:
        results=evaluate(DesignSpec.model_validate(f['design']),val,seeds=(0,1),workers=workers,provider_mode=provider_mode)
        validation.append({'design':f['design'],'summary':summary(results),'results':results})
    return {'method':'llm-feedback' if designer else mode,'tested':tested,'validation':validation,
        'rejected_proposals':rejected,
        'recommended':max(validation,key=score)['design'] if validation else DESIGNS['fixed'].model_dump(),
        'selection_status':'HUMAN_SELECTION_REQUIRED' if validation else 'NO_VALID_CANDIDATE_KEEP_BASELINE'}


def manifest(provider_mode='mock', suite='families'):
    try:revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    except Exception:revision='unknown'
    root=Path(__file__).resolve().parents[2]
    # Include dirty/untracked implementation content; HEAD alone cannot identify this build.
    files=sorted((root/'innovation').rglob('*.py')) + [root/'requirements.txt']
    files += sorted((root/'innovation/workspace/src').glob('*'))
    files += [root/'innovation/workspace/package-lock.json']
    files = [p for p in files if p.is_file() and 'node_modules' not in p.parts]
    configuration = {'model': 'deterministic-extractive-v1'}
    if provider_mode == 'external':
        from innovation.config import Settings
        settings = Settings()
        configuration = {'model': settings.v2_model, 'capabilities': settings.v2_capabilities,
            'differential': settings.v2_differential,
            'endpoint_hash': digest(settings.v2_provider_url), 'timeout_seconds': 30,
            'transport': settings.v2_transport, 'json_mode': settings.v2_json_mode, 'max_tokens': settings.v2_max_tokens}
    configuration_hash = digest(configuration)
    return {'code_revision':revision,'source_hash':digest({str(p.relative_to(root)):p.read_text() for p in files}),
        'scenario_version':digest([c.model_dump(mode='json') for c in (families() if suite=='families' else factorial())]),
        'suite':suite,'policy':POLICY,
        'provider_mode':provider_mode,'configuration_hash':configuration_hash,'clinical_verdict':'NOT_REVIEWED',
        'limitations':['Synthetic workflow vignettes/configurations, not clinician-validated patient cases.',
            'Shared generator across splits; this is not evidence of cross-hospital generalization.',
            'Mock repeats are deterministic; repeated success is not LLM reliability evidence.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['regression','search','freeze','heldout','manifest'])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--design',default=None)
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--provider',choices=['mock','external'],default='mock')
    parser.add_argument('--llm-designer',action='store_true')
    parser.add_argument('--suite', choices=['families','factorial'], default='families')
    args=parser.parse_args();meta=manifest(args.provider,args.suite)
    suite_cases=families() if args.suite=='families' else factorial()
    if args.mode=='manifest':result={'manifest':meta,'cases':[c.model_dump(mode='json') for c in suite_cases],'regression':[c.model_dump() for c in regression()]}
    elif args.mode=='regression':
        results=evaluate(DESIGNS['fixed'],regression(),workers=args.workers,provider_mode=args.provider)
        result={'manifest':meta,'summary':summary(results),'results':results}
    elif args.mode=='search':
        cases=[c for c in suite_cases if c.split!='test']
        designer=provider_from_environment() if args.llm_designer else None
        try:
            result={'manifest':meta,'search':search(cases,workers=args.workers,provider_mode=args.provider,designer=designer),
                'random':search(cases,workers=args.workers,mode='random',provider_mode=args.provider),'baselines':[]}
            for d in DESIGNS.values():
                runs=evaluate(d,[c for c in cases if c.split=='validation'],seeds=(0,1),workers=args.workers,provider_mode=args.provider)
                result['baselines'].append({'design':d.model_dump(),'summary':summary(runs),'results':runs})
        finally:
            if designer:designer.budget.close()
    elif args.mode=='freeze':
        if not args.input or not args.design:parser.error('freeze requires --input search report and --design explicit selection')
        report=json.loads(args.input.read_text())
        if report['manifest']!=meta:raise ValueError('manifest changed; rerun development/validation')
        choices=report['baselines']+report['search']['validation']+report['random']['validation']
        item=next((v for v in choices if v['design']['design_id']==args.design),None)
        if item is None:raise ValueError('selection must have validation evidence')
        result={'manifest':meta,'design':item['design'],'validation_summary':item['summary'],
            'selection_record':'explicit CLI selection','search_report_hash':digest(report)}
        result['selection_checksum']=digest(result)
    else:
        if not args.input:parser.error('heldout requires a frozen selection file')
        selection=json.loads(args.input.read_text());checksum=selection.pop('selection_checksum')
        if digest(selection)!=checksum or selection['manifest']!=meta:
            raise ValueError('selection or experiment manifest changed')
        selected=DesignSpec.model_validate(selection['design'])
        result={'manifest':meta,'selection_checksum':checksum,'arms':[]}
        for d in [*DESIGNS.values(),selected]:
            runs=evaluate(d,[c for c in suite_cases if c.split=='test'],seeds=range(5),workers=args.workers,provider_mode=args.provider)
            result['arms'].append({'design':d.model_dump(),'summary':summary(runs),'results':runs})
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        # Never silently overwrite an existing evaluation/selection artifact.
        with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result.get('summary',{'mode':args.mode,'output':str(args.output) if args.output else None,'manifest':meta}),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
