"""Authentication for both API generations, also when v2 is disabled."""
import json
import secrets
from fastapi import Header, Request, Response
from pydantic import BaseModel, Field
from threading import RLock
import time
from fastapi.responses import JSONResponse
from innovation.v2.service import Principal
from innovation.v2.store import DomainError


def install_auth(app):
    settings=app.state.settings
    principals=[]
    if settings.auth_mode=='token':
        principals=json.loads(settings.principals_file.read_text())['principals']
        if not principals or any(not {'token','subject','role'} <= set(p) or set(p)-{'token','subject','role','workspace'} or p['role'] not in {'intake','physician','pharmacist','evaluator'} or not isinstance(p['token'],str) or not p['token'] or not p['subject'] for p in principals):
            raise ValueError('Invalid principals[{token,subject,role}]')
        if len({p['token'] for p in principals})!=len(principals):
            raise ValueError('Duplicate principal token')

    sessions = {}
    session_lock = RLock()

    def identity(request: Request, authorization: str | None = Header(default=None)):
        if settings.auth_mode=='none':return Principal('local-demo',settings.demo_role)
        if settings.auth_mode=='public_demo':return public_visitor(request)
        if not isinstance(authorization, str):
            authorization = request.headers.get('authorization')
        if not authorization:
            sid = request.cookies.get('frontdoor_session', '')
            with session_lock:
                session = sessions.get(sid)
            if session and session['expires'] > time.monotonic():
                if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
                    raise DomainError(403, 'CSRF_REQUIRED')
                return session['actor']
        token=authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
        for p in principals:
            if secrets.compare_digest(token,p['token']):return Principal(p['subject'],p['role'],p.get('workspace','default'))
        raise DomainError(401,'AUTHENTICATION_REQUIRED')
    if settings.v2_enabled:
        class Login(BaseModel):
            token: str = Field(min_length=1, max_length=1024)

        @app.post('/v2/session')
        def login(body: Login, request: Request, response: Response):
            if request.headers.get('origin') and request.headers['origin'] != str(request.base_url).rstrip('/'):
                raise DomainError(403, 'ORIGIN_FORBIDDEN')
            actor = identity(request, 'Bearer ' + body.token)
            sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            with session_lock:
                for old in list(sessions):
                    if sessions[old]['expires'] <= time.monotonic():
                        del sessions[old]
                if len(sessions) >= 100:
                    raise DomainError(429, 'SESSION_LIMIT')
                sessions[sid] = {'actor': actor, 'csrf': csrf, 'expires': time.monotonic() + 28800}
            response.set_cookie('frontdoor_session', sid, httponly=True, samesite='strict',
                                secure=request.url.scheme == 'https', max_age=28800, path='/')
            return {'subject': actor.subject, 'role': actor.role, 'workspace': actor.workspace, 'csrf': csrf}

        @app.get('/v2/session')
        def current_session(request: Request):
            actor = identity(request)
            with session_lock:
                session = sessions.get(request.cookies.get('frontdoor_session', ''), {})
            return {'subject': actor.subject, 'role': actor.role, 'workspace': actor.workspace,
                    'csrf': session.get('csrf', '')}

        @app.delete('/v2/session')
        def logout(request: Request, response: Response):
            identity(request)
            with session_lock:
                sessions.pop(request.cookies.get('frontdoor_session', ''), None)
            response.delete_cookie('frontdoor_session', path='/')
            return {'signed_out': True}

    app.state.resolve_identity=identity
    if settings.auth_mode=='public_demo':
        install_public_demo(app, settings)
    if settings.auth_mode=='token':
        @app.middleware('http')
        async def protect(request,call_next):
            public=request.url.path in {'/','/health','/ready','/docs','/docs/oauth2-redirect','/openapi.json','/redoc','/ui/v2','/workspace','/platform','/nurse'} or request.url.path.startswith(('/v2-assets/', '/workspace-assets/')) or (request.url.path == '/v2/session' and request.method == 'POST')
            if not public:
                try:
                    actor=identity(request, request.headers.get('authorization'))
                    request.state.principal=actor
                    if request.method not in {'GET','HEAD','OPTIONS'}:
                        if (actor.role=='evaluator' and request.url.path not in {'/v2/session', '/v2/experiments'}) or (request.url.path.endswith('/review') and actor.role!='physician'):
                            raise DomainError(403,'ROLE_FORBIDDEN')

                except DomainError as exc:
                    from innovation.api.errors import envelope
                    return JSONResponse(status_code=exc.status, content=envelope(exc.code, str(exc), details=exc.details))

            return await call_next(request)



# ----------------------------------------------------------------------------------------
# DEC-0022 public demo: every anonymous visitor gets a private, synthetic sandbox.
SANDBOX_COOKIE, ROLE_COOKIE = 'medx_sandbox', 'medx_role'
PUBLIC_ROLES = {'intake', 'physician', 'pharmacist'}
# Requests that can reach a model or speech provider; these are rate limited per sandbox.
COSTLY = ('/jobs', '/turns', '/drafts', '/pharmacy-review', '/passport-assist', '/speech', '/transcriptions')
_seeded, _calls, _public_lock = set(), {}, RLock()


def public_visitor(request):
    sandbox = request.cookies.get(SANDBOX_COOKIE) or getattr(request.state, 'sandbox', None)
    if not sandbox or len(sandbox) > 64:
        raise DomainError(401, 'AUTHENTICATION_REQUIRED')
    role = request.cookies.get(ROLE_COOKIE)
    workspace = 'demo-' + sandbox
    service = getattr(request.app.state, 'v2_service', None)
    if service is not None and workspace not in _seeded:
        with _public_lock:
            if workspace not in _seeded:
                from innovation.v2.demo_cases import seed_cases
                from innovation.v2.providers import MockProvider
                from innovation.v2.runtime import Runtime
                from innovation.v2.service import Service
                # Example drafts come from the offline provider: seeding never spends model budget.
                seed_cases(Service(service.store, Runtime(MockProvider())), workspace, prefix=sandbox[:6] + '-')
                _seeded.add(workspace)
    return Principal('visitor-' + sandbox[:8], role if role in PUBLIC_ROLES else 'intake', workspace)


def install_public_demo(app, settings):
    from fastapi import Body

    def cookie(response, request, name, value):
        response.set_cookie(name, value, httponly=True, samesite='strict',
                            secure=request.headers.get('x-forwarded-proto', request.url.scheme) == 'https',
                            max_age=7 * 24 * 3600, path='/')

    @app.middleware('http')
    async def sandbox(request, call_next):
        from innovation.api.errors import envelope
        path, fresh = request.url.path, None
        if path.startswith(('/v1', '/ui/', '/docs', '/redoc', '/openapi.json')) or path == '/ui':
            return JSONResponse(status_code=404, content=envelope('NOT_AVAILABLE_IN_PUBLIC_DEMO', 'Not available in the public demo'))
        if request.method == 'POST' and path.startswith('/v2/experiments'):
            return JSONResponse(status_code=403, content=envelope('NOT_AVAILABLE_IN_PUBLIC_DEMO', 'Experiments are disabled in the public demo'))
        if not request.cookies.get(SANDBOX_COOKIE):
            fresh = secrets.token_urlsafe(16)
            request.state.sandbox = fresh
        if request.method == 'POST' and path.startswith('/v2/') and path.endswith(COSTLY):
            key = request.cookies.get(SANDBOX_COOKIE) or fresh
            now = time.monotonic()
            with _public_lock:
                recent = [t for t in _calls.get(key, []) if now - t < 3600]
                if len(recent) >= settings.public_calls_per_hour:
                    return JSONResponse(status_code=429, content=envelope('DEMO_RATE_LIMITED', 'Hourly limit for this demo sandbox reached'))
                _calls[key] = recent + [now]
        response = await call_next(request)
        if fresh:
            cookie(response, request, SANDBOX_COOKIE, fresh)
        return response

    @app.post('/v2/demo/role')
    def choose_role(request: Request, response: Response, role: str = Body(embed=True)):
        if role not in PUBLIC_ROLES:
            raise DomainError(422, 'UNKNOWN_ROLE')
        cookie(response, request, ROLE_COOKIE, role)
        return {'role': role, 'open': '/nurse' if role == 'intake' else '/platform'}

    @app.post('/v2/demo/reset')
    def reset(request: Request, response: Response):
        """Start a fresh sandbox; the old one is simply abandoned (it lives only in this instance's /tmp)."""
        response.delete_cookie(SANDBOX_COOKIE, path='/')
        response.delete_cookie(ROLE_COOKIE, path='/')
        return {'reset': True}
