# Slice ctrate-r1 — close the CT-RATE loader reviewer conditions (before any real download)

- Branch `factory/ctrate-r1` from `main` f9dd06e. Tier 0 only: CPU, synthetic fixture, offline tests. No download, no network, no GPU, no external API, no training.
- Gantt: task 5 data pipeline (owner ภูริณัฐ); label quality reviewed with จักรภัทร (task 4).
- Source of truth: `docs/PROPOSAL.md` v9.6 §3.3 (a report replaces an image only for tasks whose label does not come from that report), §3.4 (patient split before samples, typed items with available time, report never input when it is the label source, leakage checks), §3.6 (CT-RATE abnormalities taken from reports are labels not fed to the model; CT readers evaluated separately). Also CLAUDE.md data rules 1–8 and the human approval gates.
- Input: `slices/CONDITIONS.md` section "ctrate-loader (CONDITIONAL_PASS ×2, 2026-10-03)", the six non-human rows. Original spec: `slices/ctrate-loader/SPEC.md` (its B1–B9 stay binding).

## Scope

Files the builder may change: `research/data/ctrate/{loader,audit,access,build,types,__main__}.py`, `research/tests/test_ctrate_*.py`, `research/tests/ctrate_fixture.py` (additive: e.g. a valid patient with scans `a` and `b`), `research/train/data.py` (R2 only, CT-RATE branch only), `slices/CONDITIONS.md`.

1. **R1 no_chest file is required.** Every `no_chest_{split}.txt` listed in `ctrate.manifest.json` `expected_files` is required. A missing file adds `RowError(<path>, 0, "missing_file", …)` and `load_tree` raises `CTRateLoadError`; `build` writes nothing. A present, empty file still means zero exclusions.
2. **R2 same-patient reports are blocked.** In `report_provenance`, for CT-RATE refs only: if the report and the label source are different scans of the same patient (same `<split>_<pid>` after `canonical_source_id` normalization), the verdict is a new `same_patient` value. Substitution is refused, `decide_modalities` counts it in `events["blocked_same_patient"]`, and the `Collator` safety net raises `ReportLeakageError` for it like `same_source`. `train_k` and `valid_k` stay different patients. Verdicts for every other dataset are unchanged.
3. **R3 independent missingness audit.** `run_audit(build, raw=<root>)` and `audit <build> --raw <root>`: the `missing_not_negative` step re-reads the raw label CSVs with the stdlib `csv` module only. It must not call `load_tree`, `_read_table` or any loader parser, and it must not use `manifest.counts`. For every gold case present it checks, cell by cell: a raw blank is `"missing"` in gold, a raw `0` is `"0"`, a raw `1` is `"1"`. A scan with no raw label row is `labels_status: missing`. A gold case with no raw row, or a raw row of an unsealed split with no gold case, is an error. The exception is a row whose volume is listed in the raw `no_chest_*.txt`, which the audit also reads itself. Without `--raw`, that step is `NOT_RUN` and the overall status is not `PASS` (CLI exit ≠ 0).
4. **R4 strict approval gate.** `approval_resolves(ref)` is true only if all of these hold:
   - (a) `ref` fully matches `DEC-[0-9]{4}`;
   - (b) exactly one `## ` heading in DECISIONS.md carries `ref` as a whole token, with no digit or word character right after it (`DEC-0001` ≠ `DEC-00012`);
   - (c) that section contains the line `- **Decision:** APPROVED: CT-RATE download`;
   - (d) that section contains a non-empty `- **Approved by:** …` line;
   - (e) no line of that section matches (case-insensitive) `not approved|not decided|reject|declin|denied|defer|pending|postpone|on hold|superseded|revoked|withdrawn|^## .*open:`;
   - (f) no other section names `ref` together with `superseded|revoked|withdrawn`.

   The required format is printed by `plan-download` and stated in the `access.py` docstring. `prepare --execute` keeps its four gates.
5. **R5 verify scope and local sha256.**
   - `verify(root, raw_root=REPO_ROOT/"data/raw")` refuses with `RefusedError` when the resolved `root` is not strictly under the resolved `raw_root`. This covers `..`, absolute paths elsewhere and a symlink escaping `raw_root`. It also refuses when `root` does not exist. It never creates a directory.
   - `verify --record` writes `<root>/local_sha256.json` (gitignored location) holding the revision and the sha256 of every expected file. It does so only when every size/hash check passes and no record exists. It never overwrites a record.
   - Later runs compare against the record. A mismatch, or a different revision, is `FAIL`.
   - Without a record, LFS files are reported under `unpinned_lfs`.
6. **R6 label origin and metric name.**
   - `AbnormalityLabels.label_origin: Literal["provider_text_classifier_prediction_from_report"]` is required (no default) and written to every gold file. The audit schema step fails if it is absent or different.
   - `types.LABEL_METRIC_NAME = "agreement with report-derived labels"` is added, and the build manifest carries `label_origin` and `label_metric_name`.
   - `--unseal-test` behaviour is unchanged. Its CLI help and the `build.py` docstring state that it unseals test inputs, label sources and gold together, and that separating them is deferred to the CT reader eval slice.
7. **R7** Mark the six rows in `slices/CONDITIONS.md` CLOSED, each with the test names that prove it. Leave the human row open.

## Out of scope

- Downloading CT-RATE or any network use; reading NIfTI.
- Resolving the human decisions: download approval (who accepts the terms, accessors, multi-TB storage), `train` vs `train_fixed`, CC BY-NC-SA flow-down to released weights, and the 10% dev / seed 20260926. Do not add a CT-RATE approval entry to `docs/DECISIONS.md`; `ctrate.manifest.json` `access.approval_ref` stays `null`.
- Changing split policy, the time convention, `casegraph` contracts, other datasets' provenance verdicts, or `docs/PROPOSAL.md`.
- Splitting `--unseal-test` into separate unseal modes.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| R1 | A missing expected no_chest file fails loudly | Deleting `no_chest_train.txt` or `no_chest_valid.txt` (2/2 cases) raises `CTRateLoadError` with a `missing_file` error naming that exact path, and `build` leaves `out` absent or empty. An empty file gives 0 exclusions for that split and the load succeeds | `test_ctrate_loader.py::test_missing_no_chest_file_fails_loudly[train,valid]`, `::test_empty_no_chest_file_means_zero_exclusions` |
| R2 | Same-patient reports are blocked for every report-label task | For each task in `build.TASKS` (3/3): report of `train_k_b` vs label of `train_k_a` → `same_patient`, image not replaced, `events["blocked_same_patient"] == 1`; the same holds for `valid_k_a`/`valid_k_b`; a zero-padded or Thai-digit variant of the same patient is also blocked. A report of `valid_k_a` vs label `train_k_a`, and a report of another patient, are `allowed`. A Collator bypass with a same-patient report raises `ReportLeakageError`. Existing own-scan (`same_source`) tests stay green. MIMIC/synthetic verdicts are unchanged | `test_ctrate_guard.py::test_same_patient_other_scan_blocked_and_counted[task]`, `::test_same_patient_valid_pair_blocked`, `::test_same_patient_digit_variants_blocked`, `::test_train_k_vs_valid_k_allowed`, `::test_collator_raises_on_same_patient_report`; the full `research/tests` suite stays green |
| R3 | The missingness audit is independent of the pipeline | A planted loader bug (monkeypatch so that blank cells become `"0"` and every derived count stays self-consistent) builds, and `audit --raw` reports `missing_not_negative` FAIL with exit 1. A planted bug that turns a `0` into `missing` also FAILs. The clean build PASSes. With `load_tree`/`_read_table` monkeypatched to raise during the audit, the audit still completes. Without `--raw` the status is not PASS | `test_ctrate_audit.py::test_planted_pipeline_bug_blank_to_zero_fails`, `::test_planted_pipeline_bug_zero_to_missing_fails`, `::test_missing_audit_does_not_use_loader`, `::test_audit_without_raw_is_not_pass` |
| R4 | The approval gate is exact | ≥ 8 adversarial DECISIONS.md cases, 100% correct: (1) `DEC-0001` vs heading `DEC-00012` → false; (2) section containing "Not approved: downloading CT-RATE" → false; (3) section "deferred"/"pending" → false; (4) section "rejected" → false; (5) heading `OPEN:` → false; (6) missing the `Decision: APPROVED: CT-RATE download` line → false; (7) duplicate heading id → false; (8) later section "DEC-NNNN revoked" → false; (9) the exact well-formed section → true. `prepare --execute` still refuses with no approval, no token, no `--accept-terms` or a non-`data/raw` target (existing cases), with `subprocess.run`/`Popen` patched to fail | `test_ctrate_download_gate.py::test_approval_resolves_adversarial[case]` (parametrized), plus the existing `test_prepare_execute_refuses` |
| R5 | verify cannot create paths; local sha256 pins the LFS files | `verify` on `tmp/elsewhere`, `data/raw/../processed`, a non-existent `data/raw/x`, and a symlink under `raw_root` pointing outside (4/4) → `RefusedError`, and no new directory exists afterwards. On the synthetic fixture: `--record` writes `local_sha256.json`; a same-size byte flip in an LFS-flagged file then gives FAIL (and, before recording, is reported under `unpinned_lfs`); a second `--record` does not overwrite; a revision mismatch gives FAIL | `test_ctrate_download_gate.py::test_verify_refuses_outside_raw[case]`, `::test_verify_record_then_detects_same_size_tamper`, `::test_verify_record_never_overwrites`, `::test_verify_record_revision_mismatch_fails` |
| R6 | Label origin and metric name are explicit | Every gold `labels` item has `label_origin == "provider_text_classifier_prediction_from_report"`. Constructing `AbnormalityLabels` without it raises. A gold file with the field removed or changed makes the audit `schema` step FAIL. `LABEL_METRIC_NAME` is the exact string, and the build manifest carries both fields. `build --help` mentions that inputs, label sources and gold are unsealed together | `test_ctrate_loader.py::test_label_origin_required`, `test_ctrate_audit.py::test_label_origin_tamper_fails_schema`, `::test_manifest_names_label_metric`, `test_ctrate_split.py::test_unseal_help_documents_joint_unseal` |
| R7 | Conditions are closed with evidence; human decisions stay open | 6/6 ctrate-loader non-human rows say CLOSED and name ≥ 1 passing test each. The human row is unchanged and still open. `git diff main -- docs/DECISIONS.md` adds no CT-RATE approval. `approval_ref` is `null` | the checker reads `slices/CONDITIONS.md`, runs every named test, and runs the git diff |
| R8 | Offline, no real data, suite green | All tests pass under the repo `--disable-socket`. `git ls-files data/` is empty; `git ls-files \| grep -E '\.nii(\.gz)?$'` is empty; no CT-RATE text is committed. Original B1–B9 tests are still green. `make test` exits 0 (the known flaky `web/tests/live-call.test.tsx` F8 is accepted only if it passes on rerun) | checker log |

## Required test cases (minimum)

- no_chest: missing train file, missing valid file, empty file.
- Guard: `train_2_a`/`train_2_b` for each of the 3 tasks; a `valid` patient with scans a and b (add to the fixture); `train_02_b` and a Thai-digit variant vs `train_2_a`; `valid_3_a` vs `train_3_a` allowed; another patient allowed; Collator bypass raises.
- Audit: loader bug blank→0, loader bug 0→missing, loader functions disabled during audit, no `--raw`.
- Approval: the 9 cases listed under R4.
- verify: 4 refusal paths with no directory created; record → tamper → FAIL; no overwrite; revision mismatch.
- label_origin: missing at construction, tampered in gold.

## Clinical and validity risks

- **Report leakage.** A same-patient report of another scan often describes the same findings, so admitting it as an input inflates label agreement (R2). The official `train`/`valid` patient disjointness still rests on the provider's statement.
- **Missing treated as negative** would inflate specificity. A self-referential audit cannot catch this (R3).
- **Label quality.** The labels are text-classifier predictions from the report, not radiologist ground truth. Every metric must be named "agreement with report-derived labels" (R6). CT-RATE results are a separate CT reader evaluation, never clinical performance.
- **Governance.** A loose approval match could start a multi-TB download under a decision that deferred or rejected it (R4). An unrestricted `verify` could create directories anywhere (R5). The licence forbids redistribution, so nothing from CT-RATE may be committed.

## Run commands

```bash
.venv/bin/python -m pytest -q research/tests/test_ctrate_*.py
.venv/bin/python -m pytest -q research/tests
.venv/bin/python -m research.data.ctrate build --raw <fixture_root> --out <tmp>/build --seed 20260926
.venv/bin/python -m research.data.ctrate audit <tmp>/build --raw <fixture_root>
.venv/bin/python -m research.data.ctrate build --help | grep -i unseal
git ls-files data/ ; git ls-files | grep -E '\.nii(\.gz)?$'     # both must print nothing
git diff main -- docs/DECISIONS.md research/data/ctrate/ctrate.manifest.json
make test
```

## Decisions still required (human; unchanged by this slice)

1. Owner approval to download CT-RATE: who accepts the terms, who gets access, and the multi-TB storage plan. It must be recorded in the R4 format.
2. `volume_root`: `train`/`valid` or `train_fixed`/`valid_fixed`.
3. CC BY-NC-SA 4.0 flow-down to released weights or derived data.
4. Confirm the 10% dev fraction and seed 20260926.
