# ELMOS Batch 40–55 Implementation Rules

## Mandatory rules

1. Reuse existing ELMOS Tenant, Identity, Organization, Artifact, Policy, Audit, Workflow, Case, Contract, Finance, Customer, Data and Infrastructure aggregates.
2. Keep source facts immutable and interpretations, plans, models, policies, snapshots and provider mappings versioned.
3. Enforce tenant and resource isolation at API, database, cache, event, search, analytics, connector and export boundaries.
4. Preserve source identity, effective dates, provider versions, actor/workload, purpose, decisions and evidence.
5. Treat unknown, partial, timed-out or unreconciled states as non-success.
6. Use typed automation and provider adapters; prohibit arbitrary privileged scripts.
7. AI recommendations are candidates and cannot directly approve regulated, financial, employment, security, safety or contractual outcomes without explicit policy.
8. Sensitive data and secrets are redacted before persistence in logs, analytics or evidence.
9. Every material side effect is idempotent, auditable and reconcilable.
10. A Skill is incomplete until repository-native tests and the Skill's release gates have run and evidence is recorded.
