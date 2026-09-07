# Archived search reports

One file per search recorded in `project_state/literature.json` under `searches[]`, referenced by
that record's `report_ref`. These are the raw returns from `literature-benchmark-scout`, kept so the
protocol is auditable: anyone can compare what the search returned against what the registry
accepted, and see what was set aside and why.

They live here rather than in `artifacts/` because `artifacts/` is gitignored, and an audit trail
that is not committed is not an audit trail. `sources/` is write-denied and holds only synced
official documents.

A report here is a **search return, not a finding**. Nothing in these files is a project fact until
it has been verified against a primary source and written into the registry with a verdict.
