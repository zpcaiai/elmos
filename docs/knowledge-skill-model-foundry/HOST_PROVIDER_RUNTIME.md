# Host Provider runtime

`elmos_foundry.provider_runtime.load_provider_runtime_manifest` converts a
host-owned JSON manifest into the existing shell-free production command
Broker. It joins host Provider executables to the 1,244 repository-owned native
semantic programs and 14 exact pipeline routes without adding a wildcard or
local success fallback.

The loader checks the exact compiled catalog digest and, for every entry, the
Skill, adapter, route, operation and native-program digest. It also validates
the absolute executable path, executable digest, ordered arguments, sorted
environment allowlist, timeout and output bound. Duplicate, unknown, local,
drifted and undeclared fields fail closed. The default complete mode rejects a
manifest unless it covers all 1,244 native Skills and 14 pipelines exactly
once. A host may load
a partial manifest only by explicitly setting `require_complete=False`; such a
manifest reports `complete_catalog=False` and cannot support full-catalog
readiness.

The manifest contains environment variable names, never credentials. The
Broker inherits only the named values, invokes the executable without a shell,
passes the canonical request on stdin, and requires the response to contain the
exact seven-stage semantic trace plus a signature-verified Provider receipt.

Effect authorization is separate. Construct a `SignedPermitTrustPolicy`, then
call `build_signed_permit_verifier` with the host's signature verifier. A signed
permit covers the complete invocation, including tenant, project, actor,
environment, workspace, revision, purpose, payload, Broker, route, tools,
gates, policy decision, validity interval and trust epoch. The verifier accepts
no unsigned permit, issuer/actor self-authorization, unknown key, stale epoch,
revocation or changed claim.

Neither API issues signatures, discovers credentials, chooses a Provider, or
creates external evidence. Provider, training, deployment and independent
evidence remain `NOT_RUN`, and certification remains `NOT_CERTIFIED`, until a
real host supplies the manifest, durable store, signatures and reconciled
receipts.

An installed host can run the read-only preflight before constructing its
service:

```bash
elmos-foundry provider-runtime --manifest /absolute/path/provider-runtime.json
```

The command checks complete 1,258-route coverage and re-hashes each unique
installed executable. `--allow-partial` is available for incremental host
integration and reports `complete_catalog=false`; it does not raise readiness.
