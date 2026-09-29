# Simulated-user evaluation (synthetic) — not human usability, not clinical performance

Evaluation `simuser-g2-0002` - generated 2026-09-29T10:25:49Z. Manifest: `simuser-g2-0002` (status FROZEN).

## Setup

- Arms: A = multi-system (4 tools, one per snapshot source); B = single-case consolidated view (MedX case-page schema) (4 tools, one screen each, overview summary slots summary_vitals, summary_allergy, summary_meds, summary_labs; an adapter, not a MedX app run). One formatter renders every item in both arms. Same model, temperature, prompts, task.
- Model ids reported by the endpoint: gpt-6-luna; requested `gpt-6-luna`; tool mode `json`; temperature None.
- Dataset `/Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/data/synthetic/g2-heldout-20260930` split `test` decision point T2; 40 cases (every gold-red-flag case, then seeded random fill; seed 20260930), personas nurse, physician, pharmacist, k=4.
- Trials planned 960, run 960, complete A/B pairs analysed 480, excluded 0. Budget 0.5109 of 3.00 USD.
- Failed trials (invalid answer, turn cap, provider error) stay in the denominators: 14 of 960 not answered.
- Unit of analysis and bootstrap cluster: case (synthetic patient). Percentile 95% CI, 2000 resamples; A-B is the paired difference (same case draws). Negative A-B on success metrics / positive on effort metrics favours B.

## Results

| Metric | A n/d or mean | B n/d or mean | A-B [95% CI] |
|---|---|---|---|
| task_success | 379/480 = 0.790 [0.735, 0.842] | 402/480 = 0.838 [0.783, 0.887] | -0.048 [-0.104, 0.010] |
| field_vitals_trend | 395/480 = 0.823 [0.773, 0.871] | 433/480 = 0.902 [0.860, 0.942] | -0.079 [-0.127, -0.029] |
| field_current_meds | 437/480 = 0.910 [0.883, 0.938] | 476/480 = 0.992 [0.983, 0.998] | -0.081 [-0.110, -0.052] |
| field_medication_issues | 440/480 = 0.917 [0.883, 0.948] | 474/480 = 0.988 [0.973, 0.998] | -0.071 [-0.098, -0.042] |
| field_red_flags | 432/480 = 0.900 [0.867, 0.931] | 448/480 = 0.933 [0.881, 0.975] | -0.033 [-0.071, 0.006] |
| field_escalate | 439/480 = 0.915 [0.885, 0.940] | 460/480 = 0.958 [0.917, 0.990] | -0.044 [-0.073, -0.010] |
| field_missing_info (exploratory, not in task success) | 396/480 = 0.825 [0.746, 0.898] | 441/480 = 0.919 [0.840, 0.992] | -0.094 [-0.123, -0.065] |
| answer_valid | 467/480 = 0.973 [0.960, 0.985] | 479/480 = 0.998 [0.994, 1.000] | -0.025 [-0.040, -0.012] |
| no_answer | 13/480 = 0.027 [0.015, 0.040] | 1/480 = 0.002 [0.000, 0.006] | 0.025 [0.012, 0.040] |
| critical_miss_redflag | 42/312 = 0.135 [0.096, 0.177] | 32/312 = 0.103 [0.042, 0.178] | 0.032 [-0.025, 0.087] |
| critical_miss_med | 31/252 = 0.123 [0.079, 0.167] | 3/252 = 0.012 [0.000, 0.027] | 0.111 [0.064, 0.156] |
| critical_miss_any | 57/420 = 0.136 [0.098, 0.174] | 33/420 = 0.079 [0.032, 0.138] | 0.057 [0.005, 0.106] |
| tool_calls | mean 2.681 [2.600, 2.763] | mean 3.956 [3.921, 3.987] | -1.275 [-1.367, -1.181] |
| systems_opened | mean 2.681 [2.600, 2.763] | mean 0.990 [0.981, 0.998] | 1.692 [1.610, 1.775] |
| distinct_tools | mean 2.681 [2.600, 2.763] | mean 3.956 [3.921, 3.987] | -1.275 [-1.367, -1.181] |
| repeated_opens | mean 0.000 [0.000, 0.000] | mean 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| turns | mean 3.681 [3.600, 3.763] | mean 4.956 [4.921, 4.987] | -1.275 [-1.367, -1.181] |
| tokens | mean 10271.221 [10033.348, 10510.026] | mean 15410.996 [15133.885, 15655.463] | -5139.775 [-5446.274, -4828.866] |
| input_tokens | mean 9378.908 [9147.003, 9617.498] | mean 14810.606 [14534.837, 15055.015] | -5431.698 [-5753.612, -5115.480] |
| wall_s | mean 13.402 [13.015, 13.788] | mean 10.106 [9.744, 10.494] | 3.296 [2.766, 3.862] |
| cost_usd | mean 0.001 [0.001, 0.001] | mean 0.000 [0.000, 0.001] | 0.000 [0.000, 0.000] |
| calls_per_success (secondary) | 1287/379 = 3.396 [3.209, 3.630] | 1899/402 = 4.724 [4.464, 5.024] | -1.328 [-1.584, -1.094] |
| calls_within_success (secondary) | 1137/379 = 3.000 [3.000, 3.000] | 1607/402 = 3.998 [3.992, 4.000] | -0.998 [-1.000, -0.992] |
| pass_hat_4 | 56/120 = 0.467 [0.358, 0.567] | 68/120 = 0.567 [0.441, 0.692] | -0.100 [-0.233, 0.050] |

## Predeclared reading

Assumption support: **NOT SUPPORTED** - failed: b_fewer_tool_calls
Criteria (all required): (a) lower 95% bound of task_success B-A >= -0.10; (b) lower 95% bound of tool_calls A-B > 0; (c) critical-miss rate B <= A (point estimate). Observed: (a) -0.010, (b) -1.367, (c) A/B [0.1357142857142857, 0.07857142857142857]. pass^k per arm is in the table (pass_hat_k).
This reading is about simulated users only.

## Protocol changes before freeze (dev only)

- missing_info removed from task success and critical misses; reported as an exploratory field (field_missing_info). Reason: gold `required_inputs_missing` reflects the structured record (e.g. chief_complaint MISSING because voice extraction failed) while the simulator reads the transcript where the complaint is stated, so the label is construct-invalid for a transcript reader. Task success = the other five fields.
- Tool mode json and max_tokens 2500 (gpt-6-luna rejects native tools; hidden reasoning needs headroom). Client sends max_completion_tokens and omits temperature by default; a 400 naming an unsupported parameter is fixed and the same call retried inside the trial (params actually sent are in results.json protocol.params_sent).
- Closed vocabularies for missing_info codes, vitals_trend labels and red-flag ids/phrases, identical in both arms.


## Arm B: V2 UI screen to tool mapping (single-case consolidated view, MedX case-page schema; adapter, not a MedX app run)

| V2 web UI (file:line) | Tool | What the tool returns |
|---|---|---|
| web/components/clinical/WorkQueue.tsx:29,53 (queue API) | removed in g2-0002 | arm A has no equivalent and the case id is in the task prompt; g2-0001 exposed get_queue in B only |
| web/components/clinical/CaseWorkspace.tsx:189-215 (case header: case id, name, sex, age, HN, stage, owner, next task); :34-42 (tabs) | get_case_overview | the header fields + intake status + tab list (paths at g2-0001 freeze; header unchanged) |
| CaseWorkspace.tsx @ factory/u6 059552c :366-391 (Overview renders CaseSummary first), :440-605 (CaseSummary) | get_case_overview `summary` | one slot per tile, built from the snapshot: summary_vitals (:450-502: latest value of hr, rr, sbp, dbp, spo2, temp_c, consciousness, on_oxygen; per-vital direction vs previous reading; observed time; missing shown as missing), summary_allergy (:514-535: list / none recorded / unknown), summary_meds (:536-565: one line per medication source with recorded_value and label), summary_labs (:566-603: abnormal labs / none abnormal / none yet, unclassified when no reference range) |
| :424-429 vitalDirection, :431-437 labFlag | build_overview_summary | vital_direction and lab_flag are line-for-line mirrors of these rules (recorded numbers only, no thresholds, no clinical label) |
| :237 (red-flag banner), :557-559 (open discrepancy count), :503-513 (summary-complaint: chief complaint, onset), :382 (authored case summary text) | NOT reproduced (disclosed decisions) | banner and discrepancy count are engine outputs (consolidation only; the real UI shows them, so B under-represents it there); chief complaint/onset exist only in the intake transcript, so the model must open intake (under-represents B, conservative); the authored summary text is not computed for dataset cases |
| CaseWorkspace.tsx:251,374-403 (Intake tab), :81-87 (tab data fetched only on open) | get_intake | intake record incl. the conversation turns (assumption: the UI intake tab shows only extracted fields; the adapter exposes the transcript so the same facts are reachable as in A) |
| CaseWorkspace.tsx:284,459-517 (Medications tab: one card per source with recorded_value, captured_at) | get_medications | one source per list with a recorded_value string (drug, dose, frequency, ATC) and captured_at; the discrepancy card (:475-513) is not reproduced |
| CaseWorkspace.tsx:285,518-549 (Timeline tab: title, detail text, actor, time, version) | get_timeline | one event per record; detail text carries vitals, labs, allergy and registration facts (the V2 UI has no separate vitals/labs/allergy screen; assumption: they appear as timeline detail text) |


## Limitations

- Simulated users are one LLM role-playing personas; behaviour is not human behaviour. No usability, satisfaction, learning or clinical-outcome claim is supported.
- Gold is synthetic reference labels from predeclared rules (not expert-reviewed, not clinical ground truth); vitals_trend and current_meds references are derived by the stated rules.
- Arm B (single-case consolidated view) is a schema-faithful adapter of the MedX case-page routes populated from the snapshot, not a MedX app run and not the shipped demo router (which serves one hard-coded case). System-computed red-flag/discrepancy hints are excluded, so B measures consolidation only.
- Arm A contains only sources that exist in the snapshot (opd note, labs, medications, vitals); every fact is reachable in both arms. Labs are not required by any answer field.
- Small number of cases and one model: intervals are wide; treat as hypothesis-generating support for the Gate 2 assumption, not a test of it.
- calls_per_success / calls_within_success are predeclared secondary metrics, not part of the reading. The B overview summary (mirroring the u6 Overview tiles) lists the medication sources and shows per-vital direction vs the previous reading, which are close to the current_meds and vitals_trend fields; read B's effort gain together with task success and per-field results and do not attribute it to consolidation alone. Disclosed decisions: the real V2 Overview also shows a red-flag banner and an open-discrepancy count (engine outputs, not reproduced: consolidation only) and chief complaint/onset (only in the transcript, not reproduced: under-represents B, conservative).
- Model-version drift, provider nondeterminism and endpoint quirks (see transcripts) can change results between runs; the request settings are recorded.
- No endpoint adaptations were needed.
