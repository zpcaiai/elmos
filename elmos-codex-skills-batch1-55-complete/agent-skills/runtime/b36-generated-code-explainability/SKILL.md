---
name: b36-generated-code-explainability
description: "Implement generated-code explanations linking target constructs to source semantics rules recipes compatibility runtime model calls approvals and validation evidence."
---

# Skill 1295: b36-generated-code-explainability

## Use this skill when

- Developers need to understand why target code was generated and what is safe to change.
- Reviewers need evidence beyond generic natural-language summaries.

## Domain-specific risks and invariants

- Explanations can hallucinate, omit uncertainty, expose sensitive source, or disagree with actual generation provenance.
- LLM-generated prose must never replace deterministic rule and artifact evidence.

## Workflow

1. Define an explanation schema containing source refs, target refs, rule IDs, recipe versions, semantic decisions, compatibility components, model-call refs, approvals, tests, and confidence.
2. Generate deterministic explanations from provenance first; optionally add model-assisted summaries under policy.
3. Expose symbol, file, patch, diagnostic, and PR-level views.
4. Implement redaction, customer-private evidence boundaries, stale explanation detection, and deep links.
5. Add factuality tests that compare displayed claims with immutable provenance.

## Required repository outputs

- `explainability/profile.json`, explanation schema/renderers, evidence link resolver
- Factuality, completeness, redaction, freshness, and representative-review evidence
- Machine-readable explanation export for audit and support

## Verification

- Verify every factual claim resolves to provenance.
- Test missing, stale, contradictory, redacted, compatibility-runtime, and agent-assisted cases.
- Ensure advisory summaries are labeled and cannot change certification or policy decisions.
- Measure explanation task success with representative developers.

## Stop and escalate when

- An explanation cannot resolve to immutable evidence.
- A model summary conflicts with deterministic provenance.
- Required source disclosure violates policy.
- The UI would present unknown or approximate reasoning as certain.

## Definition of done

- P0 generated constructs have complete evidence-backed explanations.
- Unknowns, compatibility layers, and approvals are explicit.
- No sensitive source or secret is leaked.
- Representative reviewers can make correct decisions from the explanation.
