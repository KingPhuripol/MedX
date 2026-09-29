# Evaluation ledgers (slice s8r)

Research prototype - not for clinical use.

## Location

`eval/ledger/frozen.jsonl` (manifest freezes) and `eval/ledger/runs.jsonl` (recorded runs) are committed to git.
`.gitignore` has `!eval/ledger/*.jsonl`; `.gitattributes` has `eval/ledger/*.jsonl -text -merge`, so bytes stay exact
and concurrent appends conflict instead of auto-merging. A missing ledger is never auto-created:
`python -m eval ledger init --ledger-dir D` works only when both files are absent and the path has no git history.

## Format

One canonical JSON entry per line (sorted keys, no spaces, UTF-8, file ends in `\n`). Line `i` has `seq == i`,
`ledger` (`frozen` | `runs`), `kind` (`genesis` first, then `freeze` | `run`), `prev_hash` (previous `entry_hash`;
genesis uses 64 zeros) and `entry_hash = sha256(canonical entry without entry_hash)`. Entries hold only the
`evaluation_id`, hashes, seq, timestamps and kind - never patient IDs or data. `results.json` embeds `frozen_entry_hash`.

`Ledger.verify()` runs before every `freeze` and `run` and in `python -m eval ledger verify`. A missing file, a
non-canonical line, a broken chain, a seq gap or re-order, or a git-anchor mismatch (the committed `HEAD` version must
be a byte prefix of the working file) refuses with exit 2 and nothing is written.
`ledger verify --git-history` also checks that every committed version is a byte prefix of the next.

## Commit policy

1. Ledger appends happen on one integration branch only (`main`), by a single writer.
   Exception: `docs/DECISIONS.md` "2026-09-27 — Evaluation ledger: freeze and test runs allowed on factory branches"
   (own `factory/<slice>` branch, merge-only to `main` via `factory/int`, verify `--git-history` after each merge).
2. Order: `freeze`, then commit `eval(ledger): freeze <evaluation_id>` together with the manifest.
   Then `run`, then commit `eval(ledger): run <evaluation_id>`.
3. Commits that touch `eval/ledger/` are never amended, rebased, squashed or force-pushed.
4. A merge conflict in a ledger is resolved by redoing the other branch's freeze or run on top of `main`,
   never by editing lines.
5. Real data (`mimic`, `hospital`) on the test split is refused unless both ledgers are git-tracked with no
   uncommitted lines (the freeze and the previous run are committed before any new test result exists).

## Residual risk

Rewriting git history on the remote (force-push) is not detectable locally. Humans should enable branch protection
(no force-push) on `main` for `eval/ledger/`. Entries are not signed and have no external timestamp anchor.
