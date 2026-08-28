# ETGB Package Validation Summary

Generated: 2026-08-27

## Result

- Package schema/integrity: **PASS**
- Declared capability-cell coverage: **100%**
- Missing matrix cells: **0**
- Concrete test cases: **46,376**
- Offline smoke: **4/4 PASS**
- Unit tests: **7/7 PASS**
- Smoke weighted pass: **100.0%**
- Smoke SSER: **0.0%**
- Smoke evidence completeness: **100.0%**

## Cases

- Spring modernization: 3,117
- Cross-language: 29,535
- Project generation: 1,451
- SQL conversion: 11,761
- Cross-cutting: 512

## Deliberate release blocker

All 17 public repositories are metadata-only and pinned to commits, but `license_review` remains `required`. This is a governance control: `etgb validate --release` must fail until the user's legal/OSS review changes each approved item to `approved`.

## Scope note

The four offline smoke cases validate the supplied runner and oracles. External repository/database cases are executable specifications for Elmos production harness adapters and were not run in this network-disabled container.
