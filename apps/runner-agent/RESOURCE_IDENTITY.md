# Lease-scoped Runner resource ownership

Execution workspaces use `JobWorkspace.create(workRoot, lease, uid, gid)`:
the path identity hashes the job ID, lease ID and attempt, never the credential.
An existing lease path is rejected, not erased or reused. The legacy job-ID
overloads remain for non-execution callers/tests; they cannot reclaim a path
whose ownership/liveness is unknown.

Each directory has a host-owned root inode, private owner token and held OS
file lock. Close checks both directory/marker identities and the token before
deleting. Startup reclamation requires a complete valid marker and an acquired
lock; missing, malformed, incomplete or currently locked markers are retained.
An in-process per-root claim prevents opening/closing a second descriptor from
inadvertently releasing an existing POSIX advisory lock. Different leases do
not share a global filesystem-operation mutex.

Containers additionally bind the phase and a fresh invocation nonce. Cleanup
requires the runtime's owned receipt, exact engine name and ownership labels,
then uses the inspected immutable container ID for kill/remove. Name rebinding
after inspect cannot redirect cleanup into another lease or phase. Unknown
targets are never accepted as arbitrary cleanup authority; failed inspection
or disappearance verification fails closed. Existing rootless, no-network,
read-only-root, capability, PID, CPU, memory and swap restrictions remain.

## Mixed versions and recovery

This is **not transparent mixed-version compatibility**. Old binaries have a
sweeper that does not understand the new markers/locks and may delete active
new-version directories. Drain old agents first and deploy the new version
with a separate `workRoot`. Rollback likewise requires draining the new agents
and an independently owned old-version root. Never run old/new sweepers on a
shared root. Retained unmarked/incomplete directories require trusted operator
reconciliation; they are not automatically declared garbage.

Before engine spawn, a durable, fsynced container intent is recorded outside all
workload mounts in `workRoot/.elmos-container-intents/<workspace>/`. Containers
are not auto-removed: stopped metadata remains inspectable until the exact ID
is durably bound, explicitly killed/removed, and its absence verified. Only
then is the intent cleared. A missing name is not proof that a pending daemon
create has ended. Any unknown cleanup retains its intent and workspace, and
sticky-fences that runtime against new launches and lease claims. Other running
leases continue their own supervision and exact-ID cleanup. The owned-container
registry is bounded by the configured concurrency limit.

A new runtime seeing pending intents also drains without claiming. Neither
workspace close nor startup sweep treats JVM exit/lock release as evidence that
the daemon stopped. There is no automatic container adoption or recovery in
this change. A trusted host operator must independently reconcile engine IDs,
pending creates, and workspace identity before resolving retained state and
restarting admission; merely deleting an intent or rebooting the Runner is not
a recovery procedure. Old/new versions must still use separate drained roots.

## Local evidence

`ResourceIdentitySelfTest` uses real directories and additional JVMs to verify
that active leases survive both local and cross-process sweeping, and that a
JVM which exits without closing its workspace leaves a reclaimable known
orphan. It also checks duplicate lease refusal, stale close/new lease isolation,
replacement inode refusal, and preservation of unknown legacy state.
It separately checks that a pending intent survives JVM exit, blocks workspace
reclamation and cold-start launch/claim, and that unknown cleanup causes zero
subsequent claim endpoint calls and no business-failure report.

The stateful container-engine test checks lease/phase separation, unchanged
sandbox flags, rejected foreign labels, unknown cleanup targets and name
rebinding between inspection and removal. This is a deterministic engine
boundary test, not a real Docker/Podman runtime claim. `AgentSelfTest` includes
it; real-container validation still requires the explicitly configured pinned
test image and engine. Local results remain self-attested engineering evidence,
not independent verification, production SLO evidence or certification.
