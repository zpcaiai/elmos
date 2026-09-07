# External production-gate execution contract

`EXTERNAL-GATE-PLAN.json` is a repository-owned, digest-bound execution
template. It records the exact environment, provider, cluster, Redis, backup,
independent-verifier, and deployment bindings without storing credentials.

The safe first step is:

```text
make production-runtime-external-plan
```

This performs static validation and preflight only. It does not contact a
provider, cluster, Redis instance, backup service, verifier, or registry. The
checked-in template intentionally reports every external operation as
`NOT_RUN` because it contains placeholders and no authorization.

An approved operator may copy the plan outside the repository, fill the exact
provider/cluster/region/full-OCI-image-at-digest bindings, provide credentials only through
the named environment variables, and supply a separate authorization object
with an expiry, change ID, approval ID, actor, and exact operation allowlist.
Execution additionally requires:

```text
ELMOS_EXTERNAL_GATE_ACK=I_HAVE_APPROVED_THIS_EXACT_EXTERNAL_GATE_RUN \
  make production-runtime-external
```

The runner invokes only fixed argument vectors for `k6`, `kubectl`,
`redis-cli`, and `helm`; it never invokes a shell command from the plan. Redis
flush and Kubernetes disruption require explicit destructive authorization.
Provider calls and backup/PITR restores remain adapter-owned because the
protocol, idempotency key, billing semantics, backup consistency model, and
restore verification differ by provider. The generic runner refuses to invent
those semantics.

An external independent verifier must receive the content-addressed report and
return an authenticated receipt binding the exact report SHA-256, producer actor,
distinct verifier actor, decision, verification timestamp, signature, and
verification ID. A local verifier or a static plan is not
external evidence. No runner path can change production certification from
`NOT_CERTIFIED`; only the governed external gate may update the authoritative
status after all required evidence exists.

The attached ZIP remains untrusted declarative input. This contract does not
execute its scripts, installers, prompts, workflows, or validators.
