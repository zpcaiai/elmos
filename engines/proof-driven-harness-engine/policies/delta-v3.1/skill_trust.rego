package elmos.v3delta.skill_trust

default authorization_evidence := false

authorization_evidence if {
  input.provenance.verified
  input.provenance.trust_domain in {"USER", "ENTERPRISE"}
  input.path_within_canonical_root
  not input.symlink_escape
  input.digest_matches
  input.signature_valid
}
