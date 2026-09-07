---
name: semantic-diagnostics-and-risk-classifier
description: Normalize parser, binding, type, dependency, dynamic-feature, framework, and analyzer failures into evidence-backed Batch 2 diagnostics and coverage metrics. Use for semantic risk triage and gate decisions.
---

# Semantic Diagnostics and Risk Classifier

Read `../references/psp-v1.md` before acting.

Classify syntax recovery, binding failure, unresolved symbol/type/call, missing dependency/stub/classpath, dynamic call, reflection, runtime code generation, framework-managed behavior, generated semantics, unsupported construct, source-map gap, and internal adapter error. Preserve native code/message, file/range, provider, impact, recommended action, confidence, and blocking status; sanitize source/secrets from messages.

Compute parsed-file, symbol/type resolution, exact/candidate/dynamic/unresolved call, and source-map rates with documented denominators. A successful build does not erase semantic gaps. Missing authority, provenance, snapshot identity, or referential integrity is blocking. Dynamic features are not automatically errors, but must restrict automation and recommend runtime evidence where needed.
