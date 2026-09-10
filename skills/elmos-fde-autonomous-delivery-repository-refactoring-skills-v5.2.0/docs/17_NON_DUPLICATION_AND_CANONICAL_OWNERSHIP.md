# 17 — Non-duplication and Canonical Ownership

## Forbidden duplication

The package must not fork Goal, business intent, AI-SIR, Repository-SIR, DB-SIR, runtime authority, security context, capability lease, durable execution, Effect Ledger, Evidence Ledger or K8 completion state.

## Placement decision

1. Is it a repository-wide instruction? Put a concise rule in AGENTS.
2. Is it execution/state/authority/effect semantics? Extend the existing Harness/K7 owner.
3. Is it domain capability? Extend an existing Domain Pack or one non-routable component Skill.
4. Is it a provider/tool boundary? Add an Adapter and conformance tests.
5. Is it deterministic enforcement? Add policy/test/linter rather than prose.
6. Is it only a repeated technique? Add a reference/script/eval to the existing Skill.
7. Create a new Skill only when ownership and trigger boundaries are materially distinct.

Missing or ambiguous symbolic route binding is a release blocker, not permission to invent a new owner.
