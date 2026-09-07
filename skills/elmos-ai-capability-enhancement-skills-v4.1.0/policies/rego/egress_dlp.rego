package elmos.ai_factory.v4.egress_dlp
import rego.v1

default allow := false

allow if {
  input.tenant_id != ""
  input.revision_set_id != ""
  input.authority_resolved
  input.critical_unknown == 0
  input.critical_refuted == 0
  input.side_effects_settled
  input.policy_specific_pass
}

violations contains "authority-unresolved" if { not input.authority_resolved }
violations contains "critical-unknown" if { input.critical_unknown > 0 }
violations contains "critical-refuted" if { input.critical_refuted > 0 }
violations contains "side-effects-unsettled" if { not input.side_effects_settled }
violations contains "policy-specific-failure" if { not input.policy_specific_pass }

# Intent: deny unapproved destination, payload class or data-flow path.
