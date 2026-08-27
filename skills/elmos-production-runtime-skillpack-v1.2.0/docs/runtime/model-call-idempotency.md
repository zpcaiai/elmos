# Provider Call Idempotency

A duplicate Elmos request must not cause a second provider call.

## Model call receipt

Before provider invocation:
- create model_call row;
- create receipt keyed by Elmos idempotency key;
- persist provider request identity if the provider supports it.

On replay:
- if receipt COMPLETE, return stored result metadata;
- if PROVIDER_ACCEPTED/UNKNOWN, reconcile provider request status before a new call;
- only perform a fresh provider request when policy proves the previous call was not accepted.

Financial dedupe remains a second line of defense, not the only defense.
