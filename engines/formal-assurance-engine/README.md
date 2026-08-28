# ELMOS Formal Assurance Engine

This repository-owned engine binds all 60 Skills from
`elmos-formal-assurance-kernel-v1.0.0` to explicit, deterministic handlers.
It provides local contract compilation, bounded analyses, content-addressed
evidence, tenant-scoped idempotent state, lease/fencing state transitions and
the conservative release gate.

Version 1.0.0 also exposes the package control/evidence API surface for formal
specification registration, proof-plan validation, proof-run submission and
control, artifact/counterexample registration, evidence-bundle requests and
gate evaluation. Formal specifications, plans, artifacts, counterexamples and
gate decisions are stored as immutable, digest-bound aggregates. Reads and
mutations require the full authenticated tenant/account/project/artifact/
environment/workload scope.

`LocalBoundedExecutor` supplies a repository-owned execution path for exact
equality, finite predicate samples and finite trace equivalence. It accepts
data only, never code or commands, and can emit only A1 bounded evidence or a
replayable counterexample.

Optional production adapters cover digest-pinned native verification
toolchains and disposable SQLite differential checks. They are disabled unless
the host supplies an exact toolchain registry and a permit signer. Every
execution is bound to the authenticated scope, Skill, subject, input bytes,
options and timeout; its signed permit is short-lived and one-use. Native
processes use scrubbed environments and resource limits, while adapters that
execute project/runtime code require a digest-pinned, network-disabled OCI
sandbox. Receipts and stdout/stderr evidence are immutable and
content-addressed. The telemetry service stores only bounded, scope-isolated
labels and allows external export only through an explicitly configured HTTPS
exporter.

The runtime binds every request to a trusted tenant/project scope, immutable
source/target/environment digests, an idempotency key, an append-only event
chain and (when configured) a tenant-isolated content-addressed artifact store.
Each source identity has an explicit allowlisted handler; unknown identities
cannot fall through to a generic dispatcher.

The default runtime never invokes a native verifier, database, provider,
cluster, signer or customer route. Configured native and disposable-database
adapters run only under the authorization controls above and produce
self-attested local engineering receipts. Provider, independent-verifier,
customer-route and deployment evidence remains `NOT_RUN`; a local bounded or
native result is never promoted to independent proof or certification.

Run the complete repository qualification target with:

```sh
make formal-assurance-kernel
```

The local handlers and any configured native/database adapters provide
engineering evidence only. External signing, independent replay, exact
production-provider runs, customer golden routes, deployment evidence and
certification remain explicit `NOT_RUN` / `NOT_CERTIFIED` states until their
named evidence actually exists.
