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
        if not principals or any(not {'token','subject','role'} <= set(p) or set(p)-{'token','subject','role','workspace'} or p['role'] not in {'intake','physician','evaluator'} or not isinstance(p['token'],str) or not p['token'] or not p['subject'] for p in principals):
            raise ValueError('Invalid principals[{token,subject,role}]')
        if len({p['token'] for p in principals})!=len(principals):
            raise ValueError('Duplicate principal token')

    sessions = {}
    session_lock = RLock()

    def identity(request: Request, authorization: str | None = Header(default=None)):
        if settings.auth_mode=='none':return Principal('local-demo','physician')
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
    if settings.auth_mode=='token':
        @app.middleware('http')
        async def protect(request,call_next):
            public=request.url.path in {'/health','/ready','/docs','/docs/oauth2-redirect','/openapi.json','/redoc','/ui/v2'} or request.url.path.startswith(('/v2-assets/', '/workspace-assets/')) or request.url.path == '/workspace' or (request.url.path == '/v2/session' and request.method == 'POST')
            if not public:
                try:
                    actor=identity(request, request.headers.get('authorization'))
                    request.state.principal=actor
                    if request.method not in {'GET','HEAD','OPTIONS'}:
                        if (actor.role=='evaluator' and request.url.path not in {'/v2/session', '/v2/experiments'}) or (request.url.path.endswith('/review') and actor.role!='physician'):
                            raise DomainError(403,'ROLE_FORBIDDEN')
                except DomainError as exc:
                    return JSONResponse(status_code=exc.status,content={'error':exc.code})
            return await call_next(request)
