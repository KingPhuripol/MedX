"""Scripted-patient simulator driven by a fixture's ``answers_by_field``.

The agent asks (deterministic policy); the simulator replies with the next unused fixture turn listed
for the asked field, or a neutral filler when the script has nothing left for that field. It stops on
handoff and finishes the session. Times are synthetic and monotonic; a fake clock is passed to the
service so the dialogue plays at scripted pace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .models import AddTurnBody, StartSessionBody
from .service import VoiceContext, finish, start_session, timed_add_turn

FILLER_TEXT = "ค่ะ"
MAX_POSTS = 40


@dataclass
class SimRun:
    dialogue_id: str
    session_id: str
    turn_map: dict[str, str] = field(default_factory=dict)  # fixture turn id -> server turn id
    decisions: list[dict[str, Any]] = field(default_factory=list)  # every emitted next action + statuses
    posts: list[dict[str, Any]] = field(default_factory=list)  # every posted turn and its response
    latencies_ms: list[float] = field(default_factory=list)
    start: dict[str, Any] = field(default_factory=dict)
    finish: dict[str, Any] = field(default_factory=dict)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def simulate(ctx: VoiceContext, fixture: dict[str, Any], patient_ref: str | None = None) -> SimRun:
    turns = {t["turn_id"]: t for t in fixture["turns"]}
    queues = {f: list(tids) for f, tids in fixture["answers_by_field"].items()}
    cursor = _dt(fixture["turns"][0]["started_at"])
    started = start_session(
        ctx, StartSessionBody(patient_ref=patient_ref or fixture["patient_ref"], data_class="synthetic"), cursor
    )
    run = SimRun(dialogue_id=fixture["dialogue_id"], session_id=started["session"]["session_id"], start=started)
    statuses = {s["field"]: s for s in started["field_statuses"]}
    action = started["next_action"]
    run.decisions.append({"action": action, "statuses": statuses})
    cursor += timedelta(seconds=1)

    for _ in range(MAX_POSTS):
        if action["action"] == "handoff":
            break
        queue = queues.get(action["field"], [])
        if queue:
            ftid = queue.pop(0)
            src = turns[ftid]
            speaker, text = src["speaker"], src["text"]
            duration = _dt(src["ended_at"]) - _dt(src["started_at"])
        else:
            ftid, speaker, text, duration = None, "patient", FILLER_TEXT, timedelta(seconds=1)
        body = AddTurnBody(speaker=speaker, text=text, started_at=cursor, ended_at=cursor + duration)
        resp, ms = timed_add_turn(ctx, run.session_id, body, cursor + duration + timedelta(milliseconds=100))
        run.latencies_ms.append(ms)
        if ftid:
            run.turn_map[ftid] = resp["turn"]["turn_id"]
        run.posts.append({"fixture_turn_id": ftid, "body": body, "response": resp})
        action = resp["next_action"]
        statuses = {s["field"]: s for s in resp["field_statuses"]}
        run.decisions.append({"action": action, "statuses": statuses})
        cursor = cursor + duration + timedelta(seconds=2)

    run.finish = finish(ctx, run.session_id, cursor)
    return run
