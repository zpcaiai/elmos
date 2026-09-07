package elmos.autonomy.release

default allow := false

allow {
  input.all_mandatory_gates_pass == true
  input.no_open_p0_p1 == true
  input.rollback_ready == true
  input.deployment_health == true
  input.artifact_integrity == true
  input.independent_approval == true
  input.deployment_evidence == true
}
