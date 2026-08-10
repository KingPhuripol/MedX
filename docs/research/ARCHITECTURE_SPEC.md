# Architecture Specification

**Owner:** Thanapol Popit  
**Status:** v0 contract; implementation choices may evolve through recorded decisions  
**Primary invariant:** the executed graph is the actual typed computation structure, not a post-hoc narrative

## System decomposition

```text
Patient Journey + Task + Decision Time
                  |
          Modality Encoders
                  |
        Patient-State Workspace
                  |
          Case Graph Compiler
          /       |        \
 operator logits  edges   stop/abstain
                  |
       Typed Sparse DAG Executor
                  |
       Task / Safety Output Heads
                  |
   Serialized Graph + Evidence Trace
```

## Components

### 1. Evidence adapters

Adapters validate contract version, authorization, patient/encounter identity, `observed_at`, `available_at_time`, missingness, source, units/geometry, and provenance. They produce modality tokens plus an evidence reference. They must never load future evidence for the declared decision time.

### 2. Modality encoders

- Text encoder for clinical text and task prompts.
- 2D vision encoder with image/view and transformation metadata.
- 3D volume encoder or hierarchical slice/patch encoder preserving spacing/orientation metadata.
- Structured/temporal encoder that preserves units, missingness, time delta, and event identity.

Encoders expose a stable embedding interface. Dataset-specific preprocessing remains outside model logic and is versioned.

### 3. Patient-state workspace

A bounded representation containing authorized evidence embeddings, temporal state, task context, uncertainty state, and node outputs. It provides explicit evidence addressing; an operator may read only declared inputs.

### 4. Case Graph Compiler

Produces a finite acyclic graph conditioned on task and currently available evidence. It selects typed nodes, edges, operator parameters, modality reads, and stopping/escalation. The compiler must support:

- dense/soft training mode for early stabilization;
- sparse top-k mode;
- discrete execution mode for the primary claim;
- deterministic inference under fixed seed/config;
- budget constraints on nodes, edges, depth, modality reads, and estimated FLOPs;
- explicit invalid-graph and low-confidence fallback.

### 5. Typed operator library

The initial operator vocabulary is intentionally bounded:

| Type | Purpose | Allowed inputs | Expected output |
|---|---|---|---|
| `CHIEF_COMPLAINT_PARSE` | extract presenting context | text | complaint state |
| `RED_FLAG_SCREEN` | detect predeclared urgent patterns | text, structured | risk flags + uncertainty |
| `HISTORY_RETRIEVE` | select relevant prior evidence | longitudinal, text | evidence references |
| `VITAL_RISK_ASSESS` | interpret time-valid vitals | structured | risk state |
| `PERCEIVE_2D` | encode/interpret 2D evidence | 2D image | visual evidence state |
| `PERCEIVE_3D` | encode/interpret volume evidence | 3D volume | volumetric evidence state |
| `TEMPORAL_UPDATE` | update state with new evidence | prior state, timepoint | revised state |
| `COMPARE` | compare current and prior observations | two compatible states | change state |
| `CROSS_MODAL_BIND` | align evidence across modalities | typed evidence states | bound state |
| `EVIDENCE_INTEGRATE` | aggregate supporting/conflicting evidence | evidence states | integrated state |
| `NEXT_INFO_SELECT` | rank information needed next | state, availability catalog | candidates + uncertainty |
| `URGENCY_CLASSIFY` | support urgency classification | integrated/risk state | calibrated urgency |
| `PATHWAY_ROUTE` | support care-pathway selection | state, urgency | ranked pathways |
| `UNCERTAINTY_ESCALATE` | abstain/escalate | any state | escalation action |

Adding/removing/semantically changing a type requires a version bump, migration, ablation plan, and accepted decision.

### 6. DAG executor

The executor validates types, evidence authorization, acyclicity, budget, and node availability before execution. It records actual node order, inputs, outputs by safe reference, cost, timing, and status. A node failure cannot be silently skipped; policy determines retry, substitute, abstain, or escalate.

### 7. Output and safety heads

Task heads produce contract-versioned outputs. Uncertainty includes confidence/calibration metadata, out-of-distribution indicators where available, and explicit abstention. Safety rules may conservatively override a learned low-urgency/pathway result to escalation, and the override is logged.

## Graph invariants

1. Graph is finite and acyclic.
2. Node IDs are unique; types and I/O schemas are explicit.
3. Every edge connects compatible types.
4. Every evidence read references an item with `available_at_time <= decision_time` and authorized scope.
5. Node/edge budgets are enforced before execution.
6. Export contains graph/compiler/operator/model/contract versions.
7. Replay on the same versioned inputs/config matches outputs within declared numeric tolerance.
8. No hidden side channel uses future labels, filenames, site IDs, or post-outcome metadata.
9. Missing modalities stay explicit; the graph cannot invent an absent modality.
10. An invalid graph results in safe failure, not partial unmarked output.

## Serialization contract

Export at minimum:

- `graph_id`, `graph_schema_version`, `model_version`, `compiler_version`, `operator_library_version`;
- `patient_journey_id` or approved pseudonymous evaluation reference;
- `decision_time`, `task`, `seed`, budget and estimated/actual compute;
- ordered nodes with type, parameters/config hash, evidence references, timing, status, uncertainty;
- edges with typed ports;
- output references and replay tolerance;
- no raw PHI unless storage is explicitly authorized.

## Training approach

Start with differentiable routing and explicit load/diversity/budget objectives. Introduce sparsity and discreteness only after the executor and metrics work. Candidate techniques require ablation and may include top-k routing, straight-through estimators, Gumbel methods, reinforcement/credit assignment, or curriculum. The technique is not the contribution unless evaluated independently.

Total objective is predeclared per experiment and can include task loss, routing load balance, graph budget, stability, calibration, and safety/abstention objectives. Do not tune using final test results.

## Performance targets

Targets are comparisons, not invented absolute numbers:

- graph compilation overhead reported separately;
- active nodes, modality reads, latency, memory, and FLOPs per case;
- quality at matched compute and compute at matched quality;
- stable batch execution for repeated graph shapes where practical;
- no unreported fallback from discrete to dense execution.

## Test obligations

- unit: type checking, acyclicity, budget, evidence availability, serialization, deterministic compiler behavior;
- property: generated graphs always meet invariants;
- contract: API input/output and exported graph schemas;
- intervention: node, edge, graph, operator, and modality manipulation;
- robustness: missing/corrupted modality, timepoint update, provider/encoder failure;
- performance: compilation overhead and per-case cost;
- integration: identical gateway fixture across mock and team providers.

## Compatibility and change control

Model, graph, operator, data, and API versions are independent and explicit. Breaking changes need migrations and fixtures. Checkpoints must record compatible versions and fail clearly on mismatch. Architecture changes that alter a research claim or comparison require an amended manifest and Decision Log entry before new evidence is interpreted.

