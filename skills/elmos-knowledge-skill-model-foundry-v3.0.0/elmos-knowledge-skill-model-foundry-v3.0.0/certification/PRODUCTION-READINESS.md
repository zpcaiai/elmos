# Elmos v3 Production Readiness and E0–E5 Gates

## E0 — Identity and reproducibility

- every repository, dataset, model, Adapter, Skill, tool, environment and evidence artifact has a version and content identity;
- tenant, rights, source, license, region and retention are explicit;
- clean-room execution can reconstruct inputs and toolchain.

## E1 — Unit and contract conformance

- Skill Schema, triggers, negative triggers, dependencies, permissions, rollback and evaluation fixtures pass;
- parser, generator, adapter and verifier unit suites pass;
- unsupported constructs are explicit, never silently approximated.

## E2 — Integration and matrix validation

- builds and tests pass across declared language/framework/database/OS versions;
- tool failure, cancellation, retry, executor replacement and workspace fencing pass;
- data, model, RAG, cache and tenant isolation tests pass.

## E3 — Independent shadow certification

- independent environment reproduces source and target behavior;
- characterization, differential, property, mutation, security and performance evidence pass;
- no production writes; customer data remains private; rollback rehearsal passes.

## E4 — Controlled production canary

- small, bounded production exposure with real SLO and customer acceptance;
- automated stop/rollback on behavior, security, data, cost or reliability regression;
- support, evidence room, billing, SLA and incident response are operational.

## E5 — Commercial Golden Route

- repeatable across multiple disjoint real repositories and target versions;
- large-repository, long-soak, chaos, DR, security red team, upgrade and recertification pass;
- documented supported matrix, pricing, LTS, ownership, residual risks and exit path.

## Hard production blockers

- unresolved cross-tenant access or training-rights ambiguity;
- critical security issue, evidence tampering or unsigned release dependency;
- failed build, deterministic test, behavior/data equivalence or rollback rehearsal;
- unsupported source/target version presented as supported;
- incomplete billing reconciliation, backup/restore, incident ownership or customer acceptance;
- model-only judgment used to override deterministic failure.

## Reality boundary

This package's validation proves internal package integrity. It does **not** prove live PostgreSQL/RLS, OPA, Kubernetes/cloud, native compilers/databases, model training/serving, customer repositories, regulatory accreditation or external certification until those systems are implemented and executed.
