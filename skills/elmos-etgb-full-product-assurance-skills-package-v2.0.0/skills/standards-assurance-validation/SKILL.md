---
name: standards-assurance-validation
description: Map and execute objective security, AI, supply-chain, accessibility, payment, mobile and observability controls without making false accreditation claims.
---

# Standards Assurance Validation

## Purpose

Turn the 100 controls in 11 declared assurance profiles into automated-negative, configuration-evidence and runtime-observation cases. This Skill produces engineering evidence; it never claims legal compliance, audit opinion or accredited certification.

## Inputs

- `matrices/standards-controls.yaml` and `suites/standards-assurance.jsonl`.
- Exact application, AI runtime, build provenance, browser/mobile and payment test environments.
- Control-specific evidence retention and redaction policy.

## Workflow

1. Resolve each control to testable system behavior and an evidence source.
2. Run negative abuse cases, inspect configuration/build attestations and observe runtime enforcement.
3. Link findings to product feature IDs and concrete regression cases.
4. Mark non-applicable controls with signed rationale; never silently omit them.
5. Seal evidence with source/version/date and independent reviewer status.

## Profiles

The package maps OWASP ASVS, OWASP GenAI LLM and Agentic risks, OWASP AISVS, NIST SSDF and its AI profile, SLSA, WCAG, PCI DSS, OWASP MASVS and OpenTelemetry semantic conventions. The exact profile inventory and source references are versioned in the matrix.

## Gates

- Every declared control has three evidence surfaces or an approved non-applicability decision.
- Critical failed control blocks release.
- Evidence must be current for the exact release candidate and environment.
- Reports must use “engineering assurance” language, not unsupported certification language.

## Production Adapter

Use `external-standards-assurance-harness` with independent read-only evidence access wherever feasible.
