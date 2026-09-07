---
name: used-api-surface-extractor
description: Extract the source repository's actual dependency API usage with symbols, calls, construction, annotations, reflection, and evidence locations. Use before candidate discovery.
---
# Used API Surface Extractor
Read `../references/dependency-migration-v1.md`. Join Batch 2 symbols/calls and Batch 3 UIR with dependency identities. Capture imports, referenced types, methods/functions, fields/constants, constructors, inheritance, annotations/decorators, extension methods, callbacks, exceptions, serialization models, configuration keys, CLI behavior, reflection/dynamic loading, native calls and test-only usage. Record source locations, counts, criticality and unresolved dynamic paths. Only call a dependency unused when analysis coverage is complete; otherwise emit `unknown`, never an empty-used-set claim.
