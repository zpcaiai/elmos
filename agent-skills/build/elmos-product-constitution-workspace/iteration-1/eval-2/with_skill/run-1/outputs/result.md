# Decision: HUMAN_REQUIRED

- Classification is `RESTRICTED`; permitted route is the approved private provider only. The healthy public provider is not an eligible failover target.
- The private provider is unavailable and the organization has no budget reservation. Stop before credential issuance or network dispatch. Return `HUMAN_REQUIRED` (or policy-equivalent `BLOCKED`) with reasons `PRIVATE_PROVIDER_UNAVAILABLE` and `BUDGET_EXHAUSTED`.
- Secret Broker result is `NOT_ISSUED`; no provider credential may be materialized in the control plane, logs, evidence, or repository workspace.
- Usage records may contain a declined reservation/decision event, but invocation count, token consumption, and completed charge remain zero. Do not create a successful usage ledger entry.
- Evidence must include server-derived organization, actor/workload, correlation id, data classification, policy/version, candidate providers and eligibility reason, private-provider health, budget decision, final route `NONE`, secret decision, and terminal workflow reason.

No transformation, agent fix, validation, or delivery phase can be marked successful from this decision.
