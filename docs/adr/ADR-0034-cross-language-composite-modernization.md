# ADR-0034: Cross-language composite modernization above three language engines

## Status

Accepted for Batch 13 on 2026-07-21.

## Context

The Java, .NET, and Python engines can each produce valid repository-level plans and evidence while the whole application system still fails because consumers, contracts, shared databases, messages, runtime routing, business journeys, or rollback obligations cross repository and language boundaries. Repository success is therefore necessary but not sufficient.

OpenAPI provides a language-agnostic HTTP description, AsyncAPI describes event-driven channels/messages/operations, and Protobuf compatibility has separate generated-source, JSON, and binary-wire concerns. Runtime evidence adds a different view; sampled absence cannot erase a declared static dependency, and OpenTelemetry baggage must not carry sensitive values. These standards inform the catalog and evidence formats but do not delegate production authority to ELMOS.

## Decision

Add a framework-free `composite-modernization` domain above, not inside, the language engines. It owns:

- immutable, time- and environment-bound System Landscape versions;
- evidence-ranked cross-repository dependency edges, SCCs, shared-database coupling, and unknown consumers;
- language-neutral contracts, producer/consumer matrices, compatibility windows, and temporary adapters;
- explicit data ownership, outbox/inbox, CDC, resumable backfill, reconciliation, and separate read/write cutover gates;
- side-effect-safe shadow comparison, progressive traffic evaluations, cross-language business journeys, data-aware rollback, stability hold, and decommission readiness;
- layered composite evidence mapped into the existing tenant, workflow, audit, portfolio, SCM, delivery, retention, and commercial platform.

The only control-plane endpoints are evaluate/read operations. Traffic providers, CDC connectors, gateways, meshes, brokers, databases, and decommission actions remain external ports. Full traffic, production write ownership, lossy compatibility, destructive actions, irreversible steps, and decommission require explicit human approval and independent evidence.

## Consequences

Java, .NET, and Python remain the only source transformation engines. Composite code cannot depend on OpenRewrite, language workers, repair agents, Spring, JDBC, Docker, or persistence adapters. Missing landscapes, consumers, traces, contract strength, CDC evidence, business metrics, rollback paths, or decommission checks are blockers rather than inferred success.

V13 covers 76 tenant-scoped composite object/evidence types with forced RLS: it creates 74 tables and reuses the existing V7 `message_contracts` and V9 `model_endpoints` authorities with landscape projections. Observations and decisions that establish audit history are append-only. X001–X014 provide reusable operator contracts, and 18 executable accident scenarios are the minimum repository-level acceptance suite.

## Standards basis

- [OpenAPI Specification 3.2.0](https://spec.openapis.org/oas/v3.2.0.html)
- [AsyncAPI Specification 3.0.0](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
- [Protocol Buffers proto3 guide](https://protobuf.dev/programming-guides/proto3/)
- [Buf breaking-change detection](https://buf.build/docs/breaking/)
- [OpenTelemetry Baggage API](https://opentelemetry.io/docs/specs/otel/baggage/api/)
- [Debezium stable documentation](https://debezium.io/documentation/reference/stable/index.html)
- [Istio traffic mirroring](https://istio.io/latest/docs/tasks/traffic-management/mirroring/)
- [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/)
