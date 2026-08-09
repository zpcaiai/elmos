---
name: b37-extension-dependency-lock-composition
description: Implement deterministic extension dependency resolution lockfiles composition compatibility cycle detection revocation propagation and reproducible installation plans.
---

# Skill B37-X01: b37-extension-dependency-lock-composition

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Dependency constraints use exact or bounded semver and never `latest`, wildcard-only, or unpinned digests.
- A revoked or quarantined transitive dependency blocks activation unless an approved replacement is locked.
- Composition certification is separate from individual extension certification.

## Workflow

1. Inspect extension manifest dependency declarations, product compatibility, publisher trust, revocation state, and current installations.
2. Build a typed dependency graph and solve exact versions under product, SDK, policy, region, license, and tenant constraints.
3. Reject cycles, floating versions, conflicting permissions, revoked dependencies, and incompatible transitive dependencies.
4. Emit a signed lockfile with exact artifact digests, resolver version, decision trace, and install/upgrade order.
5. Run composition contract tests and revocation propagation tests against development, negative, holdout, and representative extension sets.

## Required repository outputs

- `marketplace-packs/<pack-key>/dependencies/lock.json`
- dependency decision trace, composition test results, and revocation impact report

## Verification

- Run `validate_dependency_lock.py` and resolve every node, edge, digest, and revocation reference.
- Install the locked graph twice and verify identical order, artifacts, and resulting state.

## Stop and escalate when

- A required dependency has no safe compatible version.
- The graph contains a cycle, conflicting permission, revoked node, or ambiguous ownership.

## Definition of done

- A reproducible signed lockfile exists, composition tests pass, and revocation propagation is proven.
