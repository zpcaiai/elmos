# E0-E5 evidence boundary

| Gate | Required evidence | This local target |
|---|---|---|
| E0 | exact identity, reproducible inputs, schema and policy conformance | may produce self-attested engineering evidence |
| E1 | executable unit/contract behavior for the exact handler and environment | only one of the 26 exact local handlers, after successful replay, may qualify locally |
| E2 | real integration and exact technology/version matrix | `NOT_RUN` unless separately executed |
| E3 | independent shadow environment, verifier and rollback rehearsal | `NOT_RUN` |
| E4 | bounded production canary, SLO, stop/rollback and customer acceptance | `NOT_RUN` |
| E5 | repeatable commercial Golden Route across disjoint real workloads | `NOT_RUN` |

No metric threshold, model judgment, locally generated hash, unsigned receipt,
or package fixture can substitute for a missing evidence role. The runtime can
prepare a request for an external gate; it cannot approve its own work.

The archive's stated E1/E2/E3 targets are obligations, not results. The 31,440
activation cases are text routing fixtures, not native compiler, database,
browser, device, cloud, model, customer or regulator execution.
