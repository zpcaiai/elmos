package elmos.ai_factory.mcp_enterprise_authorization
import rego.v1
default allow := false
allow if { input.token.active; input.token.audience == input.resource; every s in input.required_scopes { s in input.token.scopes } }
violations contains "wrong-audience" if { input.token.audience != input.resource }
