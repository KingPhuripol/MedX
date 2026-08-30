# Codebase Concerns

> ⚠️ **Generated snapshot, extracted 2026-08-11 — partially stale.** It still describes the
> flagship as approximately 4B. DEC-0009 (2026-08-26) makes the flagship approximately 27B and
> withdraws the 4B target. Authority sits with `docs/` and `project_state/` (DEC-0008); read
> `docs/DECISION_LOG.md` before relying on any scale figure here.

**Analysis Date:** 2026-08-11

## Critical: Imminent Deadline with Zero Implementation

**Group Application Due in 3 Days (2026-08-14 23:55 Asia/Bangkok)**

**Concern:** The project has 3 days to submit a group application, yet no actual implementation exists. The codebase contains ~1,155 lines of governance scaffolding, JSON validation, and documentation templates, but zero code for:
- ML training pipeline or model loading
- API server or clinical decision-support system
- Data loading, preprocessing, or management
- Graph routing or computation engine
- Evaluation framework

**Files:** All of `src/`, `research/`, `innovation/` are either missing or README-only stubs; actual implementation will need to be created post-submission.

**Impact:** HIGH. Missing Group Application triggers escalation (RISK-0001); if not submitted by deadline, the entire project loses official standing.

**Recommendation:** Confirm advisor and submission status immediately (this is P0 per PROJECT_CHARTER.md). Consider whether submission timeline allows for meaningful technical work in the harness before October proposal (23 days away).

---

## Schema Validator Missing Critical JSON Schema Features

**Critical Gaps in `scripts/harness_lib.py`**

The hand-rolled JSON Schema validator (lines 55-120) implements a subset of JSON Schema 2020-12 but silently does NOT enforce:

| Feature | Impact | Risk |
|---------|--------|------|
| `$ref`, `allOf`, `anyOf`, `oneOf` | Cannot compose schemas or validate alternatives | Experiment manifests with conditional fields may pass validation despite being semantically invalid |
| `patternProperties`, `dependentRequired` | Cannot validate conditional required fields | API contracts missing required-if-X fields will not be caught |
| `maxLength`, `maxItems`, `multipleOf`, `exclusiveMin/Max` | Truncated numeric/string validation | Manifest fields with overly large values (e.g., max_steps=999999999) pass without warning |
| Format validation (only date/date-time) | Ignores "email", "uuid", "uri" | Model IDs, email contacts, URIs could be malformed undetected |
| Nested schema objects | Line 41: unknown keywords return True silently | Unknown/typo'd schema keywords are ignored, allowing drift between intent and actual validation |
| YAML frontmatter with colons in values | Lines 145-146 split on first colon only | Values like `"key: value: with: colons"` will truncate |
| Multi-line values in frontmatter | Not supported | Agent descriptions, decision rationale spanning lines will be truncated |

**Files:** `scripts/harness_lib.py` (validates all JSON state and contracts via `scripts/verify_harness.py`)

**Current Use:** All state validation depends on this: official deadlines, tasks, risks, decisions, approvals, experiment manifests, patient journeys, model API contracts.

**Impact:** MEDIUM-HIGH. Malformed or semantically incorrect state can enter project_state/*.json and schemas/*.json without automated detection. Manual review catches most issues, but validators create false confidence.

**Recommendation:** Either (a) integrate `jsonschema` library (single dependency) with full 2020-12 support, or (b) explicitly document and freeze the supported subset in a VALIDATOR_SPEC.md with a test harness covering each unsupported feature.

---

## Approval Gate: Pattern Matching Brittleness and Bypass Surface

**Security-Relevant Control with Regex Vulnerabilities**

`.claude/hooks/approval_gate.py` uses regex patterns to gate expensive, publishing, destructive, and data-transfer commands before they run. **Serious bypass risks:**

### Data Transfer Detection (Lines 59-64)

```python
r"\b(?:curl|wget|scp|rsync)\b[^\n]*(?:data/|patient|journey|medical|dataset|checkpoint)"
```

**Gaps:**
- Looks for literal directory names: `data/`, `patient`, `journey`, `medical` — easily bypassed with:
  - `data_`, `data-`, `Data/` (different case/separator)
  - `pt_`, `case_`, `subject_` (aliases for patient)
  - `patient_journeys/` (nested path) — the regex looks ahead but underscore breaks word boundary `\b`
- Does not catch:
  - Variables containing patient data indirectly (e.g., `curl ... $ENCODED_DATA`)
  - Zip/tar archives with obfuscated names
  - Piped transfer (`cat data.tar | ssh remote 'tar x'`)

**Risk:** Real or identifiable patient data could be transferred to an external endpoint without triggering the approval gate.

### Publish/Deploy Detection (Lines 38-45)

Misses:
- `git push` to package registries (e.g., git push to a PyPI-like remote)
- Direct uploads via library imports (e.g., Python `requests.post(...)` in code, not bash)
- Docker registry pushes via API (not CLI)

### Compute Detection (Lines 29-35)

Assumes single `--num-gpus` or `--nproc-per-node` argument format; misses:
- `--gpus all` or `--gpus 0,1,2,3` (non-numeric)
- Config files (e.g., `torchrun --nproc_per_node=4 config.yaml`)
- Environment variable override (`NPROC=8 torchrun ...`)

### Hook Registration Risk (Lines 104-109)

If the hook is not registered in `.claude/settings.json` or fails silently, dangerous commands execute without approval. Currently hooked only in PreToolUse for Bash/Write/Edit/NotebookEdit — does NOT gate:
- Direct Python subprocess calls (if code existed)
- MCP tool use (if defined)

**Files:** `.claude/hooks/approval_gate.py`

**Impact:** MEDIUM. Actors with repo write access could bypass the gate via obfuscated command patterns or alternate execution paths.

**Recommendation:** 
1. Replace regex patterns with a more robust allowlist (whitelist safe commands) rather than denying known bad ones.
2. Augment with runtime data-access instrumentation (not just bash pattern matching).
3. Add integration tests covering the documented bypass cases.
4. Hook all tool types that could execute code, not just Bash.

---

## Harness Verification: Schema Validation Without Semantic Correctness

**`scripts/verify_harness.py` Gaps**

The verification script validates JSON structure against schemas but does NOT check semantic correctness. Specific gaps:

### Patient Journey Validation (Lines 254-261)

```python
event_ids = [item["event_id"] for item in journey["events"]]
checks.require(len(event_ids) == len(set(event_ids)), "patient fixture event IDs are not unique")
```

**Missing checks:**
- Patient split integrity: Harness does not verify that a given patient_id appears in exactly one split across ALL journey files. This is checked by `temporal_leakage_audit.py` (line 93-95), but that tool must be manually run and is not part of pre-training gates.
- Temporal ordering: No validation that events are in chronological order or that `observed_at` makes sense.
- Required event types: No enforcement that certain event types (e.g., CHIEF_COMPLAINT, DISPOSITION) are present.
- Payload consistency: No check that events marked AVAILABLE have valid payloads or that CORRUPT events are properly flagged.

### Experiment Manifest Approval Gate (Lines 178-181)

```python
tier_requires = manifest["run_tier"] >= 3
checks.require(manifest["approvals"]["required"] == tier_requires, ...)
if manifest["status"] in {"approved", "running", "completed"} and tier_requires:
    checks.require(bool(manifest["approvals"]["approval_ids"]), ...)
```

**Issues:**
- Checks that approval IDs exist but does NOT validate:
  - Whether the approval ID is actually valid (exists in `project_state/approvals.json`)
  - Whether the approval covers the actual risk/resource/action declared
  - Whether the approver had authority to approve (no role/permission matrix)
  - Whether the approval is still valid (no expiration/reconsideration logic)

### Decision Dependency Validation (Lines 164-172)

Validates that referenced task IDs exist but does NOT check:
- Task dependencies are acyclic (no circular dependencies)
- Critical tasks have evidence/completion status tracked
- Blocking dependencies are resolved before execution

**Files:** `scripts/verify_harness.py`

**Impact:** MEDIUM. Malformed experiments and incomplete data can pass harness verification, creating false assurance. Real validation must happen at runtime (e.g., before training starts).

**Recommendation:** 
1. Integrate `temporal_leakage_audit.py` as a mandatory pre-training gate (not optional manual run).
2. Add semantic validators for critical fields (e.g., patient split uniqueness, event ordering, required event types).
3. Create an approval validator that cross-references approvals.json and validates authority.

---

## Temporal Leakage Audit: Reactive Tool, Not Preventive Gate

**Manual Tool, Not Automatic Gate**

`scripts/temporal_leakage_audit.py` is a standalone audit script that must be manually invoked. It checks for:
- Patient split integrity (lines 93-95)
- Temporal consistency (lines 38-51)
- Future data usage (lines 46-51)

**Concern:** No integration into training pipeline or pre-execution gates. According to CLAUDE.md:
> "Run `/data-audit` and `/temporal-leakage-audit` before training and after any data-pipeline change."

**But:** There is no code to enforce this. An agent or training script could load data without running the audit. The audit is only checked if a human remembers to run it.

**Files:** `scripts/temporal_leakage_audit.py` (standalone, not integrated into training harness)

**Risk:** CRITICAL for data integrity. Temporal leakage or patient overlap could invalidate results, and the audit only catches it after the fact if manually run.

**Impact:** HIGH. Ties directly to RISK-0003 (Temporal or patient-identity leakage invalidates results).

**Recommendation:** 
1. Create a mandatory pre-training validation step that runs `temporal_leakage_audit.py` programmatically and fails if errors detected.
2. Add this check to any experiment manifest execution flow.
3. Document the expected behavior: training code should call `temporal_leakage_audit()` or equivalent before loading data.

---

## No Dependency Versioning or Lock Files

**Environment Reproducibility Missing**

The codebase has no `requirements.txt`, `setup.py`, `pyproject.toml`, `Pipfile`, `environment.yml`, or `.python-version` file.

**Consequence:** 
- `scripts/harness_lib.py` claims "dependency-free" (line 2), but imports Python 3.9+ standard library only.
- No explicit Python version requirement recorded.
- If actual training code uses PyTorch, transformers, numpy, pandas, etc., no version pinning means:
  - Reproducibility breaks over time as libraries update
  - Different team members may use different versions
  - Commit history cannot guarantee exact environment

**Files:** Missing from root directory.

**Impact:** MEDIUM. Makes reproduced results harder to verify. Research papers require exact dependency versions for credibility.

**Recommendation:** Create `pyproject.toml` (or equivalent) with pinned versions for all dependencies (once training code is written). Include in research release artifacts.

---

## Hook Execution Risks: Timeout and Silent Failure

**Post-Edit Validation Hook Brittleness**

`.claude/settings.json` line 78 defines PostToolUse hook with 55-second timeout for verification:

```json
{
  "type": "command",
  "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/post_edit_checks.py",
  "timeout": 60
}
```

**Risk:** If verification:
- Takes longer than 60 seconds (possible on large manifests or slow systems)
- Encounters a transient error (network, file lock, etc.)
- Crashes unexpectedly

Then `.claude/hooks/post_edit_checks.py` returns non-zero, but there is no clear user feedback about what failed. Line 47 in post_edit_checks.py prints to stderr, but Claude Code behavior on hook failure is not documented.

**Impact:** MEDIUM. A single slow verification run or system hiccup could silently break the validation gate without clear indication. Subsequent edits might proceed without verification.

**Recommendation:** 
1. Increase timeout to 120 seconds and add logging/summary output.
2. Document expected behavior on hook timeout in .claude/rules.
3. Add retry logic or fallback behavior.

---

## Documentation-Code Drift: Contracts Are Governance Source of Truth, But Not Validated

**CLAUDE.md Governance Model vs. Automation Gap**

CLAUDE.md states:
> "When documents conflict, contracts and accepted Decision Log entries override plans; plans override status summaries."

This means docs are the source of truth. But:

### Frontmatter Parsing Is Fragile (Lines 129-147 in `harness_lib.py`)

```python
key, value = line.split(":", 1)
values[key.strip()] = value.strip().strip('"').strip("'")
```

**Issues:**
- Strips only outer quotes; inner quotes remain
- No escape sequence handling (e.g., `\"`, `\n`, `\t`)
- Multi-line YAML values not supported
- Silently ignores malformed lines (line 141: `if not stripped or ... continue`)

Agent prompts in `.claude/agents/*.md` frontmatter may be truncated or misread.

### No Checksum/Hash Validation

Nothing validates that a doc's frontmatter matches its actual content. A prompt could claim "comprehensive setup instructions" but be blank.

### Semantic Correctness Not Verified

Harness checks that official_deadlines.json matches the canonical registry (lines 188-192), but does NOT verify:
- That dates in docs match dates in JSON
- That agent names in docs match agents actually defined
- That risk IDs referenced in experiments actually exist in risks.json
- That task descriptions match task status/dependencies

**Files:** `scripts/harness_lib.py` (frontmatter parser), `scripts/verify_harness.py` (verification logic)

**Impact:** MEDIUM. Drift between doc claims and machine state could go undetected, causing confusion during execution.

**Recommendation:** Add a semantic cross-validation pass in `verify_harness.py` that checks:
- Agent names mentioned in docs match defined agents
- Risk IDs match defined risks
- Task descriptions align with status (DONE tasks have evidence, IN_PROGRESS tasks have owner)

---

## Zero CI/CD, Testing, or Linting Infrastructure

**No Automated Quality Gates**

The codebase lacks:
- **Test framework/files:** No pytest, unittest, or test_*.py files (lines 95-106 in verify_harness.py have reference to test fixtures but no test execution)
- **CI pipeline:** No `.github/workflows/`, `.gitlab-ci.yml`, or equivalent
- **Linting:** No `.eslintrc`, `pyproject.toml[tool.pylint]`, `ruff.toml`, or equivalent
- **Code formatting:** No `.prettierrc` or black config
- **Type checking:** No mypy.ini or pyright config
- **Pre-commit hooks:** No `.pre-commit-config.yaml`

**Consequence:** Bugs in harness scripts (`harness_lib.py`, `verify_harness.py`, hooks) can slip through undetected. The harness is the system that validates governance, so harness bugs are critical bugs.

**Files:** Missing at root and in `.claude/`.

**Impact:** MEDIUM-HIGH. Code quality and correctness are unverified. A typo in the approval gate regex could disable a critical security control.

**Recommendation:** 
1. Add pytest with 100% coverage target for harness_lib.py (test all validator code paths).
2. Add mypy with strict mode for all Python scripts.
3. Add GitHub Actions workflow that runs tests + linting on all changes.

---

## Research Gates Not Yet Defined or Automated

**Risk-0004, Risk-0005, Risk-0007 Lack Enforcement Mechanisms**

RISK_REGISTER.md defines research gates (e.g., lines 10-11, 14-15), but the codebase does NOT implement:

### 4B Gate Requirements (RISK-0004)

> "The 4B run is prohibited until small-model evidence shows: case-dependent graph diversity; no routing or all-node collapse; competitive task quality against fixed-path and static-DAG baselines..."

**Current state:** No code to check these criteria. No manifest field to mark "4B gate cleared." The experiment manifest schema allows any model parameter_count; there is no validation that 4B > parameter_count requires prior evidence.

### Routing Collapse Detection (RISK-0005)

> "Entropy/load constraints, curriculum, operator ablations, kill tests"

No evaluation code exists to compute graph entropy, load distribution, or routing diversity metrics.

### Safety Gate (RISK-0007)

> "Red-flag override, abstention, conservative escalation, human confirmation"

No code implements these safety checks. They exist only in SAFETY_SPEC.md; PRODUCT_SPEC.md and API contracts (MODEL_API_CONTRACT.md) reference them but provide no implementation guidance.

**Files:** RISK_REGISTER.md, docs/research/ARCHITECTURE_SPEC.md, docs/innovation/SAFETY_SPEC.md

**Impact:** HIGH. Gates exist on paper but not in code. A team member could propose a 4B run, claim evidence exists, and no automated check would block it.

**Recommendation:** Create executable gate checks in verify_harness.py or a new gates.py script. For each risk gate, define what evidence must be present before proceeding:
- 4B gate: Require completed experiment manifest for 1B/2B models with specific metrics in evaluation records.
- Routing gate: Require quantitative metrics (graph entropy ≥ X, load std ≥ Y).
- Safety gate: Require sensitivity/specificity results above thresholds on external test set.

---

## Official Deadlines: Single Point of Failure with Weak Validation

**Immutable Deadlines in `project_state/official_deadlines.json` Under-Protected**

`official_deadlines.json` is protected at the path level (approval_gate.py line 23), but:

### Validation Gaps

`.claude/hooks/approval_gate.py` only checks file path, NOT content. Someone could:
- Create a different file (`project_state/deadlines_revised.json`) with altered dates
- Modify the "status" field from NEEDS_CONFIRMATION to COMPLETE without approval
- Change timezone from Asia/Bangkok to UTC without detection

Verification (verify_harness.py line 192) checks against a hardcoded CANONICAL_DEADLINES list, but:
- If the canonical list is accidentally edited, no warning
- No cryptographic signature on the registry file
- No immutability marker that persists across commits

### Status Field Under-Checked (Line 4 in `official_deadlines.json`)

```json
"transcription_status": "PENDING_VISUAL_VERIFICATION"
```

**Risk:** If transcribed from a PDF source and the source PDF is not available (line 4: "source_file_present": false), then no one can verify the dates are correct against the original source. The comment in PROJECT_CHARTER.md line 21 acknowledges the advisor is not yet recorded.

**Files:** `project_state/official_deadlines.json`, `.claude/hooks/approval_gate.py`, `scripts/verify_harness.py`

**Impact:** MEDIUM. Dates are critical for the project. If altered (even accidentally), everyone operates on false deadlines.

**Recommendation:** 
1. Require source PDF to be committed to repo (even if redacted for privacy).
2. Add cryptographic hash or GPG signature to official_deadlines.json in verification script.
3. Implement a status workflow: PENDING_VERIFICATION → VERIFIED_AGAINST_SOURCE → IMMUTABLE (blocks all edits).

---

## YAML Frontmatter Parsing: Multi-Line Values and Colon Handling

**`scripts/harness_lib.py` Lines 129-147**

```python
for number, line in enumerate(lines[1:end], start=2):
    ...
    key, value = line.split(":", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
```

**Issues:**

1. **Colons in Values:** If a value contains a colon (e.g., `description: "This is a description: with details"`), the split works correctly (split on first colon only), but the quote-stripping logic is naive:
   - `"value: with: colons"` becomes `"value: with: colons"` (quotes remain)
   - Downstream code treating this as a string may fail if it expects unquoted value

2. **Multi-Line YAML:** If an agent description spans lines (standard YAML), the parser silently ignores continuation lines:
   ```yaml
   description: |
     This is a very long description
     that spans multiple lines
   ```
   Only the first line is captured.

3. **Escape Sequences:** No support for `\n`, `\t`, `\"` in frontmatter values.

**Files:** `scripts/harness_lib.py` lines 145-146

**Impact:** LOW-MEDIUM. Affects agent/skill descriptions in `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` only; these are read by humans, not interpreted as code. But could cause confusion if descriptions are truncated.

**Recommendation:** Replace with proper YAML parser (e.g., PyYAML) if descriptions become code-relevant (e.g., skill automation triggers).

---

## Patient Data Privacy: No Runtime Enforcement Beyond Approval Gate

**Data Rules in CLAUDE.md Not Enforced by Code**

CLAUDE.md lines 34-40 define strict data rules:
> "Do not send real, identifiable, or linkable patient data to an external API without explicit authorization... Preserve missingness. Never silently treat missing as negative... Fit normalization on training data only."

**Current enforcement:** Only the approval gate checks for `curl|wget` to a path containing `data/`, `patient`, etc. But:

1. **No training code exists yet** — once it does, data loading/preprocessing code must enforce:
   - No data sent to external APIs (but no runtime check will prevent this)
   - Imputation/normalization fit on train split only (but no data loader validates splits)
   - Missingness preserved in features (but no data validation enforces this)

2. **Approval gate is command-level only** — does NOT catch:
   - Python code that loads data and sends to external API (e.g., `requests.post(...)`)
   - Synthetic data being logged/printed (could leak in logs)
   - Snapshots of data in experiment artifacts (checkpoints might contain activations from real data)

3. **No audit trail of data access** — no logging of:
   - When data was loaded, from where, by whom
   - What transformations applied
   - Which experimental runs used which data versions

**Files:** CLAUDE.md (rules, no code), `.claude/hooks/approval_gate.py` (partial enforcement)

**Impact:** HIGH. This is a critical research integrity and clinical safety issue. Temporal leakage, data leakage to external providers, or inclusion of real patient IDs in public releases would be catastrophic.

**Recommendation:** 
1. Implement data loader that validates:
   - Patient split integrity before loading
   - Available_at_time constraints for each sample
   - No external API sends without explicit authorization check
2. Add data provenance logging to experiment execution.
3. Implement pre-training manifest validation that requires:
   - `temporal_audit_id` (proof audit was run)
   - `split_checksum` matching committed data directory
   - Explicit `external_api_authorization: [APPROVED_RECORD_ID]` if external providers used

---

## Summary: Priority Triage

| Severity | Category | Action |
|----------|----------|--------|
| **CRITICAL** | Group Application (3 days) | Confirm submission status immediately; coordinate with advisor |
| **CRITICAL** | Data Privacy Enforcement | Add runtime validation for temporal leakage and external API sends |
| **HIGH** | Schema Validator Gaps | Document limitations or integrate jsonschema library |
| **HIGH** | Temporal Leakage Gate | Integrate audit as mandatory pre-training check |
| **HIGH** | Research Gates Missing | Define executable gate conditions in code; add manifest validation |
| **MEDIUM** | Approval Gate Brittleness | Add integration tests for bypass cases; strengthen patterns |
| **MEDIUM** | Harness Semantic Validation | Add cross-references (agents, risks, tasks) verification |
| **MEDIUM** | Documentation Drift | Add semantic cross-validation to verify_harness.py |
| **MEDIUM** | Testing & Linting | Add pytest + mypy + GitHub Actions CI |
| **LOW** | YAML Parsing | Low priority until descriptions become code-relevant |

---

*Concerns audit: 2026-08-11*
