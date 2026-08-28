# Golden Route: business-requirement-multitarget

**Current status:** `not-certified`

This directory specifies a repeatable commercial route. It does not claim the route has passed against a customer repository.

## Source

approved business requirement + acceptance scenarios

## Targets

dify, langgraph-python, spring-ai-java, openclaw

## Eligibility

- requirements have observable acceptance
- critical data/security constraints declared
- target versions available for native conformance

## Required evidence

- Dify native import
- LangGraph native start/checkpoint/resume
- Spring AI native build/start
- OpenClaw gateway/skill load
- cross-target normalized trace
- security/performance/recovery
- customer acceptance

## Certification rule

Run at least **3 independent repetitions**, including holdout scenarios, failure/recovery, upgrade drift and rollback. Bind every result to exact source and target revisions. E5 requires customer acceptance and deployment evidence; package validation alone cannot satisfy it.
