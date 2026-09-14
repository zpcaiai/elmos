package elmos.release_deploy_test

import rego.v1
import data.elmos.release_deploy.allow

fixture := {
    "host": {"schema":"rd.policy-input.v1", "ticket_signature_verified":true,
        "certification_signature_verified":true, "policy_signature_verified":true,
        "revocation_checked":true, "target_ownership_verified":true,
        "principal_scope":{"tenant":"a"}, "now":10, "certified_release_digest":"release",
        "certification_evidence_digest":"evidence", "policy_digest":"policy",
        "previous_snapshot_verified":true, "stateful_services_external":true,
        "migration_manifest_verified":true},
    "plan":{"scope":{"tenant":"a"}, "release_digest":"release", "target_digest":"target",
        "policy_digest":"policy", "production":true, "rollback_required":true, "migration_risk":"NONE"},
    "ticket":{"scope":{"tenant":"a"},"plan_digest":"plan","status":"APPROVED",
        "issued_at":1,"expires_at":20,"actor_id":"requester","approved_by":"reviewer"},
    "target":{"scope":{"tenant":"a"}},
    "release":{"scope":{"tenant":"a"},"evidence_digest":"evidence",
        "artifacts":[{"image_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profile":"python"}]},
    "plan_digest":"plan", "release_digest":"release", "target_digest":"target"
}

test_allowed if { allow with input as fixture }
test_no_input if { not allow with input as {} }
test_expired if { not allow with input as fixture with input.host.now as 20 }
test_cross_tenant if { not allow with input as fixture with input.ticket.scope as {"tenant":"b"} }
test_unverified_ticket if { not allow with input as fixture with input.host.ticket_signature_verified as false }
test_forged_certification if { not allow with input as fixture with input.host.certification_signature_verified as false }
test_self_approval if { not allow with input as fixture with input.ticket.approved_by as "requester" }
test_destructive_without_permit if { not allow with input as fixture with input.plan.migration_risk as "DESTRUCTIVE" }
test_unknown_migration if { not allow with input as fixture with input.plan.migration_risk as "UNKNOWN" }
test_local_db if { not allow with input as fixture with input.host.stateful_services_external as false }
test_wrong_plan if { not allow with input as fixture with input.ticket.plan_digest as "other" }
test_unpinned if { not allow with input as fixture with input.release.artifacts as [{"image_digest":"latest","profile":"python"}] }
