# Source Absorption Map

This package independently implements architecture patterns; it does not copy upstream source code.

## Prior Elmos v3.1 baseline retained
Result interception/commit, per-step finalized ExecutionPlan, lossless PermissionProfile replay, invocation-scoped CapabilityLease, VerifiedSecurityContext, environment-owned authority, remote executor fencing, workspace lease, transport/version negotiation, signed Skill provenance, durable plugin events, typed external ingress and Subagent ExecutionSpec.

## Harness architecture deltas absorbed
- unfinished root-turn suspension / same execution ID recovery;
- host-owned internal sessions and root-user authorization semantics;
- executor/plugin lifecycle provenance;
- environment-owned network policy and typed browser/computer/network capabilities;
- capability inventory vs thread-scoped runtime connection state;
- unified ExecutionSource/lineage;
- typed ContextEnvelope and propagation invariants;
- subtree lifecycle closure;
- durable failed tool-call replay;
- interrupt lifecycle;
- durable timeline + typed artifacts;
- parent-authoritative child recovery;
- restricted internal-session inheritance;
- effect/action-granular approval.

## OpenClaw-inspired control-plane patterns absorbed
- trusted control plane vs replaceable/untrusted execution plane;
- exact-bound approvals and authority narrowing;
- native/vendor harnesses as replaceable runtimes;
- prepared worker/project snapshots;
- managed worktrees/result fencing;
- release evidence + exact published artifact verification;
- peer-to-agent binding;
- Skill learning only through proposal → evaluation → certification, never direct self-promotion.
