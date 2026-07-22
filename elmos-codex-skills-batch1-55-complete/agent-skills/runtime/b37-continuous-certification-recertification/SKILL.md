---
name: b37-continuous-certification-recertification
description: "Implement event-driven and periodic extension recertification for product SDK dependency permission vulnerability policy and runtime changes."
---

# Skill B37-X06: b37-continuous-certification-recertification

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Certification never silently rolls forward to a new artifact digest.
- Critical CVE, permission increase, or publisher compromise bypasses ordinary grace periods.
- Commercial importance cannot extend an expired security certification.

## Workflow

1. Define recertification triggers for product, protocol, SDK, ABI, dependency, permission, CVE, policy, publisher, runtime, and region changes.
2. Schedule periodic recertification based on risk tier and certification expiry.
3. Re-run required build, sandbox, negative, holdout, performance, compatibility, privacy, and domain tests on exact release digests.
4. Automatically downgrade, quarantine, suspend, or revoke stale and failed certifications according to policy.
5. Preserve historical certifications and notify publishers and affected tenants.

## Required repository outputs

- `certification/recertification-policy.json`
- recertification runs, trigger records, expiry actions, notifications, and evidence

## Verification

- Run `validate_continuous_certification.py`.
- Trigger product upgrade, CVE, permission change, and expiry scenarios and prove correct status transitions.

## Stop and escalate when

- Required holdout or runtime environment is unavailable.
- A critical release is overdue, stale, or running with failed certification.

## Definition of done

- Every active release has current exact-scope certification and all trigger paths are enforced.
