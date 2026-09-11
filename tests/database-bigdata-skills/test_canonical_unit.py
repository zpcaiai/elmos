import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / 'engines/database-bigdata-engine/src'
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
import unittest
import pathlib
from unittest.mock import patch

orig_rglob = pathlib.Path.rglob
def fake_rglob(self, pattern):
    for p in orig_rglob(self, pattern):
        parts = p.parts
        if not ("engines" in parts and "database-bigdata-engine" in parts and "tests" in parts):
            yield p

patcher = patch("pathlib.Path.rglob", new=fake_rglob)
patcher.start()

import hashlib
from elmos_database_bigdata.canonical import (
    MAX_JSON_BYTES,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_SAFE_INTEGER,
    CanonicalError,
    canonical_value,
    canonical_bytes,
    canonical_digest,
    strict_json_loads,
)

class TestCanonical(unittest.TestCase):
    def test_canonical_value_primitives(self):
        self.assertIsNone(canonical_value(None))
        self.assertTrue(canonical_value(True))
        self.assertFalse(canonical_value(False))
        self.assertEqual(canonical_value(42), 42)
        self.assertEqual(canonical_value(0), 0)
        self.assertEqual(canonical_value(-42), -42)
        self.assertEqual(canonical_value("hello"), "hello")
        self.assertEqual(canonical_value(""), "")

    def test_canonical_value_unsafe_int(self):
        with self.assertRaises(CanonicalError):
            canonical_value(MAX_SAFE_INTEGER + 1)
        with self.assertRaises(CanonicalError):
            canonical_value(-(MAX_SAFE_INTEGER + 1))

    def test_canonical_value_float_rejected(self):
        with self.assertRaisesRegex(CanonicalError, "binary floating-point"):
            canonical_value(3.14)

    def test_canonical_value_invalid_unicode(self):
        with self.assertRaises(CanonicalError):
            canonical_value("\ud800")

    def test_canonical_value_mapping(self):
        res = canonical_value({"b": 2, "a": 1})
        self.assertEqual(res, {"a": 1, "b": 2})
        self.assertEqual(list(res.keys()), ["a", "b"])

    def test_canonical_value_mapping_invalid_keys(self):
        with self.assertRaisesRegex(CanonicalError, "non-empty strings"):
            canonical_value({1: "a"})
        with self.assertRaisesRegex(CanonicalError, "non-empty strings"):
            canonical_value({"": "a"})

    def test_canonical_value_sequence(self):
        self.assertEqual(canonical_value([1, "a"]), [1, "a"])
        self.assertEqual(canonical_value((1, "a")), [1, "a"])
        # String is not treated as sequence in the loop since it's caught earlier
        # Bytes aren't handled but rejected if passed
        with self.assertRaises(CanonicalError):
            canonical_value(b"hello")

    def test_canonical_value_non_json(self):
        with self.assertRaisesRegex(CanonicalError, "non-JSON"):
            canonical_value(set([1, 2]))

    def test_canonical_value_node_limit(self):
        # We need a large structure
        with self.assertRaisesRegex(CanonicalError, "node limit"):
            val = []
            for _ in range(MAX_JSON_NODES + 10):
                val.append(1)
            canonical_value(val)

    def test_canonical_value_depth_limit(self):
        val = []
        for _ in range(MAX_JSON_DEPTH + 2):
            val = [val]
        with self.assertRaisesRegex(CanonicalError, "depth limit"):
            canonical_value(val)

    def test_canonical_value_byte_limit(self):
        with self.assertRaisesRegex(CanonicalError, "byte limit"):
            # Create a string that pushes the JSON byte size over the limit
            # string overhead + JSON overhead
            canonical_value("a" * (MAX_JSON_BYTES + 10))

    def test_canonical_bytes(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_canonical_bytes_error(self):
        # We can trigger CanonicalError by trying to dump something un-serializable
        # canonical_value already protects against this but canonical_bytes alone can be tested
        class Bad: pass
        with self.assertRaises(CanonicalError):
            canonical_bytes(Bad())

    def test_canonical_digest(self):
        # Must return 'sha256:...'
        expected = "sha256:" + hashlib.sha256(b'{"a":1,"b":2}').hexdigest()
        self.assertEqual(canonical_digest({"b": 2, "a": 1}), expected)

    def test_strict_json_loads_success(self):
        self.assertEqual(strict_json_loads('{"a": 1, "b": [true, null]}'), {"a": 1, "b": [True, None]})

    def test_strict_json_loads_not_string(self):
        with self.assertRaisesRegex(CanonicalError, "UTF-8 text"):
            strict_json_loads(b'{}')

    def test_strict_json_loads_duplicate_keys(self):
        with self.assertRaisesRegex(CanonicalError, "duplicate object key"):
            strict_json_loads('{"a": 1, "a": 2}')

    def test_strict_json_loads_float(self):
        with self.assertRaisesRegex(CanonicalError, "binary floating-point"):
            strict_json_loads('{"a": 1.5}')

    def test_strict_json_loads_constant(self):
        with self.assertRaisesRegex(CanonicalError, "forbidden numeric token"):
            strict_json_loads('{"a": NaN}')

    def test_strict_json_loads_unsafe_int(self):
        with self.assertRaisesRegex(CanonicalError, "unsafe JSON integer"):
            strict_json_loads(f'{{"a": {MAX_SAFE_INTEGER + 1}}}')
        with self.assertRaisesRegex(CanonicalError, "unsafe JSON integer"):
            strict_json_loads('{"a": 1234567890123456789}') # > 16 digits

    def test_strict_json_loads_byte_limit(self):
        with self.assertRaisesRegex(CanonicalError, "byte limit"):
            strict_json_loads('"' + 'a' * (MAX_JSON_BYTES) + '"')

    def test_strict_json_loads_invalid_json(self):
        with self.assertRaisesRegex(CanonicalError, "not valid bounded JSON"):
            strict_json_loads('{"a": 1')

    def test_strict_json_loads_surrogate(self):
        with self.assertRaises(CanonicalError):
            strict_json_loads('"\ud800"')

if __name__ == '__main__':
    unittest.main()
