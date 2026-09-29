# e1 mapping table (e1-mapping-v1)

> **System Evaluation on synthetic data - not clinical performance**

Generated from `e1_mapping_v1.json` by `python -m eval.adapters render-mapping`; do not edit by hand.

Written from code definitions (department lists, ICD-10-CM titles, rule citations) before the first e1 run; pending clinical review under decision D1. Not clinically validated. Research prototype - not for clinical use.

## Target conventions

- `UNMAPPABLE`: the target system cannot express the source; the row is excluded or counted as missed exactly as the section's scoring note says
- `(absent)`: no gold value and no fact: the item is absent, never a negative
- `(no fact)`: nothing is given to the downstream component

## S1r gold department (SIL-TH cs-chi-clinic) -> evaluation space E (`department_s1r`, 11 rows)

Scoring: Department population = DPs with department_evaluable and a target in E. 12 rows are scored by the red-flag metrics; 11 rows are excluded (counted); NOT_EVALUABLE rows enter the abstention population only.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | route | rationale | source_ref |
|---|---|---|---|---|
| 01 | E-MED | department | Internal medicine clinic; S4 MED, CARD and NEURO are internal-medicine sub-clinics, so E-MED is their common parent. | data_factory/templates/departments.json (SIL-TH-CS-CHI-CLINIC 01 อายุรกรรม); backend/app/triage/departments.py |
| 02 | E-SURG | department | Surgery clinic; S4 SURG and URO are surgical clinics (urology is a surgical specialty). | SIL-TH-CS-CHI-CLINIC 02 ศัลยกรรม; S4 URO label 'ศัลยกรรมระบบทางเดินปัสสาวะ' |
| 03 | E-OBGYN | department | Obstetrics; S4 has one combined OBGYN code. | SIL-TH-CS-CHI-CLINIC 03 สูติกรรม; S4 OBGYN 'สูติ-นรีเวชกรรม' |
| 04 | E-OBGYN | department | Gynaecology; S4 has one combined OBGYN code. | SIL-TH-CS-CHI-CLINIC 04 นรีเวชกรรม; S4 OBGYN 'สูติ-นรีเวชกรรม' |
| 06 | E-ENT | department | ENT clinic; S4 ENT has the same scope. | SIL-TH-CS-CHI-CLINIC 06 โสต ศอ นาสิก; S4 ENT |
| 07 | E-EYE | department | Ophthalmology clinic; S4 EYE has the same scope. | SIL-TH-CS-CHI-CLINIC 07 จักษุ; S4 EYE |
| 08 | E-ORTHO | department | Orthopaedic surgery clinic; S4 ORTHO has the same scope. | SIL-TH-CS-CHI-CLINIC 08 ศัลยกรรมกระดูก; S4 ORTHO |
| 09 | E-PSY | department | Psychiatry clinic; S4 PSY has the same scope. | SIL-TH-CS-CHI-CLINIC 09 จิตเวช; S4 PSY |
| 11 | UNMAPPABLE | excluded | Dental clinic; the S4 department list has no dental code, so S4 cannot suggest it. Rows are excluded from the department population and counted. | SIL-TH-CS-CHI-CLINIC 11 ทันตกรรม; backend/app/triage/departments.py (10 codes, no dental) |
| 12 | UNMAPPABLE | red_flag_metrics | Emergency is not an S4 department: S4 routes urgency through red-flag alerts by design. These rows are scored by the red-flag metrics, not by department accuracy. | SIL-TH-CS-CHI-CLINIC 12 ฉุกเฉิน; departments.py docstring 'There is deliberately no emergency code' |
| NOT_EVALUABLE | UNMAPPABLE | abstention_only | Chief complaint missing: S1r labels no department. The DP enters the abstention population with y_true NOT_EVALUABLE, so any answer is wrong. | S1r gold department_evaluable=false, department_reason=chief_complaint_missing |

## S4 department code -> evaluation space E (`department_s4`, 10 rows)

Scoring: The S4 top-3 is mapped to E and de-duplicated, keeping the first occurrence.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| MED | E-MED | Internal medicine. | backend/app/triage/departments.py MED อายุรกรรม |
| CARD | E-MED | Cardiology is an internal-medicine sub-clinic; S1r has no cardiology code. | departments.py CARD อายุรกรรมหัวใจ |
| NEURO | E-MED | Neurology is an internal-medicine sub-clinic; S1r has no neurology code. | departments.py NEURO ประสาทวิทยา |
| SURG | E-SURG | General surgery. | departments.py SURG ศัลยกรรมทั่วไป |
| URO | E-SURG | Urology is a surgical specialty; S1r has no urology code. Known disagreement: S1r maps dysuria to 01 while S4 suggests URO; reported as-is, flagged for D1. | departments.py URO ศัลยกรรมระบบทางเดินปัสสาวะ |
| ORTHO | E-ORTHO | Orthopaedics. | departments.py ORTHO |
| OBGYN | E-OBGYN | Obstetrics and gynaecology. | departments.py OBGYN |
| EYE | E-EYE | Ophthalmology. | departments.py EYE |
| ENT | E-ENT | Ear, nose and throat. | departments.py ENT |
| PSY | E-PSY | Psychiatry. | departments.py PSY |

## S1r red-flag rule -> S4 rule(s) whose alert detects it (any of) (`red_flag_s1r`, 7 rows)

Scoring: A gold (DP, rule) pair is detected when any listed S4 rule fired at that DP. UNMAPPABLE pairs count as missed in the primary rule-level recall; the mappable-only recall is secondary. A not_evaluable S4 rule is never a detection.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| RF-NEWS-SINGLE3 | RF-SPO2, RF-RR, RF-SBP, RF-HR, RF-CONSC, RF-TEMP | S1r: any single NEWS parameter scoring 3 (RR, SpO2, temperature, SBP, HR, V/P/U). S4 has one NEWS2 single-parameter-3 rule per parameter with the same cut-offs. | data_factory/templates/red_flags.json (PMID 23295778); redflag_rules_v1.json (RCP NEWS2 Chart 1) |
| RF-QSOFA | RF-QSOFA | Same qSOFA >= 2 criteria (RR >= 22, SBP <= 100, altered mentation). | PMID 26903335 (both registries) |
| RF-ACUTE-CHEST-PAIN | RF-CHEST | Acute chest pain; S4 RF-CHEST fires on symptom.acute_chest_pain. | PMID 34709879 (both registries) |
| RF-FAST | RF-STROKE | Sudden face/arm/speech deficit; S4 RF-STROKE fires on sudden facial droop, limb weakness, speech or vision disturbance. | S1r PMID 12511753; S4 PMID 31662037 |
| RF-THUNDERCLAP | RF-THUNDER | Thunderclap headache. | PMID 24065011 (both registries) |
| RF-ANAPHYLAXIS | RF-ANAPH | Possible anaphylaxis (skin/mucosal plus respiratory compromise or SBP < 90). | S1r PMID 16461139; S4 PMID 33204386 |
| RF-NEWS-AGG5 | UNMAPPABLE | Aggregate NEWS >= 5 with no single parameter scoring 3; S4 has no aggregate-NEWS rule. Pairs count as missed in primary rule-level recall. | RCP NEWS 2012 Chart 1; redflag_rules_v1.json has only single-parameter rules |

## S4 red-flag rule -> S1r rule it serves (`red_flag_s4`, 16 rows)

Scoring: UNMAPPABLE rows are outside the S1r registry: their alerts are counted per rule and listed, counted in the primary FPR and excluded from the mapped-only FPR (secondary). Gold 'no red flag' means only that no S1r rule fires, not that the case is safe.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | route | rationale | source_ref |
|---|---|---|---|---|
| RF-SPO2 | RF-NEWS-SINGLE3 |  | SpO2 <= 91 is a NEWS single-parameter 3. | redflag_rules_v1.json RF-SPO2 |
| RF-RR | RF-NEWS-SINGLE3 |  | RR <= 8 or >= 25. | RF-RR |
| RF-SBP | RF-NEWS-SINGLE3 |  | SBP <= 90 or >= 220. | RF-SBP |
| RF-HR | RF-NEWS-SINGLE3 |  | HR <= 40 or >= 131. | RF-HR |
| RF-CONSC | RF-NEWS-SINGLE3 |  | AVPU not A (V/P/U score 3). S4 also fires on new confusion (NEWS2 C), which scores 0 under S1r NEWS 2012; such alerts on gold-negative DPs appear as false positives. | RF-CONSC |
| RF-TEMP | RF-NEWS-SINGLE3 |  | Temperature <= 35.0. | RF-TEMP |
| RF-QSOFA | RF-QSOFA |  | Same criteria. | RF-QSOFA |
| RF-CHEST | RF-ACUTE-CHEST-PAIN |  | Acute chest pain. | RF-CHEST |
| RF-STROKE | RF-FAST |  | Sudden focal deficit. | RF-STROKE |
| RF-THUNDER | RF-THUNDERCLAP |  | Thunderclap headache. | RF-THUNDER |
| RF-ANAPH | RF-ANAPHYLAXIS |  | Possible anaphylaxis. | RF-ANAPH |
| RF-SUICIDE | UNMAPPABLE | outside_s1r_registry | No S1r counterpart (suicidal ideation / self-harm). | RF-SUICIDE |
| RF-GIBLEED | UNMAPPABLE | outside_s1r_registry | No S1r counterpart (upper GI bleeding). | RF-GIBLEED |
| RF-ECTOPIC | UNMAPPABLE | outside_s1r_registry | No S1r counterpart (possible ectopic pregnancy). | RF-ECTOPIC |
| RF-MENING | UNMAPPABLE | outside_s1r_registry | No S1r counterpart (possible meningitis). | RF-MENING |
| RF-HYPOGLY | UNMAPPABLE | outside_s1r_registry | No S1r counterpart (level 2 hypoglycaemia); S1r has no glucose item. | RF-HYPOGLY |

## S1r Vitals / Demographics item field -> S4 fact kind (`vitals_demographics`, 12 rows)

Scoring: Every Vitals item is passed with its own available_at_time; S4 keeps the latest fact per kind (S4 behaviour, reported, not altered).

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| hr | vital.hr | Same quantity (beats/min). | S1r Vitals.hr; S4 models.NUMERIC_VITALS |
| rr | vital.rr | Same quantity (breaths/min). | S1r Vitals.rr |
| sbp | vital.sbp | Same quantity (mmHg). | S1r Vitals.sbp |
| dbp | vital.dbp | Same quantity (mmHg). | S1r Vitals.dbp |
| spo2 | vital.spo2 | Same quantity (%). | S1r Vitals.spo2 |
| temp_c | vital.temp_c | Same quantity (degrees C). | S1r Vitals.temp_c |
| consciousness | vital.avpu (+ vital.new_confusion for C) | ACVPU convention; see section consciousness. | RCP NEWS2 ACVPU |
| on_oxygen | UNMAPPABLE | S4 has no supplemental-oxygen fact kind. | S4 models._KIND |
| null value | (no fact) | A null vital is not recorded; it is never given as a normal value. | CLAUDE.md data rule 6 (preserve missingness) |
| Demographics.age_years | age | Same quantity (years). | S1r Demographics |
| Demographics.sex | sex | Same values (female, male). | S1r Demographics |
| pregnancy status | UNMAPPABLE | S1r has no pregnancy item, so no pregnancy_status fact is given (S4 treats it as not known). | S1r snapshot item types |

## S1r consciousness (ACVPU) -> S4 facts (`consciousness`, 5 rows)

Scoring: Applied to every Vitals item.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| A | vital.avpu=A | Alert. | RCP NEWS2 ACVPU |
| C | vital.avpu=A + vital.new_confusion=true | ACVPU 'new confusion': the patient is alert on AVPU and newly confused. C scores 0 under S1r NEWS 2012 but counts as altered mentation for qSOFA. | RCP NEWS2 ACVPU; S1r red_flags.json (C scores 0 in NEWS 2012, counts for qSOFA) |
| V | vital.avpu=V | Responds to voice. | RCP NEWS2 ACVPU |
| P | vital.avpu=P | Responds to pain. | RCP NEWS2 ACVPU |
| U | vital.avpu=U | Unresponsive. | RCP NEWS2 ACVPU |

## S1r chief-complaint code (ICD-10-CM) -> acceptable S3 chief_complaint codes (`chief_complaint_s1r_to_s3`, 58 rows)

Scoring: S3 outputs one code from a closed 16-code symptom vocabulary. A prediction is correct when it is in the acceptable set (the S3 codes that express the ICD-10-CM title or a symptom stated in the complaint). UNMAPPABLE cases are excluded from the chief_complaint field only, and counted. The S3 code definitions are the 16 names in backend/app/voice/models.py; runny_nose covers nasal discharge and nasal congestion (its declared phrases include คัดจมูก).

> **System Evaluation on synthetic data - not clinical performance**

| source | target | icd10cm | rationale | source_ref |
|---|---|---|---|---|
| CC-FEVER-COUGH | fever, cough | R50.9 | Fever, unspecified; complaint states fever and cough. | ICD10CM-FY2026 R50.9 |
| CC-DIARRHEA | diarrhea | R19.7 | Diarrhoea, unspecified. | ICD10CM-FY2026 R19.7 |
| CC-DYSURIA | dysuria | R30.0 | Dysuria. | ICD10CM-FY2026 R30.0 |
| CC-PALPITATION | UNMAPPABLE | R00.2 | Palpitations; no S3 code expresses palpitations (chest_pain would be a different symptom). | ICD10CM-FY2026 R00.2 |
| CC-HEADACHE | headache | R51.9 | Headache, unspecified. | ICD10CM-FY2026 R51.9 |
| CC-FATIGUE | fatigue | R53.83 | Other fatigue. | ICD10CM-FY2026 R53.83 |
| CC-RLQ-PAIN | abdominal_pain | R10.31 | Right lower quadrant pain is abdominal pain (R10). | ICD10CM-FY2026 R10.31 |
| CC-ABSCESS | UNMAPPABLE | L02.91 | Cutaneous abscess; not a rash and no S3 code for a skin swelling. | ICD10CM-FY2026 L02.91 |
| CC-GROIN-LUMP | UNMAPPABLE | K40.90 | Inguinal hernia / groin lump; no S3 code. | ICD10CM-FY2026 K40.90 |
| CC-PREG-NAUSEA | nausea_vomiting | O21.0 | Mild hyperemesis gravidarum; complaint states nausea and vomiting. | ICD10CM-FY2026 O21.0 |
| CC-PREG-ITCH | UNMAPPABLE | O26.899 | Pregnancy-related itching without a stated rash; S3 has no pruritus code and rash is not equal. | ICD10CM-FY2026 O26.899 |
| CC-DYSMENORRHEA | abdominal_pain | N94.6 | Dysmenorrhoea is cyclical lower abdominal / pelvic pain; ICD-10-CM groups pelvic pain with abdominal pain (R10 'Abdominal and pelvic pain'). Flagged for D1. | ICD10CM-FY2026 N94.6, R10.2 |
| CC-DISCHARGE | UNMAPPABLE | N89.8 | Abnormal vaginal discharge; no S3 code. | ICD10CM-FY2026 N89.8 |
| CC-SORE-THROAT | sore_throat | J02.9 | Acute pharyngitis presenting as sore throat. | ICD10CM-FY2026 J02.9 |
| CC-EAR-PAIN | UNMAPPABLE | H92.09 | Otalgia; no S3 code. | ICD10CM-FY2026 H92.09 |
| CC-VERTIGO | dizziness | H81.10 | Benign paroxysmal vertigo; vertigo is a form of dizziness (R42 'Dizziness and giddiness'). | ICD10CM-FY2026 H81.10, R42 |
| CC-RED-EYE | UNMAPPABLE | H10.9 | Conjunctivitis / red eye; no S3 code. | ICD10CM-FY2026 H10.9 |
| CC-BLURRED | UNMAPPABLE | H53.8 | Visual disturbance; no S3 code. | ICD10CM-FY2026 H53.8 |
| CC-LOW-BACK | back_pain | M54.50 | Low back pain. | ICD10CM-FY2026 M54.50 |
| CC-KNEE | joint_pain | M25.569 | Pain in knee is joint pain (M25.5). | ICD10CM-FY2026 M25.569 |
| CC-ANKLE | joint_pain | S93.409A | Ankle sprain presenting with a swollen ankle joint; the S3 joint category covers joint pain and joint swelling. Flagged for D1. | ICD10CM-FY2026 S93.409A, M25.57 |
| CC-INSOMNIA | UNMAPPABLE | G47.00 | Insomnia; no S3 code. | ICD10CM-FY2026 G47.00 |
| CC-ANXIETY | UNMAPPABLE | F41.9 | Anxiety; no S3 code. | ICD10CM-FY2026 F41.9 |
| CC-TOOTHACHE | UNMAPPABLE | K08.89 | Toothache; no S3 code. | ICD10CM-FY2026 K08.89 |
| CC-GUM | UNMAPPABLE | K05.10 | Gingivitis; no S3 code. | ICD10CM-FY2026 K05.10 |
| CC-GASTRO | diarrhea, abdominal_pain | A09 | Infectious gastroenteritis; complaint states cramping abdominal pain and loose stools. | ICD10CM-FY2026 A09 |
| CC-HEARTBURN | UNMAPPABLE | R12 | Heartburn is not chest pain (R12 vs R07); no S3 code. | ICD10CM-FY2026 R12 |
| CC-NASAL | runny_nose | R09.81 | Nasal congestion; the S3 runny_nose category covers nasal congestion. | ICD10CM-FY2026 R09.81 |
| CC-COLD | runny_nose | J00 | Common cold; complaint states runny and blocked nose. | ICD10CM-FY2026 J00 |
| CC-EPISTAXIS | UNMAPPABLE | R04.0 | Nosebleed; no S3 code (runny_nose is nasal discharge, not bleeding). | ICD10CM-FY2026 R04.0 |
| CC-CARIES | UNMAPPABLE | K02.9 | Dental caries; no S3 code. | ICD10CM-FY2026 K02.9 |
| CC-LOW-MOOD | UNMAPPABLE | F32.A | Depressed mood; no S3 code (fatigue is not equal). | ICD10CM-FY2026 F32.A |
| CC-RF-CHEST | chest_pain | R07.9 | Chest pain, unspecified. | ICD10CM-FY2026 R07.9 |
| CC-RF-CHEST-2 | chest_pain | R07.9 | Chest pain, unspecified. | ICD10CM-FY2026 R07.9 |
| CC-RF-CHEST-3 | chest_pain | R07.9 | Chest pain, unspecified. | ICD10CM-FY2026 R07.9 |
| CC-RF-CHEST-4 | chest_pain | R07.9 | Chest pain, unspecified. | ICD10CM-FY2026 R07.9 |
| CC-RF-FAST | UNMAPPABLE | R29.810 | Facial weakness with speech disturbance; no S3 code (never fatigue). | ICD10CM-FY2026 R29.810 |
| CC-RF-FAST-2 | UNMAPPABLE | R29.810 | Facial droop with one-sided arm weakness; no S3 code (never fatigue). | ICD10CM-FY2026 R29.810 |
| CC-RF-FAST-3 | UNMAPPABLE | R29.810 | One-sided limb weakness with speech difficulty; no S3 code (never fatigue). | ICD10CM-FY2026 R29.810 |
| CC-RF-FAST-4 | UNMAPPABLE | R29.810 | Slurred speech with drooping mouth corner; no S3 code. | ICD10CM-FY2026 R29.810 |
| CC-RF-THUNDERCLAP | headache | R51.9 | Headache, unspecified (S3 records no onset). | ICD10CM-FY2026 R51.9 |
| CC-RF-THUNDERCLAP-2 | headache | R51.9 | Headache, unspecified. | ICD10CM-FY2026 R51.9 |
| CC-RF-THUNDERCLAP-3 | headache | R51.9 | Headache, unspecified. | ICD10CM-FY2026 R51.9 |
| CC-RF-THUNDERCLAP-4 | headache | R51.9 | Headache, unspecified. | ICD10CM-FY2026 R51.9 |
| CC-RF-ANAPHYLAXIS | rash, dyspnea | L50.0 | Allergic urticaria (rash); complaint also states difficulty breathing. | ICD10CM-FY2026 L50.0 |
| CC-RF-ANAPHYLAXIS-2 | rash, dyspnea | L50.0 | Allergic urticaria (rash); complaint also states wheezing. | ICD10CM-FY2026 L50.0 |
| CC-RF-ANAPHYLAXIS-3 | rash, dyspnea | L50.0 | Coded allergic urticaria (rash); complaint states lip swelling and inability to breathe. | ICD10CM-FY2026 L50.0 |
| CC-RF-ANAPHYLAXIS-4 | rash, dizziness | L50.0 | Allergic urticaria (rash); complaint also states light-headedness (near-faint). | ICD10CM-FY2026 L50.0, R42 |
| CC-TNM-CHEST-1 | chest_pain | R07.89 | Other chest pain. | ICD10CM-FY2026 R07.89 |
| CC-TNM-CHEST-2 | chest_pain | R07.89 | Other chest pain. | ICD10CM-FY2026 R07.89 |
| CC-TNM-HEADACHE-1 | headache | R51.9 | Headache, unspecified. | ICD10CM-FY2026 R51.9 |
| CC-TNM-HEADACHE-2 | headache | R51.9 | Headache, unspecified. | ICD10CM-FY2026 R51.9 |
| CC-TNM-NUMB-1 | UNMAPPABLE | R20.2 | Paraesthesia of skin (finger numbness); no S3 code. | ICD10CM-FY2026 R20.2 |
| CC-TNM-NUMB-2 | UNMAPPABLE | R20.2 | Paraesthesia of skin; no S3 code. | ICD10CM-FY2026 R20.2 |
| CC-TNM-URTICARIA-1 | rash | L50.9 | Urticaria is a rash. | ICD10CM-FY2026 L50.9 |
| CC-TNM-URTICARIA-2 | rash | L50.9 | Urticaria is a rash. | ICD10CM-FY2026 L50.9 |
| CC-TNM-DEFICIT-1 | UNMAPPABLE | I69.398 | Sequelae of stroke (chronic deficit, follow-up visit); no S3 code. | ICD10CM-FY2026 I69.398 |
| CC-TNM-DEFICIT-2 | UNMAPPABLE | I69.359 | Hemiplegia following stroke (chronic); no S3 code. | ICD10CM-FY2026 I69.359 |

## S1r duration unit -> ISO-8601 (gold and S3 compared after normalisation) (`duration_unit`, 6 rows)

Scoring: PnW is normalised to P(7n)D on both sides; months and years are not converted. Gold duration MISSING is absent.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| minute | PT{n}M | ISO-8601 time component, minutes. | ISO 8601 durations |
| hour | PT{n}H | ISO-8601 time component, hours. | ISO 8601 durations |
| day | P{n}D | ISO-8601 days. | ISO 8601 durations |
| week | P{7n}D | One week is 7 days; S3 P{n}W is normalised the same way. | ISO 8601 durations |
| month | P{n}M | Calendar months are not converted to days. | ISO 8601 durations |
| year | P{n}Y | Calendar years are not converted to days. | ISO 8601 durations |

## S1r allergy_status -> S3 allergy_status (`allergy_value`, 3 rows)

Scoring: Only KNOWN S3 facts count as extracted values; UNKNOWN, REFUSED and MISSING are no extracted value. False-none: gold known or MISSING but S3 KNOWN none.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| no_known_allergy | none | Stated no drug allergy = S3 KNOWN none. | S1r gold required_fields.allergy_status; S3 ALLERGY_VALUES |
| known | present | A stated drug allergy = S3 KNOWN present. | S1r gold; S3 ALLERGY_VALUES |
| MISSING | (absent) | Not stated in the transcript: no gold value (never a negative). | CLAUDE.md data rule 6 |

## S3 chief_complaint code -> S4 symptom fact (end-to-end pipeline) (`s3_cc_to_s4_symptom`, 16 rows)

Scoring: symptom.<name>=present is given only where the meaning is equal. S4 acuity- or exposure-qualified symptoms are never produced (section s4_symptom_qualified).

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| fever | symptom.fever | Same meaning. | S3 models.CHIEF_COMPLAINT_CODES; S4 baseline_keywords_v1.json |
| cough | symptom.cough | Same meaning. | same |
| sore_throat | symptom.sore_throat | Same meaning. | same |
| runny_nose | UNMAPPABLE | S4 has no nasal symptom. | S4 symptom names |
| headache | symptom.headache | Same meaning (not thunderclap_headache, which needs onset). | same |
| dizziness | symptom.dizziness | Same meaning. | same |
| chest_pain | UNMAPPABLE | S4 has only acute_chest_pain, which is acuity-qualified; S3 records no onset. | redflag_rules_v1.json RF-CHEST |
| dyspnea | symptom.dyspnea | Same meaning (not airway_breathing_compromise, which is qualified). | same |
| abdominal_pain | symptom.abdominal_pain | Same meaning. | same |
| diarrhea | UNMAPPABLE | S4 has no diarrhoea symptom. | S4 symptom names |
| nausea_vomiting | UNMAPPABLE | S4 has only hematemesis (vomiting blood), which is not equal. | S4 symptom names |
| rash | UNMAPPABLE | S4 has only non_blanching_rash, which is qualified. | RF-MENING |
| back_pain | symptom.back_pain | Same meaning. | same |
| joint_pain | symptom.joint_pain | Same meaning. | same |
| dysuria | symptom.dysuria | Same meaning. | same |
| fatigue | UNMAPPABLE | S4 has no fatigue symptom. | S4 symptom names |

## S3 intake fact -> S4 fact (end-to-end pipeline) (`s3_field_to_s4_fact`, 10 rows)

Scoring: The final S3 fact per field at finish is used, with its own available_at_time.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| chief_complaint | chief_complaint (NFC text of the span turns) + symptom per s3_cc_to_s4_symptom | S4 reads the chief complaint as free text; the span turns are what the patient said. | S3 IntakeFact.span_turn_ids; S4 department.build_request |
| onset_duration | onset_duration (S3 ISO value) | S4 needs only a non-empty duration. | S4 models.REQUIRED_FIELDS |
| severity | UNMAPPABLE | S4 has no severity fact kind. | S4 models._KIND |
| allergy_status | UNMAPPABLE | S4 has no allergy fact kind. | S4 models._KIND |
| allergens | UNMAPPABLE | S4 has no allergy fact kind. | S4 models._KIND |
| current_medications | UNMAPPABLE | S4 has no medication fact kind. | S4 models._KIND |
| relevant_history | UNMAPPABLE | S4 has no history fact kind (diabetes_known is not produced). | S4 models._KIND |
| state MISSING | (no fact) | Not captured: never a negative. | CLAUDE.md data rule 6 |
| state UNKNOWN | (no fact) | A non-answer is not a value. | S3 FactState |
| state REFUSED | (no fact) | A refusal is not a value. | S3 FactState |

## S4 acuity- or exposure-qualified symptoms (never produced end to end) (`s4_symptom_qualified`, 8 rows)

Scoring: S3 records no onset, acuity or exposure, so these S4 inputs stay unknown and the S4 text red-flag rules cannot fire end to end. This is measured and reported, not patched.

> **System Evaluation on synthetic data - not clinical performance**

| source | target | rationale | source_ref |
|---|---|---|---|
| acute_chest_pain | UNMAPPABLE | Needs acuity. | RF-CHEST |
| sudden_facial_droop | UNMAPPABLE | Needs sudden onset. | RF-STROKE |
| sudden_limb_weakness | UNMAPPABLE | Needs sudden onset. | RF-STROKE |
| sudden_speech_disturbance | UNMAPPABLE | Needs sudden onset. | RF-STROKE |
| sudden_vision_disturbance | UNMAPPABLE | Needs sudden onset. | RF-STROKE |
| thunderclap_headache | UNMAPPABLE | Needs peak-within-1-hour onset. | RF-THUNDER |
| allergen_exposure | UNMAPPABLE | Needs an exposure history. | RF-ANAPH |
| airway_breathing_compromise | UNMAPPABLE | Needs severity qualification. | RF-ANAPH |

## Known disagreements (reported as-is, flagged for D1)

- Dysuria: S1r maps CC-DYSURIA to 01 (E-MED); the S4 keyword baseline suggests URO (E-SURG). Reported as-is; flagged for D1.
- OBGYN merge (03 and 04 -> E-OBGYN) and CARD/NEURO -> E-MED are coarsenings forced by the two department lists; flagged for D1.
- ACVPU C -> avpu A + new_confusion: S4 RF-CONSC then fires on C, which scores 0 under S1r NEWS 2012; flagged for D1.

## Replay deviations from live use

- S3 replays the recorded T1 IntakeTranscript turn by turn. S3's own policy still emits its agent questions between recorded turns and decides which field it thinks was asked last (last_asked_field); in the recording the nurse asked, not the agent, so S3's field context can differ from live use.
- Speakers keep their role (nurse -> nurse, patient -> patient). A nurse turn that is a question yields no facts (S3 behaviour).
- Turn times: started_at = spoken_at; ended_at = the next turn's spoken_at, or the transcript observed_at for the last turn. The service clock passed to S3 is the turn's ended_at.
- S3 requires patient_ref to match ^SYN-...; the S1r patient_ref (SYNP-nnnn) is passed as SYN-SYNP-nnnn. This is an identifier prefix only.
- The final fact per field at finish is used. The S3 output of the T1 transcript is used at both T1 and T2 (the T2 snapshot holds the same transcript).
- S3 and S4 run in-process on an in-memory SQLite engine with the offline mock provider through the Model Gateway; latency is not measured.

## Changelog (changes after the first dev run, with reason)

- none
