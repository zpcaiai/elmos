# Claude Code Implementation Prompt — Elmos Pricing & Billing

Use this prompt from the root of the target Elmos repository after installing the package.

```text
Invoke /elmos-billing-orchestrator and implement or independently verify the Elmos hybrid pricing and billing system described in `.elmos-billing-kit`.

Required commercial model:
- subscription + prepaid execution credits/usage;
- capped or fixed-price projects for frozen scope;
- enterprise annual contracts, committed spend, postpaid, private deployment, SLA and BYOK;
- internal Token/compute costing separated from customer-facing money/credits and caps.

First inspect CLAUDE.md, AGENTS.md, build/test commands, current schemas, services and billing code. Then read the package index, architecture, state machines, policies, schemas, batches, requirements and scenario matrix.

Do not trust prior completion claims. Rebuild the evidence map and classify each requirement as IMPLEMENTED, PARTIAL, STUB, MISSING or NOT VERIFIED. A requirement is IMPLEMENTED only when exact source symbols, automated tests, runtime/reconciliation evidence and a commit/worktree reference exist.

Implementation invariants:
- integer minor money and integer micro-credits; never floating balances;
- append-only balanced double-entry ledger; balances are rebuildable projections;
- tenant isolation and idempotency on every write;
- event-time rate versions, immutable usage and correction events;
- estimate → quote → accept → reserve → run → meter → capture/release → settle;
- hard budget pause before overspend;
- machine wall-clock ETA distinct from human effort;
- fixed/capped scope protected by hashes and change orders;
- verified webhook/query/settlement facts, not browser redirects;
- finalized invoices and posted transactions are immutable;
- BYOK secret references only, and platform resources remain billable;
- failure/refund decisions are policy-driven and evidenced.

Proceed in B00–B53 dependency order. For each batch, implement a reviewable vertical slice, add migrations/contracts/tests/telemetry/rollback, execute the relevant test matrix, and write the completion report. When reviewing Codex changes, independently inspect the diff and rerun the commands; do not reuse its PASS conclusion without evidence.

Block release on any duplicate charge, ledger imbalance, unauthorized negative balance, hard-cap breach, cross-tenant access, secret leak, migration loss, or unreconciled P0 difference. Do not modify production pricing examples into active prices without documented approval.
```
