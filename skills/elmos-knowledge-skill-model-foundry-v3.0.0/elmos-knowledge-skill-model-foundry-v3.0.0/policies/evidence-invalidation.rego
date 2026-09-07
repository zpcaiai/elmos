package elmos.evidence_invalidation

default invalidate := false

invalidate if { input.model_hash_changed }
invalidate if { input.adapter_hash_changed }
invalidate if { input.skill_hash_changed }
invalidate if { input.knowledge_snapshot_changed; input.claim_depends_on_knowledge }
invalidate if { input.toolchain_hash_changed; input.claim_depends_on_toolchain }
invalidate if { input.environment_drift_exceeds_policy }
