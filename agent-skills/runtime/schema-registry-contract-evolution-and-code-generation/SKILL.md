---
name: schema-registry-contract-evolution-and-code-generation
description: Govern Avro, JSON Schema, Protobuf, XML, Copybook, EDI, and custom schemas across replaceable registries, compatibility policies, references, code generation, and runtime payloads. Use for schema migration, compatibility windows, or generated client updates.
---

# Schema Registry and Contract Evolution

## Separate registry and governance

Support Confluent, Apicurio, cloud-managed, Git, custom, and multi-registry providers. Record subject strategy, compatibility mode, schema references, cycles, packages, producers, consumers, and business owner.

Evaluate SYNTACTIC, SERIALIZATION, BINARY, JSON, GENERATED_CODE, CONSUMER_RUNTIME, and BUSINESS_SEMANTIC compatibility separately. Never treat a registry pass as consumer or business-semantic proof.

## Freeze generation

Record generator, version, options, language, runtime library, and output hash for Java, C#, Python, TypeScript, Go, or approved targets. Compare declared, registered, observed message, and consumer-expected schemas.

Put field removal, type change, Protobuf field-number reuse, and meaning changes into a compatibility window with runtime consumer evidence.
