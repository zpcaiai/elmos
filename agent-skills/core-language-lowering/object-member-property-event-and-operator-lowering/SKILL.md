---
name: object-member-property-event-and-operator-lowering
description: Lower constructors, fields, properties, indexers, events, extensions, overloaded operators, initializers, prototypes, and inheritance. Use for object/member operations and dispatch semantics.
---
# Object, Member, Property, Event, and Operator Lowering
Read `../references/lowering-v1.md`. Classify field/property/index/method/extension/dynamic access and preserve getter/setter visibility, effects, init-only/readonly behavior, index missing/slice/range/negative-index semantics, event lifecycle/order/context and operator dispatch.

Keep constructor and initializer assignment order. Do not expose effectful properties as fields, reduce events to a single callback, assume indexers are pure, drop extension dispatch, or choose one multiple-inheritance base while discarding other behavior. Route prototype changes to the dynamic strategy.
