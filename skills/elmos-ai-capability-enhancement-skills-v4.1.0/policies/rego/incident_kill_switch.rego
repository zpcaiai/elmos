package elmos.ai_factory.incident_kill_switch
import rego.v1
default execute := false
execute if { not input.target_disabled; not input.tenant_disabled; not input.global_disabled; input.fencing_current }
violations contains "kill-switch-active" if { input.target_disabled or input.tenant_disabled or input.global_disabled }
