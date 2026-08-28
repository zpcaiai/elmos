# Billing Scenario Matrix

| ID | Priority | Scenario | Setup | Expected result |
|---|---:|---|---|---|
| S001 | P0 | Prepaid quote acceptance | Valid quote and sufficient paid credits | Reserve succeeds once; task becomes authorized |
| S002 | P0 | Duplicate quote acceptance | Same idempotency key retried | Original authorization returned; no second reserve |
| S003 | P0 | Concurrent reserve race | Two tasks compete for last balance | At most one succeeds; balance never unauthorized-negative |
| S004 | P0 | Hard-cap preflight | Next model call would exceed cap | No call occurs; task pauses before spend |
| S005 | P0 | Top-up retry | Top-up request times out and retries | Authorization increases once |
| S006 | P0 | Partial capture | Task completes below cap | Actual captured; unused reserve released |
| S007 | P0 | Task cancellation | User stops after useful partial output | Completed value rated; remainder released |
| S008 | P0 | Platform failure no value | Sandbox crash before usable output | No charge or captured amount refunded |
| S009 | P0 | Normal auto-repair | Tests fail and agent retries within cap | Retries stay within authorized task budget |
| S010 | P0 | Usage duplicate | Same source event delivered twice | One rated event and one business effect |
| S011 | P0 | Usage correction | Provider sends correction | Original retained; correction reverses/supplements |
| S012 | P0 | Late usage after close | Event arrives after invoice finalization | Adjustment candidate; invoice not mutated |
| S013 | P0 | BYOK model use | Customer-owned model key | Model provider cost excluded; platform resources charged |
| S014 | P0 | BYOK secret logging | Error path contains provider config | Secret never appears in logs/events/prompts |
| S015 | P0 | Ledger imbalance | Posting transaction has unequal sides | Database/application refuses post |
| S016 | P0 | Posted ledger mutation | Operator attempts update/delete | Operation rejected |
| S017 | P0 | Projection rebuild | Balance projection deleted | Rebuilt value equals ledger |
| S018 | P0 | Payment redirect spoof | Client claims success without webhook | No cash or wallet effect |
| S019 | P0 | Webhook replay | Valid event replayed | One payment business effect |
| S020 | P0 | Webhook out of order | Settlement before capture event | Monotonic state reconciles correctly |
| S021 | P0 | Payment settlement mismatch | Provider net differs from ledger | Suspense exception created |
| S022 | P0 | Refund ceiling | Multiple partial refunds exceed original | Excess refund rejected |
| S023 | P0 | Refund provider failure | Ledger reversal succeeds, provider fails | Saga compensates/holds in review |
| S024 | P0 | Admin self-approval | Creator approves own large adjustment | Denied by separation of duties |
| S025 | P0 | Cross-tenant wallet read | Tenant A requests tenant B wallet | Denied and audited |
| S026 | P0 | Cross-tenant analytics | Missing tenant filter in report | Trusted layer blocks or test fails |
| S027 | P0 | Quote expiry | User accepts expired quote | Rejected and re-estimation required |
| S028 | P0 | Scope changed after quote | Repository/requirements hash differs | Old quote invalidated |
| S029 | P0 | Machine ETA separation | Quote includes human comparison | Machine ETA remains independent field |
| S030 | P0 | Project cap | Actual rated work exceeds cap | Customer charge stops at cap absent change order |
| S031 | P0 | Scope drift | New feature requested during fixed project | Change order generated; original scope protected |
| S032 | P0 | Milestone rejection | Acceptance test fails | Milestone not settled; remediation path starts |
| S033 | P0 | Subscription renewal retry | Job reruns after timeout | One charge and one included-credit grant |
| S034 | P0 | Plan downgrade | Downgrade scheduled mid-period | Current rights preserved per policy; no duplicate grant |
| S035 | P0 | Finalized invoice edit | Operator edits line | Rejected; credit note/replacement required |
| S036 | P0 | Enterprise credit limit | Concurrent postpaid jobs reach limit | Atomic stop/approval according to contract |
| S037 | P1 | Committed spend true-up | Annual usage below commitment | True-up computed from immutable contract version |
| S038 | P1 | SLA service credit | Verified SLO incident | Rule-based credit with evidence |
| S039 | P0 | Price book history | New rates activated | Historical tasks/invoices retain old version |
| S040 | P0 | Vendor rate timing | Rate changes mid-day | Usage rated by event-time version |
| S041 | P1 | Promotional expiry | Promo expires while paid remains | Only eligible promo reversed/expired |
| S042 | P1 | Mixed paid/promo deduction | Task consumes both | Configured priority and audit breakdown preserved |
| S043 | P0 | Task server restart | Process crashes after usage before capture | Resume/replay without duplicate charge |
| S044 | P0 | Queue redelivery | Outbox event delivered repeatedly | Inbox idempotency preserves one effect |
| S045 | P0 | Opening balance migration | Migration rerun | Same source records create one balanced opening set |
| S046 | P0 | Dual-write authority | Legacy and new system both active | Only designated system charges |
| S047 | P0 | Canary rollback | Duplicate charge guard triggers | New authorizations stop; facts preserved |
| S048 | P1 | Analytics as-of | Current period contains late data | Total labeled posted/estimated with as-of |
| S049 | P1 | Cost allocation conservation | Shared cost allocated | Allocated sum equals source total |
| S050 | P0 | Break-glass access | Support accesses tenant data | Reason, expiry, scope, approval and audit required |
