# ELMOS Semantic Assurance Engine

This repository-owned runtime binds the 132 exact Skills in
`ELMOS-POLY-169` through `ELMOS-POLY-300` to a validated compiled contract.
The source ZIP is treated as inert, untrusted declarative material and is never
imported or executed by the runtime.

The engine provides bounded local normalization, comparison, graph, coverage,
corpus, evidence, cache and replay operations. Native runtime, formal proof and
fuzz execution cross an explicit host-provided adapter boundary with an action
allowlist and digest-bound receipts. Unknown Skills, tuples, operations,
effects, evidence and adapter actions fail closed.

Local results are `LOCAL_EXECUTED_SELF_ATTESTED` engineering evidence only.
They do not establish external execution, independent verification, route
equivalence or certification. Those states remain `NOT_RUN` and
`NOT_CERTIFIED` until the separate authorized gates produce valid evidence.

Run the repository integration target from the repository root:

```console
make semantic-assurance-expansion-skills
```
