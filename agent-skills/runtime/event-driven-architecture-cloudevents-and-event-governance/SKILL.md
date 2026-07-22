---
name: event-driven-architecture-cloudevents-and-event-governance
description: Govern event types, CloudEvents envelopes, ownership, naming, versions, keys, lifecycle, sensitivity, and hidden choreography across brokers. Use when distinguishing commands, events, notifications, queries, CDC, audit, telemetry, or control messages.
---

# Event Governance

## Classify intent first

Classify DOMAIN_EVENT, INTEGRATION_EVENT, NOTIFICATION, CDC_EVENT, AUDIT_EVENT, TELEMETRY_EVENT, and CONTROL_EVENT separately from commands and queries. Record event type/version, owner, source, subject, schema, key, timestamp semantics, classification, retention, consumers, SLA, and replay policy.

Use CloudEvents `specversion`, `id`, `source`, `type`, `subject`, `time`, `datacontenttype`, and `dataschema` as a portable envelope when appropriate. Treat `source + id` as a duplicate-detection candidate, not universal end-to-end proof. Keep secrets out of context attributes.

## Govern evolution

Assess optional additions, enum additions, renames, type changes, removals, semantic changes, splits, and merges at both schema and business levels. Detect event-as-command, command-as-event, giant events, raw database rows mislabeled as domain events, missing owner/key, embedded secrets, and hidden event-chain processes.
