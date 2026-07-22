---
name: b36-offline-private-developer-workflow
description: "Implement IDE CLI preview navigation repair evaluation review and evidence workflows for private and air-gapped environments with local trust roots mirrors models and signed bundles."
---

# Skill 1302: b36-offline-private-developer-workflow

## Use this skill when

- Customers require developer workflows without public internet or shared SaaS control planes.
- The same core developer experience must operate with local services and delayed synchronization.

## Domain-specific risks and invariants

- Hidden cloud dependencies, automatic update calls, external telemetry, model fallbacks, and unresolved clock or trust issues can break offline operation.
- Offline evidence and approvals must synchronize without duplication or tampering.

## Workflow

1. Inventory every runtime, update, package, model, telemetry, identity, certificate, and documentation dependency.
2. Define offline topology, local identity, workload CA, artifact/package mirrors, local model or no-model mode, trust roots, time source, and update process.
3. Implement local protocol endpoints, signed installation/update bundles, offline licensing, local evidence storage, and export/import synchronization.
4. Implement IDE and CLI behavior for disconnected status, queued operations, conflict resolution, and support bundle export.
5. Run a network-denied installation, upgrade, rollback, representative workflow, evidence export, and later synchronization test.

## Required repository outputs

- `offline/profile.json`, dependency manifest, local topology, signed bundle manifests
- Air-gap install/update/rollback scripts, local service configs, evidence sync contracts
- Network-denied and delayed-sync certification evidence

## Verification

- Run with outbound network blocked and monitor all connection attempts.
- Verify no external model, telemetry, package, license, or update fallback.
- Test clock skew, expired certificates, offline identity, evidence tampering, duplicate import, and conflict handling.
- Verify bundle signatures and rollback.

## Stop and escalate when

- Any hidden public service is required.
- Offline licensing or certificate expiry causes unsafe operation or data loss.
- Evidence cannot be synchronized idempotently.
- Signed update and rollback evidence is missing.

## Definition of done

- P0 developer workflows operate fully offline.
- No unauthorized external connection is attempted.
- Bundles are signed, verifiable, upgradeable, and reversible.
- Evidence and decisions synchronize safely when connectivity returns.
