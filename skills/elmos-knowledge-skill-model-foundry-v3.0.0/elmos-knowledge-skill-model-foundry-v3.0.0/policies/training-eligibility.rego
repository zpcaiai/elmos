package elmos.training

default allow := false

allow if {
  input.dataset.tier == "gold"
  input.rights.training_consent == "allow"
  input.rights.license_status == "cleared"
  input.security.secret_scan == "pass"
  input.security.pii_status == "redacted-or-not-present"
  input.tenant.scope in {"same-tenant", "global-authorized"}
  not input.revoked
  not input.benchmark_member
}

deny_reasons contains "training consent missing" if input.rights.training_consent != "allow"
deny_reasons contains "dataset is not gold" if input.dataset.tier != "gold"
deny_reasons contains "benchmark leakage risk" if input.benchmark_member
deny_reasons contains "revoked item" if input.revoked
