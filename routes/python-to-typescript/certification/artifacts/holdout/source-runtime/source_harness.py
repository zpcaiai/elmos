import json
import clamp
actual_0 = clamp.clamp(20, 10)
assert actual_0 == 10
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 0, "value": actual_0}, sort_keys=True, separators=(",", ":")))
actual_1 = clamp.clamp(-2, 10)
assert actual_1 == 0
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 1, "value": actual_1}, sort_keys=True, separators=(",", ":")))
actual_2 = clamp.clamp(7, 10)
assert actual_2 == 7
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 2, "value": actual_2}, sort_keys=True, separators=(",", ":")))
