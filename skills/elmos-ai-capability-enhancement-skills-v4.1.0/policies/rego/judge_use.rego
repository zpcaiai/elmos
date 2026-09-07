package elmos.ai_factory.judge_use
import rego.v1
default authoritative := false
allow_non_authoritative if { input.calibration_status in {"calibrated", "bounded"}; input.confidence >= input.minimum_confidence }
violations contains "self-certification" if { input.judge_model_fingerprint == input.candidate_model_fingerprint }
