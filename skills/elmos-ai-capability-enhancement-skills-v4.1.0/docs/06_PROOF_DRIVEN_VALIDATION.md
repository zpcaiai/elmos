# Proof-Driven Cross-Framework Validation

## The equivalence problem

Agent outputs are stochastic and target frameworks expose different internal events. Exact final-string comparison is too strict in some places and dangerously weak in others. Elmos compares typed observations under an explicit assurance contract.

## Normalized Agent Execution Trace

```text
Input
 → Routing decision
 → Retrieval query/results
 → Model invocation/output contract
 → Tool proposal
 → Authority/approval decision
 → Tool execution/result
 → State transition/checkpoint
 → Side effect/reconciliation
 → Evidence references
 → Output
 → Terminal state
```

Each event has:

- stable semantic key;
- causal predecessors;
- sequence or logical clock;
- typed status;
- payload hash and optional redacted view;
- AI-SIR node;
- target-native trace/span links;
- exact RevisionSet, model/tool/adapter versions;
- tenant and authority context.

## Comparison dimensions

| Dimension | Comparator |
|---|---|
| Output schema | structural/schema comparator |
| Final content | exact, normalized, semantic or authoritative-oracle comparator |
| Tool calls | typed tool/effect/argument comparator |
| Order | exact order or declared partial order |
| State | field invariants and transition relation |
| Side effects | identity, postcondition, idempotency and reconciliation |
| Retrieval | evidence set, rank tolerance, ACL, citation |
| Approval | gate occurrence, authority and timing |
| Termination | terminal state and bounded iteration |
| Cost/latency | statistical threshold and confidence |
| Security | required denial/containment observations |

A route may tolerate prose differences while requiring identical authorized evidence and side-effect postconditions.

## Proof Obligation Graph

An obligation specifies:

```yaml
id: po-external-write-approval
subject: ai-sir://workflow/external_write
claim: no external write occurs without current approved authority
assumptions:
  - identity provider available
dependencies:
  - po-fencing
criticality: critical
requiredAssurance: A3
acceptedEvidence:
  - policy-negative-test
  - crash-recovery-integration
  - side-effect-ledger-reconciliation
```

Dependencies prevent a child claim from passing when a foundation is unknown.

## Verifier portfolio

K6 selects independent combinations:

- compiler/type/static analysis;
- schema, contract and target-native conformance;
- unit/integration/E2E;
- source-target or cross-target differential execution;
- property and metamorphic tests;
- mutation and fuzzing;
- symbolic execution/SMT/model checking where suitable;
- security and supply-chain tools;
- performance/statistical tests;
- resilience/fault injection;
- manual/customer acceptance where authority is human.

Translation validation checks each generated revision. Trust in the generator does not replace evidence for the output.

## Status semantics

| Status | Meaning |
|---|---|
| `PROVED` | Claim established within declared formal assumptions/envelope |
| `TESTED` | Independent executable evidence covers declared scenarios/properties |
| `BOUNDED` | Holds only within explicit bounds |
| `RUNTIME_MONITORED` | Not pre-established; monitored with operational response |
| `WAIVED` | Authorized residual risk, with owner/expiry |
| `UNKNOWN` | Evidence cannot determine |
| `UNSUPPORTED` | Verifier/target cannot represent or execute the claim |
| `REFUTED` | Counterexample exists |

Interfaces must not paint all non-failing statuses green.

## Graph verification

Generated graph workflows receive obligations for:

- terminal reachability;
- loop bound or cancellable continuation;
- branch coverage;
- state merge conflicts;
- serialization and checkpoint compatibility;
- retry safety;
- approval before effect;
- compensation/reconciliation;
- deadlock and wait-cycle risk;
- stale resume and authority expiry.

Formal methods can establish bounded state-machine properties when encodings are faithful. Dynamic tests remain necessary at external/open-world boundaries.

## Counterexample-guided repair

```text
Verifier failure
  → minimize failing scenario/trace/input
  → attribute to AI-SIR, lowering rule, adapter, template or generated region
  → choose deterministic rule fix or bounded patch
  → rerun affected obligations and invalidated evidence
  → promote regression fixture
```

Repair stops at configured cycles, semantic risk, patch size, cost or wall-clock limits.

## E0–E5 for AI projects

- **E0 — Inventory:** source, runtime, dependencies, target versions, data and boundaries classified.
- **E1 — Semantic readiness:** requirement graph, AI-SIR, capability decisions, proof obligations and exact RevisionSet complete.
- **E2 — Build/import:** target-native import/compile/build/package succeeds.
- **E3 — Runtime:** target starts/loads, APIs/tools/state/persistence and basic integrations execute.
- **E4 — Behavioral assurance:** differential/contract/RAG/graph/security evidence meets critical gates.
- **E5 — Production assurance:** performance, resilience, tenancy, supply chain, operations, backup/restore, cutover/rollback and customer acceptance pass.
- **P05:** deployment-complete evidence for production release.

A target can be E3 and still be far from E5.

## Independent certification

K8 receives sealed evidence; it does not generate or repair code. The certificate binds:

- exact RevisionSet;
- source and generated tree/commit hashes;
- AI-SIR/schema version;
- adapter/model/toolchain/verifier digests;
- policy bundle and TCB;
- proof statuses;
- assumptions/waivers;
- E0–E5/P05;
- side-effect settlement;
- evidence root;
- expiry/drift triggers;
- signer.

Evidence drift revokes or narrows the certificate.
