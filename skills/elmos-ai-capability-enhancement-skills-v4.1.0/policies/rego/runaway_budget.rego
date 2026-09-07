package elmos.ai_factory.runaway_budget
import rego.v1
default continue_run := false
continue_run if { every k, v in input.consumed { v <= input.limits[k] }; not input.loop_detected; not input.fallback_cascade }
violations contains "budget-exhausted" if { some k; input.consumed[k] > input.limits[k] }
