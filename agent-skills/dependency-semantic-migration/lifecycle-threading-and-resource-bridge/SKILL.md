---
name: lifecycle-threading-and-resource-bridge
description: Bridge initialization, shutdown, threading, async, cancellation, pools, files, sockets, processes, and native-resource ownership across dependency boundaries. Use for every nontrivial adapter or wrapper.
---
# Lifecycle Threading And Resource Bridge
Read `../references/dependency-migration-v1.md`. Specify creation, readiness, use, cancellation, timeout, disposal, restart and failure ordering; map event loops, executors, thread affinity, callbacks, backpressure and ownership of memory/files/sockets/connections/processes/native handles. Emit leak, race, deadlock and shutdown tests. Never block event loops accidentally, detach work without ownership, double-free or leak resources, swallow cancellation, or assume source and target lifecycle conventions match.
