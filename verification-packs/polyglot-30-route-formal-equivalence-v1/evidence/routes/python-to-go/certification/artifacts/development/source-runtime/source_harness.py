import json
import pricing
actual_0 = pricing.calculate(100, 20)
assert actual_0 == 120
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 0, "value": actual_0}, sort_keys=True, separators=(",", ":")))
actual_1 = pricing.calculate(-1, 5)
assert actual_1 == 0
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 1, "value": actual_1}, sort_keys=True, separators=(",", ":")))
actual_2 = pricing.calculate(7, -2)
assert actual_2 == 5
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 2, "value": actual_2}, sort_keys=True, separators=(",", ":")))
