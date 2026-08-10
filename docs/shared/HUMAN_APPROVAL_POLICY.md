# Human Approval Policy

**Owner:** Phurinat Polasa  
**Safety co-owner:** Thanrada Tungweerapornpong  
**Schema:** `schemas/human-approval.schema.json`

## Principle

Claude Code and project agents may prepare, validate, simulate, and recommend. Humans retain authority for material cost, irreversible change, external publication, sensitive-data transfer, clinical risk acceptance, official schedule correction, and scope/claim changes.

An approval is specific, time-bounded, and recorded. Approval of one run/provider/release does not approve later variants.

## Always requires explicit approval

### Compute/training

- Tier 3 or Tier 4 runs;
- more than one GPU or any multi-node/cluster scheduler job;
- expected runtime over 60 minutes or material paid compute;
- approximately 4B/27B training, full-dataset transforms, or substantial artifact storage;
- increasing approved budget, devices, time, data, or objective after approval.

### Data/privacy

- real, identifiable, linkable, de-identified-approved, or restricted derivative data sent to any external API/service;
- destructive/irreversible dataset transformation or deletion;
- new data license/ethics interpretation, identity linkage, or release of derived data;
- access-control/retention exception.

### Publication/external effect

- Hugging Face upload/release, model/data card publication, package/deployment release, Git push to public remote, public report/site, or external message;
- deleting checkpoints, experiment evidence, audit logs, datasets, releases, or branches;
- changing a published artifact or tag.

### Governance/safety

- official deadline correction;
- material changes to mission, track boundary, modality scope, flagship target, research question, success criterion, split/label, API/evaluation contract, clinical taxonomy, safety rule, or claim;
- accepting/waiving a safety or integration failure;
- enabling any real clinical use or action affecting care.

## Approval record

The request states:

- unique approval ID and type;
- requester, approver identity/role, requested and decided times, expiry;
- exact action/command/provider/release/experiment and environment;
- data classification and fields where applicable;
- compute/cost/time/storage limits where applicable;
- rationale, alternatives, risks, safeguards, monitoring, stop/rollback, and evidence;
- decision: `APPROVED`, `DENIED`, `EXPIRED`, or `REVOKED`;
- linked task/risk/decision/manifest.

Verbal approval should be transcribed and acknowledged before execution. A hook prompt is a runtime confirmation, but the durable approval record remains required for Tier 3/4, sensitive data, release, or material governance actions.

## Approval execution

1. Validate scope and preconditions.
2. Confirm the approval is current and matches action exactly.
3. Execute within limits; log actual command/config/version and start/end.
4. Stop on deviation, gate failure, budget limit, safety issue, or revocation.
5. Record result and artifacts; update linked state.

## No self-approval

An agent cannot approve. The requester cannot impersonate the approver. For safety-critical waivers or real-data external transfer, approval must include the designated human project/safety/data authority and any required institutional authority. Repository role ownership does not override university, ethics, dataset, or clinical governance.

## Emergency stop and revocation

Any member may request a stop for safety, privacy, leakage, unexpected cost, or destructive behavior. Stop safely, preserve evidence, revoke/expire the approval, assess impact, and require a new approval before resumption.

## Hook behavior

`.claude/hooks/approval_gate.py` forces a user prompt for recognizable expensive training, publishing, external upload, destructive commands, and protected governance-file edits. Hooks reduce accidental action but are not proof of authorization and cannot recognize every risky operation. The constitution and this policy remain binding.
