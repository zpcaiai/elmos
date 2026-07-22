---
name: declaration-and-module-lifter
description: Lift PSP modules, namespaces, types, properties, events, and callables into UIR declarations. Use before body lifting or public API export.
---
# Declaration and Module Lifter
Read `../references/uir-v1.md`. Preserve containers, visibility, overloads, generics, annotations/decorators, static initialization, declaration sites, and source symbols. Keep property/event/type-alias/nominal semantics distinct; merge only authority-proven C# partial or TypeScript declarations. Constructors belong to types. Every PSP declaration must map to UIR or an explicit diagnostic/opaque record.
