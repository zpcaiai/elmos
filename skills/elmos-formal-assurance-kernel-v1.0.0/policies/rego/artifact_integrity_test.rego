package elmos.formal.artifact_integrity_test
import rego.v1
import data.elmos.formal.artifact_integrity

test_mutable_is_denied if {
  result := artifact_integrity.deny with input as {
    "classification":"confidential",
    "artifact":{"immutable":false,"ref":{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
  }
  count(result) == 1
}
