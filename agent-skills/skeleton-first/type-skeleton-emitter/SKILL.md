---
name: type-skeleton-emitter
description: Emit target classes, interfaces, records, enums, fields, properties, events, generics, and signatures from UIR. Use for contract-only type skeletons.
---
# Type Skeleton Emitter
Read `../references/skeleton-v1.md`. Preserve UIR public signatures, generic constraints/variance/nullability, inheritance, property accessibility/storage, event semantics, enum values/serialization/flags, nesting and source maps. Unsupported multiple inheritance or types need helper/composition/opaque strategy plus obligation. Business bodies remain abstract/interface or throw-not-implemented; never return null/None as a misleading implementation.
