"""Tests for the IR's canonical form and its refusals."""

import unittest

from j2p import uir
from j2p.uir import (
    Binary,
    ClassType,
    IntLiteral,
    Method,
    Module,
    Origin,
    Param,
    PrimitiveType,
    TypeDecl,
    UirError,
    UnknownType,
)

ORIGIN = Origin(file="T.java", line=1, column=1)


def _int(value: int) -> IntLiteral:
    return IntLiteral(origin=ORIGIN, type=uir.T_INT, value=value)


class CanonicalFormTest(unittest.TestCase):
    def test_digest_is_stable_across_equal_structures(self):
        a = Binary(origin=ORIGIN, type=uir.T_INT, op="+", left=_int(1), right=_int(2))
        b = Binary(origin=ORIGIN, type=uir.T_INT, op="+", left=_int(1), right=_int(2))
        self.assertEqual(uir.digest(a), uir.digest(b))

    def test_digest_changes_when_any_field_changes(self):
        a = Binary(origin=ORIGIN, type=uir.T_INT, op="+", left=_int(1), right=_int(2))
        b = Binary(origin=ORIGIN, type=uir.T_INT, op="-", left=_int(1), right=_int(2))
        c = Binary(origin=ORIGIN, type=uir.T_LONG, op="+", left=_int(1), right=_int(2))
        self.assertNotEqual(uir.digest(a), uir.digest(b))
        self.assertNotEqual(uir.digest(a), uir.digest(c))

    def test_operand_order_is_significant(self):
        a = Binary(origin=ORIGIN, type=uir.T_INT, op="-", left=_int(1), right=_int(2))
        b = Binary(origin=ORIGIN, type=uir.T_INT, op="-", left=_int(2), right=_int(1))
        self.assertNotEqual(uir.digest(a), uir.digest(b))

    def test_float_is_refused_in_canonical_form(self):
        with self.assertRaises(UirError) as ctx:
            uir.canonical_json({"value": 1.5})
        self.assertIn("float", str(ctx.exception))

    def test_set_is_refused_because_it_has_no_order(self):
        with self.assertRaises(UirError) as ctx:
            uir.canonical_json({"value": {1, 2}})
        self.assertIn("deterministic order", str(ctx.exception))

    def test_canonical_json_is_key_sorted(self):
        text = uir.canonical_json({"b": 1, "a": 2})
        self.assertEqual(text, '{"a":2,"b":1}')

    def test_insertion_order_does_not_change_the_digest(self):
        # Two dicts that are equal but were built in different orders must
        # produce the same content address, or the address is not an address.
        first = {"b": 1, "a": 2, "c": 3}
        second = {"c": 3, "a": 2, "b": 1}
        self.assertEqual(uir.canonical_json(first), uir.canonical_json(second))
        self.assertEqual(uir.digest(first), uir.digest(second))

    def test_node_kind_is_recorded(self):
        payload = uir.to_canonical(_int(3))
        self.assertEqual(payload["k"], "IntLiteral")


class NodeValidationTest(unittest.TestCase):
    def test_unknown_binary_operator_is_refused(self):
        with self.assertRaises(UirError):
            Binary(origin=ORIGIN, type=uir.T_INT, op="**", left=_int(1), right=_int(1))

    def test_unknown_primitive_is_refused(self):
        with self.assertRaises(UirError):
            PrimitiveType("number")

    def test_origin_must_be_one_based(self):
        with self.assertRaises(UirError):
            Origin(file="T.java", line=0, column=1)


class TraversalTest(unittest.TestCase):
    def _module(self) -> Module:
        method = Method(
            origin=ORIGIN,
            name="f",
            params=(Param(origin=ORIGIN, name="a", type=UnknownType("test")),),
            return_type=uir.T_INT,
            modifiers=("static",),
            body=None,
        )
        decl = TypeDecl(
            origin=ORIGIN,
            name="T",
            kind="class",
            modifiers=(),
            superclass=None,
            interfaces=(),
            fields=(),
            methods=(method,),
        )
        return Module(origin=ORIGIN, package=None, imports=(), types=(decl,))

    def test_unknown_types_are_countable(self):
        found = uir.unknown_types(self._module())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].reason, "test")

    def test_every_declaration_carries_an_origin(self):
        self.assertTrue(uir.origins(self._module()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
