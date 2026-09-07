# Codex Implementation Prompt — Batch 1–38

Implement this repository modernization platform incrementally. Treat every `agent-skills/runtime/*/SKILL.md` as an executable engineering contract.

## Rules

1. Inspect the target repository before changing code.
2. Execute Batches in dependency order unless an existing valid Artifact and Certificate proves a predecessor complete.
3. Generate runnable code, schemas, tests, tools, manifests and runbooks; do not stop at prose.
4. Preserve all failures and unknowns. Never fabricate execution, Evidence or certification.
5. Use content-addressed Artifacts and connect Requirement → Model → Code → Execution → Evidence → Certificate.
6. Enforce Builder/Verifier/CA separation.
7. For production writes use Approval, Idempotency, Fencing, Side-Effect Ledger, Reconciliation and Rollback.
8. For formal claims lock the Theorem, use Leanstral only as a candidate generator, and accept only Lean Kernel results bound to actual Artifacts.
9. Every repair must fail on the old artifact, pass on the repaired artifact, kill the corresponding mutation and pass independent regression.
10. Stop on permission expansion, cross-tenant access, money/data/safety invariant failure, hidden critical scope or invalid certificate.
11. Use `scripts/migration_platform.py prepare` to materialize the selected Batch work unit, `record` and `verify` to bind independent Evidence, and `gate` for the local decision.
12. Never promote a local decision above `LOCAL_TOOLKIT_PASS`; this distribution has no independent trust root, so certificate request/import and `CERTIFIED` remain disabled.

## Completion output

For every Batch emit a machine-readable Completion Report with artifacts, evidence, findings, unknowns, limitations, certificate ceiling and downstream inputs.
