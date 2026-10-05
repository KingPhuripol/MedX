# Slice e1r2: E1 post-hoc note v2 - every red-flag miss listed, SYNE-0196 claim corrected

- Owner (Gantt): สุปรียา
- Delta on: `slices/e1r/SPEC.md` rev 2 (branch `factory/e1r`, tip `7cd1f77`). Every e1r acceptance item (E1R-A01..A16) still holds unless this spec changes it.
- Source of truth: `docs/PROPOSAL.md` (v8): 3.6 / Table 3.2 (System Evaluation, not clinical performance), 1.3.4 (no diagnosis or autonomous routing), the Red-flag Node (a mandatory node in every graph).
- Status: PLAN rev 1, written by the planner. Tier 0 only (CPU, stored synthetic outputs, one in-memory dev replay). No GPU, no real data, no external service, 0 new ledger lines.

## Why this slice exists

The e1r note has three problems:

1. It overstates how much of SYNE-0196 is a replay artifact.
2. It lists only the 13 silent-suggest red-flag misses and leaves out the 19 abstained ones.
3. It prints Python booleans.

All three are fixed **by disclosure only**.

## Scope

Only these files may change: `eval/posthoc/e1_findings.py`, the regenerated `eval/results/e1/POSTHOC_FINDINGS.{json,md}`, `eval/tests/test_e1_posthoc.py`, `tests/e1r/test_syne0196_replay.py` and this spec.

1. **SYNE-0196 classification (MEDIUM, claim accuracy).** The current `REPLAY_ARTIFACT` half claims that in agent-led use S3 would ask `allergy_status` before the handoff, so the turn-9 answer would not reach the CC gate. The replay contradicts this, and so does the code at `8943cd1`:
   - S3's own policy hands off right after source turn 1 (`handoff.nurse_attention_phrase`, `after_turn_index` 1).
     - The handoff is deterministic: turn 1 contains `ปากเบี้ยว`. See `backend/app/voice/policy.py:17` (the phrase list), `policy.py:30` (`nurse_attention_hit`) and `backend/app/voice/service.py:157-158` (`_decide`: attention leads to handoff).
     - So in live use S3 never asks a non-CC field in this case.
   - The handoff turn has `field=None` (`policy.py:47`). As a result `last_asked` stays `chief_complaint` for every patient turn 1..11 (`service.py:401`; replay `last_asked_field_at_patient_turns`).
   - The session stays `active` after a handoff:
     - `add_turn` refuses only sessions that are not active (`service.py:378`);
     - only `finish()` sets `finished` (`service.py:548`);
     - the web turn form (speaker patient / relative / nurse) is rendered until finish (`web/components/voice/VoiceIntake.tsx:199`).

   Required changes:
   - Set `classification` to `S3_DEFECT`.
   - Restate `classification_rationale` using only the facts above plus the existing parts (a) no-field handoff turn and `last_asked`, (b) silent supersede of the CC, and (c) focal deficit coerced to `fatigue`.
   - Say that the only replay-specific differences are these: the nurse turns are pre-recorded text, and there is no ASR or audio. Neither changes the S3 code path.
   - Add the new citations to `code_citations`. Each line number must be verified against `git show 8943cd1:<file>`.
   - Add to DEF-E1R-001:
     - `live_use_reachable: true`;
     - a `live_use_reachability` statement: in live use of this exact case, a patient answer entered after the handoff (e.g. the allergy answer) reaches the CC gate and can replace the turn-1 CC, as in the replay;
     - the new citations in `evidence`.

   If the builder finds replay or code evidence that contradicts this scope item, stop and return to the planner. Do not pick another label.
2. **All red-flag misses (MEDIUM, safety disclosure).** Add a table to C-E1-2: "All rf_case_recall misses (gold red-flag-positive, 0 alerts)".
   - **Rows.** One row per `eval/results/e1/{split}/triage/predictions.jsonl` row with `task == "rf_case_recall"`, `y_true` true and `y_pred` false, joined with `system_outputs.jsonl` for the same DP.
   - **Columns.** Split, case, DP, gold department, gold expected action, gold rule(s), system outcome (`suggested` / `abstained`), dept reason, system top3, alert count, `escalation_required` (yes/no), and "also listed in" (silent escalations / C5 overlap / none).
   - **JSON.** Write it to `data.rf_case_recall_misses` (the rows) and to `data.rf_case_recall_miss_counts[split]` = {`total`, `suggested`, `abstained`, `abstained_gold_not_evaluable`, `with_any_alert`, `escalation_required_true`}.
   - **Consistency checks.** The generator raises `PosthocError` unless all three hold:
     - `total == n - x` of the frozen `rf_case_recall` row;
     - the `suggested` rows equal the E1R-A07 silent-escalation set;
     - the gold-NOT_EVALUABLE rows equal the missed subset of the C5 overlap.
   - **FAST sentence.** Add this sentence, rendered from the data: "The FAST-positive abstentions (dev SYNE-0166 T1/T2, test SYNE-0033 T1/T2, test SYNE-0131 T1/T2) are misses by the C5 rule: their gold department is 12, so they are scored in the red-flag metrics, and an abstention with no alert is not a detection."
3. **Rendering and provenance (LOW).**
   - The md renders every boolean as `yes` / `no`. The JSON keeps JSON `true` / `false`.
   - The trace gains `instrumented_replay.provenance`, and the md states it: `INSTRUMENTED_REPLAY_SYNE0196` is a hand-transcribed constant in `eval/posthoc/e1_findings.py`, recomputed and asserted equal by `tests/e1r/test_syne0196_replay.py::test_replay_constant_recomputed`.
4. **Headline.** Keep exactly 5 bullets. Bullet 2 is reworded from data so that it states all of these:
   - the misses: dev 19 and test 13 gold red-flag-positive DPs with 0 alerts;
   - of those, dev 8 / test 5 got a department suggestion and dev 11 / test 8 abstained;
   - the text-red-flag zero by construction (dev 0/8, test 0/6).

   Bullet 3 must not call SYNE-0196 an artifact.

## Out of scope

- Everything in e1r "Out of scope". In particular, these stay byte-identical to `8943cd1`: `eval/manifests/e1/`, `eval/adapters/**`, `eval/ledger/`, `eval/results/e1/{dev,test,unfrozen}/`, `eval/results/e1/e1_summary.{json,md}`, `data/`, `backend/`, `web/`.
- No new freeze or run, and no S3/S4 execution on test-split inputs.
- No fix to S3/S4. No new metric or verdict.
- The untracked `tests/e2e/` checker files. Do not commit or edit them.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| E1R2-A01 | SYNE-0196 classification matches the evidence | 1. `classification == "S3_DEFECT"`. 2. The rationale states all 3 facts of scope 1: the handoff after source turn 1 on `ปากเบี้ยว`; `last_asked` = `chief_complaint` at all patient turns 1..11; the session stays active after the handoff. 3. 0 matches in either file of `would ask allergy_status`, `would not reach the CC gate`, or any claim that S3 asks `allergy_status` in this case. 4. Every new citation's file:line resolves at `8943cd1` to the quoted code. | checker compares with `artifacts/factory/e1r/syne0196_probe.json` (`n_agent_turns` 3, handoff after the ปากเบี้ยว turn), a fresh dev-only replay (`tests/e2e/e1r_syne0196_probe.py`), and `git show 8943cd1:backend/app/voice/{service,policy}.py`, `web/components/voice/VoiceIntake.tsx` |
| E1R2-A02 | DEF-E1R-001 states live-use reachability | `live_use_reachable` is `true`. `live_use_reachability` names SYNE-0196 and says that a post-handoff answer reaches the CC gate in live use. `evidence` cites `service.py:378` and `service.py:548`. Severity stays HIGH and `target_slice` stays `i2`. All E1R-A05 fields are still present. | checker: JSON read |
| E1R2-A03 | C-E1-2 lists every red-flag miss | The table and `data.rf_case_recall_misses` have exactly dev 19 and test 13 rows, and the DP sets are equal to the checker's own recomputation. Dev: 8 suggested (SYNE-0081, 0108, 0127, 0196, each T1/T2) + 2 abstained gold-NOT_EVALUABLE (SYNE-0107 T1/T2) + 9 abstained (SYNE-0071 T1/T2, 0089 T1/T2, 0119 T1/T2, 0165 T2, 0166 T1/T2). Test: 5 suggested (SYNE-0039 T2, 0101 T1/T2, 0187 T1/T2) + 8 abstained (SYNE-0033, 0125, 0131, 0141, each T1/T2). Each row shows the outcome, alert count 0, and the gold rules. Counts `with_any_alert` = 0 and `escalation_required_true` = 0 in both splits. `total == n - x` of frozen `rf_case_recall` (dev 24-5, test 22-9). | checker recomputes independently from `*/triage/predictions.jsonl` + `*/system_outputs.jsonl` + gold; set equality |
| E1R2-A04 | FAST abstention sentence present | The md contains the scope-2 sentence naming dev SYNE-0166 and test SYNE-0033 and SYNE-0131 as misses by the C5 rule. The checker confirms from gold that these DPs have gold department `12` and `RF-FAST`. | grep + gold read |
| E1R2-A05 | No Python booleans in the md | `grep -nwE 'True\|False' eval/results/e1/POSTHOC_FINDINGS.md` prints nothing. The yes/no rendering appears in the SYNE-0196 trace rows. | grep |
| E1R2-A06 | Replay constant is provenance-labelled and recomputed | The md and the JSON state that the constant is hand-transcribed and name the verifying test. `test_replay_constant_recomputed` recomputes every key of `INSTRUMENTED_REPLAY_SYNE0196` (except `verified_by` and `provenance`) from the dev-only replay, asserts that the key sets are equal, asserts that the values are equal, and passes. | `pytest tests/e1r/test_syne0196_replay.py` |
| E1R2-A07 | Headline updated | Exactly 5 bullets. Bullet 2 carries dev 19 / test 13 misses and their suggested/abstained split, rendered from JSON. 0 forbidden-claim regex matches. No bullet calls SYNE-0196 an artifact. `spec_deviations == []`. | pytest + checker read |
| E1R2-A08 | Frozen paths untouched | `git diff --name-only 8943cd1 -- eval/manifests eval/adapters eval/ledger eval/results/e1/dev eval/results/e1/test eval/results/e1/unfrozen eval/results/e1/e1_summary.json eval/results/e1/e1_summary.md data backend web` prints nothing. `git diff --name-only 7cd1f77..HEAD` lists only the scope files. `runs.jsonl` stays at 5 lines. | checker: git |
| E1R2-A09 | Ledger integrity | `python3 -m eval ledger verify --git-history` exits 0 | checker |
| E1R2-A10 | Regeneration, isolation, suite | `--check` exits 0 and two runs are byte-identical. `test_eval_isolation` passes, so the posthoc module still imports no `app.*`. `make test` is green. | `python -m eval.posthoc.e1_findings --check`, `make test` |

## Required test cases

In `eval/tests/test_e1_posthoc.py`:

1. `test_syne0196_classification`: checks that `classification == "S3_DEFECT"`, that the three scope-1 facts are present, that the forbidden phrases in E1R2-A01 are absent from both files, and that the new citations are in `code_citations`.
2. `test_def001_live_use`: covers the E1R2-A02 fields.
3. `test_rf_case_recall_misses`: covers the exact dev/test DP sets and counts in E1R2-A03, and checks the silent-escalation subset and the C5 NOT_EVALUABLE subset.
4. `test_miss_count_mismatch_refused`: on a tmp copy whose predictions pin is re-hashed so that a miss is dropped, the generator raises `PosthocError`. Alternatively, a unit test of the consistency check with a doctored row list.
5. `test_fast_abstention_sentence`: covers E1R2-A04.
6. `test_md_no_python_booleans`: covers E1R2-A05.
7. `test_defects_and_headline`: extended for E1R2-A07.

In `tests/e1r/test_syne0196_replay.py`:

8. `test_replay_constant_recomputed`: covers E1R2-A06. It uses the dev split only and writes nothing under `eval/results` or `eval/ledger` (checked by hash).

## Clinical risks

- **Understated safety gap (HIGH).** Calling half of SYNE-0196 a replay artifact implied that live use was safer than the evidence shows. For this exact case, a FAST-positive patient can be routed to ORTHO/MED with no alert in live use. DEF-E1R-001 stays open for I2.
- **Abstention read as safe.** 19 of 32 misses are abstentions with 0 alerts and `escalation_required` false. A nurse sees "abstained", not "urgent". The note must state that these are misses and not safe abstentions.
- **Over-claim.** This is a System Evaluation on synthetic data with text replay through mock rules. It involves no ASR, no clinician review and no clinical performance claim.

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/Workstreams/SeniorProject/Full-Agent-e1
.venv/bin/python -m eval.posthoc.e1_findings
.venv/bin/python -m eval.posthoc.e1_findings --check
.venv/bin/python -m pytest -q eval/tests/test_e1_posthoc.py tests/e1r/test_syne0196_replay.py
grep -nwE 'True|False' eval/results/e1/POSTHOC_FINDINGS.md          # must print nothing
.venv/bin/python -m eval ledger verify --git-history
git diff --name-only 8943cd1 -- eval/manifests eval/adapters eval/ledger eval/results/e1/dev eval/results/e1/test \
  eval/results/e1/unfrozen eval/results/e1/e1_summary.json eval/results/e1/e1_summary.md data backend web   # must be empty
make test
```
