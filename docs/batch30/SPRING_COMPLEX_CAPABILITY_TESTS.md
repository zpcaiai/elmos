# Spring Complex Capability Test Manifest

Spring upgrades that detect security, persistence/database, transaction, or messaging behavior must include the project-owned manifest `elmos/spring-capability-tests.json`. The local worker evaluates it after source/target test parity and before guidance or artifact packaging.

Dependency declarations are discovery facts only. They can make a domain subject to this gate, but they do not prove that the capability is active or behaviorally equivalent.

## Complete example

The same bytes must exist in the source snapshot and transformed target. Replace the example test identities with identities emitted by the project's real test reports.

<!-- spring-capability-tests-example:start -->
```json
{
  "schema_version": "1.0",
  "kind": "elmos.spring-capability-tests",
  "test_identities": [
    "com.acme.messaging.MessagingContractTest#preservesMessagingContract",
    "com.acme.persistence.DatabaseContractTest#preservesDatabaseContract",
    "com.acme.security.SecurityContractTest#preservesSecurityContract",
    "com.acme.transaction.TransactionContractTest#preservesTransactionContract"
  ],
  "domains": {
    "security": {
      "invariants": [
        "authentication-success-and-failure",
        "authorization-allow-and-deny",
        "csrf-cors-session-and-error-contract",
        "filter-chain-order"
      ],
      "test_identities": [
        "com.acme.security.SecurityContractTest#preservesSecurityContract"
      ]
    },
    "persistence_database": {
      "invariants": [
        "constraint-locking-and-exception-semantics",
        "provider-dialect-and-transaction-resource-binding",
        "query-result-null-and-precision-equivalence",
        "schema-mapping-and-generated-identifiers"
      ],
      "test_identities": [
        "com.acme.persistence.DatabaseContractTest#preservesDatabaseContract"
      ]
    },
    "transactions": {
      "invariants": [
        "commit-rollback-and-exception-timing",
        "nested-and-self-invocation-boundaries",
        "propagation-isolation-read-only-and-timeout",
        "transaction-manager-selection"
      ],
      "test_identities": [
        "com.acme.transaction.TransactionContractTest#preservesTransactionContract"
      ]
    },
    "messaging": {
      "invariants": [
        "ack-retry-redelivery-and-dead-letter",
        "broker-transaction-boundaries",
        "ordering-concurrency-and-duplicate-handling",
        "payload-header-and-serialization-equivalence"
      ],
      "test_identities": [
        "com.acme.messaging.MessagingContractTest#preservesMessagingContract"
      ]
    }
  }
}
```
<!-- spring-capability-tests-example:end -->

## Schema and identity rules

- `schema_version` must be `1.0`; `kind` must be `elmos.spring-capability-tests`.
- `test_identities`, every required domain's `invariants`, and every required domain's `test_identities` must be non-empty arrays of unique strings. Values are at most 512 characters and cannot contain `*` or `?` wildcards.
- Each domain test identity must appear in the top-level list and in the executed source test identities. Because the gate separately requires exact source/target test identity equality, it is therefore also present in the target execution.
- Test identities come from Maven Surefire `surefire-reports/TEST-*.xml` or Gradle `test/TEST-*.xml` `<testcase>` results and are normalized as `<classname>#<name>`. Renaming, dropping, or adding a target identity breaks exact set equality; duplicate manifest values are rejected. The module name is not part of the identity, so project test identities must be globally unique. Failsafe-only reports are not read by the current local gate and cannot be claimed as its evidence. Source and target skipped counts must both be zero for a critical-capability run.
- The manifest must be a regular file below the project root, cannot be reached through a symbolic-link segment, must be non-empty and no larger than 512 KiB, and must remain byte-for-byte identical after transformation.
- Only detected domains are required. Extra names do not create runtime evidence and do not raise support status.

## Required invariants

| Domain | Required invariants |
|---|---|
| `security` | `authentication-success-and-failure`; `authorization-allow-and-deny`; `filter-chain-order`; `csrf-cors-session-and-error-contract` |
| `persistence_database` | `schema-mapping-and-generated-identifiers`; `query-result-null-and-precision-equivalence`; `constraint-locking-and-exception-semantics`; `provider-dialect-and-transaction-resource-binding` |
| `transactions` | `commit-rollback-and-exception-timing`; `propagation-isolation-read-only-and-timeout`; `transaction-manager-selection`; `nested-and-self-invocation-boundaries` |
| `messaging` | `payload-header-and-serialization-equivalence`; `ack-retry-redelivery-and-dead-letter`; `ordering-concurrency-and-duplicate-handling`; `broker-transaction-boundaries` |

Static fingerprints marked `observed`, `conditional`, `declared-only`, `generated`, or `unknown` in these four domains require the gate. Recognized custom or dynamic security/provider, data-source, multi-resource transaction, and listener-container behavior can add a named invariant to the applicable domain.

An unresolved conditional activation always adds `CONDITIONAL_ACTIVATION_UNRESOLVED:<capability>` and blocks packaging even when the manifest and tests are otherwise complete. A manifest cannot convert an unresolved profile, property, bean condition, or runtime registration into active-behavior evidence.

## Decision and evidence boundary

The worker writes `evidence/complex-capability-verification.json` before packaging:

- `PASS_LOCAL_ENGINEERING`: required project tests executed locally with exact identities, zero skips, and a valid unchanged manifest. The report still sets `certification_eligible=false`, `certification_status=NOT_CERTIFIED`, and independent/customer/production evidence to `NOT_RUN`.
- `NOT_APPLICABLE`: none of the four critical domains was detected. This is not a behavioral-equivalence or certification result.
- `BLOCKED`: at least one fail-closed reason exists. The run raises `COMPLEX_CAPABILITY_VERIFICATION_BLOCKED` and does not package an artifact.

The manifest declares which project tests cover the invariants; it does not independently prove their semantics. Batch 30 holdout, representative-repository, provider/runtime, and independent certification gates remain separate.

## Failure codes

The outer run error is `COMPLEX_CAPABILITY_VERIFICATION_BLOCKED`. Its report contains one or more specific blockers:

- Activation/test integrity: `CONDITIONAL_ACTIVATION_UNRESOLVED:<capability>`, `SOURCE_COMPLEX_CAPABILITY_TEST_IDENTITIES_EMPTY`, `SOURCE_TARGET_TEST_IDENTITY_MISMATCH`, `COMPLEX_CAPABILITY_TESTS_SKIPPED`.
- Manifest ownership/integrity: `CAPABILITY_TEST_MANIFEST_MISSING`, `TARGET_CAPABILITY_TEST_MANIFEST_MISSING`, `CAPABILITY_TEST_MANIFEST_CHANGED_BY_TRANSFORMATION`, `SOURCE_CAPABILITY_TEST_MANIFEST_SIZE_INVALID`, `TARGET_CAPABILITY_TEST_MANIFEST_SIZE_INVALID`, `SOURCE_CAPABILITY_TEST_MANIFEST_READ_FAILED`, `TARGET_CAPABILITY_TEST_MANIFEST_READ_FAILED`. A source manifest reached through a symbolic link is reported as missing.
- Root/schema: `CAPABILITY_TEST_MANIFEST_ROOT_INVALID`, `CAPABILITY_TEST_MANIFEST_SCHEMA_VERSION_INVALID`, `CAPABILITY_TEST_MANIFEST_KIND_INVALID`, `CAPABILITY_TEST_MANIFEST_DOMAINS_INVALID`, `CAPABILITY_TEST_MANIFEST_JSON_INVALID`.
- Arrays: `<FIELD>_EMPTY_OR_INVALID`, `<FIELD>_NON_STRING`, `<FIELD>_VALUE_INVALID`, or `<FIELD>_DUPLICATE`, where `<FIELD>` is `MANIFEST_TEST_IDENTITIES`, `MANIFEST_INVARIANTS:<domain>`, or `MANIFEST_DOMAIN_TEST_IDENTITIES:<domain>`.
- Domain binding: `MANIFEST_TEST_IDENTITIES_NOT_IN_SOURCE_EXECUTION`, `CAPABILITY_TEST_DOMAIN_MISSING:<domain>`, `MANIFEST_INVARIANTS_MISSING:<domain>:<invariant+...>`, `DOMAIN_TEST_IDENTITIES_NOT_IN_MANIFEST:<domain>`, `DOMAIN_TEST_IDENTITIES_NOT_EXECUTED:<domain>`.
