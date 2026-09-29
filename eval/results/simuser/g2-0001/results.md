# Simulated-user evaluation (synthetic) — not human usability, not clinical performance

Evaluation `simuser-g2-0001` - generated 2026-09-29T07:56:40Z. Manifest: `simuser-g2-0001` (status FROZEN).

## Setup

- Arms: A = multi-system (4 tools, one per snapshot source); B = single-case consolidated view (MedX case-page schema) (5 tools, one screen each; an adapter, not a MedX app run). Same model, temperature, prompts, task.
- Model ids reported by the endpoint: gpt-6-luna; requested `gpt-6-luna`; tool mode `json`; temperature None.
- Dataset `/Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/data/synthetic/g2-heldout-20260929` split `test` decision point T2; 40 cases (every gold-red-flag case, then seeded random fill; seed 20260929), personas nurse, physician, pharmacist, k=4.
- Trials planned 960, run 960, complete A/B pairs analysed 480, excluded 0. Budget 0.6111 of 3.00 USD.
- Failed trials (invalid answer, turn cap, provider error) stay in the denominators: 32 of 960 not answered.
- Unit of analysis and bootstrap cluster: case (synthetic patient). Percentile 95% CI, 2000 resamples; A-B is the paired difference (same case draws). Negative A-B on success metrics / positive on effort metrics favours B.

## Results

| Metric | A n/d or mean | B n/d or mean | A-B [95% CI] |
|---|---|---|---|
| task_success | 349/480 = 0.727 [0.665, 0.785] | 381/480 = 0.794 [0.713, 0.869] | -0.067 [-0.129, 0.008] |
| field_vitals_trend | 375/480 = 0.781 [0.719, 0.835] | 422/480 = 0.879 [0.821, 0.931] | -0.098 [-0.135, -0.058] |
| field_current_meds | 433/480 = 0.902 [0.869, 0.933] | 445/480 = 0.927 [0.854, 0.981] | -0.025 [-0.090, 0.060] |
| field_medication_issues | 445/480 = 0.927 [0.896, 0.954] | 445/480 = 0.927 [0.854, 0.981] | 0.000 [-0.062, 0.081] |
| field_red_flags | 407/480 = 0.848 [0.802, 0.894] | 440/480 = 0.917 [0.885, 0.946] | -0.069 [-0.096, -0.044] |
| field_escalate | 419/480 = 0.873 [0.831, 0.912] | 453/480 = 0.944 [0.917, 0.967] | -0.071 [-0.096, -0.044] |
| field_missing_info (exploratory, not in task success) | 401/480 = 0.835 [0.762, 0.894] | 444/480 = 0.925 [0.856, 0.975] | -0.090 [-0.119, -0.058] |
| answer_valid | 460/480 = 0.958 [0.938, 0.977] | 468/480 = 0.975 [0.958, 0.988] | -0.017 [-0.040, 0.006] |
| no_answer | 20/480 = 0.042 [0.023, 0.062] | 12/480 = 0.025 [0.013, 0.042] | 0.017 [-0.006, 0.040] |
| critical_miss_redflag | 60/312 = 0.192 [0.139, 0.247] | 31/312 = 0.099 [0.061, 0.139] | 0.093 [0.056, 0.128] |
| critical_miss_med | 25/228 = 0.110 [0.067, 0.160] | 27/228 = 0.118 [0.010, 0.278] | -0.009 [-0.177, 0.119] |
| critical_miss_any | 69/396 = 0.174 [0.127, 0.222] | 53/396 = 0.134 [0.060, 0.229] | 0.040 [-0.045, 0.107] |
| tool_calls | mean 2.629 [2.529, 2.737] | mean 4.546 [4.465, 4.619] | -1.917 [-2.008, -1.813] |
| systems_opened | mean 2.629 [2.529, 2.737] | mean 0.973 [0.956, 0.988] | 1.656 [1.560, 1.758] |
| distinct_tools | mean 2.629 [2.529, 2.737] | mean 4.546 [4.465, 4.619] | -1.917 [-2.008, -1.813] |
| repeated_opens | mean 0.000 [0.000, 0.000] | mean 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| turns | mean 3.629 [3.529, 3.737] | mean 5.546 [5.465, 5.619] | -1.917 [-2.008, -1.813] |
| tokens | mean 12223.665 [11814.322, 12650.131] | mean 22372.481 [21833.608, 22912.250] | -10148.817 [-10676.416, -9572.341] |
| input_tokens | mean 11285.975 [10872.125, 11721.974] | mean 21770.158 [21210.644, 22328.965] | -10484.183 [-11024.596, -9889.757] |
| wall_s | mean 15.218 [14.643, 15.785] | mean 11.735 [11.263, 12.274] | 3.483 [2.908, 4.064] |
| cost_usd | mean 0.001 [0.001, 0.001] | mean 0.001 [0.001, 0.001] | -0.000 [-0.000, 0.000] |
| pass_hat_4 | 42/120 = 0.350 [0.250, 0.458] | 66/120 = 0.550 [0.442, 0.667] | -0.200 [-0.300, -0.108] |

## Predeclared reading

Assumption support: **NOT SUPPORTED** - failed: b_fewer_tool_calls
Criteria (all required): (a) lower 95% bound of task_success B-A >= -0.10; (b) lower 95% bound of tool_calls A-B > 0; (c) critical-miss rate B <= A (point estimate). Observed: (a) -0.008, (b) -2.008, (c) A/B [0.17424242424242425, 0.13383838383838384]. pass^k per arm is in the table (pass_hat_k).
This reading is about simulated users only.

## Protocol changes before freeze (dev only)

- missing_info removed from task success and critical misses; reported as an exploratory field (field_missing_info). Reason: gold `required_inputs_missing` reflects the structured record (e.g. chief_complaint MISSING because voice extraction failed) while the simulator reads the transcript where the complaint is stated, so the label is construct-invalid for a transcript reader. Task success = the other five fields.
- Tool mode json and max_tokens 2500 (gpt-6-luna rejects native tools; hidden reasoning needs headroom). Client sends max_completion_tokens and omits temperature by default; a 400 naming an unsupported parameter is fixed and the same call retried inside the trial (params actually sent are in results.json protocol.params_sent).
- Closed vocabularies for missing_info codes, vitals_trend labels and red-flag ids/phrases, identical in both arms.


## Arm B: V2 UI screen to tool mapping (single-case consolidated view, MedX case-page schema; adapter, not a MedX app run)

| V2 web UI (file:line) | Tool | What the tool returns |
|---|---|---|
| web/components/clinical/WorkQueue.tsx:29,53 (queue API, row link to case) | get_queue | role tasks (task_id, case_id, kind, label, status) |
| web/components/clinical/CaseWorkspace.tsx:189-215 (case header: case id, name, sex, age, HN, stage, owner, next task); :34-42 (tabs) | get_case_overview | the header fields + intake status + tab list; nothing else is on the first-open overview |
| CaseWorkspace.tsx:216-231 (red-flag banner), :343-373 (Overview: summary, chief complaint, onset) | not reproduced | authored/system content in the demo; no engine computes it for dataset cases and it would leak gold. Chief complaint/onset are only in the transcript, so the model must open intake |
| CaseWorkspace.tsx:251,374-403 (Intake tab), :81-87 (tab data fetched only on open) | get_intake | intake record incl. the conversation turns (assumption: the UI intake tab shows only extracted fields; the adapter exposes the transcript so the same facts are reachable as in A) |
| CaseWorkspace.tsx:284,459-517 (Medications tab: one card per source with recorded_value, captured_at) | get_medications | one source per list with a recorded_value string (drug, dose, frequency, ATC) and captured_at; the discrepancy card (:475-513) is not reproduced |
| CaseWorkspace.tsx:285,518-549 (Timeline tab: title, detail text, actor, time, version) | get_timeline | one event per record; detail text carries vitals, labs, allergy and registration facts (the V2 UI has no separate vitals/labs/allergy screen; assumption: they appear as timeline detail text) |


## Limitations

- Simulated users are one LLM role-playing personas; behaviour is not human behaviour. No usability, satisfaction, learning or clinical-outcome claim is supported.
- Gold is synthetic reference labels from predeclared rules (not expert-reviewed, not clinical ground truth); vitals_trend and current_meds references are derived by the stated rules.
- Arm B (single-case consolidated view) is a schema-faithful adapter of the MedX case-page routes populated from the snapshot, not a MedX app run and not the shipped demo router (which serves one hard-coded case). System-computed red-flag/discrepancy hints are excluded, so B measures consolidation only.
- Arm A contains only sources that exist in the snapshot (opd note, labs, medications, vitals); every fact is reachable in both arms. Labs are not required by any answer field.
- Small number of cases and one model: intervals are wide; treat as hypothesis-generating support for the Gate 2 assumption, not a test of it.
- Model-version drift, provider nondeterminism and endpoint quirks (see transcripts) can change results between runs; the request settings are recorded.
- No endpoint adaptations were needed.
