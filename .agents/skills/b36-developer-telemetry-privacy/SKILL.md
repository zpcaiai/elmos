---
name: b36-developer-telemetry-privacy
description: Implement privacy-preserving developer-experience telemetry with allowlisted events minimization consent retention aggregation deletion and usefulness metrics without source-code or employee surveillance.
---

# Skill 1303: b36-developer-telemetry-privacy

## Use this skill when

- Product teams need evidence about workflow success, latency, friction, and adoption.
- Enterprise customers need control over what IDE, CLI, and bot telemetry leaves their environment.

## Domain-specific risks and invariants

- Telemetry can leak source, paths, identifiers, prompts, diagnostics, secrets, customer data, or individual performance details.
- High event volume without task-level meaning can drive harmful product decisions.

## Workflow

1. Define allowed business questions and a versioned telemetry policy before instrumenting events.
2. Create an allowlisted event schema with purpose, fields, classification, sampling, aggregation, retention, region, consent, and deletion behavior.
3. Instrument task success, latency, failure class, cancellation, local/remote parity, and workflow funnel without raw source or comment content.
4. Implement local filtering, DLP, tenant controls, opt-out where applicable, data residency, aggregation, and deletion.
5. Add schema linting, forbidden-field detection, synthetic leak tests, privacy review, and metric definition tests.

## Required repository outputs

- `telemetry/policy.json`, event schemas, local filter/DLP implementation, metric definitions
- Privacy threat model, data-flow diagram, retention/deletion evidence
- Representative dashboard using aggregated workflow outcomes

## Verification

- Inspect emitted payloads under success, error, crash, debug, offline, and support modes.
- Seed secrets, source snippets, paths, prompts, and personal data and verify blocking or tokenization.
- Verify opt-out, tenant policy, region, retention, and deletion.
- Confirm metrics measure successful workflows rather than raw clicks or individual productivity.

## Stop and escalate when

- A field has no approved purpose or classification.
- Raw source, secret, prompt, review comment, or sensitive employee data would be emitted.
- Tenant controls, residency, retention, or deletion cannot be enforced.
- Telemetry is proposed as an individual performance-monitoring mechanism.

## Definition of done

- Telemetry answers approved product questions with minimal data.
- Forbidden leakage and cross-tenant mixing are zero.
- Retention, deletion, consent, and residency work.
- Metrics reflect workflow outcomes and preserve employee trust.
