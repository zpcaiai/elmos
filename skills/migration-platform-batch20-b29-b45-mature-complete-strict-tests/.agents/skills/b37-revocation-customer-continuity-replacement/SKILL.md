---
name: b37-revocation-customer-continuity-replacement
description: Implement emergency revocation customer continuity restricted mode replacement migration export notification and business recovery workflows.
---

# Skill B37-X08: b37-revocation-customer-continuity-replacement

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Security containment takes precedence over convenience and revenue.
- Restricted mode cannot retain the compromised capability.
- A revoked dependency propagates to composed installations and lockfiles.

## Workflow

1. Determine revocation severity, affected releases, tenants, data, jobs, dependencies, and active business processes.
2. Stop new installation and execution, then select immediate kill, restricted mode, grace period, or tenant-specific containment.
3. Provide signed replacement candidates, configuration migration, data export, rollback, and compatibility guidance.
4. Notify customer security, operations, business owners, publisher, support, and regulators where required.
5. Run continuity drills proving critical workloads recover without revoked execution or data loss.

## Required repository outputs

- `continuity/revocation-plan.json`
- affected-tenant inventory, replacement plan, export artifacts, notification evidence, and recovery test results

## Verification

- Run `validate_continuity_plan.py`.
- Simulate malicious update, signing-key compromise, critical CVE, and publisher disappearance.

## Stop and escalate when

- No safe replacement, export, or business-continuity path exists for a critical tenant.
- Revocation scope cannot be determined from immutable digests.

## Definition of done

- Revocation is enforced while customers retain a tested path to safe continuity, replacement, or exit.
