# Implementation Guide — Proof Assistant Lean/Dafny Bridge

## Purpose

Generate reviewable theorem/contract skeletons, connect verified lemmas to code artifacts and preserve trusted-kernel and assumption evidence.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. emit typed theorem and contract artifacts
2. separate generated conjecture from checked proof
3. bind source maps and extracted code
4. record axioms, admits and trusted base
5. recheck after code or toolchain drift

## Native acceptance corpus

- `ELMOS_PROOF_ASSISTANT_LEAN_DAFNY_BRIDGE-01` — native scenario: emit typed theorem and contract artifacts
- `ELMOS_PROOF_ASSISTANT_LEAN_DAFNY_BRIDGE-02` — native scenario: separate generated conjecture from checked proof
- `ELMOS_PROOF_ASSISTANT_LEAN_DAFNY_BRIDGE-03` — native scenario: bind source maps and extracted code
- `ELMOS_PROOF_ASSISTANT_LEAN_DAFNY_BRIDGE-04` — native scenario: record axioms, admits and trusted base
- `ELMOS_PROOF_ASSISTANT_LEAN_DAFNY_BRIDGE-05` — native scenario: recheck after code or toolchain drift

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
