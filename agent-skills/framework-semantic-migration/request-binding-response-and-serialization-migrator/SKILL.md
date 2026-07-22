---
name: request-binding-response-and-serialization-migrator
description: "Migrate parameter binding, body formats, content negotiation, responses, cookies, headers, and serialization contracts. Use for framework transport boundary conversion."
---
# Request Binding Response and Serialization Migrator
Read `../references/afsm-v1.md`. Preserve path/query/header/cookie/form/multipart/body/context/principal sources and distinguish missing, null, empty, default, zero, malformed, multi-value and unknown fields.

Preserve required/default/coercion rules, status, media type, headers, cookies, Decimal/time/enum/polymorphism and streaming semantics. Never expose persistence entities as response DTOs or accept lossy serialization without a blocking differential obligation.

