---
name: elmos-policy-invariant-engine
description: Normalize heterogeneous repository rules and enforce them as context, JIT guards, blockers, repair constraints, and certification evidence.
priority: P0
---

# K6 — Policy & Semantic Invariant Engine

## Skills

- rule-source-discovery
- rule-normalizer
- cross-harness-rule-import
- policy-namespace
- policy-versioning
- policy-authority
- policy-precedence
- policy-conflict-explainer
- always-apply-policy
- lazy-rulebook
- regex-trigger
- ast-trigger
- semantic-trigger
- runtime-trigger
- tool-scope-trigger
- path-scope-trigger
- symbol-scope-trigger
- jit-rule-injection
- stream-semantic-guard
- policy-interrupt
- policy-block
- policy-auto-repair
- invariant-evidence
- policy-audit

## Supported source families

Normalize, where available:

- Elmos native policies;
- AGENTS-style instructions;
- Cursor rules;
- Cline rules;
- Copilot/GitHub instructions;
- Windsurf-style rules;
- project architecture/security standards;
- migration-specific constraints.

## Enterprise upgrade

NEVER use silent name-only first-wins semantics for production.

Conflict resolution MUST consider:

namespace + version + authority + scope specificity + explicit override.

## Example invariants

- Java synchronized semantics cannot disappear in target concurrency model.
- Transaction boundaries cannot silently shrink.
- Prepared SQL cannot become concatenated SQL.
- Security middleware cannot be bypassed by route conversion.
- Session semantics must be explicitly mapped during Struts/Servlet modernization.
- Decimal/date/timezone semantics must be preserved across DB/runtime conversion.

## Acceptance

Every blocked mutation emits a machine-readable violation with rule id, scope, evidence, and remediation path.
