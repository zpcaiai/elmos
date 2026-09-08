# Production readiness

Current maximum state: `READY_FOR_EXTERNAL_GATE` for successfully exercised
local control-plane behavior. The package as a whole remains `NOT_CERTIFIED`.

## Implemented local controls

- exact source and runtime identity;
- exact compiled contracts and runtime bindings for all 1,310 Skills, with real
  provider-free semantics for the allowlisted 66-Skill `LOCAL` set; the other
  1,244 have exact `NATIVE` programs and distinct digest-bound, fail-closed
  host Broker routes;
- tenant/project isolation and host-minted authority checks;
- bounded canonical requests and exact durable idempotency for adapter effects;
- request-bound, expiring, one-time adapter permits and trusted policy checks;
- host-owned external Broker routes with exact operation/effect matching,
  verifier-bound provider receipts and complete declared-output enforcement;
- a shell-free production command Broker that allowlists every route, pins the
  provider executable and complete route configuration by SHA-256, passes only
  explicitly inherited environment variables, bounds time/output, kills timed
  out process groups, and treats every drift, malformed response, nonzero exit
  or unreconciled outcome as failure with unknown effects;
- typed training and deployment requests that bind provider/version,
  environment, configuration and exact input/output artifact digests, plus
  external receipt verification that requires a distinct executor, reconciled
  outcome, complete outputs, canonical digest and host-supplied signature
  verifier;
- independent-acceptance and certification request/receipt protocols that bind
  provider, training and deployment evidence, holdout corpus, required gates,
  implementation/catalog/policy digests, separated producer/executor/verifier/
  authority identities, revocation, validity interval and trust epoch;
- a verify-only external qualification intake with strict JSON schemas,
  Ed25519 public trust keys, validity and revocation enforcement, trust-store
  digest binding, authority-role and public-key separation, exact executor and
  tenant/project/target bindings, and an atomic private decision artifact;
- exact permit-request and execution entry points for all 14 golden pipelines;
- durable transitions, checkpoints, audit/evidence and outbox reconciliation;
- private immutable artifact storage;
- trusted receipt verification for consent, capture, data use, E1 promotion and
  model routing; no global training by default;
- exact handler and adapter allowlists;
- fail-closed unknown, unsupported, expired, stale and unreconciled states.

The convenience knowledge, experience, dataset, model and serving managers are
bounded local APIs. When a file-backed `FoundryStore` is injected, their
metadata is persisted in SQLite with authenticated tenant/project scoping,
versioned compare-and-swap updates, immutable creation identities and atomic
audit events. Restart recovery covers knowledge metadata, sanitized episodes,
dataset quarantine and model metadata; serving health expires and a new gateway
cannot reuse prior availability. Without an injected store (or with `:memory:`),
state remains process-local. This is local SQLite durability, not PostgreSQL RLS,
provider execution or production persistence qualification.

## Open external gates

- PostgreSQL 16 RLS and policy deployment (the source design SQL contains no
  enabled RLS policies);
- OPA bundle compilation and enforcement;
- secret broker, KMS/HSM signing and revocation;
- installed real language, database, framework, cloud and model provider
  commands with exact version matrices and trusted signature keys;
- native builds, databases, browser/device journeys, model training/serving,
  shadow/canary, rollback, long soak, chaos and disaster recovery;
- independent corpora, verifier, customer acceptance, legal approval and
  production certification.

The 66 local handlers and 1,244 native program/host route bindings do not clear any item in
this external-gate list. Their
receipts are bounded, self-attested engineering evidence only.

The repository now implements the reusable external execution and evidence
verification boundary in `elmos_foundry.external_assurance` and the complete
intake gate documented in
[EXTERNAL_QUALIFICATION.md](EXTERNAL_QUALIFICATION.md). It does not ship a
provider credential, provider executable, training cluster, deployment account,
independent holdout result, verifier key or certification-authority decision.
Consequently provider, training, deployment and independent evidence remain
`NOT_RUN`, and the package remains `NOT_CERTIFIED` in this checkout.

The archive license explicitly asks for company-approved legal text before
distribution and supplies no trusted signature, SBOM or provenance
attestation. Release/distribution remains blocked until those gaps are resolved.

## Exhaustive unfinished work

[IMPLEMENTATION_MATRIX.md](IMPLEMENTATION_MATRIX.md) summarizes all 41 packs.
[IMPLEMENTATION_MATRIX.json](IMPLEMENTATION_MATRIX.json) lists every one of the
1,310 exact identities, implementation bindings, missing contract details,
dependency blockers, required tools, workflow and verification requirements.
Regenerate with `uv run python tooling/report_foundry_readiness.py --write`;
`make knowledge-skill-model-foundry-skills` rejects a stale inventory.

All 1,244 formerly `PREPARE_ONLY` Skills now have exact repository-owned native
semantic programs. Each program fixes the Skill identity, source digest, ordered
seven-stage workflow, inputs, outputs, dependencies, tools, gates, invariants and
rollback strategy; each route additionally fixes its privileged effect class. Execution remains
`NOT_RUN` until a concrete host/provider implementation and environment are
injected and its permit and result receipt verify. Even the 66 `LOCAL` Skills
cover bounded local behavior and are not whole-Skill or production completion.
All 14 golden pipelines now expose exact Broker execution paths, but none was
executed in a real training, deployment, device, database or customer
environment by this local qualification.

This expansion adds eight exact foundation handlers (ADR, taxonomy, directional
compatibility, scope, evidence, policy, consent and release contracts) and six
dataset algorithms (group/time splits, lineage, revocation impact, preference
pairs, annotation selection and Python AST structural deduplication), plus local
transaction compensation and capability-filtered lexical retrieval. Their
[bounded implementation scope](LOCAL_IMPLEMENTATION_SCOPE.md) is explicit.
They do not verify caller declarations, authorize training, attest provider
compatibility, execute unlearning, publish releases or sign artifacts.

Three additional repository handlers parse Maven/npm build declarations,
extract real Python/ECMAScript 2017 syntax trees and reconcile typed parser
projections with source spans, CFG and supplied evidence. They preserve
unsupported syntax, missing facts and conflicting interpretations. These
bounded algorithms do not execute builds, infer cross-language equivalence
or replace real source/target runtime validation.

Six knowledge-ingestion handlers now normalize supplied repository deltas, API
contracts, database metadata and runtime traces, evaluate source freshness at a
caller-supplied time, and conservatively classify caller-declared rights. They
reject cross-scope identities, path collisions, dangling graph references,
invalid time intervals and unsupported formats. They do not read repositories,
connect to APIs/databases/telemetry systems, or provide legal verification.
