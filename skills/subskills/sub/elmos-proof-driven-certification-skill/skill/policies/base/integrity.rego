package elmos.certification

import rego.v1

default allow := false

allow if {
  input.ticket.valid == true
  input.ticket.expired == false
  input.evidence.trusted_runner == true
  input.ticket.source_digest == input.evidence.source_digest
  input.ticket.case_catalog_digest == input.evidence.case_catalog_digest
  input.ticket.runner_profile_digest == input.evidence.runner_profile_digest
  input.ticket.policy_digest == input.evidence.policy_digest
  input.evidence.required_steps_complete == true
  input.evidence.tests.executed >= input.policy.minimum_tests
  input.evidence.tests.failed == 0
  input.evidence.reports_complete == true
  input.evidence.artifacts_valid == true
  input.evidence.infrastructure_failure == false
}

denial_reasons contains "TICKET_INVALID" if {
  input.ticket.valid != true
}

denial_reasons contains "TICKET_EXPIRED" if {
  input.ticket.expired == true
}

denial_reasons contains "UNTRUSTED_RUNNER" if {
  input.evidence.trusted_runner != true
}

denial_reasons contains "SOURCE_DIGEST_MISMATCH" if {
  input.ticket.source_digest != input.evidence.source_digest
}

denial_reasons contains "CASE_CATALOG_MISMATCH" if {
  input.ticket.case_catalog_digest != input.evidence.case_catalog_digest
}

denial_reasons contains "RUNNER_PROFILE_MISMATCH" if {
  input.ticket.runner_profile_digest != input.evidence.runner_profile_digest
}

denial_reasons contains "POLICY_DIGEST_MISMATCH" if {
  input.ticket.policy_digest != input.evidence.policy_digest
}

denial_reasons contains "REQUIRED_STEP_NOT_EXECUTED" if {
  input.evidence.required_steps_complete != true
}

denial_reasons contains "ZERO_TEST_EXECUTION" if {
  input.policy.minimum_tests > 0
  input.evidence.tests.executed == 0
}

denial_reasons contains "MINIMUM_TEST_COUNT_NOT_MET" if {
  input.evidence.tests.executed < input.policy.minimum_tests
}

denial_reasons contains "TEST_FAILURE" if {
  input.evidence.tests.failed > 0
}

denial_reasons contains "REPORT_MISSING" if {
  input.evidence.reports_complete != true
}

denial_reasons contains "ARTIFACT_DIGEST_MISMATCH" if {
  input.evidence.artifacts_valid != true
}

denial_reasons contains "INFRASTRUCTURE_FAILURE" if {
  input.evidence.infrastructure_failure == true
}

decision := {
  "allow": allow,
  "status": status,
  "reason_codes": denial_reasons,
}

status := "PASS" if allow
status := "DENY" if not allow
