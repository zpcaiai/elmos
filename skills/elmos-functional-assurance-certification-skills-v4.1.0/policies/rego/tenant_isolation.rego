package elmos.ai_project_factory.tenant_isolation
import rego.v1
default allow := false
allow if {
  input.subject.tenant_id == input.resource.tenant_id
  input.resource.namespace == sprintf("%s:%s", [input.subject.tenant_id, input.subject.project_id])
}
