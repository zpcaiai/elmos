---
name: unified-audit-event-model
description: Normalize security and business audit events from users, workloads, support, Runners, models, billing, deletion, approvals, and cutover. Use when defining critical audit coverage or event contracts.
---

# Unified Audit Event Model

Read `../references/batch-12-enterprise-platform.md`. Require global event ID, tenant, time, real actor, action, resource, policy decision, correlation/session/Runner context and outcome. Record both support actor and impersonated identity, while redacting sensitive values.

Audit is separate from ordinary logs. Missing critical audit must fail high-risk actions closed and blocks T-B/T-G.
