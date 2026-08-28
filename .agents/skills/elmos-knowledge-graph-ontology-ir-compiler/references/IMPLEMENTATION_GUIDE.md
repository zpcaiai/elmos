# Implementation Guide — Knowledge Graph and Ontology IR Compiler

## Purpose

Compile ontology, entities, relations, temporal validity, provenance, constraints and alignment into a framework-neutral Knowledge IR.

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

1. model ontology and entity identity
2. compile extraction and relation provenance
3. represent temporal validity and contradiction
4. align heterogeneous schemas
5. emit graph validation and migration obligations

## Native acceptance corpus

- `ELMOS_KNOWLEDGE_GRAPH_ONTOLOGY_IR_COMPILER-01` — native scenario: model ontology and entity identity
- `ELMOS_KNOWLEDGE_GRAPH_ONTOLOGY_IR_COMPILER-02` — native scenario: compile extraction and relation provenance
- `ELMOS_KNOWLEDGE_GRAPH_ONTOLOGY_IR_COMPILER-03` — native scenario: represent temporal validity and contradiction
- `ELMOS_KNOWLEDGE_GRAPH_ONTOLOGY_IR_COMPILER-04` — native scenario: align heterogeneous schemas
- `ELMOS_KNOWLEDGE_GRAPH_ONTOLOGY_IR_COMPILER-05` — native scenario: emit graph validation and migration obligations

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
