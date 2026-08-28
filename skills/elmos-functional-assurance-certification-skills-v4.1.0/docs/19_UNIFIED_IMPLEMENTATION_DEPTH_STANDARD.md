# Unified Skill Implementation Depth Standard

## Mandatory depth for every component

A Skill is not implementation-ready merely because it has a prompt and a list of tests. Every v2 component includes and must implement:

1. a canonical domain model with identities, events and invariants;
2. API/command/event contracts with idempotency and fencing;
3. persistence, RLS, outbox and evidence storage requirements;
4. exact algorithms and bounded generative scope;
5. a durable state machine with pause/resume/cancel/recovery;
6. a target/domain-specific native test matrix;
7. a threat model with preventive, detective and response controls;
8. a version support and evidence invalidation policy;
9. observability, FinOps and machine wall-clock reporting;
10. independent evidence and E0–E5/P05 completion boundaries.

## Implementation evidence ladder

- **E0 Contracted:** schemas, dependencies and acceptance contracts validate.
- **E1 Materialized:** real code, migrations, policies, fixtures and target artifacts exist.
- **E2 Native Build:** exact target import/build/load/start executes.
- **E3 Behavioral Assurance:** positive, negative, recovery, security and differential suites execute.
- **E4 Operational Acceptance:** deployment, observability, rollback, deletion, isolation and customer acceptance execute.
- **E5 Commercial Certification:** repeated hidden holdouts, current evidence, side-effect settlement and independent certificate.

No stage may infer a higher stage from document or file count.
