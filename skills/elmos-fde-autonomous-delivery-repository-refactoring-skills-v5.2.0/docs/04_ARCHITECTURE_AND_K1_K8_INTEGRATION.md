# 04 — Architecture and K1–K8 Integration

| Kernel | Canonical authority | Representative component Skills |
|---|---|---|
| K1 | Intent, Engagement and Goal Authority | adoption-change-management, business-baseline-roi, business-capability-code-mapping, final-handoff-training-support, incident-triage-remediation-and-postmortem, pilot-scope-sow-acceptance … |
| K2 | Repository Facts and Native Runtime Authority | asset-inventory-and-classification, external-dependency-stub-and-service-virtualization, git-history-ownership-change-coupling, polyglot-semantic-system-graph, portfolio-multi-repository-governance, repository-custody-and-revisionset … |
| K3 | Semantic Truth and System Graph Authority | ai-agent-system-audit, architecture-maintainability-audit, asset-inventory-and-classification, business-capability-code-mapping, business-invariant-recovery, correctness-concurrency-consistency-audit … |
| K4 | Reasoning, Planning and Decision Support | ai-agent-system-audit, architecture-maintainability-audit, business-baseline-roi, business-capability-code-mapping, business-invariant-recovery, correctness-concurrency-consistency-audit … |
| K5 | Transformation and Artifact Production | changeset-commit-and-provenance-governance, cross-language-framework-transformation, database-schema-routine-data-transformation, incident-triage-remediation-and-postmortem, modernization-strangler-and-rearchitecture, proof-guided-atomic-refactor-execution … |
| K6 | Verification and Evidence Production | ai-agent-system-audit, business-invariant-recovery, characterization-differential-mutation-verification, correctness-concurrency-consistency-audit, cross-language-framework-transformation, data-database-migration-audit … |
| K7 | Durable Execution, Effects and Lifecycle | adoption-change-management, changeset-commit-and-provenance-governance, cost-finops-sustainability-audit, database-schema-routine-data-transformation, external-dependency-stub-and-service-virtualization, final-handoff-training-support … |
| K8 | Independent Completion and Certification Authority | ai-agent-system-audit, changeset-commit-and-provenance-governance, characterization-differential-mutation-verification, data-event-permission-lineage, e0-e3-readiness-and-evidence-bundle, final-handoff-training-support … |

## Execution contract

```text
Execution = Identity + Ownership + Environment + Authority + Timeline + Artifacts + Lifecycle + Effects + Evidence
```

## Control flow

```text
K1 approved intent/scope
  → K2 exact repository/runtime facts
  → K3 semantic system graph
  → K4 findings, invariants and Transformation DAG
  → K5 atomic artifacts/ChangeSets
  → K6 independent evidence production
  → K7 durable lifecycle/effect reconciliation
  → K8 E0–E3 decision in this package; external E4/E5/P05 elsewhere
```

## Integration rule

Component Skills never route themselves. The target installer resolves `binding://...` references to an existing route owner. Adapters implement ports only. Projections may be rebuilt; append-only ledger history is authoritative.
