# Production readiness

Current maximum state: `READY_FOR_EXTERNAL_GATE` for successfully exercised
local control-plane behavior. The package as a whole remains `NOT_CERTIFIED`.

## Implemented local controls

- exact source and runtime identity;
- exact compiled contracts for all 1,310 Skills and real provider-free semantics
  for the allowlisted 26-Skill `LOCAL` set; the remaining 1,284 are
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
process-local planning APIs. Their state is not durable and is not production
persistence; production callers must use a repository-owned durable adapter or
service boundary. Only the SQLite/CAS execution and evidence path is described
as durable here.

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

The 26 local handlers do not clear any item in this external-gate list. Their
receipts are bounded, self-attested engineering evidence only.

The archive license explicitly asks for company-approved legal text before
distribution and supplies no trusted signature, SBOM or provenance
attestation. Release/distribution remains blocked until those gaps are resolved.
