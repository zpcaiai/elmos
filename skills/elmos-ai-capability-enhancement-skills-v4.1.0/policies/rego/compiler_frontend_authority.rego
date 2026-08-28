package elmos.certification.compiler_frontend_authority

import rego.v1

default allow := false

allow if {
  input.compiler_native
  input.frontend_conformance_passed
  input.tool_digest_pinned
}

decision := {"allow": allow, "policy": "compiler_frontend_authority", "failure_mode": "fail-closed"}
