package elmos.formal.solver_execution
import rego.v1

deny contains "solver network must be denied" if {
  input.adapter.spec.security.network != "deny"
}

deny contains "solver must receive no secrets" if {
  input.adapter.spec.security.secrets != "none"
}

deny contains "production adapter image must be pinned by digest" if {
  input.environment == "PROD"
  not startswith(input.adapter.spec.execution.image, "sha256:")
}

deny contains "runAsNonRoot is required" if {
  input.adapter.spec.security.runAsNonRoot != true
}

deny contains "readOnlyRootFilesystem is required" if {
  input.adapter.spec.security.readOnlyRootFilesystem != true
}

allow if {
  count(deny) == 0
}
