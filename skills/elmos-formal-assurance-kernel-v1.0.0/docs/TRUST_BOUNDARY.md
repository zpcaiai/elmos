# Trust Boundary and TCB

## Trusted components

The trusted computing base includes every component whose incorrect behavior could cause Elmos to accept a false assurance claim:

- source and target parsers;
- source maps and Semantic IR adapters;
- formal semantic definitions and normalization functions;
- obligation compiler and status policy;
- proof checker or solver;
- verifier output parser;
- compiler/runtime used to replay evidence;
- database behavior relied upon by the model;
- object-store integrity and signing services;
- external API contracts used as assumptions.

## TCB reduction

Prefer independently checkable proof certificates. Keep result parsers small and deterministic. Store raw engine output beside parsed results. Use separate processes for untrusted source parsing and proof execution. Pin images by digest, capture SBOM/provenance, and revoke evidence when a trusted component becomes vulnerable or changes.

## Evidence classes

| Class | Trust statement |
|---|---|
| Kernel checked | a small proof kernel checked a certificate |
| Solver trusted | the exact solver/adapter is part of the TCB |
| Bounded | model checker explored the declared finite scope |
| Runtime | a monitor checks behavior during execution |
| Human waiver | authorized risk acceptance; not a proof |

## External service boundary

External APIs, proprietary databases and native libraries are never assumed correct by default. They require one of:

1. executable contract and conformance evidence;
2. closed-world enumeration and digest;
3. runtime monitor and compensating control;
4. explicit unsupported boundary;
5. time-bound waiver.

## Revocation

A TCB digest, signature, license status or vulnerability change creates a drift event. Related proof runs become stale, cache entries are invalidated, and release gates are reevaluated.
