---
name: integration-estate-route-endpoint-and-runtime-discovery
description: Discover and correlate enterprise integration platforms, flows, endpoints, routes, transformations, brokers, API gateways, partners, files, workflows, certificates, producers, and consumers. Use when building an Integration Estate Twin from static exports and runtime observations.
---

# Integration Estate Discovery

## Discover separately

Collect static configuration and runtime usage as separate evidence sets. Inventory platform, application, route, endpoint, mapping, adapter, queue, topic, exchange, consumer group, gateway, partner, file route, workflow, scheduler, and certificate identities by environment.

Classify endpoints as HTTP, SOAP, GRPC, JMS, MQ_NATIVE, KAFKA, AMQP, MQTT, FTP, SFTP, AS2, FILE, DATABASE, EMAIL, or CUSTOM. Classify runtime usage as ACTIVE, SEASONAL, DORMANT, HISTORICAL, or UNKNOWN.

## Correlate ownership

- Distinguish declared and observed producers and consumers.
- Preserve unknown producer, consumer, and partner findings as formal risks.
- Build route graphs from source through decode, validate, transform, route, enrich, invoke, aggregate, and output.
- Detect ESB business rules, stateful processes, database ownership, shared lookups, hidden authorization, and manual recovery.

## Produce

Emit `integration-estate.json`, `integration-route-graph.json`, `producer-consumer-matrix.json`, `integration-runtime-usage.json`, `integration-unknowns.json`, and `integration-business-logic.json` with source evidence references.

Do not retire seasonal or unobserved flows. Do not merge environment-specific endpoints or treat declared configuration as runtime proof.
