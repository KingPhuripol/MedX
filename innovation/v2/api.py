from pathlib import Path
from fastapi import APIRouter, Depends, Header, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from innovation.v2.models import EncounterCreate, EventRequest, TurnRequest, DraftRequest, ReviewDecision, ProposalAcceptance
from innovation.v2.store import DomainError


def mount(app, service, speech):
    settings = app.state.settings
    identity = app.state.resolve_identity
    from innovation.v2.jobs import Jobs
    jobs = Jobs(service, settings.provider_concurrency)
    app.state.v2_jobs = jobs
    from innovation.v2.experiments import Experiments, ExperimentRequest
    experiment_root = settings.v2_experiment_dir
    if settings.db is None and experiment_root == Path('artifacts/v2/experiments'):
        from tempfile import TemporaryDirectory
        app.state.v2_experiment_temp = TemporaryDirectory(prefix='frontdoor-experiments-')
        experiment_root = Path(app.state.v2_experiment_temp.name)
    elif experiment_root == Path('artifacts/v2/experiments'):
        experiment_root = settings.db.parent / (settings.db.stem + '-experiments')
    experiments = Experiments(experiment_root)
    app.state.v2_experiments = experiments

    def authorize_resource(request: Request, actor=Depends(identity)):
        params = request.path_params
        encounter_id = params.get('encounter_id')
        if params.get('job_id'):
            encounter_id = jobs.get(params['job_id'])['encounter_id']
        if params.get('run_id'):
            encounter_id = service.run(params['run_id'])['encounter_id']
        if params.get('draft_id'):
            encounter_id = service.draft(params['draft_id'], actor)['encounter_id']
        if encounter_id and service.case(encounter_id).get('workspace', 'default') != actor.workspace:
            from innovation.v2.store import DomainError
            raise DomainError(404, 'ENCOUNTER_NOT_FOUND')

    router = APIRouter(prefix='/v2', dependencies=[Depends(authorize_resource)])

    @router.get('/experiments')
    def list_experiments(actor=Depends(identity)):
        service.require(actor, {'physician', 'evaluator'})
        return [e for e in experiments.latest() if e['workspace'] == actor.workspace][-50:][::-1]

    @router.post('/experiments', status_code=202)
    def create_experiment(body: ExperimentRequest, actor=Depends(identity)):
        return experiments.create(body, actor)

    @router.get('/experiments/{experiment_id}/report')
    def experiment_report(experiment_id: str, actor=Depends(identity)):
        service.require(actor, {'physician', 'evaluator'})
        return experiments.report(experiment_id, actor)

    @router.post('/encounters/{encounter_id}/jobs', status_code=202)
    def create_job(encounter_id: str, body: TurnRequest, actor=Depends(identity)):
        return jobs.create(encounter_id, body, actor)

    @router.get('/jobs/{job_id}')
    def get_job(job_id: str):
        return jobs.get(job_id)

    @router.post('/jobs/{job_id}/cancel')
    def cancel_job(job_id: str, actor=Depends(identity)):
        service.require(actor, {'intake', 'physician'})
        return jobs.cancel(job_id)

    @app.exception_handler(DomainError)
    async def error(request, exc):
        from fastapi.responses import JSONResponse
        from innovation.api.errors import envelope
        return JSONResponse(status_code=exc.status, content=envelope(exc.code, str(exc), details=exc.details))

    @router.get('/readiness')
    def readiness():
        from innovation.v2.readiness import inspect
        return inspect(settings)

    @router.get('/capabilities')
    def capabilities(actor=Depends(identity)):
        return {'profile': 'synthetic_intake_v1', 'role': actor.role,
            'gateway_contract': service.runtime.provider.contract_version,
            'modalities': service.runtime.provider.modalities,
            'raw_image_analysis': False,
            'provider': service.runtime.provider.name, 'model': service.runtime.provider.model_version,
            'differential': service.runtime.allow_differential and 'differential' in service.runtime.provider.capabilities and actor.role=='physician',
            'speech': speech.__class__.__name__ != 'UnavailableSpeech',
            'synthesis': hasattr(app.state, 'v2_synthesis'),
            'conversation': hasattr(service.runtime.provider, 'converse') and 'conversation' in service.runtime.provider.capabilities,
            'validation': 'MOCK_ONLY' if service.runtime.provider.name == 'mock-v2' else 'LIVE_VALIDATION_PENDING'}

    @router.post('/runs/{run_id}/speech')
    def synthesize(run_id: str, actor=Depends(identity)):
        from fastapi.responses import Response
        from innovation.v2.store import DomainError
        service.require(actor, {'intake', 'physician'})
        run = service.run(run_id)
        if run['status'] != 'COMPLETED':
            raise DomainError(409, 'RUN_NOT_COMPLETED')
        if not hasattr(app.state, 'v2_synthesis'):
            raise DomainError(503, 'SYNTHESIS_NOT_CONFIGURED')
        return Response(app.state.v2_synthesis.synthesize(run['response']), media_type='audio/mpeg',
                        headers={'Cache-Control': 'no-store'})

    @router.post('/encounters', status_code=201)
    def create(body: EncounterCreate, idempotency_key: str = Header(min_length=1, max_length=128), actor=Depends(identity)):
        return service.create(body, idempotency_key, actor)

    from fastapi import Query

    @router.get('/encounters')
    def encounters(q: str = Query(default='', max_length=128),
                   status: str = Query(default='', pattern=r'^(|NO_DRAFT|STALE|CONFIRMED|REJECTED|PENDING)$'),
                   offset: int = Query(default=0, ge=0),
                   limit: int = Query(default=25, ge=1, le=100), actor=Depends(identity)):
        return service.queue(actor, q, status, offset, limit)

    @router.get('/encounters/{encounter_id}')
    def encounter(encounter_id: str, include_history: bool = True):
        return service.case(encounter_id) if include_history else service.case_summary(encounter_id)

    @router.get('/encounters/{encounter_id}/history')
    def history(encounter_id: str, after: int = Query(default=0,ge=0), limit: int = Query(default=25,ge=1,le=100)):
        return service.store.page('event',encounter_id,after,limit)

    @router.get('/encounters/{encounter_id}/audit')
    def audit(encounter_id: str, after: int = Query(default=0, ge=0),
              limit: int = Query(default=25, ge=1, le=100), actor=Depends(identity)):
        service.require(actor, {'intake', 'physician', 'evaluator'})
        service.authorize_case(encounter_id, actor)
        return service.store.page('audit', encounter_id, after, limit)

    @router.get('/encounters/{encounter_id}/snapshot')
    def snapshot(encounter_id: str):
        from innovation.v2.models import now
        return service.snapshot(encounter_id, now()).model_dump(mode='json')

    @router.get('/encounters/{encounter_id}/screen')
    def screen(encounter_id: str):
        from innovation.v2.models import now
        return service.runtime.provider.prepare(service.snapshot(encounter_id, now())).model_dump(mode='json')

    @router.post('/encounters/{encounter_id}/events', status_code=201)
    def event(encounter_id: str, body: EventRequest, actor=Depends(identity)):
        return service.append_event(encounter_id, body, actor)

    @router.post('/encounters/{encounter_id}/turns', status_code=201)
    def turn(encounter_id: str, body: TurnRequest, actor=Depends(identity)):
        return service.turn(encounter_id, body, actor)

    @router.post('/runs/{run_id}/proposals/{proposal_id}/accept')
    def accept(run_id: str, proposal_id: str, body: ProposalAcceptance, actor=Depends(identity)):
        return service.accept_proposal(run_id, proposal_id, body, actor)

    @router.get('/tools')
    def tool_schemas():
        from innovation.v2.tools import schemas
        return schemas()

    from innovation.v2.models import ProposalBatchAcceptance

    @router.post('/runs/{run_id}/proposals/accept-batch')
    def accept_batch(run_id: str, body: ProposalBatchAcceptance, actor=Depends(identity)):
        return service.accept_proposals(run_id, body, actor)

    @router.get('/drafts/{draft_id}/evidence/{evidence_id}')
    def draft_evidence(draft_id: str, evidence_id: str, actor=Depends(identity)):
        return service.draft_evidence(draft_id, evidence_id, actor)

    @router.get('/runs/{run_id}/graph')
    def graph(run_id: str, actor=Depends(identity)):
        service.require(actor, {'physician', 'evaluator'})
        artifact = service.run(run_id)['provenance'].get('execution')
        if artifact is None:
            raise DomainError(404, 'GRAPH_NOT_RECORDED')
        return artifact

    @router.get('/runs/{run_id}/replay')
    def replay_run(run_id: str, actor=Depends(identity)):
        service.require(actor, {'physician', 'evaluator'})
        from innovation.v2.graph import replay
        return replay(service.run(run_id)['provenance'].get('execution'))

    @router.get('/runs/{run_id}')
    def run(run_id: str):
        return service.run(run_id)

    @router.get('/encounters/{encounter_id}/turns')
    def turns(encounter_id: str):
        service.case(encounter_id)
        return service.store.all('run', encounter_id)

    @router.post('/encounters/{encounter_id}/drafts', status_code=201)
    def draft(encounter_id: str, body: DraftRequest, actor=Depends(identity)):
        request = TurnRequest(**body.model_dump(), text='เตรียมร่างส่งต่อ', design_id='fixed')
        result = service.turn(encounter_id, request, actor)
        return service.draft(result['draft_id'], actor) if result['draft_id'] else result

    @router.get('/encounters/{encounter_id}/drafts')
    def drafts(encounter_id: str, actor=Depends(identity)):
        return service.drafts(encounter_id, actor)

    @router.get('/drafts/{draft_id}')
    def get_draft(draft_id: str, actor=Depends(identity)):
        return service.draft(draft_id, actor)

    @router.post('/drafts/{draft_id}/reviews')
    def review(draft_id: str, body: ReviewDecision, actor=Depends(identity)):
        return service.review(draft_id, body, actor)

    @router.post('/speech/transcriptions')
    async def transcribe(file: UploadFile = File(...), actor=Depends(identity)):
        service.require(actor, {'intake','physician'})
        try:
            content_type = (file.content_type or '').split(';', 1)[0].strip().lower()
            if content_type not in {'audio/webm', 'audio/wav', 'audio/ogg', 'audio/mp4', 'audio/mpeg'}:
                raise DomainError(415, 'UNSUPPORTED_AUDIO')
            data = await file.read(10_000_001)
            if not data or len(data)>10_000_000:
                raise DomainError(413, 'AUDIO_SIZE_LIMIT')
            from starlette.concurrency import run_in_threadpool
            try:
                result = await run_in_threadpool(speech.transcribe, data, content_type)
            except ValueError:
                raise DomainError(502, "INVALID_TRANSCRIPT") from None
            return result.model_dump()
        finally:
            await file.close()

    app.include_router(router)

    from fastapi.staticfiles import StaticFiles
    workspace_dist = Path(__file__).parent.parent / 'workspace' / 'dist'
    if workspace_dist.is_dir():
        app.mount('/workspace-assets', StaticFiles(directory=workspace_dist), name='workspace-assets')

        def workspace_response(app_name):
            return HTMLResponse((workspace_dist / f'{app_name}.html').read_text(), headers={
                'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'",
                'Cache-Control': 'no-store'})

        # DEC-0017: two frontends, one API. Each path serves its own bundle.
        @app.get('/platform', response_class=HTMLResponse, include_in_schema=False)
        def central_platform():
            return workspace_response('platform')

        @app.get('/nurse', response_class=HTMLResponse, include_in_schema=False)
        def nurse_intake():
            return workspace_response('nurse')

        @app.get('/workspace', include_in_schema=False)
        def modern_workspace():
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/platform', status_code=308)

    @app.get('/ui/v2', response_class=HTMLResponse, include_in_schema=False)
    def workspace():
        return HTMLResponse((Path(__file__).parent.parent/'ui/templates/workspace_v2.html').read_text(),
            headers={'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'"})

    from fastapi.staticfiles import StaticFiles
    app.mount('/v2-assets', StaticFiles(directory=Path(__file__).parent.parent/'ui/static'), name='v2-assets')
