package elmos.ai_factory.eval_data_governance
import rego.v1
default allow_use := false
allow_use if { input.lineage_complete; input.consent_valid; not input.expired; not input.holdout_exposed }
violations contains "holdout-exposed" if { input.holdout_exposed }
