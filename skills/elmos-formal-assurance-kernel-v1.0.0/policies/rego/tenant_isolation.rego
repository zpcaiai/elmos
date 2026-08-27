package elmos.formal.tenant_isolation
import rego.v1

deny contains "tenant mismatch" if {
  input.request.tenantId != input.resource.tenantId
}

deny contains "account mismatch" if {
  input.request.accountId != input.resource.accountId
  input.request.isPlatformAuditor != true
}

deny contains "cross-tenant proof cache disabled" if {
  input.operation == "CACHE_READ"
  input.request.tenantId != input.resource.tenantId
  input.resource.publicReusable != true
}

allow if {
  count(deny) == 0
}
