---
name: approval-separation-of-duties-and-break-glass
description: Enforce high-risk approvals, separation of duties, four-eyes review, and time-bounded Break-glass. Use for production cutover, security waiver, key export, tenant deletion, audit export, Runner registration, or budget changes.
---

# Approval Separation of Duties and Break-glass

Read `../references/batch-12-enterprise-platform.md`. Bind approvals to actor, exact resource/version, required independent approvers and expiry. Require strong authentication, reason, scope, alerting, command/session audit, automatic revocation and review for Break-glass.

Self-approval, artifact drift, combined-role bypass or unbounded/erasable emergency access blocks T-B.
