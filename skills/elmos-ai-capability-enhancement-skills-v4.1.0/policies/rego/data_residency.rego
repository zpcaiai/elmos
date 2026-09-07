package elmos.ai_project_factory.data_residency
import rego.v1
default provider_allowed := false
provider_allowed if {
  input.data_classification in input.provider.allowed_classifications
  every region in input.required_regions {
    region in input.provider.processing_regions
  }
  not input.zero_retention_required
}
provider_allowed if {
  input.data_classification in input.provider.allowed_classifications
  every region in input.required_regions {
    region in input.provider.processing_regions
  }
  input.zero_retention_required
  input.provider.zero_retention == true
}
