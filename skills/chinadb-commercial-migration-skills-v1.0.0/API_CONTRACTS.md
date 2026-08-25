# Core API Contracts

The concrete language may be Python/Java/Rust/TypeScript, but semantics should match these contracts.

```text
interface Converter<TSourceIR, TTargetArtifact> {
  assess(node, route) -> CompatibilityFinding
  convert(node, route, capabilities) -> ConversionResult<TTargetArtifact>
  explain(result) -> RuleTrace
}

interface DifferentialVerifier {
  run(scenario, sourceEndpoint, targetEndpoint) -> DifferentialEvidence
  minimize(mismatch) -> Reproduction
}

interface PerformanceVerifier {
  fingerprint(environment) -> EnvironmentFingerprint
  run(workload, environment) -> PerformanceEvidence
  compare(sourceEvidence, targetEvidence, policy) -> GateDecision
}

interface RepairEngine {
  classify(failedEvidence) -> FailureClass
  propose(failure, context) -> RepairPlan[]
  verify(plan) -> RepairEvidence
}

interface MigrationProvider {
  plan(route, inventory) -> MovementPlan
  snapshot(plan) -> SnapshotEvidence
  startCdc(plan, snapshotPosition) -> CdcHandle
  checkpoint(handle) -> LogPosition
  reconcile(plan) -> DataEvidence
}
```

## Stable error contract

Application behavior must not depend directly on vendor error numbers after migration. Normalize to a stable error taxonomy, while retaining source and target error metadata in evidence:

- duplicate_key
- foreign_key_violation
- check_violation
- not_null_violation
- numeric_overflow
- deadlock
- serialization_failure
- lock_timeout
- statement_timeout
- connection_failure
- permission_denied
- object_not_found
- syntax_or_feature_unsupported

## Comparison policy

Comparators must distinguish:

- exact scalar equality;
- decimal equality by declared precision/scale;
- float tolerance only when business contract permits;
- timestamp instant equality vs local-field equality;
- ordered rowsets vs unordered multisets;
- LOB checksum + optional exact byte comparison;
- stable error taxonomy + route-specific metadata;
- side-effect/event set and transaction final state.
