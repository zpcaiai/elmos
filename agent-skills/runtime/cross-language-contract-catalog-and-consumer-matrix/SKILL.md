---
name: cross-language-contract-catalog-and-consumer-matrix
description: Catalog HTTP, message, Protobuf, SOAP, data, file, and model contracts and build producer-consumer compatibility matrices across Java, .NET, and Python. Use before contract evolution or removal.
---

# Cross-Language Contract Catalog and Consumer Matrix

## Workflow

1. Assign a language-neutral permanent contract identity and immutable version records.
2. Import authoritative OpenAPI, AsyncAPI, Protobuf, WSDL, JSON Schema, Avro, database, file, and model signatures. Label inferred or observed contracts as weaker evidence.
3. Enumerate connected, disconnected, external, and unknown consumers with current and target versions.
4. Evaluate backward, forward, full, breaking, or unknown compatibility per consumer.
5. Treat field removal, optional-to-required change, enum removal, format change, and incompatible type change as breaking unless the native standard proves otherwise.
6. Check Protobuf wire field numbers/types separately from JSON mapping behavior.
7. Block destructive changes when any consumer is unknown, external confirmation is missing, old-version use remains, or the contract is merely inferred.

## Outputs

Emit the catalog, version diffs, producer-consumer matrix, unknown-consumer blockers, old-version usage, and evidence references. Producer tests alone never prove consumer compatibility.
