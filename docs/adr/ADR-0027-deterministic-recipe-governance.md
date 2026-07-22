# ADR-0027: Deterministic recipe governance and license closure

- Status: Accepted
- Date: 2026-07-21

## Decision

ELMOS selects recipes from a versioned catalog, resolves the complete composed-recipe and artifact dependency closure, and evaluates a versioned license policy before an artifact may be downloaded or executed. Execution uses an immutable manifest with exact artifact versions, SHA-256 identities, runtime image digest, network policy, options and policy hash. Dynamic versions and unresolved license facts fail closed.

Commercial ELMOS contexts block Moderne Source Available and proprietary artifacts unless a time-bound, scoped commercial grant is recorded. Customer self-managed use requiring legal interpretation remains `CUSTOMER_REVIEW_REQUIRED`, not executable approval. This boundary follows the restrictions stated in the [OpenRewrite licensing documentation](https://docs.openrewrite.org/licensing/openrewrite-licensing).

Run success requires OpenRewrite Data Tables, manifest-bound evidence and a second run in a fresh process. Oscillation, scope violations, non-idempotence, missing SBOM/signature or missing human review prevent promotion.

## Consequences

The existing `rewrite-spring` dependency remains a pinned upstream capability, not copied source. Its current MSAL license means it is not silently available to ELMOS commercial execution. Live recipe execution remains unavailable until the complete runtime artifact closure and approved sandbox image are present.
