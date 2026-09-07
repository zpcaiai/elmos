package elmos.certification.flaky_test_honesty

import rego.v1

default allow := false

allow if {
  input.critical_flakes == 0
  input.quarantines_have_owner_expiry
  input.first_failure_preserved
}

decision := {"allow": allow, "policy": "flaky_test_honesty", "failure_mode": "fail-closed"}
