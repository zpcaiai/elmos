package elmos.v3delta.permission_replay

default allow_resume := false
allow_resume if {
  input.mapping == "EXACT"
  input.canonical_profile_hash == input.restored_profile_hash
  not input.authority_widening
}
