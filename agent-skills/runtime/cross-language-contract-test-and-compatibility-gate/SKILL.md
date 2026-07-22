---
name: cross-language-contract-test-and-compatibility-gate
description: Create and verify versioned cross-language HTTP, gRPC, SOAP, message, file, database-view, model, and client-BFF contracts. Use for consumer-driven testing, provider verification, compatibility matrices, or breaking-change deployment gates.
---

# Cross-language Contract and Compatibility Gate

## Identify both sides

Record consumer, provider, their versions, contract version, environment, and source. Distinguish consumer expectation, provider specification, observed traffic, customer-approved contract, and generated candidate. Do not let a consumer-generated artifact overwrite the formal provider specification.

## Verify independently

Run consumer tests, publish a versioned artifact, verify provider states, and update the compatibility matrix. Keep contract broker/provider integrations optional behind adapters. Make provider-state setup idempotent, isolated, order-independent, fixture-versioned, free of production data, and cleanable.

## Cover all contract forms

For messages, verify channel, key, headers, payload, event version, ordering, delivery semantics, errors, and dead letters. For every form, detect spec, consumer, provider, observed-traffic, and virtual-service drift.

## Decide deployment

Return `CAN_DEPLOY`, `CANNOT_DEPLOY`, `VERIFICATION_UNKNOWN`, `CONSUMER_UNKNOWN`, `PROVIDER_UNKNOWN`, or `EXCEPTION_REQUIRED`. Block destructive removal when any consumer is unknown. Keep E2E/business-journey validation separate; a passing contract never proves final business state.
