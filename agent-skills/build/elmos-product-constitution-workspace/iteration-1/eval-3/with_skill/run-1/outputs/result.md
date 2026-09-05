# Decision: PARTIALLY_FULFILLED / NOT_READY / RED

- Deduplicate the second order event by its stable source-event/idempotency key. Return the original fulfillment decision; do not recreate subscriptions, consume allowance twice, or issue a second Runner lease.
- Order fulfillment remains `PARTIALLY_FULFILLED`: the delivered private Runner capacity is evidenced, while the pending contracted capacity stays open. Partial delivery is not entitlement completion.
- Onboarding remains `NOT_READY` because the Maven readiness gate is `BLOCKED`. A customer request cannot override a technical gate without a governed exception and new evidence.
- Project health is `RED`. The failed critical transaction gate dominates the numeric 85% progress measure; progress is context, not a release decision.
- CRM, payment collection, tax, invoicing, revenue recognition, and formal accounting are integration boundaries. With adapters absent, record `NOT_CONFIGURED` and create no external side effect. ELMOS may preserve an outbox intent only if policy-approved; it may not call that intent delivered.

Audit evidence links the source order event, deduplication decision, each fulfillment item, readiness gate, project snapshot, critical failure, adapter capability state, organization, actor/workload, policy version, and correlation id.
