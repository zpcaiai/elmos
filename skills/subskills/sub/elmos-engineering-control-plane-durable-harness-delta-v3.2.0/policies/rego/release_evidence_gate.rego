package elmos.release

default publish := false
publish if {
  every c in input.verification { c.status == "PASS" }
  input.exact_artifact_verified == true
}
