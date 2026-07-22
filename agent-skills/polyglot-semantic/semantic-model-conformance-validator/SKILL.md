---
name: semantic-model-conformance-validator
description: Validate PSP schema, references, source integrity, semantic relationships, and per-module coverage gates before Batch 3. Use whenever semantic artifacts must be accepted, restricted, or blocked.
---

# Semantic Model Conformance Validator

Read `../references/psp-v1.md` before acting.

Validate protocol/schema and ID format; unique IDs; snapshot/run consistency; Symbol/Type/Scope/File/Call/SourceMap references; ranges/hashes/declaration bounds; callable/type/scope/override/call/partial relationships; and module-level coverage. Detect every dangling relation and preserve the responsible entity in violations.

Apply Gates A/B/C from the shared contract per module, with documented language/project threshold adjustments. Repository averages may not hide a failed module; generated code is excluded by default; dynamic modules may enter Batch 3 only with restrictions. Schema validity alone is insufficient. Emit `semantic-conformance-report.json` with status, module gates, eligibility, restrictions, coverage, blocking diagnostics, violations, and executable recommendations.
