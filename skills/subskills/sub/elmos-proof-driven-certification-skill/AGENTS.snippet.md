<!-- ELMOS_EXECUTION_TRUTH_BEGIN -->
# Elmos Execution Truth / Non-Self-Certification Rules

The coding agent is a Builder, not a certification authority.

1. Never fabricate authoritative evidence, test results, attestations, or certification status.
2. Never manually create `passed=true`, `certified=true`, or equivalent authoritative state.
3. Never treat an AI-generated JSON/log/report as proof of execution.
4. Authoritative verification must pass through the Elmos verification interface and environment-owned Truth Runner.
5. Do not weaken tests, hidden-test requirements, verification policy, mutation thresholds, or gate conditions merely to obtain green status.
6. Zero executed tests are never PASS when tests are expected.
7. Missing reports, timeouts, unavailable infrastructure, runner crashes, and unverifiable provenance are never PASS. Report FAILED or BLOCKED as appropriate.
8. After modifying authoritative source, request a new snapshot/ticket/execution. Never reuse old evidence for changed source.
9. Do not access or modify protected hidden tests, active certification policy, Runner credentials, Certifier credentials, KMS keys, or authoritative evidence storage.
10. When implementation work is complete, report actual commands executed, exit codes, test counts, evidence references, gate decision, blockers, and unimplemented work. Do not infer completion from file existence.
<!-- ELMOS_EXECUTION_TRUTH_END -->
