package elmos.release_deploy

default allow := false

allow if {
  input.release.certification.deploy_allowed == true
  input.release.certification.level in {"E2", "E3", "E4", "E5"}
  input.ticket.status == "APPROVED"
  input.ticket.tenant_id == input.target.tenant_id
  input.ticket.release_id == input.release.release_id
  input.ticket.target_id == input.target.target_id
  not input.ticket.expired
  every digest in input.ticket.artifact_digests {
    digest in {a.digest | a := input.release.artifacts[_]}
  }
  migration_allowed
}

migration_allowed if {
  input.environment != "prod"
}

migration_allowed if {
  input.environment == "prod"
  input.migration.risk == "SAFE_EXPAND"
}

migration_allowed if {
  input.environment == "prod"
  input.migration.risk == "CONDITIONAL"
  input.ticket.migration_policy == "approved_conditional"
  input.migration.backup_evidence_present == true
}

# DESTRUCTIVE migrations require a separate specialized policy/ticket and are
# intentionally not allowed by this default gate.
