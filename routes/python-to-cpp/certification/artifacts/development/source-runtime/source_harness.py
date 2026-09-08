import json
import math
import struct
import _elmos_source_module
expected_0 = 120
actual_0 = _elmos_source_module.calculate(100, 20)
assert type(actual_0) is int
assert actual_0 == expected_0
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 0, "value": actual_0}, sort_keys=True, separators=(",", ":")))
expected_1 = 0
actual_1 = _elmos_source_module.calculate(-1, 5)
assert type(actual_1) is int
assert actual_1 == expected_1
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 1, "value": actual_1}, sort_keys=True, separators=(",", ":")))
expected_2 = 5
actual_2 = _elmos_source_module.calculate(7, -2)
assert type(actual_2) is int
assert actual_2 == expected_2
print("ELMOS_OBSERVATION\tjson\t" + json.dumps({"case_id": 2, "value": actual_2}, sort_keys=True, separators=(",", ":")))
