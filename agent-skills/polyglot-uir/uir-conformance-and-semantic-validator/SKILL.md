---
name: uir-conformance-and-semantic-validator
description: Validate UIR dialect, references, types, flow, effects, maps, obligations, and per-module gates. Use before Batch 4 or automatic lowering.
---
# UIR Conformance and Semantic Validator
Read `../references/uir-v1.md`. Detect dangling IDs/values, operand/result violations, missing terminators, dominance/edge mismatches, invalid calls/generics/nullability, hidden dynamic/unknown, broken finally/await/yield/throw paths, pure/effect conflicts, map/transformation gaps and missing risk obligations. Apply UIR-A through D per module; averages never hide critical failure. Emit eligibility, restrictions, errors, open obligations, coverage and executable actions.
