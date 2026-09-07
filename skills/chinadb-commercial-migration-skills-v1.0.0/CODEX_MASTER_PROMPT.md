# Codex Master Execution Prompt

Use this package to IMPLEMENT the commercial database migration platform in the current repository.

## Non-negotiable operating rule

Do not claim a skill or batch is complete because its SKILL.md exists. A skill is complete only after real implementation files, tests and evidence are present in the product repository and pass the skill's DoD.

## Execution

1. Read `README.md`, `IMPLEMENTATION_RULES.md`, `ARCHITECTURE.md`, `API_CONTRACTS.md`, `REQUESTED_CAPABILITY_MAPPING.md`, and `CODEX_EXECUTION_BATCHES.md`.
2. Inspect the existing repository before creating architecture. Reuse existing modules/contracts when compatible; record gaps.
3. Start at the earliest incomplete batch. Do not skip dependency batches unless repository evidence proves they already exist.
4. For each skill in the batch:
   - read its `SKILL.md` and target/source `capability-baseline.yaml` when present;
   - create/update actual code modules listed by the skill, adapted to the repository language/layout;
   - implement tests including negative and fail-closed cases;
   - execute tests/compilers/integration environments;
   - write evidence conforming to `schemas/evidence.schema.json`;
   - update `IMPLEMENTATION_STATUS.json` only after evidence exists.
5. Never implement SQL/PL semantic conversion using regex-only rewriting. Parse -> resolve -> IR -> rules -> target render.
6. Never silently discard or approximate unsupported constructs. Use NATIVE / REWRITE / LIFT_TO_APP / EMULATE_WITH_APPROVAL / UNSUPPORTED.
7. For TiDB, stored procedure/function/trigger gaps must route through logic decomposition/lift-to-app when no verified native equivalent exists.
8. For GoldenDB, fail closed unless exact product/version capability discovery is available.
9. Vendor-native migration tools may be integrated through `64-vendor-native-tool-bridge`; their success is not production certification.
10. After any repair or tuning patch, rerun every affected E2/E3/E4 gate.
11. Do not produce a final “all features complete” statement unless the full E1–E5 certification test suite has run successfully for the claimed routes and the evidence IDs are listed.

## End-of-batch report

Return only evidence-backed status:

- implemented files;
- tests executed + pass/fail counts;
- evidence IDs/paths;
- remaining unsupported or manual cases;
- next batch;
- explicit statement of anything NOT actually implemented or NOT executed.
