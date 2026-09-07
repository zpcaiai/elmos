---
name: metamorphic-fuzz-mutation
description: Generate high-value property, metamorphic, fuzz, mutation, and fault-injection campaigns for ETGB cases.
---

# Metamorphic, Fuzz and Mutation Assurance

## Campaign design

Select high-risk capability cells using production frequency, incident history, semantic complexity, low coverage, model uncertainty and recent changes. Campaigns use fixed master seeds plus recorded derived seeds for replay.

## Property generation

Build generators from language types, JSON/OpenAPI/Protobuf schemas, database schema and domain constraints. Include boundary, invalid and stateful sequences. Shrink failures while retaining the semantic mismatch.

## Metamorphic relations

Examples:

- SQL predicate/CTE/join rewrites with preserved semantics;
- repository addition of unreachable module leaves behavior unchanged;
- request order permutation for independent operations;
- equivalent requirement paraphrases preserve acceptance;
- split/merge dataset relation;
- serialization round-trip;
- source-preserving refactor before translation yields equivalent target behavior.

Relations must state preconditions; invalid metamorphic assumptions create false alarms.

## Fuzzing

Use grammar/AST generation rather than random bytes for deep paths, with a small malformed-input campaign for parser hardening. Run in resource-limited sandbox. Detect crash, hang, leak, inconsistent result, nondeterminism, security escape and undisclosed deletion.

## Mutation

Maintain domain mutant operators for each line. Prioritize mutants representing actual migration/generation defects. Measure kill rate per capability, not only global score. Equivalent mutants require documented review, not silent exclusion.

## Fault injection

Inject before/after durable writes and external side effects at every phase. Verify idempotency, checkpoint, ownership/fencing, compensation, billing and audit. Repeat cancel/resume at all phase boundaries.

## Campaign output

- seeds and generators;
- minimized repros;
- surviving mutants;
- flaky/nondeterministic cases;
- new fixed regressions;
- coverage gain and cost.

## Promotion rule

A fuzz-found issue is not closed until a deterministic regression exists. A P0 mutant survivor blocks release when it represents a forbidden semantic error.
