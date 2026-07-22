> Provenance copy of the supplied v1.0.0 validation claim. Its regex-only Skill validation and synthetic positive gate test were superseded after import; see `IMPORT_AUDIT.md` and `VALIDATION.md`.

# Validation Report — Batch 1–37 Strict Test Suite Skills

## Scope

- 52 repository-scoped Codex test skills.
- 408 machine-readable seed cases.
- Batch 1–37 each has 8 mandatory scenarios: success, boundary, malformed/unsupported, dependency failure, security, replay/idempotency, version drift, and evidence tamper.
- 11 cross-cutting suites cover security, concurrency, performance, compatibility, DR, customer operability, privacy, evidence anti-forgery, observability, test integrity, and final certification.

## Strict profile

- P0 pass rate: 100%.
- P1 pass rate: 100%.
- Holdout and representative workloads: 100% where required.
- Evidence and source-target traceability: at least 98%.
- Affected-test recall: at least 97% when measured.
- Mutation score: at least 85% when required.
- P95 latency regression: at most 5%; P99: at most 10%.
- Critical security, tenant isolation, test-integrity, stale evidence, forged certification, and unreplayed critical failures: zero.

## Executed validations

- Skill structure: 52/52 passed.
- Catalog validation: 408/408 cases passed required-field and unique-ID checks.
- Coverage validation: Batch 1–37 complete, at least 8 seed cases per Batch.
- JSON Schema meta-validation: 9/9 passed.
- Test-case schema validation: 408/408 passed.
- Clean installation into an empty repository: passed.
- Toolkit unit tests: 6/6 passed.
  - Catalog accepted.
  - Coverage accepted.
  - Skill bundle accepted.
  - Not-run suite rejected.
  - Placeholder-digest / evidence-free fake pass rejected.
  - Complete immutable evidence path accepted.
- Cumulative repository strict-suite tests: 6/6 passed.
- Cumulative repository Skill count after installation: 252.

## Safety behavior

The shipped result files are intentionally `not-run`. The strict gate therefore fails safely until Codex or the product test infrastructure executes the cases and supplies real result files, raw evidence, evidence manifests, exact artifact/environment digests, holdout results, and representative-workload results.
