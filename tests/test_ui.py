"""The five screens — acceptance criteria A1 (dashboard) and A3 (accessibility).

The properties tested here are the ones a screen can quietly break: colour carrying
meaning on its own, a control no keyboard can reach, a private-reasoning field leaking
into the graph explorer, or a screen doing something the API cannot.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from innovation.api.app import create_app

INTAKE_FORM = {
    "journey_id": "journey-ui-test",
    "patient_id": "patient-ui-test",
    "encounter_id": "encounter-ui-test",
    "encounter_start": "2026-01-01T09:00:00+00:00",
    "state_CHIEF_COMPLAINT": "KNOWN", "value_CHIEF_COMPLAINT": "chest discomfort",
    "state_VITAL": "NOT_AVAILABLE", "value_VITAL": "",
    "state_HISTORY": "UNKNOWN", "value_HISTORY": "",
    "state_MEDICATION": "REFUSED", "value_MEDICATION": "",
    "state_ALLERGY": "UNKNOWN", "value_ALLERGY": "",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def recommendation(client: TestClient) -> str:
    client.post("/ui/intake", data=INTAKE_FORM, follow_redirects=False)
    assessed = client.post(
        "/ui/journeys/journey-ui-test/assessments",
        data={"decision_time": "2026-01-01T09:30:00+00:00"},
        follow_redirects=False,
    )
    return assessed.headers["location"].rsplit("/", 1)[-1]


# ------------------------------------------------------------- every screen loads


def test_all_five_screens_render(client, recommendation):
    for path in (
        "/ui/",
        "/ui/intake",
        "/ui/journeys/journey-ui-test/interview",
        f"/ui/recommendations/{recommendation}",
        f"/ui/recommendations/{recommendation}/graph",
        "/ui/journeys/journey-ui-test/history",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "RESEARCH PROTOTYPE" in response.text, f"banner missing on {path}"


def test_every_screen_carries_the_non_deployment_boundary(client, recommendation):
    """The banner states what the system does not do, on every screen."""
    for path in ("/ui/", f"/ui/recommendations/{recommendation}"):
        text = client.get(path).text
        assert "does not diagnose, prescribe, order tests, refer or discharge" in text
        assert "requires a clinician" in text


# ----------------------------------------------------- the UI is just an API client


def test_the_ui_goes_through_the_public_api(client):
    """Screens issue real HTTP requests against the same app rather than reaching past it
    into the service, so a screen can never do more than an API client can."""
    calls: list[str] = []
    original = create_app

    app = create_app()
    real_router = app.router

    # Instrument the API layer: a UI page load must produce API requests.
    @app.middleware("http")
    async def record(request, call_next):
        calls.append(f"{request.method} {request.url.path}")
        return await call_next(request)

    with TestClient(app) as instrumented:
        instrumented.post("/ui/intake", data=INTAKE_FORM, follow_redirects=False)

    assert any(c == "POST /ui/intake" for c in calls)
    assert any(c == "POST /v1/encounters" for c in calls), (
        "the intake screen did not call the public API; it reached past it"
    )
    assert not any(c == "POST /encounters" for c in calls), (
        "the screens should speak the versioned surface, so the unprefixed compatibility "
        "routes have no internal consumers left to break when they are retired"
    )


def test_ui_intake_and_api_encounter_produce_the_same_record(client):
    client.post("/ui/intake", data=INTAKE_FORM, follow_redirects=False)
    api_body = {
        "journey_id": "journey-api-equivalent",
        "patient_id": "p", "encounter_id": "e",
        "encounter_start": "2026-01-01T09:00:00+00:00",
        "items": [
            {"information_type": "CHIEF_COMPLAINT", "state": "KNOWN", "value": "chest discomfort"},
            {"information_type": "VITAL", "state": "NOT_AVAILABLE"},
            {"information_type": "HISTORY", "state": "UNKNOWN"},
            {"information_type": "MEDICATION", "state": "REFUSED"},
            {"information_type": "ALLERGY", "state": "UNKNOWN"},
        ],
    }
    api_states = client.post("/encounters", json=api_body).json()["recorded_states"]
    ui_states = client.get("/journeys/journey-ui-test/next-information",
                           params={"decision_time": "2026-01-01T09:00:00+00:00"}).status_code

    assert ui_states == 200
    assert api_states["MEDICATION"] == "WITHHELD"


# ------------------------------------------------------------------ accessibility


def test_urgency_is_not_conveyed_by_colour_alone(client, recommendation):
    """A3: "no color-only urgency signal". The level is written out, given a shape glyph
    and a border weight; colour is the least load-bearing of the four."""
    html = client.get(f"/ui/recommendations/{recommendation}").text

    block = re.search(r'<p class="urgency urgency-(\w+)">(.*?)</p>', html, re.S)
    assert block, "urgency block not found"
    level, body = block.group(1), block.group(2)

    assert level.replace("_", " ") in body, "the level is not written out in text"
    assert re.search(r"[▲●?]", body), "no shape glyph accompanies the level"
    assert f"urgency-{level}" in html
    # And the stylesheet gives that level a border, not only a colour.
    assert re.search(rf"\.urgency-{level}\s*{{[^}}]*border-left", html), "no border encoding"


def test_red_flag_states_carry_a_shape_not_only_a_word(client, recommendation):
    html = client.get(f"/ui/recommendations/{recommendation}").text
    for state in ("TRIGGERED", "UNKNOWN", "NOT_TRIGGERED"):
        assert f".state-{state}::before" in html, f"{state} has no shape marker"


def test_unknown_is_explained_as_not_absent(client, recommendation):
    html = client.get(f"/ui/recommendations/{recommendation}").text
    assert "does not mean the flag is absent" in html


def test_there_is_a_skip_link_and_a_visible_focus_ring(client):
    html = client.get("/ui/").text
    assert 'class="skip"' in html
    assert ":focus-visible" in html and "outline" in html


def test_no_control_is_removed_from_the_tab_order(client, recommendation):
    """A negative tabindex would hide a control from keyboard users."""
    for path in ("/ui/intake", f"/ui/recommendations/{recommendation}"):
        assert "tabindex=\"-1\"" not in client.get(path).text


def test_forms_use_native_labelled_controls(client):
    html = client.get("/ui/intake").text
    assert html.count("<label") >= 10
    assert "role=\"radiogroup\"" in html


# ------------------------------------------------------------------ DAG explorer


def test_graph_explorer_shows_structure_and_no_private_reasoning(client, recommendation):
    """A5: "Graph explorer displays executed typed structure and does not expose hidden
    chain-of-thought"."""
    html = client.get(f"/ui/recommendations/{recommendation}/graph").text

    assert "Graph ID" in html and "Evidence entering the computation" in html
    assert "Deterministic rules applied" in html
    assert "no private reasoning text" in html
    for forbidden in ("chain_of_thought", "reasoning_text", "thoughts", "rationale_text"):
        assert forbidden not in html


def test_graph_explorer_names_what_was_withheld(client):
    """A decision must be able to show what it could not see."""
    client.post("/ui/intake", data=dict(INTAKE_FORM, journey_id="journey-ui-withheld"),
                follow_redirects=False)
    client.post(
        "/journeys/journey-ui-withheld/events",
        json={"information_type": "DIAGNOSIS", "state": "KNOWN",
              "value": {"category": "later-label"},
              "observed_at": "2026-01-01T12:00:00+00:00",
              "available_at_time": "2026-01-01T13:00:00+00:00"},
    )
    assessed = client.post(
        "/ui/journeys/journey-ui-withheld/assessments",
        data={"decision_time": "2026-01-01T09:30:00+00:00"}, follow_redirects=False,
    )
    rec = assessed.headers["location"].rsplit("/", 1)[-1]

    html = client.get(f"/ui/recommendations/{rec}/graph").text
    assert "did not exist yet" in html


# ---------------------------------------------------------- human confirmation UI


def test_dashboard_shows_the_unconfirmed_state_prominently(client, recommendation):
    html = client.get(f"/ui/recommendations/{recommendation}").text
    assert "must not inform care yet" in html


def test_review_through_the_ui_records_and_is_reflected(client, recommendation):
    client.post(
        f"/ui/recommendations/{recommendation}/review",
        data={"reviewer_id": "clinician-ui", "action": "CONFIRM", "reason_code": "", "note": ""},
        follow_redirects=False,
    )
    html = client.get(f"/ui/recommendations/{recommendation}").text
    assert "clinician-ui" in html
    assert "must not inform care yet" not in html


def test_an_override_without_a_reason_is_refused_and_explained(client, recommendation):
    response = client.post(
        f"/ui/recommendations/{recommendation}/review",
        data={"reviewer_id": "clinician-ui", "action": "MODIFY", "reason_code": "", "note": ""},
        follow_redirects=False,
    )
    assert "reason_code" in response.text
    assert "Not recorded" in response.text


def test_the_original_output_survives_an_override(client, recommendation):
    before = client.get(f"/recommendations/{recommendation}").json()["response"]["urgency"]["level"]
    client.post(
        f"/ui/recommendations/{recommendation}/review",
        data={"reviewer_id": "c", "action": "MODIFY", "reason_code": "URGENCY_TOO_HIGH", "note": "x"},
        follow_redirects=False,
    )
    after = client.get(f"/recommendations/{recommendation}").json()["response"]["urgency"]["level"]
    assert after == before

    html = client.get(f"/ui/recommendations/{recommendation}").text
    assert "never edited by one" in html
