# Status Rendering and Product UX

## Non-negotiable rendering

| Canonical status | UI label | Visual treatment |
|---|---|---|
| PROVED_CERTIFIED | Certified proof | strongest, certificate link |
| PROVED_INDUCTIVE | Inductive proof | strong, invariant/model link |
| PROVED_SOLVER_TRUSTED | Solver-proved | strong, TCB disclosure |
| PROVED_FOR_SUPPORTED_FRAGMENT | Proved in supported fragment | scoped, profile link |
| BOUNDED_NO_COUNTEREXAMPLE | No counterexample within bound | amber, bound always visible |
| REFUTED_WITH_COUNTEREXAMPLE | Counterexample found | red, replay action |
| UNKNOWN_* | Inconclusive | gray/red for gate, reason visible |
| UNSUPPORTED | Unsupported boundary | gray, feature inventory link |
| ASSUMPTION_REQUIRED | Assumption unresolved | amber, owner/action |
| RUNTIME_MONITORED | Runtime monitored | blue, monitor health |
| WAIVED_BY_APPROVER | Risk waiver active | amber, expiry/approvers |

## Prohibited UX

- a single green “verified” percentage mixing bounded and proved;
- hiding unknown results in a collapsed section;
- displaying a waiver as technical success;
- omitting model scope, loop bound, row bound or schedule bound;
- keeping green status after evidence becomes stale;
- calculating coverage without the entrypoint denominator.

## Required drill-down

Every result links to property, source location, semantic profile, assumptions, TCB, engine/mode/options/bound, raw artifacts, counterexample and gate impact.
