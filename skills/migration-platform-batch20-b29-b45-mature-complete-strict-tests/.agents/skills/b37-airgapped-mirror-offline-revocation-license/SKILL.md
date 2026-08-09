---
name: b37-airgapped-mirror-offline-revocation-license
description: Implement signed air-gapped marketplace mirrors offline catalog SBOM certification entitlement revocation and emergency update synchronization.
---

# Skill B37-X12: b37-airgapped-mirror-offline-revocation-license

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Offline operation does not disable signature, certification, license, or revocation enforcement.
- Stale mirrors automatically block high-risk new activation after the approved window.
- Trust-root rotation has an offline recovery procedure.

## Workflow

1. Define source catalog, trust roots, signed mirror bundle, import/export station, synchronization interval, maximum staleness, and offline ownership.
2. Package catalog metadata, artifacts, signatures, SBOM, provenance, certification, licenses, and revocation lists into immutable signed bundles.
3. Validate bundles before import and preserve exact source-to-mirror digest relationships.
4. Implement offline entitlement leases, emergency revocation bundles, disconnected kill switch, and delayed evidence synchronization.
5. Run completely disconnected install, upgrade, rollback, revocation, expiry, and recovery tests.

## Required repository outputs

- `offline-mirror/policy.json`
- signed mirror manifests, sync history, staleness alarms, revocation evidence, and disconnected test results

## Verification

- Run `validate_offline_mirror.py`.
- Disconnect all public network paths and execute representative lifecycle and emergency revocation tests.

## Stop and escalate when

- Mirror staleness exceeds risk policy or revocation freshness is unknown.
- No secure path exists for trust-root or emergency-revocation updates.

## Definition of done

- Air-gapped catalogs remain verifiable, current within policy, licensed, revocable, and recoverable.
