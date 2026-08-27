# Contracts

- `schemas/`: JSON Schema Draft 2020-12 machine contracts.
- `examples/`: schema-valid examples used by package validation.
- `openapi/`: control, evidence, gate and governance APIs.
- `events/`: AsyncAPI event contracts.

All mutating API calls require tenant/account identity, idempotency and trace context at the gateway even where those cross-cutting headers are omitted from the compact examples.
