package elmos.ai_factory.content_provenance
import rego.v1
default publish := false
publish if { input.required_visible_label_present; input.required_machine_mark_present; input.interaction_disclosure_present; input.provenance_bound }
