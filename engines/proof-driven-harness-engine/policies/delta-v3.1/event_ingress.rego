package elmos.v3delta.event_ingress

default allow_replay := false
allow_replay if {
  input.event.registered
  input.event.schema_valid
  input.event.semantics == "REQUIRED_STATE"
  input.upgrader_available
}
allow_replay if {
  input.event.registered
  input.event.schema_valid
  input.event.semantics == "OPTIONAL_OBSERVATION"
}
