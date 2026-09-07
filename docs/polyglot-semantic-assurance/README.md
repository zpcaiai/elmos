# Polyglot Semantic Assurance v3 integration

The package is integrated as an untrusted declarative specification behind a
repository-owned runtime boundary. The authoritative generated artifacts are:

- `COMPILED_CATALOG.json`: exact source identities, dependency graph, route
  matrix, operation families, and maximum local capability modes;
- `COLLISION_BINDINGS.json`: exact-name bindings whose installed Skill trees
  remain owned by other packages, including the 130 names owned by the
  Semantic Assurance package;
- `QUALIFICATION_RECEIPT.json`: structural integration status and explicit
  evidence gaps.

Each of the 167 repository-owned Skills has the same repository-owned wrapper
in `.agents/skills/<name>/` and `agent-skills/runtime/<name>/`. The remaining
133 exact-name bindings preserve the existing owner recorded by its package
manifest and ledger. Wrappers point to a unique allowlisted runtime handler
and never embed the source package's imperative content.

## Evidence model

Local execution is self-attested engineering evidence. External receipts must
bind the exact tenant, project, revision, environment, and operation subject;
identify distinct producer and verifier roles; remain fresh; and have their
canonical receipt digest minted into host authority. A caller-provided
`independent: true` flag alone has no effect.

Every gate has a repository-owned minimum evidence-type policy. Request input
may add stricter evidence types but cannot remove the native-build, runtime,
negative/holdout, replay, security, recovery, provenance, or independent roles
required by the applicable gate. Verified divergent or inconclusive results
remain blocking.

Unknown, invalid, stale, mismatched, incomplete, or unexecuted evidence fails
closed. The local quality gate may at most produce
`READY_FOR_EXTERNAL_GATE`; it cannot produce `CERTIFIED`.

The packaged legacy Python module namespace remains for compatibility, but its
methods are fail-closed shims: unsupported technologies remain unsupported,
caller-supplied equality is undetermined, and scan/IR/UI/database/build actions
return plans or `NOT_RUN` until routed through the authorized runtime.
