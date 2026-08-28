# Golden Route: langchain-to-langgraph

**Current status:** `not-certified`

This directory specifies a repeatable commercial route. It does not claim the route has passed against a customer repository.

## Source

existing LangChain repository + lockfile + tests/traffic fixtures

## Targets

langgraph-python

## Eligibility

- source baseline classified
- tools/retrievers/providers observable
- state/termination can be recovered or approved

## Required evidence

- source/target trace differential
- checkpoint/resume
- interrupt/HITL where required
- retry-safe side effects
- load and recovery

## Certification rule

Run at least **3 independent repetitions**, including holdout scenarios, failure/recovery, upgrade drift and rollback. Bind every result to exact source and target revisions. E5 requires customer acceptance and deployment evidence; package validation alone cannot satisfy it.
