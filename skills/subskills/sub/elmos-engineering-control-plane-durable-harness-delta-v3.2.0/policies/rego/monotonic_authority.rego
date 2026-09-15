package elmos.authority

default allow := false

# Reference policy: effective capabilities must be a subset of granted capabilities.
allow if {
  every c in input.effective_capabilities { c in input.granted_capabilities }
  every d in input.hard_denies { not d in input.effective_capabilities }
}
