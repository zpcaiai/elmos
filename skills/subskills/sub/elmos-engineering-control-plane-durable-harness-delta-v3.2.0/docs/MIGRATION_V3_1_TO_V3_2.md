# Migration v3.1 → v3.2

v3.2 extends rather than replaces v3.1 contracts.

- `Session` → add `RuntimeOwner`, `ExecutionSource`, `ContextEnvelope`, `ExecutionTimeline`.
- pause/resume → add nonterminal `SUSPENDED/HANDOFF_READY` and same-execution-id ownership transfer.
- Tool registry → split `CapabilityInventory` from `RuntimeConnectionState`.
- sandbox policy → compute `EffectivePolicy` intersection and enforce hard-deny monotonicity.
- approval → bind specific `ApprovalActionKind` and resource/plan digest.
- hook registry → typed lifecycle provenance and interrupt phase.
- result commit → add `RepositoryCheckpoint`, `ResultFence`, `ReconcileTransaction`.
- release → add exact artifact verification and four-state verification semantics.
- subagent → add `RuntimeOwner` recovery and `SessionInheritancePolicy`.
- plugin/adapter → add protocol/capability/approval/policy mapping conformance.
