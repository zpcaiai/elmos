package elmos.runtime

default admit := false
admit if { input.result == "SUPPORTED_EXACTLY" }
admit if { input.result == "SUPPORTED_WITH_NARROWER_SCOPE" }
