---
name: integration-e2e-business-journey-and-nonfunctional-validator
description: Validate real cross-module/service/client/data/model/infrastructure integrations, critical end-to-end business journeys, negative paths, and nonfunctional properties. Use when component or contract tests cannot prove final state or operational behavior.
---

# Integration, E2E, Journey, and Nonfunctional Validation

## Select meaningful boundaries

Exercise module-to-database, service-to-broker/cache/IdP, client-to-BFF, BFF-to-backend, pipeline-to-dataset, model-to-feature pipeline, and infrastructure-to-workload boundaries with real critical dependencies. Use E2E for UI-to-database, API-to-external system, event-to-final-state, batch-to-report, mobile offline sync, and desktop/device journeys.

## Assert business outcomes

Bind journey identity to business journey, test data, environment, artifact versions, contract versions, and trace ID. Assert state, data, messages, external calls, audit, authorization, balances, inventory, reports, and telemetry; do not stop at HTTP 200.

## Cover negative journeys

Include expired identity, insufficient inventory, payment timeout, duplicate request/message, unavailable downstream, data conflict, partial failure, rollback, and compensation.

## Separate nonfunctional evidence

Evaluate performance, reliability, security, accessibility, usability, compatibility, recovery, and capacity independently from functional success. Distinguish baseline, load, stress, spike, soak, capacity, and failover. Run calibrated performance tests outside shared CI.

## Control E2E volume

Keep system-level tests for critical journeys and boundary risks that lower layers cannot prove. Move combinatorial field behavior to lower levels while retaining final-state coverage.
