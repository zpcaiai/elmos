# Implementation Guide — Network Egress and Data-Exfiltration Certifier

## Purpose

Certify destination, protocol, payload, DNS, proxy and data-loss controls for every model, tool, connector and generated deployment.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. derive egress allowlist from capabilities
2. bind DNS/IP/service identity and TLS policy
3. inspect/redact classified payloads
4. test covert channels and redirect chains
5. record blocked and approved transfer evidence

## Native acceptance corpus

- `ELMOS_NETWORK_EGRESS_DATA_EXFILTRATION_CERTIFIER-01` — native scenario: derive egress allowlist from capabilities
- `ELMOS_NETWORK_EGRESS_DATA_EXFILTRATION_CERTIFIER-02` — native scenario: bind DNS/IP/service identity and TLS policy
- `ELMOS_NETWORK_EGRESS_DATA_EXFILTRATION_CERTIFIER-03` — native scenario: inspect/redact classified payloads
- `ELMOS_NETWORK_EGRESS_DATA_EXFILTRATION_CERTIFIER-04` — native scenario: test covert channels and redirect chains
- `ELMOS_NETWORK_EGRESS_DATA_EXFILTRATION_CERTIFIER-05` — native scenario: record blocked and approved transfer evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
