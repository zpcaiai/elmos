# Batch 1–37 strict test suite import audit

## Source

- Supplied directory: `/Users/stephen/Downloads/batch1-37-strict-test-suite-skills/`
- Source package identity: `batch1-37-strict-test-suite-skills` version `1.0.0`
- Source payload before generated gate output: 508 files including `FILE_MANIFEST.txt`
- Source `FILE_MANIFEST.txt` SHA-256: `e71ea7c88180c11acac6ee75c599552237502082e216cb5e97af31e4dec84b39`
- Source `manifest.json` SHA-256: `6e837145b784319fc1323e1fc6f0a6ea3c7d85b4e7aa3264ab0b6edcda35d3a3`
- Declared scope: 52 repository-scoped Skills and 408 seed cases
- Imported on: 2026-07-22

The package was imported by scoped directories. Its root `README.md`, `manifest.json`, installation script and Makefile were not allowed to overwrite the existing ELMOS root. Source copies are retained under `docs/test-suite/SOURCE_*` for provenance.

## Defects found and repaired

1. Thirty-seven Batch Skill frontmatter descriptions contained unquoted YAML colons. The package regex validator reported success, but the standard Codex YAML parser rejected them. All 52 Skills now pass the system Skill Creator validator.
2. None of the 52 Skills included `agents/openai.yaml`. Deterministic UI metadata and prompts were generated for every Skill.
3. The original six-test toolkit accepted 408 one-line synthetic logs, repeated dummy artifact/environment digests and no external trust anchor as complete certification evidence.
4. The original gate did not enforce its Draft 2020-12 schemas, did not bind the case catalog or schema bundle, did not validate ISO timestamps/freshness, did not enforce source-target trace coverage, and did not prevent executor self-verification.
5. Holdout and representative booleans could be set without separate corpus evidence. Evidence roles required by each case were not checked.
6. P1 waiver language conflicted with the declared 100% P1 pass threshold. Waivers remain auditable, but any non-passed P0/P1 result still blocks strict certification.
7. The source installation script would have overwritten the existing ELMOS root README and other root files. Integration is now explicit and repository-scoped.

## Installed and hardened scope

- 52 `$tst-*` Skills and 52 OpenAI Skill interface files
- 408 immutable seed cases and 408 fail-closed `not-run` result placeholders
- 9 Draft 2020-12 schemas and 9 schema-valid templates
- 11 test-suite scripts, including strict validators, deterministic integration manifest, signed gate and local qualification runner
- 13 toolkit regression tests covering valid structure, manifest reproducibility, fail-closed status, unsigned synthetic evidence, signed positive path, raw tamper, forged signature, self-verification, corpus independence and local/certification authority separation
- Exact control manifest binding catalog, coverage matrix, profile, suite and all nine schema digests

## Evidence boundary

The source package is a test specification and scaffold, not proof that 408 scenarios ran. ELMOS local builds may provide engineering evidence, but they do not prove customer UAT, production-equivalent performance, cloud/private runner, DR, security authorization, representative workloads, independent holdout or external certification. Those results remain `not-run`; the authoritative gate therefore returns `BLOCKED` with `field_evidence_status=NOT_RUN` until real authorized evidence exists.
