# Golden Route: autogen-sk-to-agent-framework

**Current status:** `not-certified`

This directory specifies a repeatable commercial route. It does not claim the route has passed against a customer repository.

## Source

AutoGen or Semantic Kernel repository

## Targets

microsoft-agent-framework-dotnet, microsoft-agent-framework-python

## Eligibility

- source API/version identified
- agent/tool/session/workflow semantics recovered
- unsupported extensions declared

## Required evidence

- native target build/start
- session/workflow preservation
- tool/handoff differential
- telemetry and HITL
- migration rollback

## Certification rule

Run at least **3 independent repetitions**, including holdout scenarios, failure/recovery, upgrade drift and rollback. Bind every result to exact source and target revisions. E5 requires customer acceptance and deployment evidence; package validation alone cannot satisfy it.
