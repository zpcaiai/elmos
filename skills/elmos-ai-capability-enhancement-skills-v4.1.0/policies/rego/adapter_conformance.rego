package elmos.ai_project_factory.adapter_conformance
import rego.v1
default release_allowed := false
release_allowed if {
  input.exact_upstream_version != ""
  startswith(input.adapter_digest, "sha256:")
  input.native_manifest_load == "PASS"
  input.native_minimal == "PASS"
  input.native_representative == "PASS"
  input.negative_unsupported == "PASS"
  input.authority_deny == "PASS"
  input.evidence_binding == "PASS"
}
