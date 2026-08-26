# Implementation Checklist

## Package and repository intake

- [ ] Run `./validate.sh` on this package.
- [ ] Install for the required host(s) with conflict-safe installer.
- [ ] Read repository `AGENTS.md`, `CLAUDE.md`, build, test, migration and deployment instructions.
- [ ] Record target repository URL/path, baseline commit and branch.
- [ ] Inventory existing tenant, task, model gateway, payment, database and observability modules.
- [ ] Populate the requirements traceability CSV with evidence-based five-state status.

## B00–B08: commercial foundation and entitlements

- [ ] Approve hybrid business-model ADR.
- [ ] Implement versioned price books and vendor rate books.
- [ ] Keep all example prices in draft state.
- [ ] Implement plan catalog, seats, included credits, concurrency and retention.
- [ ] Implement entitlement snapshots and tenant/contract overrides.

## B09–B16: ledger, wallet and metering

- [ ] Create integer amount types and overflow guards.
- [ ] Create ledger accounts, transactions and entries.
- [ ] Enforce balanced post and posted-entry immutability.
- [ ] Implement reserve/capture/release/credit/refund/expiry templates.
- [ ] Implement paid/promo provenance and rebuildable projections.
- [ ] Implement immutable usage events, dedupe, unit normalization and event-time rating.
- [ ] Reconcile task runtime and provider usage.

## B17–B22: estimation, quote and budget

- [ ] Extract repository/task features and historical comparable samples.
- [ ] Produce P50/P80/P90 cost and machine runtime.
- [ ] Keep human-effort reference separate.
- [ ] Produce versioned quote card with expiry, scope hash and cap.
- [ ] Reserve before task start.
- [ ] Enforce 50/80/95% alerts and pre-side-effect hard pause.
- [ ] Support top-up, downgrade, scope reduction, blockers-only and stop/export.

## B23–B25: capped/fixed projects

- [ ] Implement discovery, capped and fixed contract types.
- [ ] Freeze repository, requirement, scope, acceptance and exclusions.
- [ ] Add milestones, revisions and change orders.
- [ ] Ensure capped settlement cannot exceed cap.
- [ ] Define failed-acceptance remediation/refund/termination paths.

## B26–B34: subscription, payment and refund

- [ ] Implement lifecycle, billing anchors, proration and included-credit grant idempotency.
- [ ] Implement immutable invoices and credit-note corrections.
- [ ] Implement provider-neutral payment intents and verified webhooks.
- [ ] Implement provider/invoice/ledger/settlement reconciliation and suspense.
- [ ] Implement policy-driven full/partial refunds and chargebacks.
- [ ] Enforce maker/checker for high-risk adjustments.

## B35–B40: enterprise and economics

- [ ] Implement enterprise contract precedence and temporal versions.
- [ ] Implement committed-spend burn-down, true-up, postpaid and credit limits.
- [ ] Implement BYOK secret references and split billing.
- [ ] Implement cost centers, department budgets, PO and SLA credits.
- [ ] Build transaction-grounded cost/revenue/margin facts.
- [ ] Label analytics with as-of, close status and coverage.

## B41–B46: UX, security and operations

- [ ] Implement quote, wallet, usage, invoice, project and team budget journeys.
- [ ] Implement audited admin work queues and previews.
- [ ] Enforce tenant isolation across DB/cache/queue/object/analytics.
- [ ] Add RBAC/ABAC, separation of duties, secret management and audit.
- [ ] Add fraud, privacy, retention and export/delete workflows.
- [ ] Add traces, SLO, alerts, kill switches, replay, projection rebuild and DR.

## B47–B53: certification and rollout

- [ ] Run unit, property, contract, integration, concurrency, chaos and security tests.
- [ ] Run payment sandbox and settlement-file tests.
- [ ] Run old/new shadow rating and explain all differences.
- [ ] Complete E1–E5 certification.
- [ ] Import opening balances through balanced transactions.
- [ ] Run dual-write with a single charging authority.
- [ ] Canary by tenant risk and verify automatic rollback.
- [ ] Provide support, finance, incident and customer-communication runbooks.
- [ ] Keep legacy read-only until stability and audit conditions are satisfied.

## Final evidence gate

- [ ] All P0 requirements have source, symbol, test, runtime/reconciliation and commit evidence.
- [ ] No duplicate charge, ledger imbalance, unauthorized negative balance or hard-cap breach.
- [ ] No cross-tenant exposure or secret leakage.
- [ ] Migration and rollback/recovery are exercised.
- [ ] `VALIDATION_REPORT.md` and batch completion reports distinguish package validity from product completion.
