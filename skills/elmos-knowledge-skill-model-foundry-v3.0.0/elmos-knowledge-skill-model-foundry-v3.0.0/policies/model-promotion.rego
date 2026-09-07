package elmos.model_promotion

default promote := false

promote if {
  input.release.signature_valid
  input.release.rollback_target != ""
  input.evidence.level in {"E4", "E5"}
  input.eval.hard_gate_failures == 0
  input.security.critical_findings == 0
  input.data_lineage.complete
  input.skill_set.all_certified
  input.knowledge_snapshot.frozen
}
