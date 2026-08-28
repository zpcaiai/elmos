package elmos.ai_factory.agent_skill_supply_chain
import rego.v1
default allow := false
allow if { input.signature_status == "verified"; input.provenance_complete; input.permission_delta == [] }
violations contains "unverified-publisher" if { input.signature_status != "verified" }
violations contains "permission-expansion" if { count(input.permission_delta) > 0 }
