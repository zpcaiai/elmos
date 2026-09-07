# Implementation Guide — Graph Database Semantic IR Compiler

## Purpose

Compile property graph, RDF, ontology, traversal, constraint and transaction semantics for Neo4j, Gremlin and SPARQL-class targets.

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

1. model nodes, edges, labels, predicates and constraints
2. compile Cypher/Gremlin/SPARQL query semantics
3. represent path uniqueness and traversal bounds
4. capture graph transaction and index behavior
5. preserve ontology and provenance mappings

## Native acceptance corpus

- `ELMOS_GRAPH_DATABASE_SEMANTIC_IR_COMPILER-01` — native scenario: model nodes, edges, labels, predicates and constraints
- `ELMOS_GRAPH_DATABASE_SEMANTIC_IR_COMPILER-02` — native scenario: compile Cypher/Gremlin/SPARQL query semantics
- `ELMOS_GRAPH_DATABASE_SEMANTIC_IR_COMPILER-03` — native scenario: represent path uniqueness and traversal bounds
- `ELMOS_GRAPH_DATABASE_SEMANTIC_IR_COMPILER-04` — native scenario: capture graph transaction and index behavior
- `ELMOS_GRAPH_DATABASE_SEMANTIC_IR_COMPILER-05` — native scenario: preserve ontology and provenance mappings

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
