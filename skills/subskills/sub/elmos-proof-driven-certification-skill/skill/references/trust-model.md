# Trust Model

## Threat Model

Assume the Builder Agent is capable, optimization-seeking, and potentially adversarial with respect to shortcuts. It may:

- fabricate logs, JSON, JUnit XML, screenshots, reports, or `passed=true` fields;
- weaken/remove/skip public tests;
- alter repository-owned wrappers;
- replay old successful evidence;
- attempt path traversal/symlink escapes;
- call OPA directly with invented input;
- search for hidden tests or credentials;
- exploit retries/races to obtain contradictory state;
- claim completion when infrastructure never executed.

The architecture must remain safe even when the Builder is explicitly instructed to obtain `CERTIFIED` by the cheapest route.

## Root of Trust

Environment-owned identities, immutable digests, protected Runner configuration, protected hidden tests, separated signing authorities, and deterministic policy are roots of trust. Natural-language Agent claims are not.

## Capability Matrix

| Capability | Builder | Authority | Runner | Certifier | Gate |
|---|---:|---:|---:|---:|---:|
| source.read | ✓ | ✓ | ✓ | optional | optional |
| source.write | ✓ | ✗ | ✗ | ✗ | ✗ |
| snapshot.create | ✗ | ✓ | ✗ | ✗ | ✗ |
| ticket.issue | ✗ | ✓ | ✗ | ✗ | ✗ |
| hidden_tests.read | ✗ | ✗ | ✓ | optional/sanitized | ✗ |
| execution.run | development only | ✗ | ✓ authoritative | ✗ | ✗ |
| evidence.append | ✗ | ✗ | ✓ | ✗ | ✗ |
| evidence.update/delete | ✗ | ✗ | ✗ | ✗ | ✗ |
| semantic_audit.append | ✗ | ✗ | ✗ | ✓ | ✗ |
| policy.evaluate authoritative input | ✗ | ✗ | ✗ | ✗ | ✓ |
| certification.append | ✗ | ✗ | ✗ | ✗ | ✓ |

## Critical Isolation Rules

1. Builder must not have host root, Docker socket, Kubernetes admin, Runner namespace credentials, Hidden Test Vault credentials, or signing keys.
2. A folder boundary alone is not a trust boundary when all processes share the same powerful OS identity.
3. In production use separate workload identities/service accounts, network policy, DB roles, and KMS permissions.
4. Private keys stay in KMS/HSM signing APIs; do not mount/export PEM private keys to Builder/Runner containers.
5. Separate signing purposes/keys for Ticket, Runner execution attestation, semantic audit, policy bundle, and final certification.

## Security Invariants

- No Agent can self-certify.
- No authoritative evidence without actual execution.
- No certification for a different digest than the verified subject.
- Missing/uncertain infrastructure never becomes PASS.
- Evidence history is immutable.
- Runner FAIL cannot be overridden by Ethen PASS.
- Signatures establish identity/integrity, not the truth of unobserved events.
- Only the exact certified artifact may pass deployment.
