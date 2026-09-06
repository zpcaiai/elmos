# Optional Go process adapter

The supported fleet lifecycle remains the Java Runner. The old top-level Go
agent prototype is **not** the deployed fleet protocol and is not promoted by
this change. Do not replace the Java container entrypoint with that prototype.

Build `go build -o bin/elmos-supervisor ./cmd/elmos-supervisor` on the exact
Linux/macOS target. Configure the **host-owned Java agent environment** with
`ELMOS_RUNNER_SUPERVISOR=/absolute/approved/path/elmos-supervisor`; never obtain
this setting or binary from a repository or job payload. Unset it to retain the
Java adapter. Invalid configured binaries fail closed. No default deployment,
image allowlist, credential or sandbox-policy change is made.

Java keeps its bounded lease poller, backoff, heartbeat fencing, credential
rotation, container policy and artifact authorization/publication. The Go
adapter supervises one already-authorized argv vector in a process group and
forwards byte streams with OS-pipe backpressure. It has no network client,
credentials, scheduler or extra job queue. The existing Java concurrency limit
continues to cap running supervisors and reserves capacity before claiming.

Both Java paths cap captured output at 1 Mi UTF-16 code units per stream.
Streaming callbacks receive at most 16 Ki code units per line; oversized lines
are replaced by an explicit marker, never parsed as truncated progress events.
Callbacks are synchronous, preserving backpressure. An unconsumed pipe is not
an unbounded in-memory log queue.

The Go adapter propagates exit codes, signals the process group on cancellation
and kills remaining ordinary descendants after its grace period. It is not an
OS sandbox: descendants that deliberately create another session and container
processes still require the existing container engine's authoritative cleanup.
SIGKILL of the supervisor itself cannot run a cleanup handler. Java retains
engine-level stop/kill/rm and lease fencing. Native/container deployment and
independent verification remain NOT_RUN.

Local checks:

```sh
go test -race ./...
go build -o bin/elmos-supervisor ./cmd/elmos-supervisor
mvn -q -o test
java -cp target/classes:target/test-classes io.elmos.runner.ProcessRunnerConcurrencyTest
java -cp target/classes:target/test-classes io.elmos.runner.ProcessRunnerConcurrencyTest /absolute/path/to/bin/elmos-supervisor
```
