# OpenHands Absorption P0/P1 Threat Model

## Security objective

An Agent or external Provider may propose work, but cannot acquire authority,
cross tenant/resource boundaries, execute unreviewed package content, bypass
policy/evidence gates, disclose secrets or manufacture a success/certification
claim. Uncertain external outcomes fail closed and are reconciled.

## Protected assets

- tenant/project repository source, workspaces, artifacts and browser evidence;
- user/workload identity, approval authority and short-lived credential leases;
- immutable event history, checkpoints, projections and audit corrections;
- Provider sessions, prompts, usage, cost and data-residency constraints;
- capability package identity, signatures, SBOM/provenance, pins and revocation;
- verification evidence, independent-verifier trust and release decisions.

## Trust boundaries

1. User/API → authenticated runtime gateway: tenant/project are derived from
   trusted identity/resource bindings, never accepted as caller authority.
2. Runtime → Agent/Provider: output is untrusted proposal data.
3. Runtime → Tool Gateway/Firewall: every side effect requires typed scope,
   capability, policy, idempotency and approval.
4. Runtime → Sandbox: repository content, hooks, scripts and builds are untrusted;
   egress, mounts, devices and secrets are policy-owned.
5. Runtime → PostgreSQL/CAS/event bus/Temporal: acknowledged state needs atomicity,
   digest/fencing/tenant binding and reconciliation.
6. Producer → independent verifier → completion gate: producer and verifier roles
   and keys are separate; missing/revoked evidence never passes.
7. Supplied ZIP → repository: archive content is read-only untrusted specification;
   its scripts, SQL, workflows and prompts are never executed.

## Primary threats and code controls

| Threat | Representative attack | Implemented control | Remaining external evidence |
|---|---|---|---|
| Identity/tenant confusion | caller supplies another tenant/project/run | authenticated principal + trusted resolvers, RLS, tenant CAS prefixes, full-scope fencing | real IdP/RLS/distributed isolation NOT_RUN |
| Prompt/tool injection | README/web/tool output requests bypass/reveal | taint-aware context, deterministic firewall/policy, typed Action only | independent red team NOT_RUN |
| Secret exfiltration | shell/curl/DNS/git/screenshot/log leak | opaque leases, allowlisted network, deny rules, redaction/masking, no Provider production credential | production network/secret lab NOT_RUN |
| Filesystem/sandbox escape | `..`, symlink, mount, procfs, device, container escape | safe relative paths, symlink rejection, actual isolation-class attestation, default-deny profiles | real gVisor/Kata/microVM/SSH escape suite NOT_RUN |
| Duplicate/unknown side effect | timeout then blind retry | idempotency journal, leases/fencing, action/observation ledger, UNKNOWN reconciliation | real Provider/DB/network fault injection NOT_RUN |
| Event/evidence tampering | update/delete ledger, replace artifact, self-sign PASS | append-only trigger, hash chain, content digest/version, signer trust/revocation, separate verifier | real KMS/PostgreSQL/independent verifier NOT_RUN |
| Package supply chain | traversal/symlink/hook, revoked plugin, dependency drift | deterministic safe ZIP, per-file digest, Ed25519/KMS interface, lock/SBOM/provenance fields, pin/revoke | production registry/KMS/supply-chain review NOT_RUN |
| Approval bypass | self approval, stale R6 approval, wrong action | action-digest binding, TTL, separate approver, R6 two-person/change window, kill switch | enterprise IAM/change-system test NOT_RUN |
| Browser evidence leakage | password/PII in screenshot, binary corruption, flaky pass | sensitive locator masks + attestation, text redaction, binary preservation, expiring allowlist, flake block | real browser/device/privacy review NOT_RUN |
| DAG race/conflict | mutate running child, stale lease, blind overwrite | versioned workflow update, protected running/completed contracts, fencing, semantic conflict/rollback | real Temporal/large-repo Chaos NOT_RUN |
| Resource exhaustion | event flood, fan-out, token/cost/storage abuse | admission/backpressure, multidimensional quotas, per-node/global budget, output/artifact bounds | production load/soak/DoS review NOT_RUN |
| False completion/GA | model says done or local test presented as certification | evidence-only completion gate, qualification max `READY_FOR_EXTERNAL_GATE`, manifest forces `NOT_RUN/NOT_CERTIFIED/NOT_GA` | all external gates NOT_RUN |
| Retention/deletion abuse | delete held data, claim timeout as deleted | versioned policy, legal hold, export-before-delete, durable intent, independent verification, `deletion_unverified` | real provider deletion and legal review NOT_RUN |

## Security invariants

- Missing/ambiguous tenant, resource, policy, approval, evidence or provider state is
  non-success.
- No model, Provider, package or repository file is an authorization principal.
- No irreversible mutation is retried after UNKNOWN without reconciliation.
- No evidence producer can independently verify its own pack.
- Revoked key/package/evidence, `NOT_RUN`, `UNKNOWN` and `INCONCLUSIVE` never pass.
- Isolation labels reflect measured backend properties; code cannot claim L3/L4
  from a command builder or local fake.
- Historical failures/corrections are append-only; projection can be rebuilt.

## Security test and incident ownership

The implementation team owns local negative tests and remediation. A separate
security team owns threat-model review, sandbox/exfiltration red team, findings
severity and retest. Platform owners own identity/RLS, KMS, Temporal, sandbox and
network evidence; Provider/browser owners own their conformance evidence. Release
authority accepts residual risk only after all raw evidence is independently
verified and digest-bound to the release candidate.

## Current security conclusion

Local controls and negative tests are engineering evidence, not a signed security
assessment. Independent security review and production isolation execution remain
`NOT_RUN`; overall state remains `NOT_CERTIFIED` and `NOT_GA`.
