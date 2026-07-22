---
name: b36-review-collaboration-approvals
description: "Implement review comments discussions assignments approvals decision records and evidence-aware collaboration across IDE CLI web and pull requests with separation of duties."
---

# Skill 1301: b36-review-collaboration-approvals

## Use this skill when

- Migration work needs coordinated technical, business, security, data, and customer review.
- Approvals and comments must remain consistent across IDE, CLI, web, and SCM.

## Domain-specific risks and invariants

- Duplicate comment systems, stale approvals, self-approval, hidden edits, and disconnected evidence can make governance unreliable.
- Sensitive review context can leak across tenants or external collaborators.

## Workflow

1. Define canonical review thread, comment, suggestion, decision, approval, delegation, expiry, and resolution contracts.
2. Link threads to exact commit, artifact, source/target symbol, diagnostic, difference, patch, ownership, and evidence.
3. Implement synchronization adapters for IDE, CLI, web, and supported SCM providers with idempotency and conflict handling.
4. Enforce role, scope, separation-of-duties, step-up, customer-external access, and stale-approval invalidation.
5. Add workflow analytics for time-to-review and blocked decisions without capturing unnecessary comment content.

## Required repository outputs

- `review/policy.json`, review/approval schemas, provider adapters, synchronization manifest
- Stale approval, self-approval, replay, edit, delete, external collaborator, and cross-tenant tests
- Representative multi-role review and customer-acceptance evidence

## Verification

- Change commit, artifact, action hash, scope, or evidence and verify prior approval becomes stale.
- Test concurrent comments, duplicate webhooks, deleted users, delegated approvals, and expired access.
- Verify reviewers cannot approve their own prohibited actions.
- Inspect data isolation and telemetry.

## Stop and escalate when

- A required approval cannot bind to an immutable action or artifact.
- Provider synchronization would lose decision history or create contradictory states.
- Separation of duties or customer data boundaries cannot be enforced.
- A reviewer lacks required role, certification, or access.

## Definition of done

- Review state is consistent across all supported surfaces.
- Approvals bind to exact immutable changes and expire correctly.
- Self-approval and cross-tenant leakage are zero.
- Decision records are evidence-linked and auditable.
