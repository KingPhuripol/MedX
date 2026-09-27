# Slice s2 — Case Graph core

- Owner (Gantt): ภูริณัฐ / ธนาพล. Gantt rows 11 (data and node types, ธนาพล), 12 (Compiler and Executor, ภูริณัฐ), 13 (Replay and Regenerate, ธนาพล).
- Source of truth: `docs/PROPOSAL.md` (v8). This slice uses 1.3.1, 1.3.4, 2.1.3, 2.1.4, 3.1 (Model Gateway), 3.2.1 plus Table 3.1, 3.2.2, 3.2.3, and the "Replay and Regenerate" and "Case Graph" rows of Table 3.2.
- Builds on s0: `casegraph.types` (`TypedData`, `EvidenceItem`, `NodeType`, `Node`) and `backend/app/gateway` (contract `0.1.0`, `MockProvider`, `build_provider`).
- Status: PLAN. The planner wrote this. It is library-only: no UI and no HTTP routes.

## Scope

1. **Typed data** (`casegraph/data.py`)
   - Evidence types subclass `EvidenceItem`: `ClinicalText, CTVolume, MRIVolume, CXRImage, Vitals, LabSeries, MedicationList`.
   - Each evidence type also carries a required `item_id` and a required `data_class` (`synthetic|mimic|hospital|real|unknown`, no default).
   - Validation rejects an item with `available_at_time < event_time`.
   - Derived types subclass `TypedData`: `Findings, ImageTokens, Alerts, CaseSummary, DepartmentSuggestion, CareSuggestion, MedicationIssues, ConfirmedResult`.
   - Every derived value records `produced_by` (node id) and `input_refs` (evidence `item_id`s and/or upstream output hashes).
   - `ImageTokens` records its encoder provider.
   - All models are frozen and `extra="forbid"`.
   - No output model has a free-text reasoning, thought, or chain-of-thought field.
   - Imaging types hold a reference plus metadata only (URI, shape, sha256). They never hold pixel arrays.
2. **Node Library** (`casegraph/library.py`)
   - `NodeType` gains the 8 Table 3.1 types: `READER_TEXT, READER_VITALS_LABS, READER_CXR, READER_CT_MRI, RED_FLAG, PHARMA_AGENT, REASONING, HUMAN_CHECKPOINT`. The s0 `PLACEHOLDER` is removed.
   - Each spec declares `input_types`, `output_types`, `required_inputs`, `allowed_providers` and `mandatory`, exactly as in Table 3.1:

     | Node type | Allowed providers |
     |---|---|
     | Reader:Text | `project_model`, `external_model` |
     | Reader:Vitals/Labs | `rules`, `project_model` |
     | Reader:CXR | `encoder_2d`, `external_model`, `classifier` |
     | Reader:CT/MRI | `encoder_3d`, `external_model`, `segmentation` |
     | Red-flag | `rules` only; mandatory |
     | Pharma Agent | `project_model`, `rules` |
     | Reasoning | `project_model`, `external_model` |
     | Human Checkpoint | `human:nurse`, `human:physician`, `human:pharmacist`; mandatory |

   - `ImageTokens` is produced only by the `encoder_2d` or `encoder_3d` provider. Every other imaging provider emits `Findings`.
   - Reasoning `required_inputs` is a Library config value. Its default is Findings derived from `ClinicalText` and from `Vitals`. It is a documented placeholder: the clinical required-input set belongs to a later slice with clinical review.
3. **Compiler** (`casegraph/compiler.py`), per 3.2.2
   1. Build a snapshot at T. It contains only items with `available_at_time <= T`, from exactly one `patient_ref`, and it gets a `snapshot_id` (hash).
   2. Select nodes from the data types in the snapshot. Each Reader is added only if its input type is present. Pharma Agent is added only if `MedicationList` is present. Red-flag, Reasoning and Human Checkpoint are always added.
   3. Assign providers from a `ProviderConfig` (node type → provider id, `model_version`, params). This config is the experiment/deployment setting.
   4. Wire the nodes by type.
   5. Validate. Validation fails with a typed `GraphValidationError` if any of these holds:
      - the graph has a cycle;
      - an edge has mismatched types;
      - Red-flag or Human Checkpoint is missing;
      - the graph has no direct `Alerts → Human Checkpoint` edge;
      - a Reasoning or Pharma output does not reach a Human Checkpoint;
      - a provider is not in `allowed_providers`;
      - `ImageTokens` goes to any node other than a Reasoning node with provider `project_model`;
      - an evidence ref is not in this graph's snapshot;
      - an `external_model` node receives an input whose `data_class != synthetic` (1.3.4; the gateway also enforces this).
   - An invalid graph cannot be executed. The Executor accepts only a `ValidatedGraph` token that the Compiler issues.
   - Compiling is deterministic: the same snapshot plus the same config gives byte-identical graph JSON.
   - New data produces a new graph version (`version = n+1`, `parent_version = n`). Stored versions are immutable and are never overwritten.
4. **Executor** (`casegraph/executor.py`), per 3.2.3
   - Uses `graphlib.TopologicalSorter` and `asyncio`. Independent ready nodes run concurrently. Sync providers run via `asyncio.to_thread`.
   - A node starts only after all of its predecessors have finished.
   - At a Human Checkpoint it persists `status=pending_confirmation` through a `StateStore`. The StateStore has an in-memory and a file/SQLite (stdlib) implementation.
   - `resume(graph_version, action=confirm|edit|reject, reviewer_id, reviewer_role, edited_payload?)` records a `ConfirmedResult` with reviewer, role, UTC time and action.
   - The resume role must equal the checkpoint's configured `human:<role>`.
   - Confirm and edit emit the confirmed result as a new evidence item with `available_at_time = confirmation time`. That item enters later snapshots only. Reject records the decision and emits no clinical evidence.
   - Failure is fail-safe. A gateway `rejected` or `error` result, or a schema-invalid output, gives node `status=error, output=null`.
   - A Reasoning node whose required inputs are missing or errored gives `status=abstained, missing_inputs=[...]` and makes 0 gateway calls.
   - Red-flag and the Human Checkpoint still run. `Alerts` are never dropped.
   - Red-flag with none of its inputs present gives `Alerts{status: not_evaluated, missing_inputs}`. It never gives an empty "no alerts".
5. **Output Store, Replay, Regenerate** (`casegraph/store.py`)
   - The cache key is `sha256(canonical_json{node_type, provider, model_version, params, input_hash})`.
   - Each entry stores the output, `output_sha256`, status, timing and call count. There is a file-backed implementation (stdlib).
   - `replay(graph_version)` reads stored outputs only. It never calls a provider or executes a node body.
   - On a cache miss or a hash mismatch, replay raises `ReplayError`. It never falls back to recomputing.
   - `regenerate(graph_version, swap_provider={node: cfg} | remove_node=node)` compiles a new version. Nodes whose cache key is unchanged read from the store.
   - Only nodes whose key changed are recomputed. With a deterministic provider, that is exactly the changed node and its descendants.
   - Removing Red-flag or Human Checkpoint gives `GraphValidationError`.
   - A Human Checkpoint whose input hash changed returns to `pending_confirmation`. A prior confirmation never carries over to changed content.
   - Ablation is `regenerate(remove_node=<Reader>)`.
6. **Providers via the Gateway** (`casegraph/providers.py`)
   - Every model-backed node calls a single `GatewayClient.invoke(GatewayRequest) -> GatewayResponse` seam. This seam uses s0 contract types.
   - The in-process `LocalGateway` wraps a provider from `build_provider`. It applies the same fail-safe semantics as `/api/gateway/invoke`: ideally the router's logic is refactored into a shared `app.gateway.service` that both use.
   - `LocalGateway` writes exactly 1 audit record per call to an injectable sink. The record has the same fields as s0 A12 and no raw inputs.
   - The request `data_class` is the most restrictive `data_class` among the node's inputs.
   - `rules` providers are in-process pure functions versioned by a rule-set version.
   - The Red-flag and Pharma rule sets in this slice are tiny test rule sets, labelled `PLACEHOLDER — not clinical`.
   - Nodes on `project_model` record greedy decoding (`temperature=0`) in their params. Nodes on `external_model` are flagged `reproducible=false` ("may differ on rerun", 3.2.3).
   - Tests use 2 or more `MockProvider`-backed provider ids with distinct `model_version`s. A provider swap therefore changes the cache key.
7. **Export and inspect** (`casegraph/export.py`, `python -m casegraph inspect <graph.json>`)
   - The JSON export has `schema_version, patient_ref, T, snapshot_id, version, parent_version`.
   - It lists nodes with `type, provider, model_version, params, cache_key, status, started_at, ended_at, gateway_calls, reproducible, output, output_sha256`.
   - It lists edges with their data type, and evidence refs with `item_id, data_type, event_time, available_at_time, source, version`.
   - It records graph-level totals: gateway calls and wall time. These feed the Table 3.2 "Case Graph" row later.
   - Import followed by export is byte-identical.
   - `inspect` prints one line per node (type, provider, status) and the edges, and exits 0.
8. **Synthetic fixtures** (`casegraph/tests/fixtures/`)
   - Hand-written. Patients are `SYN-*` and every item has `data_class=synthetic` unless the test says otherwise. They do not depend on s1.
   - Minimum set:
     - F1: T1 has text and vitals. T2 adds a CXR and a medication list. This reproduces Fig. 3.2.
     - F2: text, vitals, labs, CT and MRI.
     - F3: text only, for abstention.
     - F4: mixed availability times around T, including an item exactly at T.
     - F5: vitals that trigger the placeholder urgent rule.
     - F6: one `mimic` item.
9. **s0 test update**
   - `casegraph/tests/test_types.py::test_no_compiler_or_executor_symbols` and the `PLACEHOLDER` assertion are superseded by this slice as s0 foreseen ("Those are slice S2"). Replace them. Do not delete coverage silently.
   - No new third-party runtime dependency (stdlib `asyncio`, `graphlib`, `sqlite3`, `hashlib`). If a test dependency is added, `requirements.lock` must be updated with hashes.

## Out of scope

- UI, API routes, Dashboard, Voice Agent, and DB persistence in the backend's `DATABASE_URL`. The StateStore interface is where that plugs in later.
- Real models, vLLM, encoders, the team 27B model, and any real external API call. External providers stay mocked or disabled.
- Pharma Agent 3.2.4 logic (RxNorm/TMT, duplicate/dose/allergy rules, model phrasing), the real Red-flag rule set, and clinically defined Reasoning required inputs. This slice only provides node types, interfaces and placeholder rule sets.
- Evaluation metrics of Table 3.2 (accuracy, coverage, cost), the no-graph single-prompt baseline, the s1 synthetic dataset, and any MIMIC or hospital data.
- LangGraph. It is optional per 3.2.3 and not used here.

## Acceptance

All criteria are measured by pytest in `casegraph/tests/` (sockets blocked) as part of `make test`. "Gateway calls" means the count at the `GatewayClient` seam. "Node executions" means an instrumented counter on node bodies, including rule functions.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S2-A01 | Replay reproduces stored graph | 100% of node `output_sha256` equal to the original run; **0** gateway calls; **0** node executions; works from a fresh process-equivalent (new Executor + new store instance on the same file) | `test_replay_reproduces_all_outputs` over F1–F5 |
| S2-A02 | Replay never recomputes | A missing or tampered store entry raises `ReplayError`; 0 gateway calls | `test_replay_missing_or_tampered_entry_fails` |
| S2-A03 | Regenerate after one provider swap | Recomputed set **==** {swapped node} ∪ descendants(swapped node), as exact set equality with the count asserted. All other nodes are served from the store with 0 calls. Gateway calls == model-backed nodes in the recomputed set. The recomputed count is below the full-graph count. | `test_regenerate_swap_provider_recomputes_only_descendants` (F1-T2: swap Reader:CXR `encoder_2d`→`external_model`; F2: swap Reader:Text) |
| S2-A04 | Ablation = remove a Reader + regenerate | New version lacks the node. Recomputed set == descendants of the removed node. If a required input is lost, Reasoning abstains with it listed. | `test_ablation_remove_reader` |
| S2-A05 | Deterministic rerun without cache (Table 3.2) | A full rerun with an empty store and the mock provider gives 100% identical `output_sha256` | `test_rerun_without_cache_is_identical` |
| S2-A06 | Mandatory nodes | Red-flag and Human Checkpoint are present in 100% of compiled graphs across all fixtures × T values. A graph missing either, or missing the direct Alerts→Checkpoint edge, fails compile (3/3). Regenerate that removes either fails (2/2). | `test_mandatory_nodes_present`, `test_missing_mandatory_node_rejected[red_flag\|checkpoint\|alerts_edge]`, `test_cannot_remove_mandatory_node` |
| S2-A07 | Snapshot has no future data | 0 items with `available_at_time > T` in any snapshot, graph, node input or export across F1–F6 × ≥3 T values. The boundary item at `== T` is included. A foreign-snapshot or foreign-patient ref fails validation. | `test_snapshot_excludes_future_items` (property-style sweep), `test_foreign_snapshot_item_rejected`, `test_mixed_patient_rejected` |
| S2-A08 | ImageTokens routing | `ImageTokens` to a Reasoning node on `external_model`, or to any non-Reasoning node, fails compile. Encoder→project-model Reasoning compiles. 0 executions happen on the rejected graphs. | `test_imagetokens_to_external_rejected`, `test_imagetokens_to_project_model_ok` |
| S2-A09 | Type and structure validation | Cycle, type mismatch, disallowed provider, and a Reasoning/Pharma output not reaching a checkpoint each fail compile (4/4). The Executor refuses a non-`ValidatedGraph` input. | `test_validation_rejects[cycle\|type_mismatch\|provider\|unreviewed_output]`, `test_executor_requires_validated_graph` |
| S2-A10 | Node selection by data present | For each fixture, the node set equals the expected set (table-driven). Pharma Agent appears in 100% of graphs with `MedicationList` and 0% without. F1 T2 vs T1 node diff is exactly {Reader:CXR, Pharma Agent} (Fig. 3.2). | `test_node_selection_matrix`, `test_fig_3_2_versions` |
| S2-A11 | Versioning | New data gives version n+1 with `parent_version=n`. The v_n export bytes are unchanged after v_{n+1} is created. Compiling the same snapshot + config twice gives byte-identical JSON. | `test_new_data_new_version_old_kept`, `test_compile_deterministic` |
| S2-A12 | Independent Readers run concurrently | With a test provider that blocks on a `threading.Barrier(n_readers, timeout=5s)`, F2 completes. A sequential executor would time out. Trace shows overlapping `[started_at, ended_at]` for ≥2 Readers. | `test_independent_readers_run_concurrently` |
| S2-A13 | Dependency order respected | In 100% of traces, every node's `started_at` ≥ max(`ended_at`) of its predecessors | `test_topological_order_respected` over all fixtures |
| S2-A14 | Reasoning abstains on missing required inputs | F3 gives Reasoning `status=abstained`, `missing_inputs` == exact expected list, 0 gateway calls for Reasoning, and no Suggestion/Summary object. The checkpoint still receives Alerts. | `test_reasoning_abstains_with_missing_list` |
| S2-A15 | Human Checkpoint pending/resume | Execution stops at `pending_confirmation`, which persists in a file StateStore. A fresh Executor resumes it. confirm/edit/reject each produce the correct `ConfirmedResult` with reviewer id, role and UTC time (3/3). A wrong reviewer role is rejected. Resume makes 0 gateway calls for completed nodes. | `test_checkpoint_pending_and_resume[confirm\|edit\|reject]`, `test_resume_wrong_role_rejected` |
| S2-A16 | Confirmed result becomes new evidence, time-gated | After confirm/edit, a snapshot at T ≥ confirm time contains the item. A snapshot at T < confirm time does not. Reject adds 0 evidence items. | `test_confirmed_result_is_new_evidence` |
| S2-A17 | Confirmation never carries over changed content | Regenerate that changes a checkpoint's input hash gives `pending_confirmation` (not confirmed) | `test_confirmation_not_reused_after_change` |
| S2-A18 | Red-flag priority and fail-safe | F5: Alerts contain the urgent placeholder alert, and the checkpoint payload has `escalation=true`, even when Reasoning abstains or errors. With no Red-flag inputs, Alerts `status=not_evaluated` (never an empty "clear"). | `test_red_flag_escalates_regardless_of_reasoning`, `test_red_flag_not_evaluated_without_inputs` |
| S2-A19 | Provider failure fails safe | Gateway `error`, `rejected`, and schema-invalid output each give node `status=error, output=null`. Descendant Reasoning abstains and lists the errored input. 0 fabricated outputs (3/3). | `test_provider_failure_fail_safe[error\|rejected\|schema_invalid]` |
| S2-A20 | Providers only through the Gateway; data policy | 0 imports of `app.gateway.adapters` or any provider SDK in `casegraph/`. Every model-backed node execution produces exactly 1 `GatewayClient` call and 1 audit record, with no raw input sentinel in audit. F6 (`mimic`) wired to `external_model` fails compile. The mock provider is deterministic (the same request gives byte-identical output). | `test_casegraph_provider_isolation` (AST scan), `test_one_gateway_call_and_audit_per_model_node`, `test_non_synthetic_to_external_rejected` |
| S2-A21 | Cache key composition | Changing any one of node_type, provider, model_version, params or any input byte changes the key (5/5). Identical inputs give an identical key. | `test_cache_key_components` |
| S2-A22 | Export round-trip and inspect | export→import→export is byte-identical for all fixtures. Export contains every field listed in Scope 7 and `reproducible=false` on external nodes. `python -m casegraph inspect` exits 0 and prints every node. An imported graph replays with 0 calls. | `test_export_roundtrip`, `test_export_fields`, `test_inspect_cli` |
| S2-A23 | Typed data contract | 7 evidence types reject a missing `event_time/available_at_time/source/version/data_class` and `available_at_time < event_time`. Derived outputs forbid extra fields. 0 output fields named `reasoning`, `thought`, `chain_of_thought` or `rationale_hidden`. | `test_typed_data_contract`, `test_no_hidden_reasoning_fields` |
| S2-A24 | Whole suite green, offline | `make test` exit 0: s0 and s2 tests pass (0 failed/errors). Sockets are blocked. The casegraph suite runs in < 60 s on CPU. | `make test` in the worktree, output recorded |

## Required test cases

These live in `casegraph/tests/`:

- `test_typed_data.py`: A23.
- `test_library.py`: Table 3.1 declarations and allowed providers.
- `test_compiler.py`: A06–A11, A08, A20 (policy).
- `test_executor.py`: A12–A15, A18, A19.
- `test_store_replay.py`: A01–A05, A16, A17, A21.
- `test_export.py`: A22.
- `test_isolation.py`: A20.
- Updated `test_types.py`: s0 A15 superseded as noted.

Every named test in the acceptance table must exist and pass.

## Clinical and safety risks

| Risk | Mitigation (criterion) |
|---|---|
| Future information leaks into a decision (2.1.4) | Snapshot filter plus a validation sweep (A07). Confirmed results are time-gated (A16). |
| An urgent red flag is hidden behind ranking or failure | Red-flag is mandatory. There is a direct Alerts→Checkpoint edge and escalation irrespective of Reasoning (A06, A18). |
| "No alerts" is shown when nothing was evaluated | `not_evaluated` status instead of an empty result (A18). |
| Fabricated certainty when data is missing or a provider fails | Abstain with a missing-input list and a fail-safe `error` (A14, A19). |
| An output affects care without human review | Every Reasoning or Pharma output must reach a Human Checkpoint. Execution halts pending. Confirmation is bound to the input hash (A09, A15, A17). |
| MIMIC or non-synthetic data goes to an external provider (1.3.4) | Compile-time rejection plus the gateway's runtime policy (A20). |
| A replay silently differs from what the clinician saw | Replay is store-only, with hash verification and no fallback (A01, A02). External nodes are flagged non-reproducible (A22). |
| A placeholder rule set is mistaken for clinical rules | Rule sets are labelled `PLACEHOLDER — not clinical`. The real rules are out of scope. |
| Hidden chain-of-thought is exposed | Output schemas have no reasoning fields. The inspectable artifact is the executed graph (A22, A23). |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent-casegraph
make test                                        # full suite (s0 + s2), offline
.venv/bin/python -m pytest -q casegraph/tests    # s2 only (PYTHONPATH=.:backend, as set by Makefile)
.venv/bin/python -m casegraph inspect <graph.json>
```

## Decisions needed (none blocking)

- Whether to refactor the s0 router fail-safe logic into a shared `app.gateway.service` is the engineer's choice. The constraint is that s0 A09 and A12 stay green.
- The clinical required-input set for Reasoning and the real Red-flag rules need clinical review in a later slice. The placeholders here must not be used for evaluation claims.
