---
name: b37-policy-extension-sdk
description: "Implement a Policy Extension SDK for typed decisions inputs obligations explanations tests composition precedence simulation and fail-closed execution."
---

# Skill 1315: b37-policy-extension-sdk

## Use this skill when

- Customers need custom data, security, approval, cost, or execution policy.
- Policy logic is embedded in application code.

## Domain-specific risks and invariants

- A policy extension can silently permit data egress privilege escalation or self approval.
- Conflicting policies can produce nondeterministic results.

## Workflow

1. Define typed policy input/output, decision, obligations, deny reasons, explanation, owner, scope, version, priority, and conflict rules.
2. Generate SDK and reference policies.
3. Implement simulation, dry run, composition, precedence, and fail-closed behavior.
4. Add allow, deny, conflict, missing-input, and adversarial fixtures.
5. Require separation of duties for publication and activation.

## Required repository outputs

- policy SDK and schema
- policy simulator and conformance fixtures
- decision explanation and audit evidence

## Verification

- Verify unknown input fails closed.
- Verify extension cannot modify its own enforcement policy.
- Run conflict and self-approval negative tests.

## Stop and escalate when

- A policy has no accountable owner or deterministic precedence.
- A deny decision can be overridden without approved break-glass flow.

## Definition of done

- Third-party policies are deterministic, explainable, and fail closed.
- Policy activation and rollback are audited.
