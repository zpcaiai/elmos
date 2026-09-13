# 10 — Product UI/UX and Workspaces

| ID | Surface | Purpose |
|---|---|---|
| fde-command-center | FDE Command Center | Engagement portfolio, milestones, risks, decisions, access, value and customer status. |
| engagement-workspace | Engagement Workspace | Discovery notes, workflow map, stakeholders, scope, SOW, acceptance and action tracking. |
| repository-xray | Repository X-Ray | Asset inventory, support depth, build status, topology, ownership, hotspots and unknown coverage. |
| system-graph-explorer | System Graph Explorer | Business-to-code, call/data/event/permission/deployment graphs with evidence and confidence. |
| finding-workbench | Finding Workbench | Normalized findings, deduplication, root cause, impact, suppression, waiver and remediation decisions. |
| architecture-studio | Architecture & Transformation Studio | Alternatives, ADRs, invariants, Transformation DAG, cost, wall-clock and change windows. |
| changeset-console | ChangeSet Console | Atomic patches, tool results, unexpected deltas, review, commit, rollback and provenance. |
| proof-center | Proof & Readiness Center | Claims, obligations, evidence, counterexamples, unknowns, freshness, E0-E3 gates and independent decisions. |
| runtime-lab | Native Runtime Lab | Reproducible builds, service virtualization, profiles, fault injection, replay and benchmark control. |
| release-operations | Release & Operations | Shadow/dual-run/canary preparation, SLOs, reconciliation, rollback rehearsal and incident workflow. |
| adoption-value | Adoption & Value | Training, usage funnels, user feedback, value realization, support and handoff readiness. |
| admin-trust | Admin & Trust Center | Tenants, roles, policies, connectors, data use, residency, retention, audit exports, quotas and billing. |

## Cross-surface UX requirements

- One stable ID links requirement, finding, unknown, invariant, plan step, ChangeSet, evidence, claim, risk, approval and deployment stage.
- Every page displays exact scope/revision, freshness, confidence, support depth and completion boundary.
- Unknown, unsupported, denied, stale, partial and failed states are first-class—not empty states.
- Risky actions show authority, side effects, checkpoint, rollback and approver before execution.
- Collaboration supports comments, decisions, mentions, ownership, due dates, export and immutable audit history.
- Accessibility, keyboard operation, responsive layouts, internationalization and large-graph performance are release requirements.
