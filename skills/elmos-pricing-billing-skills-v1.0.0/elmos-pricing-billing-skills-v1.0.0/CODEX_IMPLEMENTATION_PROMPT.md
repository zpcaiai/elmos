# Codex Implementation Prompt — Elmos Pricing & Billing

Use this prompt from the root of the target Elmos repository after installing the package.

```text
Use $elmos-billing-orchestrator and implement the Elmos hybrid pricing and billing program from the installed `.elmos-billing-kit`.

Business model that must be preserved:
1. Base subscription for platform, seats, collaboration, concurrency and retention.
2. Prepaid execution credits / actual usage for variable task cost.
3. Capped-price or fixed-price projects when scope and acceptance are frozen.
4. Enterprise annual contracts with committed spend, postpaid credit, private deployment, SLA and BYOK.
5. Raw tokens and compute are internal cost units; customer-facing pricing uses money/credits, quotes, caps and actual settlement.

Execution rules:
- Read AGENTS.md and all applicable repository instructions before editing.
- Read `.elmos-billing-kit/SKILL_INDEX.md`, `BATCH_INDEX.md`, architecture, state machines, schemas, policies, and traceability CSV.
- Audit the current repository first. Classify every assigned requirement as IMPLEMENTED, PARTIAL, STUB, MISSING, or NOT VERIFIED.
- Preserve the existing stack and conventions. Do not rewrite the repository to match the reference architecture unless an approved ADR requires it.
- Work batch by batch in dependency order. Use worktrees only for non-conflicting boundaries.
- The financial core must use integer units, append-only balanced double-entry entries, idempotent commands, tenant isolation, audit, outbox/inbox, and deterministic recovery.
- A paid task must follow estimate → quote → accept → reserve/authorize → run → meter → capture/release → settle.
- Enforce the hard budget before every new billable side effect. UI checks do not count as enforcement.
- Report Elmos autonomous machine wall-clock ETA separately from human-effort comparison.
- BYOK excludes only the customer-owned model-provider cost; continue charging applicable platform resources.
- Fixed/capped projects require repository/requirements/scope hashes, acceptance criteria, revisions, exclusions and change orders.
- Never mutate finalized invoices or posted ledger entries; use credit notes, reversals and compensating transactions.
- Do not hard-code production prices from the example catalog. Keep them draft until approved.
- Do not claim completion from source inspection. Run tests and collect runtime/reconciliation evidence.

For each batch:
1. State the batch and requirements.
2. Show current evidence-based status.
3. Implement the smallest coherent vertical slice.
4. Add migrations, API/event contracts, tests, telemetry and rollback/compensation.
5. Run targeted tests, then repository-required checks.
6. Update `manifests/requirements.traceability.csv` in the installed kit or the repository's copied implementation state.
7. Write a completion report from the skill template with Requirement → source → symbol → test → runtime evidence → commit.

Stop affected financial writes and report a blocker if you find duplicate charging, unbalanced ledger entries, unauthorized negative balances, hard-cap breaches, cross-tenant exposure, missing idempotency, secret leakage, ambiguous production policy, or unrecoverable data loss.

Begin with B00. Continue through the highest safe batch achievable in this session. Never ask for confirmation when repository inspection can resolve the question; make a safe, documented assumption when necessary. Do not say “fully implemented” unless all P0 requirements have executable evidence and the E1–E5 gates pass.
```
