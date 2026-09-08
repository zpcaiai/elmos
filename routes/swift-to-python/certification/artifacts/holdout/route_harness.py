import json
import math
import struct
import migrated
expected_0 = 10
actual_0 = migrated.clamp(20, 10)
assert type(actual_0) is int
assert actual_0 == expected_0
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 0, "value": actual_0}, sort_keys=True, separators=(",", ":")))
expected_1 = 0
actual_1 = migrated.clamp(-2, 10)
assert type(actual_1) is int
assert actual_1 == expected_1
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 1, "value": actual_1}, sort_keys=True, separators=(",", ":")))
expected_2 = 7
actual_2 = migrated.clamp(7, 10)
assert type(actual_2) is int
assert actual_2 == expected_2
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 2, "value": actual_2}, sort_keys=True, separators=(",", ":")))
