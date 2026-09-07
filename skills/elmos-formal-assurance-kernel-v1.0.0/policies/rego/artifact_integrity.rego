package elmos.formal.artifact_integrity
import rego.v1

valid_sha256(s) if {
  regex.match("^[a-f0-9]{64}$", s)
}

deny contains "artifact sha256 is invalid" if {
  not valid_sha256(input.artifact.ref.sha256)
}

deny contains "proof artifact must be immutable" if {
  input.artifact.immutable != true
}

deny contains "restricted artifact must be encrypted" if {
  input.classification == "restricted"
  not input.artifact.ref.encryptionKeyRef
}

allow if {
  count(deny) == 0
}
