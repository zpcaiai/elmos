# Honest Limitations

The reference implementation proves contract behavior only within its deterministic in-memory model. It does not prove real Rust/TypeScript provider adapters, OS-level capability revocation, distributed exactly-once delivery, PostgreSQL RLS, OPA policy execution, remote Executor replacement or customer repository behavior. Those require target-environment evidence and remain activation gates.
