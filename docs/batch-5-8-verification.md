# Batch 5–8 verification and external gates

## Offline evidence included in this repository

| Batch | Verified locally | Binding boundary |
|---|---|---|
| 5 | License closure, deterministic selection/manifest, pinned argv, idempotence/oscillation, patch segmentation, promotion policy | No real OpenRewrite customer run without approved Workspace and artifact closure |
| 6 | Failure redaction/fingerprints, minimal context, hard routing, reservation/settlement, provider plans, patch policy, bounded loop/escalation | Agent provider execution requires a separately configured isolated runner |
| 7 | Environment comparability, build/test differential, API/serialization/database/transaction/performance comparisons, policy aggregation | Docker/Testcontainers evidence must come from two fresh pinned environments |
| 8 | Delivery read model/reports, Draft SCM/check plans, annotation batching, signed pack create/verify, rollback/acceptance policy | Live PR/MR/check/signing/rollback requires provider credentials, key service and target system evidence |

## Required live acceptance sequence

1. Prove a rootless daemon with `docker info`; build sandbox and service images, record immutable digests, SBOM, vulnerability scan, provenance and secret scan, then approve them in the registry.
2. Use a non-production private test repository and short-lived GitHub App or GitLab installation token. Freeze a source Snapshot and show that the token is revoked before transformation begins.
3. Resolve and hash the complete OpenRewrite artifact closure. Confirm the license decision for the exact execution context before allowing download. Run a changed recipe twice using fresh processes and collect all required Data Tables.
4. Configure one Agent provider in an editing-only Workspace. Verify denied network, Docker Socket, secret and SCM actions; rebuild the patch in another fresh Workspace.
5. Provision distinct Baseline and Migrated validation environments with pinned image digests and identical fixtures. Disable Testcontainers reuse and capture container identities and cleanup.
6. Configure a test SCM target. Create only a Draft PR/MR, bind checks to its exact HEAD, then change HEAD and verify the former result becomes stale. For GitHub, exercise more than 50 annotations; for GitLab, test tier detection and fallback.
7. Supply an external Ed25519 signing key without writing private key material to logs or the evidence pack. Verify archive tamper rejection and configured retention.
8. Execute a rollback drill covering data, cache/message compatibility and traffic. Record observed RTO/RPO; do not substitute target estimates for measurements.
9. Obtain named human acceptance, merge and release evidence separately before closing the delivery.

## Fail-closed states

`NOT_RUN` means the external action did not execute. `BLOCKED` means policy refused it. `INCONCLUSIVE` means evidence exists but cannot support a decision. None may be converted to `PASS` by a renderer, Coding Agent, Recipe runner or SCM adapter.
