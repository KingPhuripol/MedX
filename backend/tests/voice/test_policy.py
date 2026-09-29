"""S3-A04 / S3-A05: the next-question policy never re-asks answered fields and asks every missing one."""

import itertools
import random

import pytest

from app.voice.models import ASK_ORDER, FieldStatus
from app.voice.policy import MAX_ASKS, next_action

from .helpers import ALL_FIELDS, VoiceAPI, simulate_all

STATUSES = ("MISSING", "KNOWN", "UNKNOWN", "REFUSED")


def _check_decision(statuses: dict[str, FieldStatus]) -> None:
    action = next_action(statuses)
    if action.action == "ask":
        st = statuses[action.field]
        assert st.status == "MISSING", f"asked answered field {action.field}"
        assert st.times_asked < MAX_ASKS
        # It is the first askable field in the fixed order.
        first = next(f for f in ASK_ORDER if statuses[f].status == "MISSING" and statuses[f].times_asked < MAX_ASKS)
        assert action.field == first
    else:
        missing = [f for f in ASK_ORDER if statuses[f].status == "MISSING"]
        assert all(statuses[f].times_asked >= MAX_ASKS for f in missing)
        assert action.reason == ("attempts_exhausted" if missing else "complete")
        assert action.missing_fields == missing


def _generated_states(n: int = 600):
    rng = random.Random(0)
    for _ in range(n):
        yield {
            f: FieldStatus(field=f, status=rng.choice(STATUSES), times_asked=rng.randrange(0, 4)) for f in ASK_ORDER
        }


def test_policy_never_asks_answered_field(app):
    # 1) Simulated runs of all 15 fixtures (scripted patient driven by answers_by_field).
    n_asks = 0
    for run in simulate_all(app):
        for d in run.decisions:
            if d["action"]["action"] == "ask":
                n_asks += 1
                assert d["statuses"][d["action"]["field"]]["status"] == "MISSING", run.dialogue_id
    assert n_asks >= 15
    # 2) >= 500 generated field-state combinations.
    count = 0
    for statuses in _generated_states():
        _check_decision(statuses)
        count += 1
    # 3) Every status combination with no asks yet (4^6 = 4096).
    for combo in itertools.product(STATUSES, repeat=len(ASK_ORDER)):
        _check_decision({f: FieldStatus(field=f, status=s, times_asked=0) for f, s in zip(ASK_ORDER, combo)})
        count += 1
    assert count >= 500


def test_policy_asks_all_missing_before_finish(app):
    runs = simulate_all(app)
    assert len(runs) == 15
    for run in runs:
        final = run.decisions[-1]
        statuses = final["statuses"]
        assert final["action"]["action"] == "handoff", run.dialogue_id
        if final["action"]["reason"] == "nurse_attention_phrase":
            continue
        assert final["action"]["reason"] in {"complete", "attempts_exhausted"}
        for field in ALL_FIELDS:
            st = statuses[field]
            assert st["times_asked"] <= MAX_ASKS
            # Every field is either answered (possibly volunteered before being asked) or was asked.
            assert st["status"] != "MISSING" or st["times_asked"] >= 1, (run.dialogue_id, field)
            if st["times_asked"] == 0:
                assert st["status"] != "MISSING"
        if final["action"]["reason"] == "complete":
            assert all(statuses[f]["status"] != "MISSING" for f in ALL_FIELDS)
        else:
            assert final["action"]["missing_fields"] == [f for f in ALL_FIELDS if statuses[f]["status"] == "MISSING"]


def test_policy_max_two_asks(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    first = api.start().json()["next_action"]
    asked = [first["utterance_id"]]
    action = first
    for _ in range(20):
        if action["action"] == "handoff":
            break
        action = api.turn("อืม").json()["next_action"]
        asked.append(action["utterance_id"])
    expected = [f"{kind}.{f}" for f in ALL_FIELDS for kind in ("ask", "reask")]
    assert asked[:-1] == expected
    assert action["reason"] == "attempts_exhausted"
    assert action["missing_fields"] == list(ALL_FIELDS)
    statuses = {s["field"]: s for s in api.get().json()["field_statuses"]}
    assert all(s["times_asked"] == 2 and s["not_elicited"] for s in statuses.values())
    # A further turn does not re-ask or repeat the handoff line.
    n_turns = len(api.get().json()["turns"])
    assert api.turn("อืม").json()["next_action"]["reason"] == "attempts_exhausted"
    assert len(api.get().json()["turns"]) == n_turns + 1
    for run in simulate_all(app):
        for d in run.decisions:
            assert all(s["times_asked"] <= MAX_ASKS for s in d["statuses"].values())


@pytest.mark.parametrize("answers", [0, 2, 4])
def test_finish_early_lists_missing(client, login, app, answers):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    script = ["ไอค่ะ", "สามวันค่ะ", "ปานกลางค่ะ", "ปฏิเสธแพ้ยาค่ะ"][:answers]
    for text in script:
        api.turn(text)
    done = api.finish().json()
    truly_missing = list(ALL_FIELDS[answers:])
    assert done["missing_fields"] == truly_missing
    assert done["handoff_reason"] == "finished_by_nurse"
    statuses = {s["field"]: s["status"] for s in done["field_statuses"]}
    assert [f for f in ALL_FIELDS if statuses[f] == "MISSING"] == truly_missing
    assert done["session"]["status"] == "finished"
