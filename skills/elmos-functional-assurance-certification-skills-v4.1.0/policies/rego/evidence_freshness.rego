package elmos.ai_project_factory.evidence_freshness
import rego.v1
default valid := false
valid if {
  input.evidence.revision_set_id == input.claim.revision_set_id
  input.evidence.policy_digest == input.claim.policy_digest
  input.evidence.adapter_digest == input.claim.adapter_digest
  input.evidence.revoked == false
  input.drift_affects_claim == false
}
