package elmos.session

default allow := false
allow if {
 input.role in {"REVIEWER","VERIFIER","GUARDIAN"}
 input.inherit_user_instructions == false
 input.inherit_extensions == false
 input.inherit_mcp_servers == false
}
