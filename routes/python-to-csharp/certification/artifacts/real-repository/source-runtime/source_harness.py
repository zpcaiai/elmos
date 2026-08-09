import json
import difference
actual_0 = difference.difference(20, 7)
assert actual_0 == 13
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 0, "value": actual_0}, sort_keys=True, separators=(",", ":")))
actual_1 = difference.difference(3, 8)
assert actual_1 == 0
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 1, "value": actual_1}, sort_keys=True, separators=(",", ":")))
actual_2 = difference.difference(4, 4)
assert actual_2 == 0
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 2, "value": actual_2}, sort_keys=True, separators=(",", ":")))
