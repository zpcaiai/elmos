package elmos.formal.tenant_isolation_test
import rego.v1
import data.elmos.formal.tenant_isolation

test_cross_tenant_is_denied if {
  result := tenant_isolation.deny with input as {
    "request":{"tenantId":"a","accountId":"1","isPlatformAuditor":false},
    "resource":{"tenantId":"b","accountId":"1","publicReusable":false},
    "operation":"READ"
  }
  count(result) >= 1
}
