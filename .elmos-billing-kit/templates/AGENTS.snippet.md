## Elmos billing implementation rules

Use skills under `.agents/skills/` and shared contracts in `.elmos-billing-kit/`. For any billing change, preserve integer amounts, append-only balanced ledger, idempotency, tenant isolation, immutable price/rate versions, pre-side-effect budget enforcement, and Requirement→source→symbol→test→runtime evidence→commit. Never mark billing complete without E1–E5 evidence.
