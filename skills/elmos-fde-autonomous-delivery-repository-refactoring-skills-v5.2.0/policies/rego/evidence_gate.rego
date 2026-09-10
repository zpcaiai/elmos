package elmos.fde.evidence_gate
default allow := false
blockers := {x | x := input.items[_]; x.status in {"unknown", "unsupported", "stale", "failed"}; x.material == true}
allow if {
  count(blockers) == 0
  input.producer_independent == true
  input.level in {"E0", "E1", "E2", "E3"}
}
