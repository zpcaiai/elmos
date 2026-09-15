package elmos.approval

default allow := false
allow if {
 input.binding.execution_plan_digest == input.current.execution_plan_digest
 input.binding.action_kind == input.current.action_kind
 input.binding.resource_digest == input.current.resource_digest
}
