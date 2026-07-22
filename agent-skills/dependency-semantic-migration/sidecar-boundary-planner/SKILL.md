---
name: sidecar-boundary-planner
description: Plan a colocated sidecar boundary for isolated runtimes, native tools, protocol bridges, or separately managed dependencies. Use when lifecycle coupling is acceptable.
---
# Sidecar Boundary Planner
Read `../references/dependency-migration-v1.md`. Specify image/artifact identity, local protocol, ports/sockets, auth, resources, startup/readiness, restart policy, ordering, timeouts, cancellation, serialization, logs/metrics/traces, upgrades and cleanup. Model sidecar absent, slow, crashed, incompatible and partially ready states. Never rely on localhost as an authorization boundary, use mutable images, omit resource limits, or conceal an external runtime inside the target application package.
