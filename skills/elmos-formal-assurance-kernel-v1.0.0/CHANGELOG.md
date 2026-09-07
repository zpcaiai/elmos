# Changelog

## 1.0.0 — 2026-08-27

### Added

- 60 Formal Assurance Skills across six domains.
- 17 JSON Schemas and 16 valid contract examples.
- 17 fail-closed verifier adapter contracts.
- 10 durable workflows and 7 install profiles.
- 4 PostgreSQL 17 migrations with RLS, immutable evidence, fencing and anti-status-inflation guards.
- 6 Rego policy modules plus tests.
- 4 OpenAPI contracts and 1 AsyncAPI contract.
- Executable Python reference kernel with gate, cache, planner, evidence, counterexample and orchestration logic.
- Formal model examples for TLA+, Alloy, JML, Dafny, Lean, Boogie, K, Kani and Frama-C.
- 5 E1–E5 commercial Golden Routes.
- No-overwrite installer and hash-aware uninstaller.
- Validation, catalog, checksum and release packaging scripts.

### Security

- External verifier default network policy is deny.
- No secrets are passed to solver sandboxes.
- Proof status and evidence immutability are fail closed.
- Cross-tenant cache is denied by default.

### Known release-time work

- Pin exact verifier/application image digests.
- Execute target-environment PostgreSQL, OPA, container, Kubernetes and external verifier checks.
- Complete P05 and E1–E5 evidence.
