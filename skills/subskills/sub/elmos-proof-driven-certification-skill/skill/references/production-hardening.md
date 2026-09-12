# Production Hardening

## Workload Identity

Use one organization-level SPIFFE trust domain initially with distinct workload identities for Authority, Runner, Certifier, Gate and Builder. Enforce service-to-service identity through mTLS and capability mapping. Consider stronger separate trust roots only for higher-assurance E4/E5 deployments when operationally justified.

Identity must be environment-established, never trusted from a request header/body role string.

## KMS

Use separate keys/purposes:

- Authority Ticket key;
- Runner execution-attestation key;
- Certifier semantic-audit key;
- Policy bundle key;
- final certification/release key.

Do not export private key material. Authorize KMS signing by workload identity + signing purpose.

## in-toto / Sigstore

Sign/attest already-established execution facts. Suggested path:

```text
TrustedToolResults → EvidenceManifest digest → in-toto Statement → Runner-authorized signature → immutable attestation
```

Bind exact subject/artifact digest, Ticket digest, Runner identity/image, case catalog, hidden test package, evidence manifest and relevant counts/results.

## Temporal

Temporal is a durable orchestrator, not a root of trust.

Use separate task queues and workers:

- `elmos-authority-q`
- `elmos-runner-q`
- `elmos-certifier-q`

Workers receive only their domain credentials. Workflow history contains opaque IDs/digests, not hidden tests/private keys/customer secrets.

Externally visible Activities must be idempotent. Preserve multiple real execution attempts; never overwrite history.

## Hidden Test Vault

Keep protected tests outside Builder-readable repositories. Runner requests a ticket-pinned package using its workload identity. Sanitize diagnostics so Builder receives actionable failure categories but not exact hidden fixtures/oracles.

## Mutation

Record generated/eligible/killed/survived/timeouts/score/scope. Detect artificial exclusion/scope collapse. Thresholds are risk/policy-specific.

## Sabotage

Attack the trust infrastructure itself: fake evidence, unsigned/tampered attestations, wrong identities, key misuse, replay, hidden-test substitution, OPA outage, duplicate Temporal delivery, commit/time-out races, object mutation and deployment substitution.

Known certification escape rate must be zero before production release.

## Ethen

Ethen is an independent semantic auditor. Claims reference authoritative evidence and may be SATISFIED/VIOLATED/UNKNOWN/NOT_APPLICABLE/CONFLICTING_EVIDENCE. No evidence reference means a required claim cannot authoritatively be SATISFIED.

## Signed OPA Bundles

Production policy should be signed and released independently of Builder. Ticket pins the policy bundle digest. Signature/digest verification failure denies activation/evaluation.

## Build and Deployment Binding

Create Build Attestation binding artifact digest A to source digest S. Prefer verification against deployable artifact A. Final Certification subject is artifact A. Deployment Gate permits only the exact certified digest.
