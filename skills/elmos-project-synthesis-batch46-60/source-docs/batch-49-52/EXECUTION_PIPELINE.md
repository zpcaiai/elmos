# Execution and Certification Pipeline

## Gate A — Domain Specification

Required outputs:

- User stories and fully dressed use cases
- Business rules and decision tables
- Aggregates, entities, and value objects
- Bounded-context candidates and context map
- Commands, queries, events, and causality
- Workflows and state machines
- Data dictionary and classifications
- Draft interface contracts
- Permission matrix
- Requirement traceability graph

Blocking conditions include orphan must-have requirements, contradictory rules, illegal state transitions, unclassified sensitive data, implicit authorization allow, and broken high-risk verification paths.

## Gate B — Architecture Baseline

Required outputs:

- Architecture style decision
- System context and containers
- Module and service boundaries
- Quality-attribute tradeoff analysis
- Data ownership and consistency
- Communication and timeout plan
- Resilience and recovery tactics
- Threat model and controls
- Multitenancy topology where applicable
- Observability and SLOs
- Deployment, backup, rollback, and disaster recovery
- ADR catalog and approval

Blocking conditions include unmitigated critical threats, ambiguous write ownership, distributed transactions without safe coordination, unsupported quality targets, and deployment without restore or rollback validation.

## Gate C — Project Blueprint

Required outputs:

- Application profiles
- Language/framework profiles
- Runtime version lock
- Dependency catalog and BOM
- Repository layout and namespace plan
- Reproducible build plan
- Safe configuration and secret references
- Code-quality profile
- Immutable Project Blueprint and generation work plan

Blocking conditions include unsupported profiles, end-of-life runtime without exception, critical dependency vulnerabilities, ownership overlap, unpinned tools, nonreproducible builds, and generated production secrets.

## Gate D — Common Generation

Required outputs:

- Trusted template catalog and signed provenance
- Semantic Code Model and symbol table
- Scaffold and generation-unit graph
- AST/CST source output
- Parser-validated configuration
- Ownership manifest
- Protected extension contracts
- Idempotency evidence
- Three-way structural merge evidence
- Formatter, linter, analyzer, and type evidence
- Signed Generation Manifest and SBOM

Blocking conditions include tampered templates, syntax or round-trip failure, ambiguous ownership, user-code overwrite, unstable diffs, unresolved error-level quality findings, and incomplete artifact or dependency inventory.
