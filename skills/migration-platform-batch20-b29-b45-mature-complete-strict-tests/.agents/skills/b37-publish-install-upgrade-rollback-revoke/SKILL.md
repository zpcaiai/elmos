---
name: b37-publish-install-upgrade-rollback-revoke
description: Implement extension publication discovery installation activation upgrade rollback disable uninstall quarantine and revocation with immutable releases and tenant policy.
---

# Skill 1322: b37-publish-install-upgrade-rollback-revoke

## Use this skill when

- Certified extensions need safe distribution and operation.
- Customers require controlled upgrades and emergency revocation.

## Domain-specific risks and invariants

- Mutable marketplace releases prevent rollback and audit.
- Revocation that only hides a listing does not stop installed malicious code.

## Workflow

1. Implement immutable release records and channels.
2. Verify signatures, compatibility, permissions, policies, license, and certification before installation.
3. Support staged rollout, tenant approval, canary, health checks, configuration migration, and rollback.
4. Implement disable, quarantine, uninstall cleanup, global revocation, and kill switch.
5. Track install base, version, status, policy decisions, and evidence.

## Required repository outputs

- release catalog and channel records
- installation and activation state machine
- upgrade rollback uninstall and revocation evidence

## Verification

- Install, upgrade, rollback, disable, uninstall, and revoke in an isolated tenant.
- Verify revoked versions cannot execute, renew leases, or reinstall.
- Verify configuration and data migrations are reversible or explicitly blocked.

## Stop and escalate when

- Upgrade has no rollback or forward-recovery path.
- Revocation cannot reach offline or private installations within policy.

## Definition of done

- Immutable release lifecycle works end to end.
- Revocation stops execution, not merely discovery.
- Tenant policy remains authoritative.
