package elmos.ai_project_factory.secretless_egress
import rego.v1
default allow_network := false
default allow_secret := false
allow_network if {
  input.phase == "execution"
  input.destination in input.authority.allowed_egress
  input.purpose in input.authority.allowed_purposes
}
allow_secret if {
  input.secret_reference in input.authority.allowed_secret_references
  input.materialization == "brokered-short-lived"
  input.persisted == false
}
