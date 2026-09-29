# Slice s1r — Synthetic case factory v1.1: label validity fixes (revision 2)

- Owner (Gantt task 21, same as s1): สุปรียา
- Source of truth: `docs/PROPOSAL.md` (v8). This spec is a **delta** on `slices/s1/SPEC.md` (plan b7ac024, implementation 47d3a6d). Everything in the S1 spec still applies unless a row below amends it. PROPOSAL sections used: 1.3.1 (the Red-flag Node uses predeclared rules; required intake fields), 1.3.4 (simulated environment only), 2.1.4 and 3.4 (no leakage; snapshot at decision time), 3.2.2 (abstain when required data is missing), 3.6 (labels come from data not sent to the model; abstention proportion reported alongside accuracy on concluded cases).
- Status: PLAN, revision 2. Revision 1 (46af005) was implemented in 027422f. The checker then found S1R-A08, A09 and A10 ambiguous or unmeasurable and raised a risk on A06. Revision 2 fixes those four items (section "Revision 2 decisions") and adds S1R-A15 to A17. The implementation must be updated to this revision.
- Tier 0 (CPU, synthetic, deterministic). No GPU and no external API.
- Claim boundary (unchanged): the labels are **synthetic reference labels** for **system evaluation only**. They are not clinical ground truth until the clinical expert review (D1) is recorded in `docs/DECISIONS.md`. A "no red flag" gold label means only that no rule in this registry fires. It does not mean the patient is clinically safe.

## Reviewer findings this slice fixes

| # | Severity | Finding | Fix (scope item) |
|---|---|---|---|
| F1 | HIGH | Near-miss negatives can meet an urgent criterion from the cited NEWS source. Example: SYNE-0105 has RR 22 (2 points), SBP 101 (1), fever 38.1–38.9 (1), and HR 91–110 (1), so aggregate NEWS is 5. It is still labelled no-red-flag. `test_near_miss_negatives` skips any case its own oracle flags. | 1, 2 |
| F2 | MEDIUM | Cases with a missing chief complaint carry a department label (from the hidden planned complaint) that cannot be derived from the inputs. | 3 |
| F3 | MEDIUM | Lexical shortcut: every text red flag contains `ทันที`, and no negative case does. | 4, 4a |
| F4 | MEDIUM | Nothing says that only `snapshot_T*.json` is a valid model input. `journey.json` sits next to the snapshots. | 5 |
| F5 | LOW-MEDIUM | Pregnancy (obstetric-complaint) cases can carry ACE inhibitors or statins without any labelled issue. | 6 |
| F6 | LOW | `make data` runs `rm -rf "$(OUT)"` for any OUT path that contains a `splits.json`. | 7 |

## Revision 2 decisions (checker findings on revision 1)

The planner re-ran the checker's analysis on the 027422f output at the default seed. The planner used the character-substring scan defined in 4a. Results:

- **Targets.** Positive cases at T1: 28 for any text red flag and 7 for each text rule.
- **Violating substrings.** Substrings with F1 ≥ 0.75, per target:
  - any text red flag: 34, for example `่วโมง`, from the duration unit `ชั่วโมง`: P 0.81, R 0.79;
  - RF-FAST: 48, for example `ยวและ`: P 1.00, R 1.00;
  - RF-THUNDERCLAP: 45, for example `ที่สุด`: P 1.00, R 1.00;
  - RF-ANAPHYLAXIS: 40, for example `หายใจ`: P 1.00, R 1.00;
  - RF-ACUTE-CHEST-PAIN: 0.
- **Duration units.** Text red-flag cases that state a duration: 22/22 give it in hours. Ordinary cases: 2/85 in hours. Near-miss cases: 3/55 in hours.
- **Missing chief complaint.** 0/10 missing-chief-complaint cases carry a red flag.

| Checker item | Decision |
|---|---|
| S1R-A08 (tokenisation of V) | **V is every contiguous character substring**, length 1 to 30, of the NFC text of each patient turn in `snapshot_T1.json`. Whitespace tokens and registry lexicon terms are added to V. Thai has no word spaces. Any word segmenter's output (with words ≤ 30 characters; the longest lexicon term is 20) is therefore a subset of V, and V needs no new dependency. The pass threshold becomes **F1 < 0.75 for every substring and every target**. This is stricter than "not (P ≥ 0.8 and R ≥ 0.8)": that condition implies F1 ≥ 0.8. It also catches the checker's three examples: F1 1.00, 0.80 and 0.83. Targets are "any text red flag" and **each of the 4 text rules**. Revision 1 covered only the 3 onset-dependent rules. |
| S1R-A08 (duration units) | Duration units are **not made fully independent** of the label. Acute presentations are defined by timing, and a FAST deficit "for 3 weeks" would be clinically wrong. Instead, a unit must **not be a sufficient cue**. Text red flags state their duration in both `นาที` and `ชั่วโมง`. Benign acute complaints and near-miss cases also use `ชั่วโมง` or `นาที`. The unit words fall under the A08 F1 bound (S1R-A16). |
| S1R-A09 (vacuous D4 path) | The generator must plan **≥3 cases** with a missing chief complaint and a vitals red flag (a text red flag needs the complaint stated). At least 1 of them has onset at T1 and at least 1 has onset at T2. The T2-onset case checks the transition from `abstain` to `escalate` while the department stays `NOT_EVALUABLE`. |
| S1R-A10 (`make audit` short-circuits) | `make audit` runs **both** steps unconditionally: the leakage script, then the factory audit. It prints a status line per step and exits non-zero if either step failed. The planted-fault test checks two things separately. First, the factory audit, run directly, fails on exactly one check, `snapshot_items_after_T`, and names the planted item. Second, `make audit` exits non-zero and its output contains `snapshot_items_after_T` and the planted item_id. The leakage script also failing is expected (defence in depth). |
| S1R-A06 risk (arrival turn not label-independent) | The arrival-turn variant (`ทันที` in its travel sense) is assigned **per stratum** at the same quota of 1/3. The strata are: text red flag, vitals red flag, vitals near-miss, text near-miss, and ordinary. Each stratum's share must be within 1/3 ± 0.05 (S1R-A16). |

## Scope

1. **Aggregate NEWS rule (F1).**
   - Add `RF-NEWS-AGG5` to `data_factory/templates/red_flags.json`. It fires when aggregate NEWS ≥ 5 on any single `Vitals` item. It keeps its own `rule_id`, so single-parameter-3 cases stay under `RF-NEWS-SINGLE3`.
   - Scoring follows NEWS (2012), Royal College of Physicians working-party report, July 2012, Chart 1 and the clinical response section (`RCP-NEWS-2012`). The same NEWS is evaluated by Smith 2013 (PMID 23295778). Bands:
     - RR: ≤8 → 3, 9–11 → 1, 12–20 → 0, 21–24 → 2, ≥25 → 3.
     - SpO2: ≤91 → 3, 92–93 → 2, 94–95 → 1, ≥96 → 0.
     - Any supplemental O2: yes → 2.
     - Temperature: ≤35.0 → 3, 35.1–36.0 → 1, 36.1–38.0 → 0, 38.1–39.0 → 1, ≥39.1 → 2.
     - SBP: ≤90 → 3, 91–100 → 2, 101–110 → 1, 111–219 → 0, ≥220 → 3.
     - HR: ≤40 → 3, 41–50 → 1, 51–90 → 0, 91–110 → 1, 111–130 → 2, ≥131 → 3.
     - AVPU: A → 0; V, P or U → 3.
     - Trigger: an aggregate of 5 or more, or a single parameter scoring 3, "should prompt an urgent review".
   - Consciousness `C` scores 0 under NEWS 2012. It still counts toward qSOFA. Moving to NEWS2 is a D1 question.
   - A `null` parameter contributes 0, so the computed sum is a lower bound. The rule fires when that lower bound is ≥5.
   - Add red-flag variant `NEWS-AGG5`: no parameter scores 3, qSOFA ≤1, and the aggregate is 5–6.
2. **Near-miss constraints and a non-skipping test (F1).**
   - Every `Vitals` item of every *vitals near-miss* case, including repeat vitals, must meet all of these:
     - all 7 NEWS inputs are non-null;
     - AVPU is A;
     - no parameter scores 3;
     - the aggregate is ≤4;
     - qSOFA is ≤1;
     - SBP is ≥90.
   - Each such case must have ≥1 item near a threshold: aggregate = 4, a parameter scoring 2, or RR 22 / SBP 100 with qSOFA = 1.
   - No fever band may push a near-miss case to ≥5.
   - Add variant `NM-NEWS-AGG4`.
   - `test_near_miss_negatives` selects cases by the gold tag, never by oracle output. It asserts every tagged case and every T, and checks `n_asserted == n_tagged`. It has no skip or continue path.
   - The independent oracle has its own literal NEWS band table and does not import `data_factory.generate`. An equality test pins the table to the registry.
3. **Department not evaluable when the chief complaint is missing (F2).**
   - When the chief complaint is `MISSING`, every gold row sets:
     - `target_department: "NOT_EVALUABLE"`;
     - `department_evaluable: false`;
     - `department_reason: "chief_complaint_missing"`.
   - All other rows set `department_evaluable: true`.
   - `expected_action` precedence is unchanged: a red flag gives `escalate` (D4); otherwise a missing field gives `abstain`.
   - **New in revision 2:** the plan guarantees ≥3 missing-chief-complaint cases with a vitals red flag, with onset at T1 in ≥1 of them and at T2 in ≥1.
   - The DATACARD and gold README state that department accuracy is computed only over rows with `department_evaluable == true`.
   - The new keys are gold-only (the audit bans them in inputs).
4. **Remove the lexical shortcut (F3): templates.**
   - **Paraphrases:** each of the 4 text rules has ≥3 complaint templates. For the 3 onset-dependent rules, ≥2 templates contain no `ทันที`. An onset-dependent rule fires on a concept term AND a sudden-onset term in the same patient turn.
   - **Text near-miss families** (scenario `text_near_miss`): ≥6 cases each, ≥30 in total. Each has normal vitals (aggregate ≤2), a `near_miss_reason`, and a `near_miss_ref`. The families:
     - `TNM-CHEST-STABLE`: chest pain for weeks that is reproducible with movement or palpation.
     - `TNM-HEADACHE-GRADUAL`: headache that builds over days. Here `ที่สุด` is used only in a time-of-day sense (e.g. `ปวดมากที่สุดตอนบ่าย`), never as "worst ever".
     - `TNM-NUMB-BILATERAL`: bilateral finger numbness for months.
     - `TNM-URTICARIA-ONLY`: skin or lip swelling only, with no respiratory, GI or BP terms and no stated exposure to a likely allergen.
     - **New** `TNM-DEFICIT-CHRONIC`: an old, unchanged face, speech or arm deficit, e.g. a follow-up visit years after a stroke with `อาการเท่าเดิม`. It has no sudden-onset term, and its duration is in months or years. It is not an acute FAST presentation (Harbison 2003, `PMID-12511753`).
   - **Minimal pairs** (so that a single term can never be sufficient; S1R-A15):
     - Each concept term of an onset-dependent rule that appears in a positive case must also appear in ≥3 negative cases with no onset term in the same turn.
     - Each onset term that appears in a positive case must also appear in ≥3 negative cases with no concept term of any rule in the same turn. Allowed forms: the arrival sense of `ทันที`, or a benign sudden event (e.g. `ท้องเสียเฉียบพลัน`, or vertigo on position change lasting `ไม่กี่วินาที`).
     - Each skin/mucosal term of RF-ANAPHYLAXIS that appears in a positive case must appear in ≥3 negative cases with no respiratory term.
     - Negatives that contain `หายใจ` may use only upper-airway phrasing (e.g. `คัดจมูก หายใจทางจมูกไม่สะดวก`). They must never contain a registry respiratory term (`หายใจลำบาก`, `หายใจมีเสียงหวีด`, `หายใจไม่ออก`) or chest dyspnoea.
   - **Superlatives:** `ที่สุด`/`มากที่สุด` also appear in ordinary complaints in a time-of-day sense (e.g. `ไอมากที่สุดตอนกลางคืน`).
   - Nurse turns are one fixed script for every case.
4a. **Remove the lexical shortcut (F3): measurement and surface features.**
   - **Shortcut scan** (`test_single_token_baseline_fails`), unit = case at T1:
     - A case's text is the NFC text of the patient turns in its `snapshot_T1.json`.
     - V = all substrings of length 1–30 of each patient turn, plus the whitespace tokens and every registry lexicon term.
     - A substring *s* predicts positive when it occurs in any patient turn.
     - Targets: "any text red flag at T1", plus each of the 4 text rules.
     - Negatives are all other cases, including vitals red-flag and missing-chief-complaint cases.
     - For each target, the test prints the top 5 substrings by F1 with P, R and support. This goes to the test log as evidence.
     - The scan code must not import `data_factory.generate`.
   - **Template balance:** within each text rule, no template covers >40% of that rule's T1 positives. Within each near-miss family, no template covers >60% of the family.
   - **Duration:**
     - Each text rule uses ≥2 duration units drawn from {`นาที`, `ชั่วโมง`}, with no unit covering >70% of the rule's cases that state a duration.
     - ≥15 non-red-flag cases state a duration in `ชั่วโมง` or `นาที`. Candidate benign acute complaints: diarrhoea, ear pain, urticaria-only, and ankle injury (the implementer may add templates, each with an ICD-10-CM `source_ref`).
   - **Arrival turn:** the `ทันที` arrival variant is assigned with a per-stratum counter at quota 1/3 in each stratum (text red flag, vitals red flag, vitals near-miss, text near-miss, ordinary).
5. **Snapshot-only model inputs (F4).**
   - `DATACARD.md` states verbatim: "Only `inputs/<split>/<case_id>/snapshot_T*.json` files are valid model inputs. `journey.json` is the full timeline, including items after every decision time, for audit only; it must never be given to a model."
   - `manifest.json` has `model_inputs_glob` and `audit_only_globs`, and both are covered by the manifest hash.
   - The factory audit has a named check `snapshot_items_after_T`. It fails on any snapshot item with `available_at_time`, `observed_at` or `event_time` > T, and lists the item_ids.
   - **New in revision 2:** the `make audit` target runs the leakage script and then the factory audit **without short-circuiting**. It prints `STEP leakage: PASS|FAIL` and `STEP factory: PASS|FAIL`, and exits non-zero if either step failed.
   - The layout is unchanged (D3).
6. **Pregnancy medication exclusion (F5).**
   - Pregnancy cases draw no ATC `C09*` or `C10AA*` drug in any list: home list, patient-reported list, new order, duplicate partners, or injected entries.
   - The exclusions are in `pregnancy_exclusions.json` with these sources:
     - `DAILYMED-ENALAPRIL`: fetal-toxicity boxed warning.
     - `FDA-DSC-STATIN-2021`: the contraindication was removed, but most pregnant patients should stop.
   - This slice removes the drugs and adds no "contraindication" label, because such a label would misstate the current statin labelling.
   - The S1-A18 injection quotas must still hold.
7. **OUT path guard (F6).**
   - OUT is resolved with `realpath`. It must be a strict descendant of `<repo>/data/`, of `realpath(tempfile.gettempdir())`, or of `realpath("/tmp")`.
   - The check runs in Python before any deletion. Deletion happens through `--replace`, after the "is a factory dataset" check. The Makefile contains no `rm -rf "$(OUT)"`.
   - A refusal exits with code 2, names the allowed roots, and creates or deletes nothing.
8. Bump `GENERATOR_VERSION` to `1.1.1` (1.1.0 is the revision-1 output) and regenerate. Record the new default-seed `tree_sha256` in the implementation commit message.

## Out of scope

- Everything in S1's out-of-scope list.
- NEWS2: SpO2 scale 2, and new confusion scored as 3. This is D1.
- Negation handling, and any NLP beyond same-turn lexicon co-occurrence.
- Non-lexical shortcuts: turn length, number of items, and timing gaps. They are listed as a risk and are not measured here.
- Other pregnancy-relevant drugs (NSAIDs, sulfamethoxazole–trimethoprim, sulfonylureas, atenolol): D1.
- A pregnancy-contraindication issue type for the Pharma Agent.
- Moving `journey.json` out of `inputs/` (D3).
- Metric computation (evaluation slices).

## Acceptance

- The default seed is 20260926.
- "Near-miss case": gold `scenario.near_miss` or `scenario.text_near_miss` is set.
- "Text red flag": `RF-FAST`, `RF-ACUTE-CHEST-PAIN`, `RF-THUNDERCLAP` or `RF-ANAPHYLAXIS`.
- Every threshold is measured at the default seed on the regenerated set.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S1R-A01 | All S1 acceptance items still pass, amended only as in S1R-A14 | S1-A01…S1-A26: 26/26 PASS. Every S1 test name still exists and passes. | `make test`; `make data && make audit`; `tests/e2e/s1_dataset_check.py` if present |
| S1R-A02 | The oracle recomputes aggregate NEWS from the source bands | 100% match on ≥30 band-boundary vectors (every band edge of RR, SpO2, temperature, SBP and HR, plus O2 and AVPU). The oracle table equals the registry table. 0 imports of `data_factory.generate` in the oracles. | `test_news_score_bands`, `test_oracle_thresholds_match_registry`, import scan |
| S1R-A03 | 0 near-miss cases meet any urgent criterion | Over every Vitals item of every vitals near-miss case at every T, each of the following counts is 0: aggregate ≥5; any parameter scoring 3; qSOFA ≥2; SBP <90; AVPU ≠ A; a null NEWS input. Over every text near-miss case: 0 oracle text-rule hits and 0 gold red flags. | `test_near_miss_negatives` |
| S1R-A04 | The near-miss test asserts on every near-miss case | `n_asserted == n_tagged` (100%). There are ≥20 vitals near-miss cases, and 100% of them have ≥1 near-threshold item. The test has 0 skip or continue paths. `pytest -rs` reports 0 skips in `data_factory/tests`. | `test_near_miss_negatives`; pytest summary |
| S1R-A05 | The aggregate-NEWS rule is exercised and the oracle agrees | `RF-NEWS-AGG5` fires in ≥5 cases and is the only rule in ≥3 of them. The regression vector {RR 22, SBP 101, T 38.5, HR 95, SpO2 97, A, no O2} scores 5 and is flagged by both the generator and the oracle. The oracle equals gold on 100% of ≥400 case×T pairs (0 FP, 0 FN). | `test_red_flag_oracle_agrees`, `test_news_agg_regression_vector`, `test_red_flag_subset` |
| S1R-A06 | Text near-miss negatives exist, and `ทันที` appears in negative contexts | ≥30 text near-miss cases: 5 families with ≥6 each (including `TNM-DEFICIT-CHRONIC`). 100% have aggregate NEWS ≤2 on every Vitals item, 0 gold red flags, a concept term of the paired rule, and a resolving `near_miss_ref`. ≥5 text near-miss cases and ≥5 ordinary cases contain `ทันที` in the arrival turn. | `test_text_near_miss_negatives` |
| S1R-A07 | Red-flag phrasing is paraphrased | Each of the 4 text rules has ≥3 templates, and each template is used in ≥1 case. For the 3 onset-dependent rules, ≥2 templates contain no `ทันที`. The registry has ≥3 sudden-onset terms. | `test_red_flag_paraphrase_templates` |
| S1R-A08 | No single substring solves a text red-flag target (V as defined in scope 4a) | Each of the 5 targets has ≥7 T1 positives ("any" ≥28). For every *s* in V and every target: **F1 < 0.75**, which implies 0 substrings with P ≥ 0.8 and R ≥ 0.8. `contains("ทันที")` over patient turns has P < 0.8 **and** R < 0.8 for "any text red flag". The test log lists the top 5 substrings by F1 per target. | `test_single_token_baseline_fails` |
| S1R-A09 | A missing chief complaint never gives an evaluable department, and the D4 path is exercised | 0 missing-chief-complaint rows have `department_evaluable == true`. 100% of them have `NOT_EVALUABLE`. 100% of those without a red flag are `abstain`, and 100% of those with a red flag are `escalate`. **≥3 cases (≥4 case×T rows) have a missing chief complaint and a red flag, with ≥1 T1-onset case and ≥1 T2-onset case. The T2-onset case is `abstain` at T1 and `escalate` at T2, and `NOT_EVALUABLE` at both.** ≥5 missing-chief-complaint cases have no red flag. 100% of other rows are evaluable and carry one of the 10 codes. | `test_missing_cc_department_not_evaluable`, `test_missing_cc_red_flag_escalates`, `test_expected_action_precedence` |
| S1R-A10 | Snapshot-only inputs are documented and audited | The DATACARD contains the verbatim snapshot-only sentence and the department-accuracy exclusion. The manifest has `model_inputs_glob` and `audit_only_globs`, both hash-covered. `snapshot_items_after_T` PASSes on the generated set. For one future item planted in a snapshot (manifest hashes recomputed): (a) `python -m data_factory audit` exits non-zero with **exactly 1** failing check, `snapshot_items_after_T`, whose report lists the planted item_id (1/1); (b) `make audit OUT=<planted>` exits non-zero, its output contains `STEP factory: FAIL`, `snapshot_items_after_T` and the planted item_id, and both STEP lines are printed. | `test_datacard_snapshot_only`, `test_manifest_model_inputs`, `test_audit_detects_planted[snapshot_after_T]`, `test_make_audit_runs_all_steps` |
| S1R-A11 | No unlabelled RAS-acting drug or statin in pregnancy | 0 pregnancy cases carry an ATC `C09*` or `C10AA*` drug in any list. There are ≥5 pregnancy cases with medication data. 100% of exclusions have a resolving `source_ref`. S1-A18 quotas still hold. | `test_pregnancy_no_ras_or_statin`, `test_injection_counts` |
| S1R-A12 | `make data` refuses an out-of-tree OUT | 5/5 refusal cases exit non-zero: `../x`; an absolute path outside; a symlink under `data/` that resolves outside; `data/` itself; the repo root. After each refusal the sentinel survives and 0 new paths exist. `make data OUT=<repo>/build/s1r_probe` (with a fake `splits.json`) is refused and the probe survives. OUT under `data/synthetic/` and under pytest `tmp_path` succeeds. | `test_out_path_guard[parent\|absolute\|symlink\|data_root\|repo_root]`, `test_make_data_rejects_out_of_tree`, `test_out_path_allowed` |
| S1R-A13 | `make test` and `make audit` are green | `make test` exits 0 with 0 failures and 0 skips in `data_factory/tests`. `make data && make audit` exits 0, both STEP lines are PASS, and all factory checks PASS, including `snapshot_items_after_T`. Generation takes ≤30 s. | `make test`; `make data && make audit`; timed run |
| S1R-A14 | S1 items are amended without being weakened | S1-A12: each of the 7 rules is used ≥5 times. S1-A13: now S1R-A03 to A05. S1-A14: "every code ≥5 cases" and "red flag → 12" apply to evaluable rows. S1-A11: the gold keys include `department_evaluable`, `department_reason` and `NOT_EVALUABLE`, with 0 occurrences in `inputs/`. S1-A20: all new templates are Thai-well-formed. S1-A23: every new template (complaints, near-miss, exclusions) has a resolving `source_ref`. | Existing S1 tests, updated in the same change |
| S1R-A15 | Minimal pairs: no single criterion term is sufficient | For each onset-dependent rule: each concept term that occurs in ≥1 positive occurs in ≥3 negative cases with no onset term in that turn; each onset term that occurs in ≥1 positive occurs in ≥3 negative cases with no concept term of any rule in that turn. For RF-ANAPHYLAXIS: each skin/mucosal term that occurs in a positive occurs in ≥3 negatives with no respiratory term. 0 negative cases contain a registry respiratory term. | `test_minimal_pairs` |
| S1R-A16 | Surface features are not label cues | Arrival: the `ทันที` arrival share in each of the 5 strata is within 1/3 ± 0.05. Duration: each text rule uses ≥2 of {`นาที`, `ชั่วโมง`}, with no unit >70% of the rule's cases that state a duration. ≥15 non-red-flag cases state `ชั่วโมง` or `นาที`. Nurse turns are identical in 100% of cases. | `test_arrival_turn_label_independent`, `test_duration_unit_not_a_cue`, `test_nurse_script_fixed` |
| S1R-A17 | Templates are balanced | Within each text rule, the maximum template share of T1 positives is ≤0.40. Within each near-miss family, the maximum template share is ≤0.60. | `test_template_balance` |

## Required test cases (`data_factory/tests/`, run by `make test`)

- **New (revision 1):**
  - `test_news_score_bands`
  - `test_news_agg_regression_vector`
  - `test_text_near_miss_negatives`
  - `test_red_flag_paraphrase_templates`
  - `test_missing_cc_department_not_evaluable`
  - `test_datacard_snapshot_only`
  - `test_manifest_model_inputs`
  - `test_audit_detects_planted[snapshot_after_T]`
  - `test_pregnancy_no_ras_or_statin`
  - `test_out_path_guard[...]`
  - `test_make_data_rejects_out_of_tree`
  - `test_out_path_allowed`
- **New or rewritten (revision 2):**
  - `test_single_token_baseline_fails`: character substrings, 5 targets, F1 bound, top-5 log.
  - `test_missing_cc_red_flag_escalates`
  - `test_make_audit_runs_all_steps`: runs `make audit` on a planted copy under `tmp_path`.
  - `test_minimal_pairs`
  - `test_arrival_turn_label_independent`
  - `test_duration_unit_not_a_cue`
  - `test_nurse_script_fixed`
  - `test_template_balance`
- **Rewritten:** `test_near_miss_negatives` (selects by tag, asserts all, `n_asserted == n_tagged`).
- **Extended:**
  - `test_oracle_thresholds_match_registry`
  - `test_red_flag_oracle_agrees`
  - `test_red_flag_subset` (7 rules)
  - `test_department_labels` (evaluable rows only)
  - `test_gold_separation`
  - `test_expected_action_precedence`
  - `test_templates_have_source_ref`
- **Independence:** the oracles and the shortcut scan do not import `data_factory.generate`. The NEWS table and the lexicons are literal copies, pinned to the registry by equality tests.
- **Destructive-test safety:** the OUT-guard and `make audit` tests only touch directories that the tests create under `tmp_path` or `build/`.

## Clinical and validity risks

| Risk | Mitigation |
|---|---|
| A "negative" case is urgent under a criterion the registry does not encode | Aggregate NEWS is added (A05). Near-miss cases are constrained against every cited criterion (A03). Unencoded criteria (NEWS2 confusion, other SNOOP features, other anaphylaxis criteria) go to D1. The label wording stays "no registry rule fires". |
| `TNM-DEFICIT-CHRONIC` hides a new stroke in a patient with old deficits | Templates must state an unchanged deficit, a months-or-years duration and no onset term. The label means only "FAST onset condition not met". Flagged for D1. |
| Respiratory-word negatives read as dyspnoea | Only upper-airway nasal phrasing is allowed, and there are 0 registry respiratory terms in negatives (A15). |
| `ที่สุด`/`ทันที` in negatives read as "worst ever" or as sudden onset | `ที่สุด` is limited to a time-of-day sense and `ทันที` to an arrival sense. D1 reviews the templates. |
| The implementer games the F1 bound with unnatural text | New templates must be natural Thai (S1-A20) and carry a `near_miss_reason` or `source_ref`. D1 reviews them. The top-5 substring log makes gaming visible. |
| Non-lexical shortcuts remain (turn length, timing, number of items) | Out of scope. Named here so that evaluation slices do not read label-free performance on this set as language understanding. |
| Small per-rule positive counts (≈7) make F1 coarse | The bound is deterministic at a fixed seed. ≥7 positives per target are required. Claims are limited to "this dataset has no single-substring solution". |
| Department accuracy is biased by non-derivable labels | `NOT_EVALUABLE` rows are excluded. The D4 path is now non-vacuous (A09). |
| A model sees `journey.json` (future leakage) | The snapshot-only statement, the manifest globs, and an audit check that is visible from `make audit` (A10). |
| Unsafe prescribing in pregnancy is modelled without a label | Exclusion with cited sources (A11). Other drugs go to D1. |
| `make data` deletes a user directory | A realpath strict-descendant guard runs before any deletion (A12). |

## Run commands

```bash
make data                      # SEED=20260926 OUT=data/synthetic/v1; refuses OUT outside data/ or the temp dir
make audit                     # runs leakage + factory audit, prints STEP lines, non-zero if either fails
make test                      # 0 skips expected in data_factory/tests
python3 -m pytest -q -rs data_factory/tests -k "near_miss or news or single_token or minimal_pairs or arrival or duration or balance or not_evaluable or escalates or pregnancy or out_path or make_audit"
make data OUT=../escape        # must exit non-zero and create or delete nothing
```

## Decisions needed (none blocking the build)

- **D1 (extended):** clinical expert review. Until it is recorded, all labels stay synthetic reference labels. Items:
  - NEWS 2012 versus NEWS2;
  - the 5 text near-miss families, including `TNM-DEFICIT-CHRONIC`;
  - the negative-context `ทันที`, `ที่สุด` and `หายใจ` templates;
  - the pregnancy exclusion list;
  - a pregnancy-contraindication issue type.
- **D3:** move `journey.json` from `inputs/` to `audit/` in a later slice.
- **D4:** a red flag with a missing chief complaint gives `escalate` and `NOT_EVALUABLE`. It is now exercised by ≥3 cases. Owner confirmation is needed only if the evaluation slices want a different convention.
