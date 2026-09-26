# Slice s1r — Synthetic case factory v1.1: label validity fixes

- Owner (Gantt task 21, same as s1): สุปรียา
- Source of truth: `docs/PROPOSAL.md` (v8). This spec is a **delta** on `slices/s1/SPEC.md` (plan commit b7ac024, implementation commit 47d3a6d). Everything in the S1 spec still applies unless a row below amends it. PROPOSAL sections used: 1.3.1 (the Red-flag Node uses predeclared rules; required intake fields), 1.3.4 (simulated environment only), 2.1.4 and 3.4 (no leakage; snapshot at decision time), 3.2.2 (abstain when required data is missing), 3.6 (labels come from data not sent to the model; abstention proportion reported alongside accuracy on concluded cases).
- Status: PLAN, written by the planner. Tier 0 (CPU, synthetic, deterministic). No GPU and no external API.
- Claim boundary (unchanged): the labels are **synthetic reference labels** for **system evaluation only**. They are not clinical ground truth until the clinical expert review (D1) is recorded in `docs/DECISIONS.md`. A "no red flag" gold label means only that no rule in this registry fires. It does not mean the patient is clinically safe.

## Reviewer findings this slice fixes

| # | Severity | Finding | Fix (scope item) |
|---|---|---|---|
| F1 | HIGH | Near-miss negatives can meet an urgent criterion from the cited NEWS source. Example: SYNE-0105 has RR 22 (2 points), SBP 101 (1), fever 38.1–38.9 (1), and HR 91–110 (1), so aggregate NEWS is 5. It is still labelled no-red-flag. `test_near_miss_negatives` skips any case its own oracle flags. | 1, 2 |
| F2 | MEDIUM | Cases with a missing chief complaint carry a department label (from the hidden planned complaint) that cannot be derived from the inputs. | 3 |
| F3 | MEDIUM | Lexical shortcut: every text red flag contains `ทันที`, and no negative case does. | 4 |
| F4 | MEDIUM | Nothing says that only `snapshot_T*.json` is a valid model input. `journey.json` sits next to the snapshots. | 5 |
| F5 | LOW-MEDIUM | Pregnancy (obstetric-complaint) cases can carry ACE inhibitors or statins without any labelled issue. | 6 |
| F6 | LOW | `make data` runs `rm -rf "$(OUT)"` for any OUT path that contains a `splits.json`. | 7 |

## Scope

1. **Aggregate NEWS rule (F1).**
   - Add `RF-NEWS-AGG5` to `data_factory/templates/red_flags.json`. It fires when aggregate NEWS ≥ 5 on any single `Vitals` item. It keeps its own `rule_id`, so single-parameter-3 cases stay under `RF-NEWS-SINGLE3`.
   - Scoring follows NEWS (2012). Source: Royal College of Physicians, *National Early Warning Score (NEWS): Standardising the assessment of acute-illness severity in the NHS*, working-party report, July 2012, Chart 1 and the clinical-response section. The planner checked this against the report text on 2026-09-26. The same NEWS is the one evaluated by Smith 2013 (PMID 23295778). Bands:
     - RR: ≤8 → 3, 9–11 → 1, 12–20 → 0, 21–24 → 2, ≥25 → 3.
     - SpO2: ≤91 → 3, 92–93 → 2, 94–95 → 1, ≥96 → 0.
     - Any supplemental O2 (`on_oxygen`): yes → 2.
     - Temperature: ≤35.0 → 3, 35.1–36.0 → 1, 36.1–38.0 → 0, 38.1–39.0 → 1, ≥39.1 → 2.
     - SBP: ≤90 → 3, 91–100 → 2, 101–110 → 1, 111–219 → 0, ≥220 → 3.
     - HR: ≤40 → 3, 41–50 → 1, 51–90 → 0, 91–110 → 1, 111–130 → 2, ≥131 → 3.
     - Consciousness: A → 0; V, P or U → 3.
     - Trigger: "a medium score: NEWS aggregate score of 5 or more, or a RED score … should prompt an urgent review".
   - How the rule treats consciousness and missing values:
     - `C` (new confusion) scores 0 under NEWS 2012. It still counts toward qSOFA. Whether to move to NEWS2 is added to D1.
     - A `null` parameter contributes 0, so the computed sum is a lower bound. The rule fires if that lower bound is ≥5.
   - Registry changes:
     - Add reference `RCP-NEWS-2012` (URL of the report) to `references.json`.
     - The `vitals_bands.json` entries that cite NEWS switch to `RCP-NEWS-2012` or keep `PMID-23295778`. Both must resolve.
     - Add a red-flag variant `NEWS-AGG5` in which no parameter scores 3, qSOFA is ≤1, and the aggregate is 5–6. Example: RR 21–24, SBP 101–110, temperature 38.1–39.0, HR 91–110.
2. **Near-miss constraints and a non-skipping test (F1).**
   - A *vitals near-miss* case (gold `scenario.near_miss` set) must meet all of the following on **every** `Vitals` item in its journey, including repeat vitals:
     - all 7 NEWS inputs are non-null;
     - consciousness is `A`;
     - no parameter scores 3;
     - aggregate NEWS ≤ 4;
     - qSOFA count ≤ 1;
     - SBP ≥ 90.
   - It must also be near a threshold: at least 1 item has aggregate NEWS = 4, a parameter scoring 2, or a qSOFA criterion met exactly at its boundary (RR 22 or SBP 100). The generator must not add a fever band on top of a near-miss variant when that would take the aggregate to ≥5.
   - Add near-miss variant `NM-NEWS-AGG4` (aggregate exactly 4, no parameter scoring 3).
   - Rewrite `test_near_miss_negatives`:
     - It selects cases by gold `scenario.near_miss` / `scenario.text_near_miss`, never by filtering on its own oracle output.
     - For **each** such case and each T it asserts: the oracle returns no flags, gold `red_flags == []`, and the item-level constraints above hold.
     - It asserts `n_asserted == n_tagged`. It contains no `if … continue` or `pytest.skip` path.
   - The independent oracle (`test_oracles.py`) gains its own NEWS band table and aggregate function. They are copied from the RCP 2012 chart, not imported from the generator or read from the registry. A registry-equality test pins them.
3. **Department not evaluable when the chief complaint is missing (F2).**
   - When `required_fields.chief_complaint == "MISSING"`, every gold row sets:
     - `target_department: "NOT_EVALUABLE"`;
     - `department_evaluable: false`;
     - `department_reason: "chief_complaint_missing"`.
   - Every other row sets `department_evaluable: true`.
   - `expected_action` precedence is unchanged. A missing chief complaint without a red flag gives `abstain`. A missing chief complaint **with** a red flag still gives `escalate`: the red-flag invariant wins. The department stays `NOT_EVALUABLE` because escalation does not require a department (D4).
   - The DATACARD and the gold README text state that department accuracy is computed only over rows with `department_evaluable == true`. Those rows then enter the abstention/coverage metric (PROPOSAL 3.6).
   - Add `department_evaluable`, `department_reason` and `NOT_EVALUABLE` to the audit's banned-in-inputs gold keys.
4. **Remove the lexical shortcut (F3).**
   - **Paraphrases:**
     - Each text red-flag rule (`RF-FAST`, `RF-ACUTE-CHEST-PAIN`, `RF-THUNDERCLAP`, `RF-ANAPHYLAXIS`) gets ≥3 complaint templates in `complaints.json` (group `red_flag_text`).
     - For the three onset-dependent rules, ≥2 of the ≥3 templates express sudden onset **without** `ทันที`, for example `จู่ ๆ`, `เป็นขึ้นมาเฉียบพลัน`, or `ปวดสุดในไม่กี่วินาที`.
     - The onset-dependent rules become *concept term AND sudden-onset term within the same patient turn*. Registry lexicons hold ≥3 sudden-onset terms and ≥2 concept terms per rule.
   - **Text near-miss negatives** (new scenario `text_near_miss`, ≥20 cases, ≥5 per family). All are complaint group `general` with normal vitals (aggregate NEWS ≤2). Each template has a `source_ref` stating which criterion of the cited rule it fails to meet.
     - `TNM-CHEST-STABLE`: chest pain for weeks that is reproducible with movement or palpation. It must not mention dyspnoea or sweating. It is not acute chest pain per Gulati 2021.
     - `TNM-HEADACHE-GRADUAL`: headache that builds over days. It must not mention fever, neck stiffness, a neurological deficit or a peak at onset. It is outside the Ottawa SAH inclusion for acute headache peaking within 1 h.
     - `TNM-NUMB-BILATERAL`: bilateral finger numbness for months. It must not mention face, speech or one-sided weakness. It is not a FAST deficit.
     - `TNM-URTICARIA-ONLY`: hives with no respiratory, GI or BP terms, and no statement of exposure to a likely allergen. It fails Sampson criteria 1–3.
   - **`ทันที` in negative contexts:**
     - ≥5 text near-miss cases contain `ทันที` in an **extra, different patient turn**, with a non-symptom meaning (travel or arrival, e.g. `ลูกพามาทันทีหลังเลิกงาน`). It must never refer to symptom onset or symptom relief.
     - The same non-symptom turn appears in ≥5 ordinary non-red-flag cases, so the extra turn does not itself mark near-miss cases.
   - Nurse turns must not depend on the label (same question script for all cases).
5. **Snapshot-only model inputs (F4).**
   - `DATACARD.md` states verbatim: "Only `inputs/<split>/<case_id>/snapshot_T*.json` files are valid model inputs. `journey.json` is the full timeline, including items after every decision time, for audit only; it must never be given to a model."
   - `manifest.json` adds `"model_inputs_glob": "inputs/*/*/snapshot_T*.json"` and `"audit_only_globs": ["inputs/*/*/journey.json", "gold/**"]`. These fields are covered by the manifest hash.
   - `python -m data_factory audit` adds a named check `snapshot_items_after_T`. It fails if any snapshot item has `available_at_time > T`, or `observed_at` or `event_time > T`. It writes the offending item_ids to the report.
   - The layout is unchanged. Moving `journey.json` out of `inputs/` is deferred to D3.
6. **Pregnancy medication exclusion (F5).** This slice takes the *remove* option. It does not add a contraindication label.
   - For pregnancy cases (complaint group `obstetric`; gold `scenario.pregnant: true`), the generator draws no drug with ATC prefix `C09` (all renin–angiotensin-acting drugs, including ACE inhibitors) or `C10AA` (statins).
   - The exclusion covers the home list, the patient-reported list, the new order, duplicate partners and injected entries.
   - The rule lives in `data_factory/templates/pregnancy_exclusions.json`, each entry with a `source_ref`:
     - `DAILYMED-ENALAPRIL`: boxed warning, fetal toxicity: "When pregnancy is detected, discontinue … as soon as possible. Drugs that act directly on the renin-angiotensin system can cause injury and death to the developing fetus."
     - `FDA-DSC-STATIN-2021`: FDA Drug Safety Communication, 20 Jul 2021. It removed the pregnancy contraindication but "still advises most pregnant patients should stop taking statins".
   - A "contraindication" label would misstate the current statin labelling, which is why this slice removes the drugs.
   - Medication injection quotas (S1-A18) must still be met through substitute drugs.
7. **OUT path guard (F6).**
   - OUT is resolved with `os.path.realpath`, which follows symlinks and `..`. The resolved path must be a **strict descendant** of one of:
     - `<repo>/data/`;
     - `realpath(tempfile.gettempdir())`;
     - `realpath("/tmp")`.
   - The check runs in Python (`python -m data_factory generate`) **before any deletion**. Removing an existing dataset moves into Python (`--replace`), after the path check and the existing "is a factory dataset" check. The Makefile no longer calls `rm -rf "$(OUT)"` directly.
   - On refusal: exit code 2, a message naming the allowed roots, and no files created or deleted.
8. Bump `GENERATOR_VERSION` to `1.1.0` and regenerate. `tree_sha256` changes, which is expected. Record the new default-seed `tree_sha256` in the implementation PR description.

## Out of scope

- Everything in S1's out-of-scope list.
- NEWS2 (SpO2 scale 2; scoring new confusion as 3). This is a D1 question.
- Negation handling in general, and any NLP beyond same-turn lexicon co-occurrence.
- Other pregnancy-relevant drugs in the formulary (NSAIDs, sulfamethoxazole–trimethoprim, sulfonylureas, atenolol). These are listed for D1. They are not changed here.
- A pregnancy-contraindication issue type for the Pharma Agent.
- Moving `journey.json` out of `inputs/` (D3).
- Metric computation (evaluation slices).

## Acceptance

Default seed is 20260926. "Near-miss case" means a case with gold `scenario.near_miss` or `scenario.text_near_miss` set. "Text red flag" means one of `RF-FAST`, `RF-ACUTE-CHEST-PAIN`, `RF-THUNDERCLAP`, `RF-ANAPHYLAXIS`.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S1R-A01 | All S1 acceptance items still pass, with amended S1-A12, S1-A13, S1-A14 and S1-A11 as in S1R-A14 | S1-A01…S1-A26: 26/26 PASS at the default seed. Every S1 test name still exists and passes. | `make test`; `make audit`; `tests/e2e/s1_dataset_check.py` if present |
| S1R-A02 | Oracle recomputes aggregate NEWS from the source bands | The oracle's NEWS function matches the RCP 2012 chart on 100% of ≥30 band-boundary vectors: each band edge for RR, SpO2, temperature, SBP and HR, plus O2 and AVPU. The oracle band table equals the registry band table. It has 0 imports from `data_factory.generate`. | `test_news_score_bands`, `test_oracle_thresholds_match_registry` (extended), import scan |
| S1R-A03 | 0 near-miss cases meet any urgent criterion | Over every Vitals item of every vitals near-miss case, across all Ts: 0 with aggregate NEWS ≥5, 0 with any parameter scoring 3, 0 with qSOFA ≥2, 0 with SBP <90, 0 with consciousness ≠ A, and 0 null NEWS inputs. Over every text near-miss case: 0 oracle text-rule hits and 0 gold red flags. | `test_near_miss_negatives` |
| S1R-A04 | Near-miss test asserts on every near-miss case | `n_asserted == n_tagged` (100%). ≥20 vitals near-miss cases. 100% have ≥1 item that is near a threshold (aggregate = 4, a parameter scoring 2, or RR = 22 / SBP = 100 with qSOFA = 1). The test has 0 skip or continue paths, and `pytest -rs` reports 0 skips in `data_factory/tests`. | `test_near_miss_negatives`; pytest summary |
| S1R-A05 | The aggregate-NEWS rule is exercised and agrees 100% | `RF-NEWS-AGG5` fires in ≥5 cases, and is the only rule firing in ≥3 of them. The regression vector {RR 22, SBP 101, T 38.5, HR 95, SpO2 97, A, no O2} scores 5 and is flagged by both the generator labeller and the oracle. The oracle equals gold on 100% of case×T pairs (≥400), with 0 FP and 0 FN. | `test_red_flag_oracle_agrees`, `test_news_agg_regression_vector`, `test_red_flag_subset` |
| S1R-A06 | Text near-miss negatives exist | ≥20 text near-miss cases, and ≥5 in each of the 4 families. Each has aggregate NEWS ≤2 on every Vitals item, has 0 gold red flags, and contains a concept term of its paired rule. ≥5 contain `ทันที` in a different patient turn from the concept term. | `test_text_near_miss_negatives` |
| S1R-A07 | Paraphrased red-flag phrasing | Each of the 4 text red flags has ≥3 templates. For FAST, chest pain and thunderclap, ≥2 templates contain no `ทันที`. Each template appears in ≥1 generated case. The registry has ≥3 sudden-onset terms. | `test_red_flag_paraphrase_templates` |
| S1R-A08 | A single-token baseline cannot solve text red flags | This criterion is evaluated per case at T1. Positives are cases whose gold at T1 contains a text red flag. `contains("ทันที")` over patient turns gives recall < 0.8 **and** precision < 0.8. For every token in V, "precision ≥ 0.8 and recall ≥ 0.8" holds for 0 tokens, both for "any text red flag" and for each onset-dependent rule. V is the union of all registry lexicon terms, all near-miss template terms, and all whitespace-split tokens of patient and nurse turns. | `test_single_token_baseline_fails` (reports P/R for `ทันที` and the best token in V) |
| S1R-A09 | Missing chief complaint gives no evaluable department | 0 case×T rows with `chief_complaint == "MISSING"` have `department_evaluable == true`. 100% of those rows have `target_department == "NOT_EVALUABLE"`. 100% of those without a red flag have `abstain`; 100% with a red flag have `escalate`. 100% of other rows have `department_evaluable == true` and a code from the 10-code list. | `test_missing_cc_department_not_evaluable`, `test_expected_action_precedence` |
| S1R-A10 | Snapshot-only inputs are documented and audited | DATACARD contains the verbatim snapshot-only sentence and the department-accuracy exclusion. The manifest has `model_inputs_glob` and `audit_only_globs`. The `snapshot_items_after_T` check PASSes on the generated set. For a planted future item in one snapshot, with manifest hashes recomputed so that only this check can catch it, `make audit` exits non-zero and the report names `snapshot_items_after_T` (1/1). | `test_datacard_snapshot_only`, `test_manifest_model_inputs`, `test_audit_detects_planted[snapshot_after_T]` |
| S1R-A11 | No unlabelled RAS-acting drug or statin in pregnancy | 0 pregnancy cases carry a drug with ATC `C09*` or `C10AA*` in any list. There are ≥5 pregnancy cases with medication data. Every exclusion entry has a resolving `source_ref`. S1-A18 quotas still hold. | `test_pregnancy_no_ras_or_statin`, `test_injection_counts` |
| S1R-A12 | `make data` refuses out-of-tree OUT | Each of the 5 refusal cases exits non-zero: parent escape (`../x`); absolute outside path; a symlink under `data/` that resolves outside; `data/` itself; the repo root. After each refusal, a pre-created sentinel file survives and 0 new paths exist. `make data OUT=<repo>/build/s1r_probe` (outside `data/`, contains a fake `splits.json`) is refused and the probe survives. OUT under `data/synthetic/` and under pytest `tmp_path` still succeeds. | `test_out_path_guard[parent|absolute|symlink|data_root|repo_root]`, `test_make_data_rejects_out_of_tree`, `test_out_path_allowed` |
| S1R-A13 | `make test` and `make audit` are green | `make test` exits 0 with 0 failures and 0 skips in `data_factory/tests`. `make audit` over the default OUT exits 0 with all checks PASS, including `snapshot_items_after_T`. Generation still takes ≤30 s. | `make test`; `make data && make audit`; timed run |
| S1R-A14 | S1 items amended without being weakened | S1-A12: each of the **7** rules is used ≥5 times. S1-A13: now S1R-A03, A04 and A05. S1-A14: "every code ≥5 cases" and "red-flag → 12" apply to rows with `department_evaluable == true`. S1-A11: gold keys include `department_evaluable` and `NOT_EVALUABLE`, with 0 occurrences in `inputs/`. S1-A20: all new templates are Thai-well-formed. S1-A23: all new template records carry a resolving `source_ref`. | Existing S1 tests, updated in the same change |

## Required test cases (`data_factory/tests/`, run by `make test`)

- **New:**
  - `test_news_score_bands`
  - `test_news_agg_regression_vector`
  - `test_text_near_miss_negatives`
  - `test_red_flag_paraphrase_templates`
  - `test_single_token_baseline_fails`
  - `test_missing_cc_department_not_evaluable`
  - `test_datacard_snapshot_only`
  - `test_manifest_model_inputs`
  - `test_audit_detects_planted[snapshot_after_T]`
  - `test_pregnancy_no_ras_or_statin`
  - `test_out_path_guard[parent|absolute|symlink|data_root|repo_root]`
  - `test_make_data_rejects_out_of_tree`
  - `test_out_path_allowed`
- **Rewritten:** `test_near_miss_negatives` (selects by tag, asserts all, `n_asserted == n_tagged`).
- **Extended:**
  - `test_oracle_thresholds_match_registry`: NEWS bands, AGG5, and the text lexicons.
  - `test_red_flag_oracle_agrees`: aggregate NEWS and same-turn text logic.
  - `test_red_flag_subset`: 7 rules.
  - `test_department_labels`: evaluable rows only.
  - `test_gold_separation`: new keys.
  - `test_expected_action_precedence`
  - `test_templates_have_source_ref`: pregnancy exclusions and near-miss templates.
- **Oracle independence:** the oracles must not import `data_factory.generate`. The oracle's NEWS table and text lexicons are literal copies from the sources, pinned to the registry by an equality test.
- **Destructive-test safety:** OUT-guard tests only target probe directories that the tests create themselves. They never target `/`, `$HOME` or the repo root with a real dataset in it.

## Clinical and validity risks

| Risk | Mitigation in this slice |
|---|---|
| A "negative" case is urgent under a criterion the registry does not encode | Aggregate NEWS added (A05). Near-miss cases are constrained against every cited criterion: NEWS single and aggregate, qSOFA, and the Sampson BP threshold (A03). Remaining unencoded criteria (NEWS2 confusion, other SNOOP headache features, other anaphylaxis criteria) go to D1. Label wording stays "no registry rule fires". |
| Text near-miss scenarios are clinically questionable (e.g. stable chest pain still needs review) | Each is limited to the cited rule's non-inclusion condition and excludes co-symptoms (scope 4). They are labelled synthetic and flagged for D1. They test the detector's specificity, not clinical triage. |
| `ทันที` in a negative context reads as symptom onset or relief (e.g. relief like angina) | Negative-context `ทันที` is restricted to travel or arrival meaning (scope 4). D1 reviews the templates. |
| Silent lower-bound NEWS when vitals are missing | Near-miss cases require all 7 inputs (A03). The rule fires on the lower bound. Missingness is still never imputed as normal. |
| Department accuracy inflated or deflated by non-derivable labels | Rows marked `NOT_EVALUABLE` and excluded; stated in the DATACARD (A09, A10). |
| Model trained or evaluated on `journey.json` (future leakage) | Snapshot-only statement, manifest globs, and the audit check with planted-fault sensitivity (A10). |
| Pregnancy cases model unsafe prescribing without a label | Exclusion with cited sources (A11). Other drugs are flagged for D1. |
| `make data` deletes a user directory | realpath strict-descendant guard before any deletion, plus sentinel-survival tests (A12). |
| The paraphrase lexicon is itself a new shortcut (the oracle and the model learn the same lexicon) | The single-token scan over all input tokens (A08). The detection logic stays a registry rule, not a claim about language understanding. |

## Run commands

```bash
make data                      # SEED=20260926 OUT=data/synthetic/v1; refuses OUT outside data/ or the temp dir
make audit                     # leakage audit + schema + gold separation + identifier scan + manifest + snapshot_items_after_T
make test                      # includes data_factory/tests (0 skips expected there)
python3 -m pytest -q -rs data_factory/tests -k "near_miss or news or single_token or not_evaluable or pregnancy or out_path"
make data OUT=../escape        # must exit non-zero and create or delete nothing
```

## Decisions needed (none blocking the build)

- **D1 (extended):** Clinical expert review of these items. Until it is recorded, all labels remain synthetic reference labels.
  - NEWS 2012 versus NEWS2, including new confusion `C` scored as 3 and SpO2 scale 2.
  - The 4 text near-miss families and the negative-context `ทันที` templates.
  - The pregnancy exclusion list: whether to add NSAIDs, sulfamethoxazole–trimethoprim, sulfonylureas and atenolol.
  - Whether a pregnancy-contraindication issue type belongs in the Pharma Agent scope.
- **D3:** Move `journey.json` from `inputs/` to `audit/`. This breaks the layout and the S1 test paths, so it is deferred to a later slice.
- **D4:** For a red flag together with a missing chief complaint: `expected_action = escalate` and department `NOT_EVALUABLE`. This keeps the red-flag-first product invariant rather than the literal "abstain" in the review note. It needs owner confirmation only if the evaluation slices want a different convention.
