package elmos.release_deploy

import rego.v1

# Input is assembled inside the authenticated host after cryptographic checks.
# Never expose this decision point to arbitrary client-provided authority facts.
default allow := false

allow if {
    input.host.schema == "rd.policy-input.v1"
    input.host.ticket_signature_verified == true
    input.host.certification_signature_verified == true
    input.host.policy_signature_verified == true
    input.host.revocation_checked == true
    input.host.target_ownership_verified == true
    input.host.principal_scope == input.plan.scope
    input.ticket.scope == input.plan.scope
    input.target.scope == input.plan.scope
    input.release.scope == input.plan.scope
    input.ticket.plan_digest == input.plan_digest
    input.ticket.status == "APPROVED"
    input.ticket.issued_at <= input.host.now
    input.host.now < input.ticket.expires_at
    input.release_digest == input.plan.release_digest
    input.target_digest == input.plan.target_digest
    input.host.certified_release_digest == input.release_digest
    input.host.certification_evidence_digest == input.release.evidence_digest
    input.host.policy_digest == input.plan.policy_digest
    count(input.release.artifacts) > 0
    every artifact in input.release.artifacts {
        regex.match("^sha256:[0-9a-f]{64}$", artifact.image_digest)
        artifact.profile in {"spring", "vue", "python", "dotnet"}
    }
    production_allowed
    migration_allowed
}

production_allowed if {
    input.plan.production == false
}

production_allowed if {
    input.plan.production == true
    input.plan.rollback_required == true
    input.host.previous_snapshot_verified == true
    input.ticket.actor_id != input.ticket.approved_by
    input.host.stateful_services_external == true
}

migration_allowed if {
    input.plan.migration_risk in {"NONE", "SAFE_EXPAND"}
    input.host.migration_manifest_verified == true
}

migration_allowed if {
    input.plan.migration_risk in {"CONDITIONAL", "DESTRUCTIVE"}
    input.host.migration_manifest_verified == true
    input.host.dedicated_migration_authorization_verified == true
    input.host.backup_evidence_verified == true
    input.host.restore_plan_verified == true
}
