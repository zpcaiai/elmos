# Implementation Guide — Cross-Language Serialization and Wire Compatibility Verifier

## Purpose

Preserve JSON, Protobuf, Avro, MessagePack and custom wire contracts across language generators, including defaults, unknown fields, precision, ordering and schema evolution.

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

1. generate multi-language round-trip fixtures
2. verify unknown-field and default semantics
3. compare decimal, timestamp and binary encodings
4. check canonicalization and signature stability
5. certify backward and forward compatibility

## Native acceptance corpus

- `ELMOS_CROSS_LANGUAGE_SERIALIZATION_WIRE_COMPATIBILITY_VERIFIER-01` — native scenario: generate multi-language round-trip fixtures
- `ELMOS_CROSS_LANGUAGE_SERIALIZATION_WIRE_COMPATIBILITY_VERIFIER-02` — native scenario: verify unknown-field and default semantics
- `ELMOS_CROSS_LANGUAGE_SERIALIZATION_WIRE_COMPATIBILITY_VERIFIER-03` — native scenario: compare decimal, timestamp and binary encodings
- `ELMOS_CROSS_LANGUAGE_SERIALIZATION_WIRE_COMPATIBILITY_VERIFIER-04` — native scenario: check canonicalization and signature stability
- `ELMOS_CROSS_LANGUAGE_SERIALIZATION_WIRE_COMPATIBILITY_VERIFIER-05` — native scenario: certify backward and forward compatibility

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
