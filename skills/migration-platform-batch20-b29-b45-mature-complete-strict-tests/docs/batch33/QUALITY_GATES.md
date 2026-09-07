
# Batch 33 quality gates

## Structural

- Exact source and target tuples with no floating versions.
- Static plus runtime source fingerprint.
- Typed Runtime Architecture Contract and IaC IR with source mapping.
- Target and validation profiles with accountable owners.

## Functional

- Real source and target plan validation.
- Target apply or runtime/emulator validation in an approved isolated environment.
- Container, orchestrator, CI/CD, identity, network, secret, managed-service, ingress, observability, drift, cost, rollback, and destroy evidence as applicable.
- P0 deployment contracts and representative workloads pass.

## Security

- No privilege expansion, secret leak, unapproved public ingress or egress, data-residency breach, unsigned mutable release, or cross-tenant state reuse.
- State backends are encrypted, access controlled, and locked where applicable.
- Security and policy-as-code checks run before apply.

## Certification

- Unknown critical behavior, silent resource drops, critical regressions, orphaned resources, and test-integrity violations are zero.
- Holdout and representative workload corpora are non-empty.
- Evidence references resolve to real files or approved external evidence.
- The certification status is determined by `scripts/batch33/run_cloud_gate.py`.
