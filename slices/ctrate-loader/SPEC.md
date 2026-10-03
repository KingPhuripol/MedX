# Slice ctrate-loader — CT-RATE dataset manifest + loader (patient split, available_at_time)

- Branch `factory/ctrate-loader` from `main` 24a491b. Tier 0 only: CPU, synthetic fixture, offline tests. No download, no training, no GPU, no external API.
- Gantt: task 5 data pipeline (owner ภูริณัฐ); task 4 data selection/quality (จักรภัทร) reviews the manifest and exclusions.
- Source of truth: `docs/PROPOSAL.md` v9.6, sections 1.3.2 (CT-RATE [11] is a public dataset, and it is the fallback when MIMIC access is late), 3.3 (stage 2 trains the connector on CT-RATE CT/report pairs; stage 3 substitutes a report only when the label does not come from it), 3.4 (dataset list with source, version and access; typed items with patient ID, event time and available time; split by patient before samples are made; report never input when it is the label source; leakage checks), 3.6 (CT-RATE abnormalities taken from reports are labels not fed to the model; CT readers are evaluated separately from the graph; 95% CI by patient-level bootstrap; CT-CHAT comparator). Also binding: the CLAUDE.md data rules 1–8 and the human approval gates.
- Planner evidence: `slices/ctrate-loader/evidence/hf_api_snapshot_2026-10-03.json`. It holds unauthenticated Hugging Face Hub API metadata only: revision, license, gated terms text, file sizes, git/LFS oids. It contains no dataset content.

## Verified source facts (retrieved 2026-10-03 from the official Hugging Face dataset page and API)

| Fact | Value | Source |
|---|---|---|
| Repo | `ibrahimhamamci/CT-RATE` (HF dataset) | https://huggingface.co/datasets/ibrahimhamamci/CT-RATE |
| Pinned revision | `deeca4d89e9f978d4d1bccd88a55071ddbb146bb` (lastModified 2026-03-16T14:26:48Z) | HF API `/api/datasets/ibrahimhamamci/CT-RATE` |
| License | CC BY-NC-SA 4.0, https://creativecommons.org/licenses/by-nc-sa/4.0/ | dataset card `license: cc-by-nc-sa-4.0`; README "License" section |
| Access | `gated: auto`. The user must agree to the terms on HF (fields: Name, Institution, Email, agree checkbox), then download with their own HF token | HF API `extra_gated_fields` |
| Terms (summary; the verbatim text is in the evidence JSON) | academic/research/educational use only; no commercial use without permission; comply with privacy law (GDPR/HIPAA); no re-identification; cite the dataset; no ownership claims; **no redistribution of the dataset or any portion**; derived data must respect confidentiality; access revocable; terms may change | `extra_gated_prompt` |
| Layout | `dataset/{train,valid}/<split>_<pid>/<split>_<pid>_<scan>/<split>_<pid>_<scan>_<recon>.nii.gz`, plus `dataset/{train_fixed,valid_fixed}/`. CSVs: `dataset/metadata/{train,validation}_metadata.csv`, `dataset/radiology_text_reports/{train,validation}_reports.csv`, `dataset/multi_abnormality_labels/{train,valid}_predicted_labels.csv`, `dataset/metadata/no_chest_{train,valid}.txt` | HF tree API at the pinned revision |
| Counts (provider-stated) | 21,304 patients (20,000 train / 1,304 valid); 25,692 scans; 50,188 volumes with reconstructions | README at the pinned revision |
| Naming | `split_patientID_scanID_reconstructionID`, e.g. `valid_53_a_1` | README |
| Columns | `VolumeName`, `Findings_EN`, `Impressions_EN`, `RescaleSlope`, `RescaleIntercept`, `XYSpacing`, `ZSpacing`; label CSV = `VolumeName` + abnormality columns | the official CT-CLIP loader `scripts/data.py` / `data_inference_nii.py`. The full CSV headers are gated and **unverified**. |

**Verdict:** the terms permit our academic, non-commercial research use, so the slice proceeds. Two terms bind the work. No redistribution: the repository is public, so no CT-RATE content may be committed. Share-alike/NC: this applies to any released derivative, see Decisions required.

## Scope

1. **Dataset manifest.**
   - Add `research/data/ctrate/ctrate.manifest.json` and validate it against a new `schemas/dataset-manifest.schema.json` (jsonschema).
   - Required fields:
     - `dataset_id`, `source_url`, `hf_repo`, `revision` (40-hex);
     - `license {name, url, retrieved_on}`;
     - `terms {summary, verbatim_sha256, retrieved_on, source_url}`;
     - `access {gated, requires_user_agreement, token_owner, approval_ref}`; `approval_ref` stays `null` until the owner records a decision;
     - `deletion_obligations`: on access revocation or project end, delete `data/raw/ctrate` and its derivatives; no redistribution;
     - `citation` (proposal reference [11], DOI 10.1038/s41551-025-01599-y);
     - `expected_files[] {path, size, git_blob_sha1, lfs_sha256|null}` for every CSV/TXT in the table above, copied from the evidence JSON;
     - `expected_counts` (with source);
     - `volume_root` (`train`|`train_fixed`; open decision);
     - `local_root` (`data/raw/ctrate`, gitignored);
     - `time_convention` (see item 2);
     - `split_policy` (see item 3).
   - Volume checksums are not committed. `verify` computes them locally after an authorized download and writes them under gitignored `data/raw/ctrate/`.
2. **Loader.** `research/data/ctrate/` (new package: `types.py`, `loader.py`, `split.py`, `build.py`, `__main__.py`).
   - Parse metadata, report, label and no_chest files from a root directory. Header-driven: `VolumeName` is required in every table, and `Findings_EN` and `Impressions_EN` are required in report tables. Label columns are every column of the label CSV except `VolumeName`. Unknown extra columns are carried through as is.
   - Typed evidence subclasses of `casegraph.types.EvidenceItem`. Each has `available_at_time`, `source`, `provenance` (`hf://datasets/ibrahimhamamci/CT-RATE@<rev>/<path>#row=<n>`) and `version` (`ct-rate@<rev>;ctrate-loader/1`):
     - `CTVolume` (input): volume ref, scan ref, reconstruction, metadata fields;
     - `RadiologyReport` (`role=label_source`);
     - `AbnormalityLabels` (`role=label`, values `1`/`0`/`missing`, `label_source` = the scan's report ref).
   - The provider labels are text-classifier predictions from the report (file name `*_predicted_labels.csv`), so their `label_source` is the report.
   - **available_at_time convention `ctrate_synthetic_anchor_v1`.** CT-RATE has no clinical timestamps, so a sentinel anchor `A = 2000-01-01T00:00:00+00:00` is used, flagged `time_basis="synthetic_anchor"`; it is never a real clinical time.
     - `CTVolume`: event = observed = available = A.
     - `RadiologyReport`: event A, available A+1 day.
     - `AbnormalityLabels`: event A, available A+2 days, so labels come strictly after the report, which comes strictly after the volume.
     - The reader decision time is `T_read = A`.
     - One case = one scan (`encounter_ref` = `<split>_<pid>_<scan>`). The order of scans `a`, `b`, … is undocumented, so no scan is ever evidence for another scan of the same patient. There is no cross-scan longitudinal input.
   - **Malformed input fails loudly.** The loader raises a typed error listing each offending row. Cases:
     - a `VolumeName` that does not match `^(train|valid)_[1-9][0-9]*_[a-z]+_[1-9][0-9]*\.nii\.gz$` (ASCII only, no normalization);
     - a split prefix that disagrees with the file it came from;
     - duplicate `VolumeName`;
     - a label value not in {0, 1, blank};
     - a report or label row with no metadata row;
     - reports or labels that differ across reconstructions of one scan.
   - A volume without a report, or without labels, is kept and its missingness is recorded. A blank label is `missing`, never 0. A `no_chest` listed volume is excluded with reason `provider_no_chest` and counted.
   - Rows are never silently dropped.
3. **Patient split.**
   - Patient key = `<official_split>_<int pid>`. `train_7` and `valid_7` are different patients.
   - Assignment uses patient keys only, before any scan or reconstruction expansion:
     - official `valid` → `test` (sealed);
     - official `train` → `train` / `dev`, with dev = 10% of train patients. Rank train patients by `sha256(f"{seed}:{patient_key}")`; the lowest `round(0.10·N)` are dev. Default seed 20260926.
   - Emit `split_manifest.json`. It holds:
     - the policy: seed, fraction, method;
     - per split: patient, scan and volume counts, plus sha256 of the sorted patient-key list;
     - exclusions with reasons;
     - `pinned revision`;
     - a `manifest_sha256` over canonical JSON (sorted keys, no timestamps).
   - Test gold is sealed. The library returns test-split labels only when `purpose="final_eval"` is passed explicitly. The CLI writes them only with `--unseal-test`.
4. **Build output** (to gitignored `data/processed/ctrate/<build_id>/`; tmp_path in tests). The layout is the one `scripts/temporal_leakage_audit.py --dataset` reads:
   - `splits.json`;
   - `inputs/<split>/<case>/journey.json` with `snapshot_T*.json`. Inputs hold volume and metadata items only; report text and labels never go under `inputs/`;
   - `label_sources/<split>/<case>.json` (reports);
   - `gold/<split>/<case>.json` (labels; decision_times `[{T: A}]`);
   - `manifest.json` with file sha256.
   - Also add `python -m research.data.ctrate audit <out>`, a data-audit equivalent of `data_factory/audit.py`. It checks:
     - schema;
     - gold separation: no label column name, label value field or report text under `inputs/`;
     - identifier scan of `inputs/`;
     - manifest hashes;
     - no snapshot item after T;
     - patient overlap;
     - missing ≠ negative.
5. **Fixture + offline tests.**
   - `research/tests/ctrate_fixture.py` generates a tiny synthetic tree that mimics the layout above into `tmp_path`:
     - ≥ 6 train patients and ≥ 3 valid patients, including a train/valid pair with the same pid;
     - a patient with scans `a` and `b`, a scan with 3 reconstructions;
     - a blank label, a volume with no report, a no_chest entry;
     - placeholder `.nii.gz` bytes (not real NIfTI).
   - All text is visibly synthetic (`SYNTHETIC REPORT …`). Nothing is copied from CT-RATE. No fixture binary or CSV of real origin is committed.
6. **Download/prepare command, gated.** `python -m research.data.ctrate plan-download` prints the steps only:
   1. accept the terms on HF with your own account;
   2. `huggingface-cli download ibrahimhamamci/CT-RATE --repo-type dataset --revision <rev> --include <patterns> --local-dir data/raw/ctrate`;
   3. `verify`.

   `prepare --execute` refuses (non-zero, no subprocess, no network) unless all four conditions hold: `--approval DEC-…` resolves to an entry in `docs/DECISIONS.md`, `HF_TOKEN` is set, `--accept-terms` is given, and the target is under `data/raw/`. `verify <root>` checks sizes and git-blob-SHA1/LFS-SHA256 of the CSVs against the manifest. No new runtime dependency is added: `huggingface-cli` is invoked only by an explicit, approved `--execute`.
7. Wire the new tests into `make test` (they sit under `research/tests/`, which is already in pytest `testpaths`).

## Out of scope

- Downloading real CT-RATE data, or reading NIfTI voxels (no nibabel).
- A 3D encoder, a CT reader, training, evaluation metrics.
- VQA, segmentation and anatomy files.
- Linking CT-RATE to MIMIC (they are different patients; proposal 3.6 evaluates CT readers separately).
- Age-scope (≥ 18) filtering: count it only if an age column exists, and filter nothing.
- Any change to `casegraph` contracts, the collator semantics, the splits of other datasets, or `docs/PROPOSAL.md`.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| B1 | Manifest is complete and sourced | 100% of required fields present and schema-valid. `revision` = the pinned 40-hex SHA. License name + URL + `retrieved_on` = 2026-10-03, and the terms verbatim sha256 matches the evidence JSON. Every `expected_files` entry has size + checksum fields | `test_ctrate_manifest.py`: jsonschema validation; a removed required field fails the test (adversarial); cross-check against `evidence/hf_api_snapshot_2026-10-03.json` |
| B2 | Typed parsing with full coverage | On the fixture, 100% of metadata/report/label rows become typed evidence with `available_at_time`, `source`, `provenance`, `version`, and there are 0 untyped rows. Each malformed case (bad name, Unicode/zero-padded digits, split mismatch, duplicate, bad label value, orphan row, cross-reconstruction conflict) raises a typed error naming the row: 7/7 cases, 0 silent drops | `test_ctrate_loader.py`: count(rows in) = count(evidence) + count(recorded exclusions); one parametrized adversarial case per malformation |
| B3 | Patient-level split | 0 patients in more than one split across all scans and reconstructions. Official `valid` maps only to `test`; `train` maps only to `train`/`dev`. Dev is exactly `round(0.10·N_train_patients)` patients, chosen by patient. `train_k` ≠ `valid_k`. `split_manifest.json` is byte-identical across 2 runs with the same seed; with a different seed, dev differs and test is identical | `test_ctrate_split.py`: overlap set empty; assignment-function signature takes patient keys only; double-run sha256 equality |
| B4 | Label-source guard | For every CT-RATE task (abnormality labels, report generation, image–text alignment), report text is never in inputs. Report/label refs canonicalize via `research.train.data.canonical_source_id` to the scan id (all reconstructions → one scan), so `report_provenance` = `same_source`. An adversarial sample with the scan's own report as a substituted input raises `ReportLeakageError`, or is blocked and counted. A report of a *different* scan is not mistaken for the same source | `test_ctrate_guard.py`, using the existing `decide_modalities`/`Collator`; the `events["blocked_label_source"]` count is asserted |
| B5 | Temporal correctness | For every item, volume ≤ report < labels. `scripts/temporal_leakage_audit.py --dataset <fixture build>` exits 0 (PASS). An injected report or label item with `available_at_time > T` in a snapshot makes the audit exit 1 (FAIL) | `test_ctrate_temporal.py` runs the script as a subprocess on the fixture build and on 2 mutated copies |
| B6 | Data audit + missingness | `python -m research.data.ctrate audit <build>` reports PASS on all steps. A blank label is serialized as `missing` (never 0), with ≥ 1 such case in the fixture. A volume without a report is recorded as `report: missing`. The no_chest exclusion is counted. Planted label/report text under `inputs/` makes the audit FAIL | `test_ctrate_audit.py` (PASS case + 2 planted-failure cases) |
| B7 | No network, no real data | The tests pass under pytest-socket `--disable-socket`. `plan-download` performs no I/O beyond stdout. `prepare --execute` without approval, token, terms flag or a valid target exits non-zero with `subprocess` monkeypatched to fail if called (4/4 refusal cases). `git ls-files data/` is empty and `git ls-files \| grep -E '\.nii(\.gz)?$'` is empty. No CT-RATE text is committed | `test_ctrate_download_gate.py`; the checker runs the two `git ls-files` commands |
| B8 | Test split sealed | Requesting test labels without `purpose="final_eval"` (library) or `--unseal-test` (CLI) raises an error or writes nothing | `test_ctrate_split.py::test_test_gold_sealed` |
| B9 | Full suite green | `make test` exits 0. The known flaky `web/tests/live-call.test.tsx` F8 is accepted only if it passes on rerun | checker log |

## Required test cases (minimum)

- `train_7` vs `valid_7` are kept as different patients.
- A patient with scans a and b has every reconstruction in the same split.
- A 3-reconstruction scan with identical reports passes.
- The same scan with a differing report is rejected.
- A blank label is `missing`. A `0` label is a negative.
- `train_01_a_1` (zero-padded) is rejected.
- A Thai digit (`train_๑_a_1`) is rejected.
- A `valid_*` row in a train CSV is rejected.
- A label row with no metadata row is rejected.
- A no_chest volume is excluded with its reason and counted.
- The same seed gives byte-identical split manifests; a different seed changes dev but not test.
- The temporal audit PASS case, plus 2 FAIL injections.
- A substituted own-report input raises `ReportLeakageError`; a substituted different-scan report is allowed.
- Test labels stay sealed without explicit opt-in.
- The 4 download refusals.

## Clinical and validity risks

- **Label quality.** The labels are classifier predictions from the reports, not radiologist ground truth. Any metric on them must be called "agreement with provider report-derived labels".
- **Population.** A single provider cohort of non-contrast chest CT only. It is not Thai and not linkable to MIMIC. CT reader results are reported as a separate system evaluation, never as clinical performance.
- **Missing as negative.** Treating a missing label as negative would inflate specificity. B6 guards against this.
- **Leakage.** Reconstructions and repeat scans of one patient could cross splits (B3). The report could leak into the input (B4). The patient-disjointness of the official train/valid split relies on the provider's statement; it cannot be verified across pseudonymous IDs (assumption).
- **Contamination.** CT-CLIP/CT-CHAT were trained on CT-RATE train. Base models may have seen CT-RATE: the literature scout checks this before any comparison, and official valid is kept as the only test set (proposal 3.4).
- **License and privacy.** The repository is public, so committing any CT-RATE row, report or volume would breach the "no redistribution" term. Re-identification attempts are prohibited.

## Run commands

```bash
.venv/bin/python -m pytest -q research/tests/test_ctrate_*.py
.venv/bin/python -m research.data.ctrate plan-download            # prints steps only
.venv/bin/python -m research.data.ctrate build --raw <fixture_root> --out <tmp>/build --seed 20260926
python3 scripts/temporal_leakage_audit.py --dataset <tmp>/build
.venv/bin/python -m research.data.ctrate audit <tmp>/build
git ls-files data/ ; git ls-files | grep -E '\.nii(\.gz)?$'        # both must print nothing
make test
```

## Decisions required (human; not made by this slice)

1. Owner approval to download CT-RATE, recorded in `docs/DECISIONS.md`. It must cover:
   - acceptance of the terms with the owner's HF account;
   - which team members may access the data;
   - storage location: the volumes are about 100–150 MB each × 50,188, roughly several TB. A storage estimate or subset plan is needed first.
2. `volume_root`: `train`/`valid` or `train_fixed`/`valid_fixed`. Read the gated `dataset/data_correction_note.md` after access is granted.
3. CC BY-NC-SA 4.0 and "derivative works shared under similar terms" may flow down to any released weights or derived data trained on CT-RATE. This needs a decision before any Hugging Face release (DEC-0009 open-weight goal).
4. Confirm the predeclared dev fraction (10%) and seed. Changing either after results exist needs a decision.
