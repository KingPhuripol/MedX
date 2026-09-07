"""The five screens in `PRODUCT_SPEC.md` §Core screens.

Intake · Adaptive interview · Clinical dashboard · DAG explorer · Human confirmation.

**Every screen goes through the public API.** These handlers do not reach past it into the
service; they issue real HTTP requests against the same ASGI app, in-process, using
httpx's ASGI transport. So "the UI is one caller of the same API" is a fact the tests can
check rather than a claim in a README — if a screen can do something, an API client can do
the same thing, and no screen has a privileged path.

Accessibility (A3) lives mostly in `templates/base.html`: urgency is written out, marked
with a shape and given a border weight before colour is considered, every control is a
native focusable element, and there is a skip link. The DAG explorer shows the executed
structure and no private reasoning text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from innovation.frontdoor.intake import TYPE_MODALITY
from innovation.frontdoor.service import OverrideReason
from typing import get_args

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

#: A shape for each urgency level, so the level survives greyscale printing and screen
#: readers. Colour is never the only carrier (A3: "no color-only urgency signal").
GLYPH = {
    "IMMEDIATE_REVIEW": "▲▲",
    "URGENT_REVIEW": "▲",
    "ROUTINE_REVIEW": "●",
    "INSUFFICIENT_INFORMATION": "?",
}

INTAKE_STATES = [
    ("KNOWN", "Known"),
    ("UNKNOWN", "Asked — not known"),
    ("REFUSED", "Asked — declined to answer"),
    ("NOT_AVAILABLE", "Not yet available"),
]

DEFAULT_FORM_ITEMS = [
    {"key": "CHIEF_COMPLAINT", "label": "Chief complaint", "default": "KNOWN", "value": ""},
    {"key": "VITAL", "label": "Vital signs", "default": "NOT_AVAILABLE", "value": ""},
    {"key": "HISTORY", "label": "Relevant history", "default": "UNKNOWN", "value": ""},
    {"key": "MEDICATION", "label": "Medication", "default": "UNKNOWN", "value": ""},
    {"key": "ALLERGY", "label": "Allergy", "default": "UNKNOWN", "value": ""},
]


#: The API version the screens speak. One constant, one place to change it.
API_PREFIX = "/v1"


def mount_ui(app: FastAPI) -> FastAPI:
    """Attach the screens to an app that already carries the API."""
    router = APIRouter(prefix="/ui", include_in_schema=False)

    async def api(method: str, path: str, *, versioned: bool = True, **kwargs) -> httpx.Response:
        """Call this app's own API over HTTP, in-process and with no network.

        Every screen goes through here, which is why adding the version prefix cost one
        line rather than one per screen. The UI is a client of the public API and gets no
        privileged path into the service (`PRODUCT_SPEC.md` §Architecture).

        `versioned=False` reaches the probes, which are deliberately unversioned: a
        deployment should not have to know the contract version to ask whether the
        process is alive.
        """
        transport = httpx.ASGITransport(app=app)
        target = (API_PREFIX + path) if versioned else path
        async with httpx.AsyncClient(transport=transport, base_url="http://frontdoor") as client:
            return await client.request(method, target, **kwargs)

    def render(request: Request, template: str, **context) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, template, {"glyph": GLYPH, **context})

    # ---------------------------------------------------------------------- index

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        health = (await api("GET", "/health", versioned=False)).json()
        journeys = app.state.service.journey_ids()
        return render(request, "index.html", health=health, journeys=journeys)

    # --------------------------------------------------------------------- intake

    @router.get("/intake", response_class=HTMLResponse)
    async def intake_form(request: Request, error: str | None = None):
        suffix = datetime.now(timezone.utc).strftime("%H%M%S")
        return render(
            request,
            "intake.html",
            states=INTAKE_STATES,
            form_items=DEFAULT_FORM_ITEMS,
            suggested_id=f"journey-{suffix}",
            suffix=suffix,
            default_time=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            error=error,
        )

    @router.post("/intake")
    async def intake_submit(request: Request):
        form = await request.form()
        items = []
        for spec in DEFAULT_FORM_ITEMS:
            key = spec["key"]
            state = form.get(f"state_{key}")
            raw = (form.get(f"value_{key}") or "").strip()
            if not state:
                continue
            items.append(
                {
                    "information_type": key,
                    "state": state,
                    # A value is only ever carried for a KNOWN answer; the API refuses the
                    # rest, so a stray value cannot slip in behind a missing status.
                    "value": raw if state == "KNOWN" and raw else None,
                }
            )

        response = await api(
            "POST",
            "/encounters",
            json={
                "journey_id": form.get("journey_id"),
                "patient_id": form.get("patient_id"),
                "encounter_id": form.get("encounter_id"),
                "encounter_start": form.get("encounter_start"),
                "items": items,
            },
        )
        if response.status_code != 201:
            return await intake_form(request, error=_detail(response))
        journey_id = response.json()["journey_id"]
        return RedirectResponse(f"/ui/journeys/{journey_id}/interview", status_code=303)

    # ---------------------------------------------------------- adaptive interview

    @router.get("/journeys/{journey_id}/interview", response_class=HTMLResponse)
    async def interview(request: Request, journey_id: str, decision_time: str | None = None):
        when = decision_time or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        response = await api(
            "GET", f"/journeys/{journey_id}/next-information", params={"decision_time": when}
        )
        if response.status_code != 200:
            return render(request, "index.html", health={}, journeys=[], error=_detail(response))
        return render(
            request,
            "interview.html",
            journey_id=journey_id,
            decision_time=when,
            plan=response.json(),
            states=INTAKE_STATES,
            information_types=sorted(TYPE_MODALITY),
        )

    @router.post("/journeys/{journey_id}/events")
    async def append_event(
        request: Request,
        journey_id: str,
        information_type: str = Form(...),
        state: str = Form(...),
        value: str = Form(""),
    ):
        await api(
            "POST",
            f"/journeys/{journey_id}/events",
            json={
                "information_type": information_type,
                "state": state,
                "value": value.strip() if state == "KNOWN" and value.strip() else None,
            },
        )
        return RedirectResponse(f"/ui/journeys/{journey_id}/interview", status_code=303)

    @router.post("/journeys/{journey_id}/assessments")
    async def assess(request: Request, journey_id: str, decision_time: str = Form(...)):
        response = await api(
            "POST",
            f"/journeys/{journey_id}/assessments",
            json={"decision_time": decision_time, "missing_information": []},
        )
        if response.status_code != 201:
            return RedirectResponse(f"/ui/journeys/{journey_id}/interview", status_code=303)
        return RedirectResponse(
            f"/ui/recommendations/{response.json()['recommendation_id']}", status_code=303
        )

    # ---------------------------------------------------------- clinical dashboard

    @router.get("/recommendations/{recommendation_id}", response_class=HTMLResponse)
    async def dashboard(request: Request, recommendation_id: str, error: str | None = None):
        response = await api("GET", f"/recommendations/{recommendation_id}")
        if response.status_code != 200:
            return render(request, "index.html", health={}, journeys=[], error=_detail(response))
        rec = response.json()
        return render(
            request,
            "dashboard.html",
            rec=rec,
            r=rec["response"],
            reason_codes=list(get_args(OverrideReason)),
            error=error,
        )

    @router.post("/recommendations/{recommendation_id}/review")
    async def review(
        request: Request,
        recommendation_id: str,
        reviewer_id: str = Form(...),
        action: str = Form(...),
        reason_code: str = Form(""),
        note: str = Form(""),
    ):
        response = await api(
            "POST",
            f"/recommendations/{recommendation_id}/review",
            json={
                "reviewer_id": reviewer_id,
                "action": action,
                "reason_code": reason_code or None,
                "note": note or None,
            },
        )
        if response.status_code != 200:
            return await dashboard(request, recommendation_id, error=_detail(response))
        return RedirectResponse(f"/ui/recommendations/{recommendation_id}", status_code=303)

    # ------------------------------------------------------------- DAG explorer

    @router.get("/recommendations/{recommendation_id}/graph", response_class=HTMLResponse)
    async def graph(request: Request, recommendation_id: str):
        response = await api("GET", f"/recommendations/{recommendation_id}")
        if response.status_code != 200:
            return render(request, "index.html", health={}, journeys=[], error=_detail(response))
        rec = response.json()

        audit = await api("GET", f"/audit/{rec['response']['request_id']}")
        records = audit.json() if audit.status_code == 200 else []
        rules = [rule for record in records for rule in record.get("applied_safety_rules", [])]
        # The withheld list comes from the recommendation, not the audit record: the Front
        # Door filters future evidence before the request is built, so the gateway never
        # sees it and its audit trail has nothing to report.
        withheld = rec.get("withheld", [])

        return render(
            request, "graph.html", rec=rec, r=rec["response"], withheld=withheld, rules=rules
        )

    # ------------------------------------------------------------------- history

    @router.get("/journeys/{journey_id}/history", response_class=HTMLResponse)
    async def history(request: Request, journey_id: str):
        response = await api("GET", f"/journeys/{journey_id}/history")
        if response.status_code != 200:
            return render(request, "index.html", health={}, journeys=[], error=_detail(response))
        return render(request, "history.html", journey_id=journey_id, history=response.json())

    app.include_router(router)
    return app


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return f"HTTP {response.status_code}"
    detail = body.get("detail", body)
    if isinstance(detail, list) and detail:
        first = detail[0]
        return f"{'.'.join(str(p) for p in first.get('loc', []))}: {first.get('msg', '')}".strip(": ")
    return str(detail)
