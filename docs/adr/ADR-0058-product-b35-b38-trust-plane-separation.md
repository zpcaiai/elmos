# ADR-0058: Separate Product B35-B38 trust planes and external decisions

## Status

Accepted

## Context

The commercial roadmap reuses numbers 35 through 38 that already identify
Migration Pack M35-M38. It also spans SCM providers, private runners, sandbox
enforcement, third-party evidence, independent assurance, policy decisions and
runtime enforcement. Combining those responsibilities would let the producer
of a change judge or authorize its own result.

## Decision

Use `Product Batch B35-B38` for the commercialization roadmap and `Migration
Pack M35-M45` for `.agents/skills/b35-*` through `.agents/skills/b45-*`.

Implement four independent Product modules:

1. source-control and workspace governance;
2. secure runner, sandbox and site execution admission;
3. artifact, external-evidence and assurance judgement;
4. policy information/decision and continuous-authorization admission.

Provider calls, runner work, evidence production, independent verification,
policy decisions and policy enforcement remain distinct. Local APIs can only
produce readiness for an external gate or human decision. They cannot emit a
certification, approval, merge, deployment, runtime side effect or enforcement
receipt.

All persistence projections are organization scoped, force RLS, append-only,
evidence-bound and constrain `external_operation_executed` to `false`.

## Consequences

- A digest proves identity and integrity, not trust or authorization.
- Unknown capability, missing evidence and unsupported policy obligations fail
  closed.
- Native third-party evidence remains available beside normalized projections.
- Policy producers cannot act as their own independent evidence verifier.
- Customer/provider/runner/production evidence remains `NOT_RUN` until an
  authorized external workflow supplies immutable receipts.
