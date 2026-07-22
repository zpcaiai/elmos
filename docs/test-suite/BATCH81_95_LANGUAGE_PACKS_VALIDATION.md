# Batch 81–95 Language Pack supplemental qualification

This suite is supplemental engineering qualification for the 180 package-local Language Pack Skills. It does not replace or update the 408-case Batch 1–37 strict certification suite, and it does not reinterpret package-local PG223–PG402 as globally numbered Project Synthesis Skills.

## Exact inventory

- Immutable source package: 104 manifest-owned files with matching SHA-256 checksums
- 40 test Skills: T081–T095 Batch owners and T096–T120 cross-platform gates
- 640 exact cases: CASE-0001 through CASE-0640
- 180 direct source-Skill cases and 47,700 total case-target links
- Severity counts: Critical 170, High 400, Medium 70
- 640 exact result records, initially and truthfully `NOT_RUN`

Every direct binding preserves the package-local PG ID, `LP-Bxx-PGxxx` compound source key, original name and digest, normalized `$b81-*`–`$b95-*` alias and digest, direct case, related case count, and owning test Skill. The 120-case generated design was replaced only after confirming all of its results remained `NOT_RUN`.

## Commands

```bash
make test-suite-81-95-check
make test-suite-81-95-gate
```

The check validates the immutable source package, Language Pack ZIP declaration, exact target manifest, installed Runtime/Codex test Skills and interfaces, package-local identity, controlled definitions, case/result order and completeness, severity distribution, direct and aggregate coverage, evidence roles, authorization, deterministic replay, executor/verifier separation, and zero-tolerance behavior. Twelve regression tests exercise missing and reordered results, fabricated passes, self-verification, claims attached to `NOT_RUN`, namespace/source-ID relabeling, removed coverage, stale install bindings, and zero-tolerance findings.

The supplied source evaluator is retained as package provenance but is not authoritative: it does not require all 640 results and cannot represent fail-closed `NOT_RUN`. Only the repository validator and conservative gate produce this supplemental decision.

The gate requires the source thresholds: 100% Critical pass rate, at least 98% High and 95% overall pass rate, 100% Batch execution and direct source-Skill coverage, 100% Critical/High and 98% overall evidence completeness, at most 1% flaky and 0.5% quarantined, no zero-tolerance finding, two deterministic positive executions, independent verification, authorization, and immutable raw evidence.

The maximum successful decision is `READY_FOR_EXTERNAL_GATE`; `certified`, `approves_vendor_or_physical_operation`, and `updates_batch1_37_certification` always remain false. Static validation, generated fixtures, mocks, or starter-project acceptance cannot satisfy mainframe, SAP, database, PLC, simulation, vendor, hardware, parallel-run, safety, cutover, or production evidence.

## Local result — 2026-07-22

- Immutable package validation passed: 104 files, 40 test Skills, 640 cases, and 180 direct source bindings.
- Repository validation passed all 640 cases/results, 47,700 target links, installed identities, and controlled digests.
- All 12 namespace, completeness, evidence, independence, and zero-tolerance regressions passed.
- The complete repository test-suite run passed 50 main tests plus 10 Batch 38–45 strict-toolkit tests.
- The conservative gate remained `BLOCKED` with all 640 cases `NOT_RUN`; this is the truthful result before authorized native execution and independent verification.
