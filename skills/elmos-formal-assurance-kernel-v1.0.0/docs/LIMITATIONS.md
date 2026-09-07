# Honest Limitations

This package is a production-grade implementation contract plus executable reference kernel. It is not a claim that:

- all 60 Skills are already wired into the user's Elmos main repository;
- any third-party verifier is installed or licensed;
- PostgreSQL migrations were applied to a live PostgreSQL 17 service;
- Rego modules were compiled by OPA in this artifact build;
- container images were built, signed or deployed;
- Kubernetes network policy was enforced;
- the illustrative TLA+/Alloy/JML/Dafny/Lean/Boogie/K/Kani/Frama-C models were executed;
- complete formal semantics exist for every feature of every supported language;
- a whole repository is proved merely because selected obligations pass;
- a commercial E5 Golden Route has passed on customer repositories.

Dynamic reflection, FFI/native code, proprietary external systems, weakly specified requirements, concurrency memory-model gaps, floating-point behavior, database vendor deviations and solver/semantic-adapter soundness remain material risks.

The package addresses these risks through explicit semantic profiles, assumptions, TCB, unsupported states, bounded statuses, differential tests, runtime monitoring, drift invalidation and waivers. None of those controls may be rendered as a stronger proof than they are.
