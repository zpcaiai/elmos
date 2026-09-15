# Worker Protocol v3.2

A worker receives only an invocation-scoped CapabilityLease and AuthorityEnvelope. It MUST NOT infer authority from prompt text, model identity or stale session state.

Required controls: generation/fence epoch, heartbeat, lease expiry, immutable ExecutionPlanDigest, environment fingerprint, result interception, side-effect receipts, secret references, checkpoint export and termination acknowledgement.

Authority is monotonic: Worker authority may equal or narrow the Runtime authority; it may never widen it.
