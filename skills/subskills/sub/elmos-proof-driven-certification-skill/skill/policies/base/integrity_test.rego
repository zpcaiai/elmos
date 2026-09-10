package elmos.certification_test

import rego.v1
import data.elmos.certification

valid_input := {
  "ticket": {
    "valid": true,
    "expired": false,
    "source_digest": "sha256:S",
    "case_catalog_digest": "sha256:C",
    "runner_profile_digest": "sha256:R",
    "policy_digest": "sha256:P",
  },
  "evidence": {
    "trusted_runner": true,
    "source_digest": "sha256:S",
    "case_catalog_digest": "sha256:C",
    "runner_profile_digest": "sha256:R",
    "policy_digest": "sha256:P",
    "required_steps_complete": true,
    "tests": {"executed": 25, "failed": 0},
    "reports_complete": true,
    "artifacts_valid": true,
    "infrastructure_failure": false,
  },
  "policy": {"minimum_tests": 20},
}

test_valid_input_allows if {
  certification.allow with input as valid_input
}

test_zero_tests_denies if {
  x := object.union(valid_input, {
    "evidence": object.union(valid_input.evidence, {"tests": {"executed": 0, "failed": 0}})
  })
  not certification.allow with input as x
}

test_source_mismatch_denies if {
  x := object.union(valid_input, {
    "evidence": object.union(valid_input.evidence, {"source_digest": "sha256:OTHER"})
  })
  not certification.allow with input as x
}

test_infrastructure_failure_denies if {
  x := object.union(valid_input, {
    "evidence": object.union(valid_input.evidence, {"infrastructure_failure": true})
  })
  not certification.allow with input as x
}

test_missing_report_denies if {
  x := object.union(valid_input, {
    "evidence": object.union(valid_input.evidence, {"reports_complete": false})
  })
  not certification.allow with input as x
}
