---
name: differential-oracle-engine
description: Capture, normalize, compare, and explain source/target behavior, state, side effects, traces, security, and performance.
---

# Differential Oracle Engine

## Responsibility

Provide independent, deterministic and explainable comparison. It must not rely on the transformation Agent's self-evaluation.

## Inputs

- source/target environment handles;
- normalized workload and seed;
- contract schema;
- comparison policy and tolerances;
- dynamic-field ignore rules;
- criticality and expected error semantics.

## Capture layers

1. stdout/CLI/function return;
2. HTTP/RPC/browser interaction;
3. database snapshots and change sets;
4. messages, cache, files and external-call recordings;
5. transaction/event trace;
6. security decisions;
7. performance/resource/cost.

## Normalization

Canonicalize JSON keys, numeric formats, timezone, identifiers and explicitly unordered collections. Maintain type information where coercion matters. Each ignored path is versioned, reviewed and surfaced in evidence.

## Compare

- exact for business-critical discrete values;
- declared tolerance for floating/scientific computations;
- multiset for unordered result collections;
- partial order for concurrent traces;
- schema-aware key mapping for generated IDs;
- logical error taxonomy across runtimes/DBMS.

## Output

For each Oracle return pass/fail, criticality, first difference, compact context, raw artifact refs and normalization policy. Mark `silent_semantic_error=true` when execution/build succeeds but semantic Oracle fails after a success-capable target is produced.

## Guardrails

- Never auto-add an ignore rule to make a test pass.
- Never compare only target against target-generated snapshots.
- Never suppress a mismatch because source and target tests both pass.
- Oracle exceptions are `error`, not pass.
- Preserve raw evidence before normalization, with access control and redaction.

## Metamorphic integration

Accept a relation Oracle `R(source_input, transformed_input, outputs)` rather than requiring a fixed answer. Store transformation and relation definition in evidence.
