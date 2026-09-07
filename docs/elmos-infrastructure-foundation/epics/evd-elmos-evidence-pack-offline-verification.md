# Immutable Evidence Pack, Offline Verification, and Delivery Provenance

- Skill: `elmos-evidence-pack-offline-verification`
- Priority: `P0`
- Phase: `G7`
- Dependencies: `elmos-content-addressed-cache`, `elmos-verification-fabric`, `elmos-staging-snapshot-promotion`, `elmos-policy-supply-chain-signing`

## Objective

Turn each project generation or migration into an independently auditable delivery rather than an opaque output archive.

## Task groups

### Evidence data model

- [ ] `ELMOS-EVD-001` Define evidence pack/item, type, schema version, digest, size, producer, tenant, project, workflow, stage, task, attempt, timestamps, sensitivity, retention, and provenance.
- [ ] `ELMOS-EVD-002` Link items to source/target snapshots, action, toolchain, rule, prompt, model, policy, approvals, and certification.
- [ ] `ELMOS-EVD-003` Define mandatory/optional evidence by workflow and certification level.
- [ ] `ELMOS-EVD-004` Represent absent, failed, waived, superseded, and expired evidence explicitly.

### Evidence types

- [ ] `ELMOS-EVD-005` Capture source snapshot, inventory, dependency, toolchain, rule execution, model/agent, patch, build, tests, contracts, behavior, performance, security, supply chain, sandbox, resilience, cost, risk, approval, promotion, rollback, and DR evidence.
- [ ] `ELMOS-EVD-006` Use structured schemas plus referenced raw reports.
- [ ] `ELMOS-EVD-007` Normalize timestamps and canonicalize structured documents for digest/signature.

### Pack assembly

- [ ] `ELMOS-EVD-008` Build a deterministic directory/manifest containing every artifact path, media type, schema, digest, size, sensitivity, and relationship.
- [ ] `ELMOS-EVD-009` Include missing evidence, Known Deviations, Risk Register, Manual Tasks, certification, and verification instructions.
- [ ] `ELMOS-EVD-010` Reference large CAS objects or embed them according to export policy.
- [ ] `ELMOS-EVD-011` Generate ZIP/TAR plus overall digest without nondeterministic timestamps/order.
- [ ] `ELMOS-EVD-012` Scan the pack for secrets and prohibited source before release.

### Signing and trust

- [ ] `ELMOS-EVD-013` Sign canonical manifest and optionally individual high-value items.
- [ ] `ELMOS-EVD-014` Record signer identity, certificate/key reference, trust root, algorithm, time, and transparency/provenance where applicable.
- [ ] `ELMOS-EVD-015` Support enterprise/offline trust roots and rotation.
- [ ] `ELMOS-EVD-016` Reject altered, unknown, expired, or revoked signatures according to policy.

### Offline verifier

- [ ] `ELMOS-EVD-017` Provide elmos evidence verify with no control-plane dependency.
- [ ] `ELMOS-EVD-018` Verify archive safety, manifest schema, path uniqueness, size, digest, signature, trust, mandatory evidence, relationships, certification rules, and expiry.
- [ ] `ELMOS-EVD-019` Output human summary and stable JSON report with CERTIFIED/LIMITED/EXPERIMENTAL/BLOCKED plus reasons.
- [ ] `ELMOS-EVD-020` Support air-gapped operation and signed verifier releases/checksums.
- [ ] `ELMOS-EVD-021` Never execute project content during verification.

### Lifecycle and export

- [ ] `ELMOS-EVD-022` Apply tenant retention, legal hold, export, delete, redaction, and residency policies.
- [ ] `ELMOS-EVD-023` Keep immutable historical packs while allowing metadata supersession links.
- [ ] `ELMOS-EVD-024` Audit every export/download/delete/hold/sign/verify operation.
- [ ] `ELMOS-EVD-025` Reconcile pack references against CAS and backup state.

## Validation

- [ ] Alter one byte, remove an item, change manifest order/path, inject traversal/symlink, and verify failure.
- [ ] Verify with unknown/revoked/expired trust roots.
- [ ] Remove mandatory evidence and require downgraded/blocking status.
- [ ] Inject secret/source patterns and prevent export.
- [ ] Verify the same pack in an offline clean environment.

## Exit gate

- [ ] Every promoted delivery has a deterministic signed evidence pack.
- [ ] Tampering and missing evidence are detected offline.
- [ ] The pack explains source-to-output provenance, deviations, risk, approvals, and certification.
- [ ] Export contains no forbidden secret or source material.
