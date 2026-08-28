package elmos.certification.qa_oracle_independence

import rego.v1

default allow := false

allow if {
  input.authoritative_oracle_registered
  input.candidate_producer_is_not_certifier
  input.critical_llm_only_oracles == 0
}

decision := {"allow": allow, "policy": "qa_oracle_independence", "failure_mode": "fail-closed"}
