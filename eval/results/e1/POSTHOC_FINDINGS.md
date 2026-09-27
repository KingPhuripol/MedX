Post-hoc findings - computed after the frozen run from stored predictions; not part of the predeclared evaluation

# E1 post-hoc findings (slice e1r)

> **System Evaluation on synthetic data - not clinical performance**
> **Research prototype - not for clinical use**

Disclosure only: computed after the frozen e1 run from stored, hash-pinned outputs. No metric, verdict, manifest, adapter or ledger line is changed; nothing is re-run; the test split is analysed from stored outputs only.

Evaluation IDs: e1-voice-dev-v1, e1-triage-dev-v1, e1-voice-test-v1, e1-triage-test-v1.

## C-E1-1: CC assertions hidden by exclusion; the SYNE-0196 trace

The frozen voice_cc_precision excludes cases whose gold chief complaint is UNMAPPABLE to the S3 vocabulary. S3 still asserted a KNOWN chief complaint in 3 such cases (dev+test); each assertion is wrong by definition (the mapping forbids e.g. RF-FAST -> fatigue), so the frozen 1.0 hides them.

All-assertion CC precision = correct KNOWN CC assertions / all KNOWN CC assertions over every case of the split. Clopper-Pearson 95% (eval.exact) assumes independent cases; cases of one patient are not independent. It is shown beside the frozen value and never replaces it.

SYNE-0196 classification: BOTH. S3_DEFECT: after the nurse-attention handoff the agent emits no further field-bearing turn (the handoff turn has field None and is not repeated), so last_asked stays chief_complaint for the rest of the session; the CC gate then admits every later patient turn as a chief-complaint answer, and the latest CC fact replaces the earlier one. The allergy answer at turn 9 names a joint-pain drug class (ยาแก้ปวดข้อ), matches the joint_pain pattern, and replaces the turn-1 CC. This path does not depend on the replay: any session that continues after a handoff reaches it. REPLAY_ARTIFACT: the recorded interview is nurse-led; S3 does not track the nurse's questions, so its field context differs from agent-led live use (a documented replay deviation in e1_mapping_v1). Both parts contributed; the case stays an open HIGH defect (DEF-E1R-001), not fixed and not artifact-only.

Why the stored CC is not from turn 1: turn 1 did yield a KNOWN chief complaint - fatigue, from the word อ่อนแรง (one-sided arm weakness read as a fatigue word; S3 has no focal-deficit code) - but it was superseded at turn 9 by joint_pain (instrumented replay). The stored output keeps only the final fact per field, so only the turn-9 span is visible. Even the turn-1 value would have been wrong for scoring: the gold CC is UNMAPPABLE to S3.

Correction to the e1r spec premise: the spec says turn 1 yielded no CC and the e1 replay has 0 agent turns. The instrumented replay shows 3 agent turns emitted by S3's own policy (ask and reask of chief_complaint, then the handoff) and a turn-1 CC that was later superseded. The two cited code lines are still the mechanism: last_asked is derived only from agent turns and stays chief_complaint, which is exactly what the CC gate admits.

### KNOWN CC assertions excluded from frozen scoring (gold CC UNMAPPABLE)

> **System Evaluation on synthetic data - not clinical performance**

| Split | Case | S3 CC | Value text | Span turn | Gold CC code | Gold CC text |
|---|---|---|---|---|---|---|
| dev | SYNE-0012 | fatigue | อ่อนแรง | 1 | CC-TNM-DEFICIT-1 | หน้าเบี้ยวและพูดไม่ชัด แขนอ่อนแรงข้างเดียวมาตั้งแต่เป็นอัมพฤกษ์ อาการเท่าเดิม มาตรวจตามนัด |
| dev | SYNE-0196 | joint_pain | ปวดข้อ | 9 | CC-RF-FAST-2 | จู่ ๆ ก็ปากเบี้ยวและแขนอ่อนแรงข้างเดียว |
| test | SYNE-0031 | fatigue | อ่อนแรง | 1 | CC-TNM-DEFICIT-2 | ปากเบี้ยวและพูดลำบาก แขนขาอ่อนแรงซีกเดียวหลังเป็นอัมพฤกษ์ อาการเท่าเดิม มาตรวจตามนัด |

### CC precision: frozen (scored population) vs all KNOWN assertions

> **System Evaluation on synthetic data - not clinical performance**

| Split | Frozen x/n | Frozen point | All-KNOWN x/n | All-KNOWN point | All-KNOWN CP 95% | Cases / patients |
|---|---|---|---|---|---|---|
| dev | 24/24 | 1.0000 | 24/26 | 0.9231 | [0.7487, 0.9905] | 40 / 36 |
| test | 19/19 | 1.0000 | 19/20 | 0.9500 | [0.7513, 0.9987] | 40 / 36 |

### SYNE-0196 (dev) trace from stored outputs and gold

> **System Evaluation on synthetic data - not clinical performance**

| Item | Value |
|---|---|
| Turn 1 (gold CC text; replay-checked) | จู่ ๆ ก็ปากเบี้ยวและแขนอ่อนแรงข้างเดียว (CC-RF-FAST-2; sudden facial droop and one-sided arm weakness) |
| S3 chief_complaint (stored) | KNOWN joint_pain from turn 9: แพ้ยาแก้ปวดข้อกลุ่มเอ็นเสดค่ะ |
| S3 allergy_status (stored) | KNOWN present from turn 9 |
| S3 handoff_reason (stored) | nurse_attention_phrase |
| Instrumented replay: CC facts | turn 1 fatigue (อ่อนแรง) superseded; turn 9 joint_pain (ปวดข้อ) final |
| Instrumented replay: agent turns | ask.chief_complaint (field chief_complaint); reask.chief_complaint (field chief_complaint); handoff.nurse_attention_phrase (field None) |
| S4 at T1 (stored) | cc_symptom joint_pain; department suggested top3 [ORTHO, MED]; alerts 0; RF-STROKE not_evaluable True |
| Gold at T1 | red flags RF-FAST; target 12; expected escalate |
| S4 at T2 (stored) | cc_symptom joint_pain; department suggested top3 [ORTHO, MED]; alerts 0; RF-STROKE not_evaluable True |
| Gold at T2 | red flags RF-FAST; target 12; expected escalate |

### SYNE-0196 code citations (file:line at the run commit)

> **System Evaluation on synthetic data - not clinical performance**

| Citation | Code |
|---|---|
| backend/app/voice/mock_rules.py:194 @ 8943cd1 (CC rule) | def _chief_complaint(text: str, tid: str, asked: str \| None) -> list[dict]: |
| backend/app/voice/mock_rules.py:195 @ 8943cd1 (CC gate) | if asked not in (None, "chief_complaint"): |
| backend/app/voice/service.py:401 @ 8943cd1 (last_asked from agent turns only) | last_asked = next((t["field"] for t in reversed(turns) if t["speaker"] == "agent" and t["field"]), None) |
| backend/app/voice/service.py:158 @ 8943cd1 (handoff on attention) | return handoff("nurse_attention_phrase", missing_fields(statuses)) |
| backend/app/voice/policy.py:47 @ 8943cd1 (handoff turn has no field) | action="handoff", field=None, utterance_id=uid, utterance_th=utterance(uid), reason=reason,  # type: ignore[arg-type] |
| backend/app/voice/service.py:180 @ 8943cd1 (no further agent turn after handoff) | if action.action == "handoff" and last_agent is not None and last_agent["utterance_id"] == action.utterance_id: |
| backend/app/voice/service.py:119 @ 8943cd1 (latest fact per field wins) | def latest_by_field(facts: list[IntakeFact]) -> dict[str, IntakeFact]: |
| backend/app/voice/mock_rules.py:63 @ 8943cd1 (fatigue pattern includes the turn-1 word) | ("fatigue", ("อ่อนเพลีย", "อ่อนแรง", "เพลีย")), |
| backend/app/voice/mock_rules.py:61 @ 8943cd1 (joint_pain pattern matches the allergy answer) | ("joint_pain", ("ปวดเข่า", "ปวดข้อ", "ข้อบวม")), |
| backend/app/voice/policy.py:17 @ 8943cd1 (nurse-attention phrase) | "ถ่ายเป็นเลือด", "อยากตาย", "ฆ่าตัวตาย", "ทำร้ายตัวเอง", "ปากเบี้ยว", "แขนขาอ่อนแรง", |

## C-E1-2: text red flags; silent escalations

Frozen rf_text_t1_recall (quoted, no threshold): dev 0/8, test 0/6.

The zero is by construction: each of the 4 text rules needs at least one of its symptom fact kinds (three-valued logic: a missing symptom leaves the rule not_evaluable, never fired), and 0 T1 decision points (dev+test) carry any of them, because S3 records no onset, acuity or exposure and the e1 mapping gives S4 no acuity-qualified symptom.

Symptom fact kinds present at T1 in stored S4 inputs (dev+test): symptom.abdominal_pain, symptom.dizziness, symptom.dyspnea, symptom.dysuria, symptom.fever, symptom.headache, symptom.joint_pain, symptom.sore_throat.

Follow-up recommendation (I2): add onset/acuity/exposure capture and a symptom extractor to S3 (DEF-E1R-002) and an aggregate-NEWS rule to S4 (DEF-E1R-003), then re-evaluate under new, separately frozen manifests (v2) with disclosure that the v1 test split was already consumed.

Silent escalations: rule = gold expected_action escalate AND system department status suggested AND 0 alerts. Dev 8, test 5 decision points. A nurse could read these as routine: a department suggestion with no alert.

### Frozen rf_text_t1_recall (quoted from results.json)

> **System Evaluation on synthetic data - not clinical performance**

| Split | x/n | Point | CP 95% |
|---|---|---|---|
| dev | 0/8 | 0.0000 | [0.0000, 0.3694] |
| test | 0/6 | 0.0000 | [0.0000, 0.4593] |

### S4 text rules: required fact kinds and T1 decision points carrying them

> **System Evaluation on synthetic data - not clinical performance**

| S4 rule | Symptom fact kinds in the rule condition | Rule citation | Dev T1 DPs | Test T1 DPs | Total | By construction |
|---|---|---|---|---|---|---|
| RF-CHEST | symptom.acute_chest_pain | backend/app/triage/rules/redflag_rules_v1.json:75 @ 8943cd1 | 0 | 0 | 0/80 | yes |
| RF-STROKE | symptom.sudden_facial_droop, symptom.sudden_limb_weakness, symptom.sudden_speech_disturbance, symptom.sudden_vision_disturbance | backend/app/triage/rules/redflag_rules_v1.json:84 @ 8943cd1 | 0 | 0 | 0/80 | yes |
| RF-THUNDER | symptom.thunderclap_headache | backend/app/triage/rules/redflag_rules_v1.json:96 @ 8943cd1 | 0 | 0 | 0/80 | yes |
| RF-ANAPH | symptom.allergen_exposure, symptom.airway_breathing_compromise | backend/app/triage/rules/redflag_rules_v1.json:105 @ 8943cd1 | 0 | 0 | 0/80 | yes |

### Silent escalations (gold escalate, department suggested, 0 alerts)

> **System Evaluation on synthetic data - not clinical performance**

| Split | Case | DP | Gold rules | Gold target | System top3 | Alerts |
|---|---|---|---|---|---|---|
| dev | SYNE-0081 | T1 | RF-ACUTE-CHEST-PAIN | 12 | [CARD] | 0 |
| dev | SYNE-0081 | T2 | RF-ACUTE-CHEST-PAIN | 12 | [CARD] | 0 |
| dev | SYNE-0108 | T1 | RF-THUNDERCLAP | 12 | [NEURO] | 0 |
| dev | SYNE-0108 | T2 | RF-THUNDERCLAP | 12 | [NEURO] | 0 |
| dev | SYNE-0127 | T1 | RF-THUNDERCLAP | 12 | [NEURO] | 0 |
| dev | SYNE-0127 | T2 | RF-THUNDERCLAP | 12 | [NEURO] | 0 |
| dev | SYNE-0196 | T1 | RF-FAST | 12 | [ORTHO, MED] | 0 |
| dev | SYNE-0196 | T2 | RF-FAST | 12 | [ORTHO, MED] | 0 |
| test | SYNE-0039 | T2 | RF-NEWS-AGG5 | 12 | [MED] | 0 |
| test | SYNE-0101 | T1 | RF-NEWS-AGG5 | 12 | [MED] | 0 |
| test | SYNE-0101 | T2 | RF-NEWS-AGG5 | 12 | [MED] | 0 |
| test | SYNE-0187 | T1 | RF-ACUTE-CHEST-PAIN | 12 | [CARD] | 0 |
| test | SYNE-0187 | T2 | RF-ACUTE-CHEST-PAIN | 12 | [CARD] | 0 |

## C-E1-3: degenerate F1; CC coverage

A frozen F1 row is listed when its bootstrap interval has zero width (ci_low == ci_high) or it has no errors at all (x == n, i.e. fp = fn = 0). Such an interval carries no uncertainty information; the precision and recall Clopper-Pearson bounds (eval.exact, independent cases assumed) are shown beside it. The frozen values and verdicts are unchanged.

The voice_cc_f1 verdict is computed on the scored CC population only; the cases with an UNMAPPABLE gold chief complaint are excluded (counted), so the verdict covers part of each split.

### Degenerate frozen F1 rows with P and R Clopper-Pearson bounds

> **System Evaluation on synthetic data - not clinical performance**

| Split | Metric | Point | Bootstrap CI | Why listed | tp/fp/fn | Precision x/n CP 95% | Recall x/n CP 95% |
|---|---|---|---|---|---|---|---|
| dev | voice_dur_f1 | 1.0000 | [1.0000, 1.0000] | ci_low == ci_high; x == n | 36/0/0 | 36/36 [0.9026, 1.0000] | 36/36 [0.9026, 1.0000] |
| dev | voice_allergy_f1 | 1.0000 | [1.0000, 1.0000] | ci_low == ci_high; x == n | 36/0/0 | 36/36 [0.9026, 1.0000] | 36/36 [0.9026, 1.0000] |
| test | voice_dur_f1 | 1.0000 | [1.0000, 1.0000] | ci_low == ci_high; x == n | 36/0/0 | 36/36 [0.9026, 1.0000] | 36/36 [0.9026, 1.0000] |
| test | voice_allergy_f1 | 1.0000 | [1.0000, 1.0000] | ci_low == ci_high; x == n | 36/0/0 | 36/36 [0.9026, 1.0000] | 36/36 [0.9026, 1.0000] |

### voice_cc_f1 verdict beside CC scored coverage

> **System Evaluation on synthetic data - not clinical performance**

| Split | voice_cc_f1 | Verdict | Scored/total cases | Excluded (UNMAPPABLE) |
|---|---|---|---|---|
| dev | 0.9796 | PASS | 27/40 | 13 |
| test | 0.9268 | PASS | 24/40 | 16 |

## C2: what the Voice rows measure

The e1 Voice Agent rows measure a text-transcript replay through the S3 mock rules voice-mock-rules-0.3.0. There is no ASR and no audio. The latency and total-time metrics of Table 3.2 are not measured. The rows are key-field extraction on synthetic text only.

### Scope of the e1 Voice Agent rows

> **System Evaluation on synthetic data - not clinical performance**

| Aspect | e1 status |
|---|---|
| Input | T1 IntakeTranscript text, replayed turn by turn (text transcript, not speech) |
| Extractor | S3 mock rules voice-mock-rules-0.3.0 (backend/app/voice/mock_rules.py:16 @ 8943cd1) |
| ASR / audio | none: no speech recognition and no audio in e1 |
| Table 3.2 response latency | not measured |
| Table 3.2 total time | not measured |
| Table 3.2 form-filling comparator | not measured |

## C3: version and code bindings

Product code (backend/app/voice, backend/app/triage) is not hash-bound in the e1 manifests: the e1-hashes bindings cover the dataset tree, splits, mapping and eval/adapters only. The binding to product code is by git: the trees below are identical at the freeze (e5fcd78) and the test run (8943cd1), and git diff e5fcd78 8943cd1 -- backend is empty.

### Version and code bindings

> **System Evaluation on synthetic data - not clinical performance**

| Item | Frozen / recorded | Re-derived | Check |
|---|---|---|---|
| manifest_sha256 e1-voice-dev-v1 | 7e49c310063bdc45c6c93b9438fd80400308a43ff8c28ac7d4801e4077195542 | 7e49c310063bdc45c6c93b9438fd80400308a43ff8c28ac7d4801e4077195542 | match |
| manifest_sha256 e1-triage-dev-v1 | 46fc5399852102a27281179fe7a5c16ab0d0e4e2050449e8b391320704ecfc0e | 46fc5399852102a27281179fe7a5c16ab0d0e4e2050449e8b391320704ecfc0e | match |
| manifest_sha256 e1-voice-test-v1 | 460389615be2190180e37c30b6bd1a593c380c40153e31814a54e97358b387b0 | 460389615be2190180e37c30b6bd1a593c380c40153e31814a54e97358b387b0 | match |
| manifest_sha256 e1-triage-test-v1 | d9be1b73ce9c4b863a9c5a9f23bebc13fa8e8e349359e510918d1639f138f691 | d9be1b73ce9c4b863a9c5a9f23bebc13fa8e8e349359e510918d1639f138f691 | match |
| freeze entry_hash e1-voice-dev-v1 | 201dc5dbf08ca1ad23aac2682dd9640536689714b3ef9645860312d4a44c5856 | frozen.jsonl | - |
| freeze entry_hash e1-triage-dev-v1 | e6aa3b6b4aaf569cd7879e957c2ea4bdf0dc9f2cc317ddeee73d797605e35ae7 | frozen.jsonl | - |
| freeze entry_hash e1-voice-test-v1 | 97cbdee3bbbec4c07b9310024015b2fccd52ab67964607a9fb0a36eb59abc818 | frozen.jsonl | - |
| freeze entry_hash e1-triage-test-v1 | c884b4178599bb283189140a1ffdd2209a1ce4c7cdb65197f8e81168b22dac5a | frozen.jsonl | - |
| run entry_hash e1-voice-dev-v1 | 6971925bb2bccfc3e3a8e74c45583bdc2e4686ac7d10de514e24a64ddaa06a3f | runs.jsonl | - |
| run entry_hash e1-triage-dev-v1 | 2570c551f0a0454b072bd9544260acda9b45247745c8f3ad72254abf3199ccf9 | runs.jsonl | - |
| run entry_hash e1-voice-test-v1 | cec00327a93a4ba71e0e665c7645239319238d1f2717a386e4643e9662d9c97a | runs.jsonl | - |
| run entry_hash e1-triage-test-v1 | 7d642633a367cbb0c2a3514985ea4a89fd177241eea3545ab22a132169c9d14f | runs.jsonl | - |
| adapters_sha256 | 9c07252fbb62dea212a36fe0bbc7432ad3b0eb72128ced80c26f223720fffe27 | 9c07252fbb62dea212a36fe0bbc7432ad3b0eb72128ced80c26f223720fffe27 | match |
| mapping_sha256 | 7748c53b041870a56b815d0f815456bd571422adb4b70d32b59610cc19d68787 | 7748c53b041870a56b815d0f815456bd571422adb4b70d32b59610cc19d68787 | match |
| dataset_tree_sha256 | e76e38cc67d6317d82196f105cb9781bedf3451b9ba74a1585b19662d4d1162b | e76e38cc67d6317d82196f105cb9781bedf3451b9ba74a1585b19662d4d1162b | match |
| split_sha256 | fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9 | fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9 | match |
| ruleset_version (stored S4 outputs) | rf-1.1.0 | backend/app/triage/rules/redflag_rules_v1.json @ 8943cd1: rf-1.1.0 | match |
| department model_version (stored S4 outputs) | mock-0.1.0+baseline-kw-1.0.0, null (abstained before any model call) | - | - |
| S3 extractor version | voice-mock-rules-0.3.0 | backend/app/voice/mock_rules.py @ 8943cd1 | - |
| commit (freeze) | e5fcd78 | e5fcd788e7bfa842ff518db3819465f2e1449f4b eval(ledger): freeze e1-voice-dev-v1 e1-voice-test-v1 e1-triage-dev-v1 e1-triage-test-v1 | - |
| commit (run dev) | 0a9f94e | 0a9f94e752cff135cd452eb9233a6992db4be380 eval(ledger): run e1-voice-dev-v1 e1-triage-dev-v1 | - |
| commit (run test) | 8943cd1 | 8943cd11ff2e4ca63b45508102840b6538ec2bff eval(ledger): run e1-voice-test-v1 e1-triage-test-v1 | - |
| git tree backend/app/voice @ e5fcd78 | 0fa4f82b515511c025c54487e7b2c7cdf5d2838b | @ 8943cd1: 0fa4f82b515511c025c54487e7b2c7cdf5d2838b | match |
| git tree backend/app/triage @ e5fcd78 | 286b87264a00aa0d266c5d808f81405328a26dbe | @ 8943cd1: 286b87264a00aa0d266c5d808f81405328a26dbe | match |
| git diff e5fcd78 8943cd1 -- backend | empty | - | - |
| product code hash-bound in manifests | no | e1-hashes keys: adapters_sha256, always_answer_fallback, dataset_tree_sha256, generator_version, mapping_sha256, s_star, split_sha256 | - |

### Stored inputs and their pins

> **System Evaluation on synthetic data - not clinical performance**

| File | sha256 | Pinned by | Check |
|---|---|---|---|
| eval/results/e1/dev/voice/predictions.jsonl | a7c9dacf3da70f0a7a53ac344658c66045dfae6e4213715e005cd492cdef4335 | runs.jsonl e1-voice-dev-v1 predictions_sha256 | match |
| eval/results/e1/dev/voice/results.json | 270144175ec38eab176c861db8226b761c2de60ef299e34975c9abf03b123496 | runs.jsonl e1-voice-dev-v1 results_sha256 | match |
| eval/results/e1/dev/triage/predictions.jsonl | 7b388fc08c81112c040c815cff7345266d03da8ee46c8b90d63c3349f5e9b1b9 | runs.jsonl e1-triage-dev-v1 predictions_sha256 | match |
| eval/results/e1/dev/triage/results.json | c73b32052e64802973e534eb29e0486e0c520dab3f34ee3d14c1f614e2e53351 | runs.jsonl e1-triage-dev-v1 results_sha256 | match |
| eval/results/e1/test/voice/predictions.jsonl | ed5e514eebdb5d3c8ea30c5f71db6323df7787c43dca1857d2640fd5dbb8864e | runs.jsonl e1-voice-test-v1 predictions_sha256 | match |
| eval/results/e1/test/voice/results.json | c37ed706af72ee73a4896140ee4c68af4459580b2739fc39e3df273942a23bcf | runs.jsonl e1-voice-test-v1 results_sha256 | match |
| eval/results/e1/test/triage/predictions.jsonl | 6c66d654a5beb666e06c0b9339407ac35c7dda6f6ba79803b4be2fdb200a6207 | runs.jsonl e1-triage-test-v1 predictions_sha256 | match |
| eval/results/e1/test/triage/results.json | 4bb66650b216ac51e091cb912e8e6d215f5c2929a2371bc08a42869054583440 | runs.jsonl e1-triage-test-v1 results_sha256 | match |
| eval/results/e1/dev/system_outputs.jsonl | 87d41144062b599d06bbf4d69267792055d183f46cfa645690bc0bbc576daa44 | git blob at 8943cd1 (not pinned in runs.jsonl) | match |
| eval/results/e1/test/system_outputs.jsonl | d162f5e16035fb41e539d07db5ce550415ea03606bf48522a025396495959a4a | git blob at 8943cd1 (not pinned in runs.jsonl) | match |

## C5: dept 12 vs NOT_EVALUABLE

Mapping rules (e1_mapping_v1, frozen): gold department 12 (emergency) -> red-flag metrics, because S4 routes urgency through alerts; NOT_EVALUABLE (chief complaint missing) -> abstention metrics only.

Dept-12 decision points: dev 22, test 21; gold-escalate among them: dev 22, test 21.

The 3 decision points below are both NOT_EVALUABLE and gold red-flag-positive. 3 of 3 count as correct abstentions in abst_rate_not_evaluable; 2 of them are missed in rf_case_recall (dev SYNE-0107 T1, dev SYNE-0107 T2), while test SYNE-0053 T2 raised an alert and is detected. For safety reading, escalation takes precedence: an abstention with no alert on a red-flag-positive decision point is a miss, not a success.

Correction to the e1r spec premise: the spec says every listed decision point is missed in rf_case_recall; test SYNE-0053 T2 raised an alert (stored) and counts as detected.

### Gold department 12 decision points

> **System Evaluation on synthetic data - not clinical performance**

| Split | Dept-12 DPs | Gold escalate |
|---|---|---|
| dev | 22 | 22 |
| test | 21 | 21 |

### NOT_EVALUABLE and gold red-flag-positive decision points

> **System Evaluation on synthetic data - not clinical performance**

| Split | Case | DP | Gold rules | Gold action | System department | Correct abstention | Alerts | Missed in rf_case_recall |
|---|---|---|---|---|---|---|---|---|
| dev | SYNE-0107 | T1 | RF-NEWS-AGG5 | escalate | abstained | yes | 0 | yes |
| dev | SYNE-0107 | T2 | RF-NEWS-AGG5 | escalate | abstained | yes | 0 | yes |
| test | SYNE-0053 | T2 | RF-QSOFA | escalate | abstained | yes | 2 | no |

## Defects filed for I2

Filed for I2; not repaired in e1r. Each defect keeps its evidence and a stored-file repro.

### Defects filed for I2

> **System Evaluation on synthetic data - not clinical performance**

| ID | Severity | Target | Component | Repro | Observed | Expected |
|---|---|---|---|---|---|---|
| DEF-E1R-001 | HIGH | i2 | S3 voice: chief-complaint attribution (backend/app/voice/service.py last_asked; backend/app/voice/mock_rules.py _chief_complaint gate) | dev SYNE-0196 (eval/results/e1/dev/system_outputs.jsonl) | CC KNOWN joint_pain from turn 9 (the allergy answer) after a nurse_attention_phrase handoff; S4 cc_symptom joint_pain, top3 [ORTHO, MED], 0 alerts at T1 and T2. | No chief complaint taken from an answer to another question; a CC that cannot be expressed (focal deficit) is not coerced to a code; after a nurse-attention handoff the case is escalated, never routed to a routine department. |
| DEF-E1R-002 | HIGH | i2 | S3 voice extractor (no onset/acuity/exposure capture, no symptom extractor) and the S3->S4 fact path | dev SYNE-0196 (eval/results/e1/dev/system_outputs.jsonl) | 0 T1 decision points (dev+test) carry a fact kind required by RF-CHEST, RF-STROKE, RF-THUNDER or RF-ANAPH; rf_text_t1_recall dev 0/8, test 0/6. | Text red flags stated in the interview reach S4 as the acuity-qualified facts its rules need, so the rules are evaluable (S4-A01 recall target 1.00). |
| DEF-E1R-003 | HIGH | i2 | S4 red-flag rules (backend/app/triage/rules/redflag_rules_v1.json): no aggregate-NEWS rule | dev SYNE-0030 (eval/results/e1/dev/triage/predictions.jsonl) | RF-NEWS-AGG5 gold decision points: dev 5 (2 with any alert), test 8 (5 with any alert); no S4 rule can express an aggregate NEWS score of 5 or more. | An aggregate NEWS rule in S4 so gold RF-NEWS-AGG5 decision points can be detected. |

## Headline for the progress report

- Red-flag recall FAILS the predeclared threshold (point >= 1.00) on both splits: case-level dev 5/24 (0.2083, FAIL), test 9/22 (0.4091, FAIL); rule-level dev 0.1923 (FAIL), test 0.3103 (FAIL).
- Text red flags at T1 are missed by construction (dev 0/8, test 0/6), and 13 gold-escalate decision points (dev 8, test 5) received a department suggestion with no alert.
- The frozen CC precision of 1.0 excludes wrong assertions: over all KNOWN CC assertions it is dev 24/26 and test 19/20; dev SYNE-0196 (stroke-sign presentation) was routed to ORTHO/MED with no alert - open HIGH defect DEF-E1R-001.
- Department top-3 FAILS its threshold (>= 0.80): dev 0.5000, test 0.4082; three HIGH defects are filed for I2 (DEF-E1R-001..003).
- Claim boundary: System Evaluation of a research prototype on synthetic data with text-transcript replay through mock rules; no ASR, no audio, no clinician review, not clinical performance; these post-hoc numbers never replace a frozen value or verdict.
