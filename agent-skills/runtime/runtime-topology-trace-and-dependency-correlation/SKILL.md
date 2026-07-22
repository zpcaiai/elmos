---
name: runtime-topology-trace-and-dependency-correlation
description: Correlate OpenTelemetry, gateway, mesh, broker, database, and log observations with static Batch 13 topology. Use to validate production dependencies and trace cross-language business journeys.
---

# Runtime Topology, Trace, and Dependency Correlation

## Workflow

1. Keep DEVELOPMENT, TEST, STAGING, PRODUCTION, and SHADOW observations isolated.
2. Correlate trace/span IDs, request/correlation IDs, message/causation IDs, business journey IDs, and migration experiment IDs.
3. Join HTTP client/server spans, producer-message-consumer spans, database spans, model inference spans, and gateway observations to known nodes.
4. Propagate trace context, message ID, causation ID, and schema version through approved headers. Do not hide tracking fields in payloads outside the contract.
5. Reject baggage keys containing credentials, secrets, tokens, authorization, passwords, or PII.
6. Apply policy confidence: declared plus observed at least 0.95, repeated runtime 0.90, direct static 0.80, configuration 0.60, log-only 0.50. Name similarity is inadmissible.
7. Sampling absence never deletes a static edge; raise coverage gaps and increase controlled sampling for critical journeys.

## Outputs

Emit runtime topology, static/runtime differences, trace coverage, correlation conflicts, sensitive-baggage blockers, and raw evidence references.
