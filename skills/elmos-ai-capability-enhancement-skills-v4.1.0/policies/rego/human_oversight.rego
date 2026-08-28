package elmos.ai_factory.human_oversight
import rego.v1
default allow := false
allow if { input.action_digest == input.approval.action_digest; input.approval.status == "approved"; input.approval.expires_at > input.now; count(input.distinct_qualified_approvers) >= input.required_approvals }
