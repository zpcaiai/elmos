# Skill 09 — Cost, Budget, Rate Limit & Concurrency Accounting

## Goal
Make model spend a first-class Elmos control-plane concern.

## Budget hierarchy
Support:
- platform
- tenant
- workspace/project
- user/service-account
- task
- step

## Preflight
Estimate:
`input_tokens * price_in + expected_output_tokens * price_out + fixed/tool/cache modifiers`.

Reject when hard budget would be exceeded unless an authorized override exists.

## Postflight
Reconcile:
1. provider-reported usage
2. gateway usage
3. Elmos tokenizer estimate as fallback

Record confidence/source.

## Rate limiting
Enforce at:
- tenant
- provider
- deployment
- model alias
- task class

Use token bucket/leaky bucket + concurrency semaphores.

## Backpressure
When capacity is exhausted:
- reject low-priority work,
- queue durable background work,
- downgrade only if policy explicitly permits,
- never silently exceed task deadline.

## Accounting event
Append:
- task/step/attempt
- tenant
- model alias
- deployment/provider
- input/output/cache/reasoning tokens where available
- estimated cost
- actual reconciled cost
- retry/fallback waste
- currency
- pricing snapshot/version

## Acceptance
- budget race under concurrency cannot overspend beyond configured tolerance.
- retry cost is visible.
- cost attribution survives fallback.
