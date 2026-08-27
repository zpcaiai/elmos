# ELMOS Formal Assurance Engine

This repository-owned engine binds all 60 Skills from
`elmos-formal-assurance-kernel-v1.0.0` to explicit, deterministic handlers.
It provides local contract compilation, bounded analyses, content-addressed
evidence, tenant-scoped idempotent state, lease/fencing state transitions and
the conservative release gate.

The runtime binds every request to a trusted tenant/project scope, immutable
source/target/environment digests, an idempotency key, an append-only event
chain and (when configured) a tenant-isolated content-addressed artifact store.
Each source identity has an explicit allowlisted handler; unknown identities
cannot fall through to a generic dispatcher.

The engine never invokes a verifier, database, provider, cluster, signer or
customer route. Those are separate adapters and remain `NOT_RUN` until a
trusted external workflow supplies independently verified evidence. A local
bounded result is never promoted to an unbounded proof or certification.

Run the focused suite with:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

The local handlers provide deterministic engineering evidence only. Native
compiler/database/solver execution, external signing, independent replay,
customer golden routes, deployment evidence and certification remain explicit
`NOT_RUN` / `NOT_CERTIFIED` states until authorized evidence exists.
