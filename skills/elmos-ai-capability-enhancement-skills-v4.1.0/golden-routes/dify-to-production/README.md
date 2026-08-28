# Golden Route: dify-to-production

**Current status:** `not-certified`

This directory specifies a repeatable commercial route. It does not claim the route has passed against a customer repository.

## Source

exported Dify DSL + plugin dependencies + representative scenarios

## Targets

langgraph-python, spring-ai-java

## Eligibility

- DSL importable at exact version
- custom plugins available or declared opaque
- critical workflow features representable

## Required evidence

- source Dify execution traces
- target native build/start
- tool/retrieval/state/side-effect differential
- unsupported feature ledger
- rollback

## Certification rule

Run at least **3 independent repetitions**, including holdout scenarios, failure/recovery, upgrade drift and rollback. Bind every result to exact source and target revisions. E5 requires customer acceptance and deployment evidence; package validation alone cannot satisfy it.
