# 08 — Transformation Planning and Execution

## Classify before editing

Repair, refactor, modernization and re-architecture/rewrite carry different proof obligations. Recover business, API, data, security, transaction, message, performance and operational invariants first.

## Alternatives

Generate conservative, balanced and strategic target states. Record evidence, assumptions, consequences, risks, cost, machine wall-clock, human review, exit and rollback in ADRs. Microservices and rewrites are not defaults.

## Transformation DAG

Every step declares dependencies, write scope, preconditions, tool/Adapter, evidence obligations, side effects, checkpoint, approval, rollback and expected outputs. Critical unknowns block dependent steps.

## Edit hierarchy

Compiler refactor API > typed LST/AST recipe > Semantic IR rule > constrained synthesis > free-form patch. Each ChangeSet is single-purpose, independently buildable/testable/reversible and reviewed before commit.
