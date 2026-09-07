package elmos.ai_factory.delegated_identity
import rego.v1
default allow := false
allow if { input.workload_attested; input.credential.expires_at > input.now; input.delegated_scopes_subset }
violations contains "unattested-workload" if { not input.workload_attested }
