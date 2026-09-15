package elmos.publication

default allow := false
allow if {
 input.result_fence_state == "CERTIFIED"
 input.actor_role == "PUBLICATION_BROKER"
 input.approval_valid == true
}
