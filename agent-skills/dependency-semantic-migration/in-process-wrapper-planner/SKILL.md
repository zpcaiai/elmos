---
name: in-process-wrapper-planner
description: Plan same-process managed, native, embedded-runtime, or foreign-function wrappers with explicit ABI and lifecycle constraints. Use when process isolation is unnecessary and safe.
---
# In Process Wrapper Planner
Read `../references/dependency-migration-v1.md`. Choose wrapper mode from ABI stability, runtime coexistence, memory ownership, callbacks, exceptions, threading, GC/pinning, loading, platform assets and crash impact. Specify contracts, ownership, initialization/disposal, error propagation, concurrency and packaging. Never choose in-process wrapping when an unsafe native crash, incompatible runtimes, unbounded callbacks or unsupported platforms violate policy. Treat native binaries and embedded interpreters as governed dependencies.
