# Experiment Manifests

Every Research run has one immutable planning/result record validated against `schemas/experiment-manifest.schema.json`.

`exp_0000_harness_smoke.json` is a real Tier 0 synthetic Harness validation plan. It does not train a model and does not authorize later compute.

Create a new manifest only after the research question, owner, task, model/data/split versions, primary metric, and tier are known:

```bash
python3 scripts/new_experiment.py --help
python3 scripts/validate_manifest.py experiments/manifests/exp_0000_harness_smoke.json
```

Rules:

- IDs are sequential `exp_NNNN`; never reuse or overwrite another experiment.
- Planning fields remain intact after execution; append `result` and move status through its real lifecycle.
- Tier 3/4 requires an approval ID before execution.
- Failed, stopped, and invalidated runs remain in the repository record.
- Large logs/checkpoints/predictions live in ignored artifact storage; the manifest stores paths/checksums.
- No raw patient data, secrets, or restricted payloads belong in a manifest.

