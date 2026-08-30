# Knowledge-Skill-Model Foundry v3 integration

This integration turns the pinned 16,007-entry ZIP into a typed control plane
with 26 exact provider-free semantic handlers, 1,284 conservative prepare-only
contracts, and a separately gated external-effect boundary. It does not
reinterpret the archive as trusted instructions and does not claim that its
1,310 specifications already have native provider or customer evidence.

## Imported authority

- Archive SHA-256:
  `e29673a598756deff422e8dd7f36b2826e9c1aaff6df22db2c0699b0857ee0e4`
- Manifest authority: `registry/skill-catalog.yaml`, v3.0.0, 1,310 atomic Skills
- Auxiliary JSON: `registry/skill-catalog.json`, v2.0.0, 458 Skills,
  `STALE_NON_AUTHORITATIVE`
- Meta discovery: 41 entries, at most 16 candidates and 8 activations
- Source evidence: digest-bound package bytes only

The archive has no trusted signature, SBOM, provenance attestation, production
license text, provider runtime, or independent evidence bundle. Its five
executable Python files remain inert input.

## Implemented repository surface

- safe, read-only ZIP and contract validation in
  `tooling/integrate_knowledge_skill_model_foundry_skills.py`;
- deterministic compiled-contract v2 catalog binding all 7,860 authoritative
  per-Skill source documents, with 458 BASIC and 852 ENHANCED contracts;
- 41 pack handlers and 1,310 explicit allowlisted atomic bindings;
- 26 exact local semantic handlers covering contract/hash/graph, registry and
  routing, trust and audit, normalization/provenance, durable experience replay,
  dataset, evidence and serving controls;
- request-bound, policy-gated, durable and non-replayable Broker execution for
  external semantics; direct external Python callbacks are forbidden, route
  operations and effect classes are exact, and successful receipts must carry
  every declared output;
- authenticated scope, capability lease, exact idempotency, durable lifecycle,
  checkpoints, append-only audit/evidence, outbox reconciliation, and private
  content-addressed artifacts on the injected execution-control path;
- verifier-bound consent, trajectory capture, dataset use, E1 promotion and
  route planning; the convenience asset managers remain process-local;
- conservative pipeline preparation for all 14 declared pipelines.

## Status vocabulary

`LOCAL` identifies one of the 26 exact repository-owned semantic handlers;
`PREPARE_ONLY` means that the repository can validate scope and produce a
content-bound execution plan. `REQUIRES_ADAPTER` means the requested semantic or
external effect did not run. `LOCAL_EXECUTED_SELF_ATTESTED` is local engineering
evidence. `READY_FOR_EXTERNAL_GATE` is not certification. `NOT_RUN`,
`INCONCLUSIVE`, and `UNKNOWN` never pass a gate.

The immutable mirror under `skills/elmos-knowledge-skill-model-foundry-v3.0.0/`
and the source ZIP are never modified by the runtime.
