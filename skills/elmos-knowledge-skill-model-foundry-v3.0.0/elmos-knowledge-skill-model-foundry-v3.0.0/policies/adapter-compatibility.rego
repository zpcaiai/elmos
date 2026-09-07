package elmos.adapter_compatibility

default compatible := false

compatible if {
  input.adapter_signed
  input.source_version_supported
  input.target_version_supported
  input.conformance_level >= input.required_level
  not input.revoked
}
