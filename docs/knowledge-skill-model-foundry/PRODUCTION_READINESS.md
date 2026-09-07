# Production readiness

Current maximum state: `READY_FOR_EXTERNAL_GATE` for successfully exercised
local control-plane behavior. The package as a whole remains `NOT_CERTIFIED`.

## Implemented local controls

- exact source and runtime identity;
- exact compiled contracts for all 1,310 Skills and real provider-free semantics
  for the allowlisted 45-Skill `LOCAL` set; the remaining 1,265 are
  `PREPARE_ONLY`;
- tenant/project isolation and host-minted authority checks;
- bounded canonical requests and exact durable idempotency for adapter effects;
- request-bound, expiring, one-time adapter permits and trusted policy checks;
- host-owned external Broker routes with exact operation/effect matching,
  verifier-bound provider receipts and complete declared-output enforcement;
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
- real language, database, framework, cloud and model adapters with exact
  version matrices;
- native builds, databases, browser/device journeys, model training/serving,
  shadow/canary, rollback, long soak, chaos and disaster recovery;
- independent corpora, verifier, customer acceptance, legal approval and
  production certification.

The 45 local handlers do not clear any item in this external-gate list. Their
receipts are bounded, self-attested engineering evidence only.

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

The 1,265 `PREPARE_ONLY` Skills lack exact semantic implementations; these are
code gaps, not merely unexecuted tests. Even the 45 `LOCAL` Skills cover bounded
local behavior and are not whole-Skill or production completion. All 14 golden
pipelines still prepare plans only. Source input/output schemas, concrete tool
operations, target versions and environment bindings marked `UNBOUND` require
implementation refinement and cannot be completed by generic dispatch.

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
