# Our Senior Project, Explained in Plain Words

**For:** every team member, including those who don't work on the AI parts. Read this before the proposal presentation (8–9 Oct 2026).
**Based on:** proposal v9.6. This file explains the same project with as few technical terms as possible. The technical details are in the other files in this folder. If this file and the proposal disagree, the proposal is correct.
**Official title** (registered, cannot change): *Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and Care-Pathway Decision Support*

---

## 0. Words used in this document

This document uses a few words with a fixed meaning. They are explained properly later, but here is the short version:

| Word | Meaning here |
|---|---|
| **Work plan** | The list of jobs the computer does for one patient at one moment, and which job passes its result to which (section 4.1) |
| **Job** | One small task in a work plan, for example "read the X-ray" or "check danger signs" |
| **Worker** | Whatever actually does a job: our AI model, an outside AI service, a small specialist AI, or fixed rules (section 6.3) |
| **Danger-sign check** | A job that uses fixed rules to look for signs of serious danger (section 4.2) |
| **Staff confirmation** | The job where a nurse, doctor or pharmacist accepts, edits or rejects the system's output (section 4.3) |
| **Stage** | The nurse stage, doctor stage or pharmacist stage of a patient's visit (section 5) |

Some basic terms you will also see:

| Term | Meaning |
|---|---|
| **AI model** | A computer program trained on many examples to do a task, such as reading text or images. Large models that read and write text are called **language models**. Some, like ours, can also read images through extra parts |
| **Token** | A model reads its input as small pieces called tokens (roughly a word or part of a word; an image is also turned into tokens). A model can only handle a limited number of tokens at once |
| **Parameters** | The internal numbers an AI model learns during training. "27B" means about 27 billion parameters. More parameters usually means a more capable model, but more GPU memory is needed |
| **GPU** | The special processor used to train and run AI models. "B200" is a type of NVIDIA GPU |
| **API** | A way for our program to send a request to another company's service over the internet and get an answer back |
| **CT / MRI / X-ray** | Types of medical image. An X-ray is one flat (2D) picture. A CT or MRI scan is a 3D stack of hundreds of slices through the body |
| **ED** | Emergency department |
| **Label** | The correct answer we compare the AI's output with when testing |
| **MIMIC** | Large research datasets of real, de-identified patient records from a hospital in Boston, USA. Researchers get access through a website called **PhysioNet**, after training and signing an agreement |

---

## 1. The 30-second version

When a patient comes to a hospital, information about them arrives **piece by piece**:

- first, what they tell the nurse, and their blood pressure and temperature
- later, **if the doctor orders tests**, lab results and X-rays or CT scans
- finally, **if the doctor prescribes medicines**, the new prescriptions

Staff must make decisions at each point with only the information they have **at that time**.

We are building an AI assistant that helps the **nurse, the doctor and the pharmacist**. Each time new information arrives for a patient, it:

1. Uses only the information about this patient that exists **at that time**.
2. Makes a **work plan**: a list of small jobs for this patient now. A job is only included if its data exists. For example, "read the X-ray" is only included if there is an X-ray.
3. Runs the jobs and saves what each job received and what it produced, so anyone can check later where a suggestion came from.
4. Says "not enough information" instead of guessing when required information is missing.
5. Leaves every decision to a person. Nothing is used until staff confirm it.

We will also train **our own version of a medical AI model**. We start from an existing public model and add the ability to read **3D CT scans**. It will be the main worker the assistant uses.

Everything is tested in a **simulated setting** (test cases, not a live hospital), using research datasets. The system is never used on real patients.

---

## 2. The problem we are solving

### 2.1 Information arrives at different times

A patient's information comes from many sources and in different forms:

- what the patient says
- numbers (vital signs, lab values)
- flat images (chest X-ray)
- 3D scans (CT, MRI)
- medication lists

It is not all available at the start. Staff often decide with incomplete information and update their view as more arrives.

### 2.2 Medication information is messy

Medication information comes from several places:

- what the patient says they take
- the patient's existing medication list
- the doctor's new prescriptions

These can be incomplete or disagree with each other. The pharmacist must compare them and contact the doctor or others if something is wrong, before giving out the medicines. This is called **medication reconciliation**. Guidance from two US organisations, AHRQ (Agency for Healthcare Research and Quality) and ASHP (American Society of Health-System Pharmacists), gives pharmacists this role.

### 2.3 An AI can accidentally "see" later information

When an AI is trained and tested with old hospital records, it is easy to give it information that **did not exist yet** at the time of the decision. For example, giving it the final diagnosis while it is suggesting a department when the patient first arrives. The AI then looks much better in testing than it would be in real use. This is called **data leakage**.

### 2.4 Most AI systems use the same steps for every patient

The common approach is to send **all** of the patient's information to **one** AI model in **one** request, with the same steps for every patient. This causes two problems:

- It is hard to tell **which piece of information** led to a suggestion.
- It is hard to change the AI for **only one task**. For example, you cannot use a better X-ray reader without changing everything.

> **Note for the presentation:** our project is **not** about triage (sorting patients by how urgent they are). The system does suggest a department, and it does flag danger signs as an extra safety check. But it only **flags**; it does not **rank** patients by urgency. Triage is not the problem we are solving.

---

## 3. What we are building: three parts

| Part | In plain words | How important |
|---|---|---|
| **A. The work-plan system** (called "Case Graph" in the proposal) | For each patient, each time new information arrives, it makes a work plan, runs the jobs, saves every result and waits for staff to confirm | **Main contribution** |
| **B. Our medical AI model** | An existing public AI model that we train further for medicine, with an added part for reading 3D CT scans | **Second important contribution**. It is the main worker used by part A |
| **C. The AI Clinical Front Door** (the app) | A demonstration web app: a Thai voice assistant that takes the patient's history, a department suggestion for the nurse, care suggestions for the doctor, a medication checker for the pharmacist, and a screen for staff | Used to demonstrate and test parts A and B |

There is also a supporting piece: **time-aware data preparation**. Every piece of patient data is labelled with *the time it became available*, so the AI is never given information from later in the patient's timeline (section 8.3).

**About the title.** The title was registered early and cannot change, so it needs explaining:

- "Case-Adaptive" describes the **work plan**, which changes for each patient. It does not mean the model changes itself.
- "Foundation Model" means a large AI model trained on lots of data that can be used for many tasks. We do not build one from nothing; we start from one and train it further (section 7).
- In the proposal, the work-plan system is the main contribution and the model is the second important one.

---

## 4. Three ideas to understand first

### 4.1 What is a "work plan"?

A **work plan** is:

- the list of **jobs** the computer will do for **one patient at one moment**, and
- which job passes its result to which other job.

The system makes the plan automatically from the information the patient has at that moment. Staff do not write it. They can look at it on screen if they want to see how a suggestion was made.

Some jobs can run at the same time. Others must wait because they need another job's result. It is similar to a cooking recipe, where some steps need the result of earlier steps.

**Example.** This is the work plan for a patient who has just talked to the voice assistant and had his vital signs measured:

```
 Patient data              Job                                       Result of the job
 ──────────────            ──────────────────────────────────        ───────────────────────────
 conversation text  ──►  [1] Read the conversation             ──►  key facts: main complaint,
                                                                     how long, allergies, medicines
 vital signs        ──►  [2] Read the vital signs              ──►  findings, e.g. "high fever (39.2 °C)"

 results of 1 + 2,  ──►  [3] Danger-sign check (fixed rules)   ──►  alerts (if any)
 and the vital signs

 results of 1, 2, 3 ──►  [4] Summarise + suggest a department  ──►  draft summary + department,
                                                                     or "not enough information"

 result of 4 + alerts ─► [5] Nurse confirms / edits / rejects  ──►  confirmed result
```

- Job 2 turns the raw numbers into short findings, such as "high fever", using rules or our model. Lab results are read the same way.
- Jobs 1 and 2 don't need each other's results, so they run at the same time.
- Job 3 waits for 1 and 2. Job 4 waits for 1, 2 and 3. Job 5 waits for 4, and also receives the alerts from 3 directly.
- If the patient later has a chest X-ray, the **next** work plan adds a job "read the X-ray", and its result also goes into the summary job.
- If a patient has no X-ray, there is no "read the X-ray" job. So different patients get different plans. The plan **adapts to the patient's case**. This is what "case-adaptive" in the title means.

In the proposal, a work plan is drawn as boxes (jobs) joined by arrows (results passed along). In computer science, this kind of drawing is called a **graph**, which is why the proposal calls the system **Case Graph**. There is one graph for each patient at each moment. The proposal's Figure 3.2 (in the `figures/` subfolder) shows three of them.

### 4.2 What is the "danger-sign check"?

The **danger-sign check** (called the "Red-flag Node" in the proposal) looks for signs that the patient may be in **serious danger and needs attention immediately**.

- **It uses fixed rules written in advance, not AI.** Each rule is a simple condition. The real list of rules is **not decided yet** and will be set with medical experts. The rules will be of this kind (examples only):
  - blood oxygen level below a set value
  - blood pressure far too low
  - heart rate far too fast
  - very high fever
  - the patient said they have chest pain or difficulty breathing
- **What it reads:** the measured vital signs, and the written findings from the conversation and the vitals/lab results. It does **not** read X-ray or CT results. In the proposal's design (Figure 3.2), image results go only to the summary job, and rules cannot read the image format our model uses. Whether written image findings should also feed this check is an open question (section 18).
- **When a rule matches, it creates an alert.** The alert goes to **two places**:
  - into the summary job, so the AI's summary takes it into account
  - **directly to the staff member confirming at that stage**, shown on their screen. The proposal shows this for the nurse and the doctor. Whether the pharmacist also sees alerts is not stated (section 18).
- Because of the direct route, the AI **cannot remove or weaken** an alert once a rule has matched.
- **Limitation to know:** rules about vital signs use the measured numbers directly. Rules about symptoms (like chest pain) depend on the conversation-reading job finding that symptom. If that job misses it, the rule cannot match. So the check is an extra safety layer, not a replacement for staff judgement. At the nurse stage, the nurse is with the patient the whole time.
- It is in **every** work plan. Its worker is always "fixed rules". It cannot be swapped for an AI.
- **Why rules and not AI:** rules give the same answer every time, a person can read and check them, and their alerts cannot be overruled by the AI.

### 4.3 What is "staff confirmation"?

Every work plan ends with a staff member who **confirms, edits or rejects** what the system produced: the nurse, doctor or pharmacist, depending on the stage. Nothing the system suggests is used until a person confirms it. The confirmed version is saved in the patient's record. (How later plans use a confirmed or edited result is not fully defined in the proposal; see section 18.)

Like the danger-sign check, this job is in **every** work plan.

---

## 5. A patient's journey through the system

This example patient, Mr. A, is invented to show the flow. The setting is a hospital's **first point of contact**, where a nurse takes the patient's history and sends them to a department.

A **stage** is a part of the visit (nurse, doctor, pharmacist). A **work plan** is made each time new information arrives. The proposal shows three typical work plans, **T1, T2 and T3**, one for each stage:

- Every patient gets T1.
- T2 is made only if test results arrive. If a second batch of results arrives, another doctor-stage plan is made in the same way.
- T3 is made only if the doctor writes new prescriptions. This can happen with or without T2.

### Stage 1: The nurse (work plan T1). Every patient goes through this.

1. Mr. A arrives at the hospital. The nurse greets him and measures his blood pressure and temperature.
2. Mr. A **talks to the voice assistant in Thai**, and the nurse stays with him. The assistant asks about:
   - his main complaint
   - how long he has had it
   - drug allergies
   - medicines he already takes

   It only asks follow-up questions about information that is still **missing**.
3. The conversation (the full text and the key facts taken from it) and his vital signs are saved in his record.
4. The system makes the work plan shown in section 4.1:
   - read the conversation
   - read the vital signs
   - danger-sign check
   - summarise and **suggest a department**
   - nurse confirmation
5. **The nurse** reads the summary, the suggested department and any alerts, edits them if needed, and confirms. Mr. A goes to the confirmed department.

### Stage 2: The doctor (work plan T2 only if test results arrive)

6. Mr. A sees the doctor. The doctor can already see the summary the nurse confirmed in stage 1.
7. **Not every patient needs tests.** If the doctor orders tests, for example blood tests, a chest X-ray or a CT scan, the results come back later and are added to Mr. A's record. The doctor then reviews the results.
8. When the results arrive, the system makes a **new, larger** work plan (T2):
   - the jobs from T1, whose saved results are reused because their information has not changed
   - a new job that reads the lab results or the X-ray / CT
   - the danger-sign check again, now also using any new lab results
   - summarise and make **care suggestions** for the doctor, using all of the above including the image results
   - doctor confirmation
9. The care suggestions contain:
   - a summary of the patient
   - which further tests or information to collect
   - initial care steps the doctor could consider
   - **which information the suggestion is based on**, and **what is still missing**

   If information that this suggestion requires is missing, the system **says it cannot conclude** and lists what is missing. It does not guess.
10. **The doctor** reviews the suggestions and makes their own decision. This may include **new prescriptions**.

If no tests are ordered, there is no T2 plan in the proposal's design. The doctor works from the nurse-stage summary. (Whether the doctor should also get care suggestions before any tests is an open question; see section 18.)

### Stage 3: The pharmacist (work plan T3 only if the doctor prescribes new medicines)

11. The doctor's new prescriptions cause a new work plan (T3). It contains:
    - all jobs from the earlier plan (reading jobs, danger-sign check, the doctor-stage summary). Their saved results are **reused**; nothing is run again, because their information has not changed
    - the **medication checker** job (new). The proposal calls it the **Pharma Agent**
    - pharmacist confirmation (new)
12. The medication checker compares:
    - the new prescriptions
    - Mr. A's medication list from before this visit
    - the medicines Mr. A mentioned in the conversation
    - his allergy history (from the conversation and his records)

    It lists possible problems (details in section 9.4).
13. **The pharmacist** reviews the listed problems before giving out the medicines. If there is a problem, the pharmacist contacts the doctor as they normally would. The system never changes a prescription itself.

### During the whole visit

- Every confirm, edit or reject is **recorded with who did it and when**, on the staff screen.
- The proposal's Figure 3.4 shows this journey, and its Figure 3.2 shows the three work plans. Both are in the `figures/` subfolder of this docs folder.

---

## 6. Part A: How the work-plan system works

In the proposal this is called **Case Graph**. Section 4 explained the basic idea. This section gives more detail.

### 6.1 The jobs

Every job has a fixed kind of input and a fixed kind of output. The system has a catalogue of all possible jobs:

| Job | Input | Output | When it is in the plan |
|---|---|---|---|
| Read the conversation / notes | Clinical text | Key facts | When there is text |
| Read vital signs / lab results | Numbers measured over time | Findings | When there are vitals or labs |
| Read chest X-ray | X-ray image | Findings (written), or the image in our model's format (see below) | When there is an X-ray |
| Read CT / MRI | 3D scan | Findings (written), or the scan in our model's format | When there is a scan |
| Danger-sign check | Written findings from text and vitals/labs + vital signs | Alerts | **Always** |
| Summarise and suggest (department or care) | Results of all reading jobs (written findings and/or images in our model's format) + alerts | Summary + suggestion, or "not enough information" | Nurse and doctor stages (at the pharmacist stage, the earlier result is reused) |
| Medication checker | Medication lists + findings (medicines and allergies from the conversation) | Medication problems | When the doctor wrote new prescriptions |
| Staff confirmation | The suggestion or medication problems, plus alerts (pharmacist stage: not stated, section 18) | Confirmed result | **Always** |

**"Findings, or the image in our model's format":**

- If our own model does the X-ray job, the image is converted into the form our model reads, and passed straight to our model in the summary job. It is not turned into words first.
- If an outside AI service or a small specialist AI does the X-ray job, it returns **written findings**, for example "possible fluid in the right lung". The summary job then reads these words.

This is why our model is trained on both images and written image reports (section 7.3).

The fixed input and output kinds let the system check that a plan makes sense before running it (6.2), and let us change the worker of one job (6.3).

### 6.2 Rules the system always follows

1. **Only use information that existed at that time.** When the plan is made, the system takes a copy of the patient's information that **had already arrived** by that time. Later information is not included. Results reused from an earlier plan are allowed, because their input information has not changed.
2. **Two jobs are always included:** the danger-sign check and staff confirmation.
3. **The plan is checked before it runs.** The system checks that:
   - each job receives the kind of input it expects
   - results only move forward (no job ends up waiting for its own result)
   - the two required jobs are present
   - all jobs use the same copy of the patient's information
4. **Choosing the jobs uses fixed rules, not AI.** For example: "there is an X-ray, so add the X-ray job". This is deliberate, so the plan is predictable and easy to check.
5. **"Not enough information" is allowed.** The job catalogue lists, for each suggestion job, the information it **requires**. If any of it is missing, the job does not make a suggestion. Instead it tells staff what is missing. This is also a fixed rule.
   - This is different from a reading job being left out. "No X-ray" is normal: the X-ray job is simply not in the plan. "Required information missing" means the summary job cannot give a safe suggestion without it.
   - The exact required list for each suggestion is set by the team in the job catalogue and is not fixed in the proposal yet. For example, the department suggestion would at least need the main complaint and the vital signs.

### 6.3 Each job can use a different worker

A job can be done by different kinds of **worker**:

- **our own AI model** (part B)
- **an outside AI service** through an API. Only with invented data, or data whose agreement allows it (for example, partner-hospital data if its agreement permits), **never** with MIMIC data (section 8.3).
- **a small specialist AI** that does one thing only, for example an AI that only detects abnormalities on X-rays, or one that only outlines tumours on brain MRI
- **fixed rules**, for example the danger-sign check and the medication rule checks

A job can also use more than one worker together. The medication checker uses our model to read and explain, and fixed rules to find the problems (section 9.4). The danger-sign check always uses fixed rules; its worker is never changed to an AI.

You can **change the worker for one job** without changing anything else. For example, use an outside AI service only for the X-ray job and our own model for everything else. The choice is written in a settings file, not decided by the AI. This lets us test fairly which worker is better for a job.

All calls to AI workers go through **one central entry point** (called the **Model Gateway** in the proposal). It:

- makes every AI call use the same input and output format
- records every call
- enforces the data rules, such as "MIMIC data never goes to outside services"

### 6.4 Everything is recorded

- The result of **every job** is saved, with what the job received and which worker (and which version) produced it.
- This gives three abilities:
  - **Replay:** show exactly what the system said before, by reading the saved results. The AI is not run again. This is useful for checking past decisions.
  - **Regenerate:** when new data arrives or a worker is changed, make a new plan and **run only the jobs that are affected**. Jobs whose input has not changed reuse their saved results. This saves time and cost. Every new plan in the patient journey (T2, T3) works this way.
  - **Ablation:** remove one source of information, for example the X-ray job, and run again. Comparing the two results shows **how much that information changed the suggestion**.
- Old plans are never overwritten. Each update makes a new version, so you can see how the information about the patient changed over time.
- Our model is set to give the **same answer to the same input** (no randomness), so results can be reproduced. We test this and report any differences.

### 6.5 How does this show which information led to a suggestion?

- Each reading job's input and output are saved. So you can see exactly which findings went into the summary job.
- The suggestion itself lists the information it was based on. This list is written by the AI, so it should not be fully trusted on its own.
- **Ablation** is how we actually measure the effect of each piece of information: remove it, run again, and compare.

### 6.6 Why not just send everything to one AI?

This is the key comparison in our evaluation. We compare our system with **the same AI model receiving all of the patient's information in one request**, with no work plan.

We do **not** claim a big increase in accuracy. We expect **similar accuracy**, with things that one request cannot give:

| Benefit | How we show it |
|---|---|
| Similar accuracy to one request | Measured: care-suggestion accuracy, our system vs one request (11.1) |
| Cost of the work-plan approach | Measured: number of AI calls and time, our system vs one request (11.1). Our system may make more calls per plan; the saving from reusing results is measured separately in the Replay/Regenerate test |
| Can change the worker for one job | Measured: the worker-change test (11.1) |
| Says "not enough information" instead of guessing | Measured: how often it answers, and accuracy when it does (11.1) |
| Results can be replayed; updates re-run only affected jobs | Measured: the Replay/Regenerate test (11.1) |
| You can see which findings went into each suggestion | Shown in the demo and the staff screen (saved inputs/outputs). Ablation can measure the effect of one data source |
| Danger-sign alerts go directly to staff | A design property, shown in the demo; not a number |

The proposal does not set a number for "similar accuracy" (for example, "no more than X% lower"). The team should decide this (section 18).

---

## 7. Part B: Our medical AI model

### 7.1 What it is

- Training a large AI model from nothing costs far too much for a student project, so **we don't do it**.
- We start from an existing **open-weight model**: a large AI model whose files are public and whose licence allows further training. The model we start from is called the **Base Model**.
- The target size is **about 27 billion parameters** ("27B"). This is a target, not a promise. The final size depends on the GPUs we actually get.
- **Candidates:**
  - **MedGemma 27B**: from Google, trained on medical data
  - **Qwen3.8-27B**: a general model released in August 2026, not specialised in medicine
  - **Lingshu-32B**: medical, a little larger, so it needs more GPU memory
- We choose one after a small **trial training** in semester 1. It must:
  - allow further training under its licence
  - accept images as input
  - have good results on medical benchmarks (standard tests used to compare models)
  - fit on the GPUs we actually get

### 7.2 Why not just use an existing model as it is?

- **It must run on our own machines.** MIMIC data cannot go to outside services (section 8.3), so the main worker must be an open model we run ourselves. This explains why we use an open model, but not yet why we train it.
- **None of the candidates can read a 3D CT scan directly.** We add that, and the added parts must be trained.
- **Training on medical data for our tasks** should make the model better at them, including using written findings from outside workers. We check this by comparing it with the Base Model before training (section 11). If training does not help, that is also a result we report.

### 7.3 What we add

The model has four parts:

| Part | Proposal term | What it does |
|---|---|---|
| **2D image part** | 2D Encoder | Already in the Base Model. Converts a chest X-ray into tokens the language model can read |
| **3D image part** | 3D Encoder | **Added by us.** Converts a CT scan into that form by cutting it into small 3D blocks. We start from an existing trained one (CT-CLIP), not from nothing |
| **Adapter** | Connector | **Added by us.** Reduces the 3D part's output to a fixed, limited number of tokens, so a large CT scan does not use up most of the tokens the model can handle at once |
| **Language model** | Backbone | The main part. Reads the image information and the text together, and writes the answer: a summary, suggestions, and the information it used |

- Information that is not an image is written out as text for the model to read. This includes clinical notes, vital signs, and written findings from outside workers.
- The voice parts (speech-to-text and text-to-speech) are **separate outside services**, not part of our model.

### 7.4 How we train it

1. **Trial training (semester 1):** train on a small part of the data to measure memory use and speed. Then choose the Base Model.
2. **Train the adapter:** keep the language model unchanged ("frozen") and train only the new adapter. We use CT scans paired with their radiology reports (the CT-RATE dataset), so the model learns to connect CT images with medical words.
3. **Main training:** train the model further on MIMIC and CT-RATE data using **LoRA**. LoRA adds a small set of new parameters and trains only those, instead of changing all 27 billion, so it needs much less memory and time. Two methods make the model more reliable:
   - **Randomly remove some kinds of data** in training examples, so the model still works when a patient has, for example, no X-ray.
   - **Sometimes give the written image report instead of the image**, so the model also works when an outside worker returns written findings. We only do this for tasks where the correct answer does **not** come from that same report, for example care suggestions, whose correct answers come from what the doctor actually ordered. For image-reading tasks, the correct answer comes from the report, so the report is never given as input there.

An **MRI part** would be trained the same way, but **only if** the partner hospital gives us enough MRI data. It is not in the core plan.

### 7.5 GPUs

- **Plan:** 8 NVIDIA B200 GPUs. **Not confirmed yet.**
- **Plan B:** use a smaller Base Model or train on less data, and report the real size and results honestly. The rest of the system is not affected, because it only uses the model through the central entry point.

---

## 8. The data we use

### 8.1 Datasets

| Dataset | What it contains | What we use it for |
|---|---|---|
| **MIMIC-IV** | Records from a large US hospital: lab results, prescriptions, the clinical **service** that cared for each admitted patient (a US term, close to a department such as internal medicine or surgery), and more | Training and testing; department labels; prescriptions for the medication checker |
| **MIMIC-IV-ED** | Emergency department visits at the same hospital: main complaint, first vital signs, medicines taken before arrival, medicines given in the ED, where the patient went next | First-contact cases; the "medicines before arrival" list |
| **MIMIC-IV-Note** | Written clinical notes | Clinical text |
| **MIMIC-CXR** | Chest X-rays with radiology reports, linked to MIMIC patients | Training and testing X-ray reading |
| **CT-RATE** | 3D chest CT scans with reports. These are **different patients** from MIMIC | Training and testing CT reading |
| **BraTS 2021** | Brain MRI scans with tumour outlines drawn by experts | Testing the small specialist AI that outlines tumours |
| **Thai role-play conversations** | Patient conversations written by the team with experts, acted out live by people | Testing the voice assistant |

**Access:**

- MIMIC requires **PhysioNet credentialed access**. Team members are applying for it individually.
- CT-RATE and BraTS do not need it.

### 8.2 Partner-hospital data (not confirmed)

We are discussing **3 months of past data** with a partner hospital. It may include:

- basic patient information and vital signs
- recordings of nurse–patient conversations at intake
- CT and MRI scans
- prescriptions and pharmacist review results
- patients who visited more than once

Whether we get it depends on the data agreement, ethics approval and data quality. **Do not promise this data in the presentation.**

### 8.3 Rules that protect the data and keep the tests honest

- **MIMIC data never leaves machines the team controls.** PhysioNet's guidance does not allow sending it to outside AI services or online tools, because the data is about real patients and the agreement limits who may see it. Outside services only receive **invented data**, or data whose agreement allows it.
- **No later information.** Every piece of data is labelled with **the time it became available**. When the system assesses a patient at a certain time, it only uses data from before that time.
- **Patients are split first.** Each patient is put into exactly one group: training, tuning or testing. All of a patient's images and reports stay in the same group. So the model is never tested on a patient it saw during training.
- **Diagnoses and outcomes are only used as correct answers**, never as input.
- **We check for leakage:** the same patient in two groups, or data from after the assessment time.
- **Datasets the Base Model may already have seen.** The Base Model may have been trained on public data like MIMIC-CXR. Model makers usually train only on a dataset's official training part, so we test on the dataset's **official test part** to lower the chance that the model has seen the test images. We also never give the model the report of the X-ray it is being tested on, because that report is where the correct answer comes from.

### 8.4 Preparing the data, step by step

1. List every dataset with its source, version and access conditions.
2. Convert all data into a standard format. Each item has a patient ID, a visit ID, the time it happened and the time it became available.
3. Split patients into training / tuning / testing groups.
4. Build training examples from copies of what was known at different times.
5. Run the leakage checks.

---

## 9. The app (part C) in more detail

### 9.1 Thai voice assistant (proposal term: "Voice Agent")

- **What it does:** talks with the patient in Thai and decides the next question itself. It only asks about information that is still missing.
- **What it records:** main complaint, how long the patient has had it, drug allergies, and medicines the patient takes.
- **Two modes:**
  - **Pipeline mode (main):** speech → text → AI → text → speech. Each part can be replaced, and you can read the text between the parts.
  - **Direct speech mode (optional):** an outside AI that listens and answers by voice directly. It responds faster.
- **The output is the same in both modes:** the full conversation text and the key facts. The rest of the system does not depend on the mode.
- The audio connection uses a replaceable framework (LiveKit Agents is one option), so we do not depend on a single company.
- **Test data:** only invented role-play scripts, so no real patient data reaches outside speech services.
- **How we test it:**
  - accuracy of the key facts it records
  - how quickly it responds
  - total intake time

  We compare these with the same intake done by **filling in a form**.
- **Not done, by team decision:**
  - We **don't** report a speech-recognition error rate. We measure what matters for the system: whether the key facts are correct.
  - We **don't** compare the two modes with each other.

  Both would add a lot of work for little benefit.

### 9.2 Department suggestion

- From the conversation and the vital signs, the system suggests which department the patient should go to.
- **The nurse confirms or changes it.** The system never sends a patient anywhere by itself.

### 9.3 Care suggestions for the doctor

- **Contents:**
  - a patient summary
  - which further tests or information to collect
  - initial care steps to consider
  - the information the suggestion is based on
  - the information still missing
- If required information is missing, it **says so instead of making a suggestion**.
- It does **not** show a confidence percentage. Instead, it shows the information it used and what is missing, so the doctor can judge it.

### 9.4 Medication checker for the pharmacist (proposal term: "Pharma Agent")

- **When it runs:** only when the doctor writes **new prescriptions**. It never changes prescriptions.
- **Three steps:**
  1. **Read:** the AI takes the drug name, dose and how often it is taken from each source:
     - the earlier medication list
     - what the patient said in the conversation
     - the new prescriptions
  2. **Convert and check with fixed rules:**
     - Convert drug names to standard drug codes, so the same drug written differently is recognised as the same:
       - **RxNorm** for US data
       - **TMT**, the Thai standard, for Thai data, if we get a licence
     - Check for these problems:
       - **Duplicate:** the same drug twice, or two drugs from the same drug class. Drug classes come from RxClass or ATC lists, depending on their licences.
       - **Different dose or frequency** between sources
       - **Missing:** a medicine the patient was taking is not in the new prescriptions
       - **Allergy:** a drug the patient is recorded as allergic to
  3. **Explain:** the AI writes each problem in plain words, showing which sources disagree, and sends it to the pharmacist.
- **The rules find the problems.** The AI only helps read the lists and write the explanations.
- **Is it really an "agent"?** It is an agent in the sense that it does one role's work (reviewing medication lists for the pharmacist) using AI. But it is not a free-acting agent that decides its own next actions: it always follows the same three steps, and it is one job inside the work plan, run like every other job. This is deliberate, so its results are predictable and can be checked. The same applies to the voice assistant ("Voice Agent"), except that it does choose its own next question in the conversation.
- Some listed differences will be **intentional** changes by the doctor (for example, stopping a medicine on purpose). The checker only shows the difference; the pharmacist decides whether it is a real problem.
- **Not checked:**
  - **Drug–drug interactions.** These need a licensed drug database we don't have. If we get one later, it can be added as another worker.
  - Whether the dose or treatment is medically appropriate. It only compares the sources.
- **Where the "earlier medication list" comes from:**
  - In MIMIC, it is the list of medicines taken before arrival, recorded in the emergency department.
  - In a real hospital, it would come from the hospital's existing records.
- **How we test it:**
  - **Recall** (of the real problems, how many it finds): we put known errors into real medication lists on purpose and check whether they are found.
  - **Precision** (of the problems it lists, how many are real): a pharmacist reviews a sample.
  - Both are compared with the rule checks alone, without the AI reading and explaining steps. This shows what the AI steps add.
  - **Allergy problems on MIMIC** are tested only by putting errors in on purpose. MIMIC records allergies only in notes written at the end of the hospital stay, which cannot be used as input at an earlier time.

### 9.5 Staff screen (proposal term: "Clinical Dashboard")

- **Shows:**
  - the queue of patients waiting
  - a timeline of each patient's information
  - draft summaries
  - suggested departments
  - care suggestions
  - medication problems
  - each patient's work plan, so staff can see which jobs ran
- Staff **confirm, edit or reject** results, according to their role: nurse, doctor or pharmacist.
- Every action is recorded with who did it and when.

### 9.6 Medical Passport (optional extra)

If there is time, the app can create a patient health-summary document using **confirmed information only**. It is not part of the core plan.

---

## 10. What the system does NOT do

These limits are important for safety. State them clearly in the presentation.

- It is a **research prototype in a simulated setting**. It is **not connected to any hospital system** and **not used on real patients**. Test patient records are loaded into the system, and people play the staff roles.
- It does **not diagnose**, does **not order treatment or prescribe**, and does **not send a patient to a department** without staff confirmation. Everything it produces is **support for a staff decision**.
- Testing covers **adults (18 years and older)** only.
- It is a **web app** for computers and tablets.
- The quality of Thai speech recognition depends on the speech service we choose.
- Partner-hospital data and the GPUs are **not confirmed yet**. There is a Plan B for both (section 12).

---

## 11. How we will prove it works

- All tests use **test patients** made from the **testing group** of the data (section 8.3), not live patients.
- Clinical criteria are set **with medical experts**. If we cannot get experts, we call the results a **"System Evaluation"** and do not claim clinical performance.
- Every result is reported with a **95% confidence interval**: a range showing how much the number could change by chance. We calculate it by repeatedly re-sampling the test patients (a method called bootstrap).

### 11.1 What we test

| What we test | What we measure | Compared with |
|---|---|---|
| Our AI model, for each kind of data (text, chest X-ray, CT) | Standard accuracy scores (explained below) | The Base Model before our training; for CT, also **CT-CHAT**, an existing CT AI |
| Brain MRI tumour outlining | Dice score | (tests the small specialist AI worker) |
| The work-plan system | Accuracy of care suggestions, number of AI calls, time | **Our same model receiving all the information in one request** |
| Changing the worker for one job | Accuracy, time, cost per patient | Three workers for the image job: our model, an outside AI (invented data only), a small specialist AI |
| Voice assistant | Accuracy of the key facts, response time, total time | The same intake done with a form |
| Department suggestion | How often the suggested department is correct | (no comparison system; see labels below) |
| Medication checker | Precision and recall for each kind of problem | The rule checks alone |
| "Not enough information" | How often the system gives an answer, and its accuracy when it does | A system that always answers |
| Replay and Regenerate | (1) Run the same plan again **without** the saved results and check the AI gives the same output, so saved results can be trusted. (2) Count how many jobs Regenerate runs after a change | (2) is compared with re-running every job in the plan |

**The accuracy scores:**

- **Macro-F1:** a score from 0 to 1 that combines precision and recall. It gives equal weight to rare and common abnormalities.
- **AUROC:** a score for how well the model separates "abnormal" from "normal" cases. 0.5 means no better than random guessing, and 1 is perfect.
- **Report accuracy:** how correct a written image report is. The exact method is not decided yet.
- **Dice:** how much a predicted tumour outline overlaps the expert's outline, from 0 (none) to 1 (exact).

### 11.2 Where the correct answers come from

The correct answers (called **labels**) always come from information the AI did **not** receive as input:

- **Model:** abnormalities written in the X-ray and CT reports.
- **Department:** the first hospital service that cared for the patient in MIMIC, converted to department names using a table made with experts.
  - This is an **approximation** (proposal term: "Proxy Label"). It only works for emergency patients who were admitted to the hospital.
  - These are US hospital admissions, which may differ from patients arriving at a Thai hospital. We state this as a limitation.
- **Care suggestions:** the tests the doctor actually ordered after that time, plus expert scoring of a sample.
- **CT and MRI:** these patients are not MIMIC patients, so the CT and MRI jobs are tested **on their own datasets**, not inside full patient journeys.

---

## 12. Plan B for each risk

| Risk | Plan B |
|---|---|
| MIMIC access is late | Start the model work with CT-RATE (CT). Test the work-plan system, the voice assistant and the medication checker on **invented patients**, with planned timelines and planted medication problems. Report those results separately |
| No MIMIC access by test time | Same as above. The tests that need real records and experts (department suggestion, care suggestions including the one-request comparison, and medication-checker precision on real lists) cannot be done properly. For those parts we report only that the system works correctly |
| No partner-hospital data | Use public datasets and invented conversations as planned. No MRI part for our model |
| Not enough GPU | Smaller Base Model or less training. Report the real size |
| No experts | Report results as a "System Evaluation" |
| No licensed drug database | Drug–drug interactions stay out of scope. Use TMT only if we get a licence |

---

## 13. Who does what, and when

### 13.1 Team

| Member | Main responsibilities |
|---|---|
| **จักรภัทร** | Literature and dataset review; choosing data and checking its quality; connecting workers to jobs (semester 1) |
| **ธัญรดา** | UI design; staff screen; care-suggestion system; medication checker (semester 1); Medical Passport (if time) |
| **ภูริณัฐ** | PhysioNet access; hospital coordination; data pipeline; making and running work plans; voice assistant; medication checker (semester 2); connecting workers (semester 2); testing the model |
| **ธนาพล (Wan)** | Choosing the Base Model; trial training; 3D image part + adapter; main training; designing the data and job types; Replay and Regenerate |
| **สุปรียา** | Invented patients and conversations; evaluation criteria; experiments and analysis; system and usability testing |

The AI research and development parts (the model, and the core of the work-plan system) belong to **ธนาพล** and **ภูริณัฐ**.

**How the work runs in parallel:**

- The data and model work, the work-plan system and the app are built **at the same time**.
- A shared data format is agreed at the start.
- While the model is being trained, the work-plan system and app are tested with **invented data and existing AI models**.
- Everything is connected and evaluated together in semester 2.

### 13.2 Key dates

| Date | What |
|---|---|
| 2 Oct 2026 | Proposal + Self Assessment were due |
| **8–9 Oct 2026** | **Proposal presentation** |
| 4 Dec 2026 | Progress report |
| 14–15 Dec 2026 | Progress presentation |
| Apr–May 2027 | Final report and final presentation |

### 13.3 What we deliver

**End of semester 1:**

- data access and a data pipeline
- the chosen Base Model and trial-training results
- a first version of the work-plan system that saves results
- first versions of the voice assistant, the medication checker and the staff screen
- progress report

**End of semester 2:**

- the trained medical model with 2D and 3D image parts
- the full work-plan system with our model and outside workers
- the app working from intake to staff confirmation
- all evaluation results
- source code, documentation and the final report
- Medical Passport (if time)

The week-by-week Gantt chart is in `15-project-plan.md`.

---

## 14. Tools we use (short)

| Area | Tools |
|---|---|
| Web app | React, Next.js, TypeScript |
| Server | Python, FastAPI |
| Work-plan system | Python (Pydantic for data types, asyncio for running jobs at the same time) |
| Database and files | PostgreSQL, object storage |
| Training the model | PyTorch, Hugging Face Transformers, PEFT (for LoRA), DeepSpeed |
| Running the model | vLLM (a fast model server), behind the central entry point |
| Medical images | pydicom, SimpleITK, MONAI (libraries for reading and preparing medical images) |
| Voice | Whisper-family speech-to-text, a text-to-speech service, a voice framework such as LiveKit Agents |

---

## 15. Questions the committee may ask, with short answers

**"Isn't 'case-adaptive' just if-else?"**
Yes. Choosing the jobs is rule-based **on purpose**, so it is predictable and can be checked. The research is not the if-else itself. It is whether a per-patient work plan can:

- keep the accuracy of sending everything to one AI
- make every result traceable
- allow one job's worker to be changed
- refuse to answer when information is missing
- update by re-running only the affected jobs

We measure most of these (section 11.1): the one-request comparison, the worker-change test, the "not enough information" test, and the Replay/Regenerate test. Traceability is shown in the demo, where staff can see which findings went into each suggestion.

**"Why not send everything to one AI?"**
That is exactly what we compare against. We expect similar accuracy. Our system adds traceability, changing the worker per job, safe "not enough information" answers, alerts that go directly to staff, and cheaper updates.

**"Why train your own model instead of using MedGemma as it is?"**
MIMIC data cannot be sent to outside services, so we need an open model on our own machines. None of the candidates reads 3D CT directly, so we add and train a 3D part. We also train on medical data for our tasks, and we measure whether this helps by comparing with the Base Model before training.

**"Isn't the danger-sign check triage?"**
No. It is an extra safety check with fixed rules. It **flags** possible danger and sends the alert straight to staff. It does not **rank** patients by urgency or replace staff judgement.

**"Why no drug–drug interaction check? Isn't that the most important one?"**
It is important, but a reliable check needs a licensed drug-interaction database, which we don't have. The checker is built so it can be added as another worker if we get one. Our four checks (duplicates, dose/frequency differences, missing medicines, allergies) match what medication reconciliation is for: finding differences between medication lists.

**"Is the scope too big for five students?"**

- The parts are built in parallel and connect through a shared data format and one central entry point for AI calls.
- Each uncertain resource (data, GPUs, experts) has a Plan B, so every objective can still be tested on public and invented data.

**"Is the department label reliable?"**
It is an approximation, and we say so. It comes from the hospital service that first cared for admitted emergency patients in MIMIC, converted with experts.

**"Could the Base Model have already seen MIMIC-CXR?"**
Possibly. That is why we test on the official test part and never give the model the report it is tested against.

**"Will you send patient data to ChatGPT or other AI services?"**
No. MIMIC data stays on machines the team controls. Outside services only receive invented data or data whose agreement allows it.

**"Will you definitely get hospital data?"**
It is not confirmed. The plan works without it.

**"Do you already have a working prototype?"**
Answer only with what actually exists at the time of the presentation. Never claim more than we have.

---

## 16. Proposal terms and what they mean

| Proposal term | Meaning |
|---|---|
| Case Graph | The work-plan system (part A) |
| Case-Adaptive | The jobs change according to each patient's available information |
| Typed DAG | A work plan: jobs with fixed input/output types, joined by arrows that only go forward (no loops) |
| Case Graph Compiler | The part that **makes and checks** the work plan |
| Typed Graph Executor | The part that **runs** the jobs in the correct order and waits for staff confirmation |
| Node | One job in the work plan |
| Node Library | The catalogue of all possible jobs and what each one needs |
| Reader Node | A job that reads one kind of data (text, vitals/labs, X-ray, CT/MRI) |
| Red-flag Node | The danger-sign check |
| Reasoning Node | The summarise-and-suggest job |
| Human Checkpoint | Staff confirmation |
| Provider | The worker that does a job |
| Model Gateway | The central entry point for all AI calls |
| Findings | Written results from a reading job |
| ImageTokens | An image converted into our model's format (only our model can use it) |
| Snapshot | The copy of everything known about the patient up to a given time |
| Assessment time | The time a work plan is made for (T1, T2, T3) |
| Availability time | The time a piece of data became available |
| T1 / T2 / T3 | The work plans for the nurse, doctor and pharmacist stages |
| Output Store | Where every job's result is saved |
| Cache Key | A fingerprint of a job's inputs and settings. If it is unchanged, the saved result is reused |
| Replay / Regenerate / Ablation | See section 6.4 |
| Abstention | Saying "not enough information" |
| Base Model | The existing public model we start from |
| Open-weight | The model's files are public and may be trained further |
| Encoder | An image part of the model (2D or 3D) |
| Connector | The adapter |
| Backbone | The language model part |
| Fine-tune | Training an existing model further for our tasks |
| LoRA | A cheaper way to fine-tune, by training a small set of added parameters |
| Modality Dropout | Randomly removing some kinds of data during training |
| Multimodal | Able to handle several kinds of data (text, images, numbers) |
| Foundation Model | A large AI model trained on lots of data that can be used for many tasks |
| Voice Agent | The Thai voice assistant |
| Cascade / Realtime | Pipeline mode / direct speech mode of the voice assistant |
| Pharma Agent | The medication checker |
| Medication Reconciliation | Comparing medication lists from different sources to find differences |
| RxNorm / TMT | Standard drug code systems (US / Thai) |
| RxClass / ATC | Lists of drug classes |
| Synthetic Error Injection | Putting known errors into data on purpose to test whether they are found |
| Proxy Label | An approximate correct answer |
| Data leakage | The AI receiving information it should not have, such as later information or test patients |
| Precision / Recall | Of the problems listed, how many are real / of the real problems, how many are found |
| Macro-F1 / AUROC / Dice | Accuracy scores (section 11.1) |
| 95% CI (bootstrap) | The range a result could vary by chance (section 11) |
| AI Clinical Front Door | The demonstration app (part C) |
| Clinical Dashboard | The staff screen |
| CT-CLIP / CT-CHAT | Existing CT AI models: the starting point for our 3D image part / a model we compare with |
| CT-RATE / BraTS | Public CT-with-reports dataset / brain MRI tumour dataset |
| AHRQ / ASHP | US healthcare organisations whose guidance we follow for medication reconciliation |

---

## 17. Where to find more detail

| Topic | File |
|---|---|
| Overview and objectives | `00-project-overview.md` |
| Decisions and why | `01-decisions-log.md` |
| System design (work plans, jobs, entry point) | `02` to `07` |
| The AI model | `08-multimodal-model.md` |
| Data | `09-data.md` |
| Voice assistant | `10-voice-agent.md` |
| Medication checker | `11-pharma-agent.md` |
| Suggestions and staff screen | `12-care-suggestion-and-dashboard.md` |
| Patient journey | `13-front-door-workflow.md` |
| Evaluation | `14-evaluation.md` |
| Tasks and Gantt | `15-project-plan.md` |
| Open questions and risks | `20-open-questions.md` |

---

## 18. Questions the proposal does not answer yet

The team should agree on answers to these. They are also listed in `20-open-questions.md`.

- **Care suggestions before any tests.** In the proposal, the doctor-stage plan is only made when new test results arrive. Should the doctor also get suggestions (for example, which tests to order) at the first consultation, before any tests?
- **Does a staff confirmation start a new work plan?** The confirmed result is saved as new patient information, but the proposal doesn't say whether that alone creates a new plan.
- **Which danger-sign rules exactly?** These are not defined yet. Should alerts appear **during** the voice conversation, not only after it?
- **Alerts at the pharmacist stage.** It is not clear whether danger-sign alerts are shown to the pharmacist.
- **CT inside the patient journey.** CT-RATE patients are not MIMIC patients, so CT is tested separately. How will CT appear in the end-to-end demonstration?
- **Which test data for the worker-change test?** Outside AI services may only see invented data, but the proposal names no invented image set.
- **What information is "required" for each suggestion?** This decides when the system says "not enough information".
- **What counts as "similar accuracy"** in the main comparison?
- **What is the first-contact input for MIMIC test patients?** MIMIC has no voice conversations, so the department test needs another text source, such as the recorded main complaint.
- **Edited results.** If the nurse edits the summary, do later plans use the edited version?
- **Image findings and danger signs.** Should written findings from X-ray/CT (for example, from an outside worker) also be checked by the danger-sign rules?
- **Exact setting.** Is the first point of contact an emergency department or an outpatient department? The proposal does not say, and the MIMIC data is from an emergency department.
