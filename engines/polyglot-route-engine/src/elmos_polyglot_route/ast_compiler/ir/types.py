"""High-Fidelity Universal Type Lattice and Algebraic Type System.

Provides formal subtyping, variance calculation, least common supertype (LCA),
greatest lower bound (GLB), generic substitution, and coercion analysis across 15 languages.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import PrimitiveKind, UniversalType


class Variance(str, Enum):
    INVARIANT = "invariant"        # T = T
    COVARIANT = "covariant"        # +T (sub <: super implies F[sub] <: F[super])
    CONTRAVARIANT = "contravariant"# -T (sub <: super implies F[super] <: F[sub])
    BIVARIANT = "bivariant"        # both covariant and contravariant


class ExtendedTypeKind(str, Enum):
    PRIMITIVE = "primitive"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    RECORD = "record"
    ENUM = "enum"
    VARIANT = "variant"
    LIST = "list"
    MAP = "map"
    SET = "set"
    TUPLE = "tuple"
    OPTIONAL = "optional"
    RESULT = "result"
    POINTER = "pointer"
    FUNCTION = "function"
    GENERIC_PARAM = "generic_param"
    UNION = "union"
    INTERSECTION = "intersection"
    ANY = "any"
    NEVER = "never"


@dataclass
class GenericParam:
    name: str
    variance: Variance = Variance.INVARIANT
    upper_bounds: list[UniversalType] = field(default_factory=list)
    lower_bounds: list[UniversalType] = field(default_factory=list)


@dataclass
class FunctionSignature:
    param_types: list[UniversalType] = field(default_factory=list)
    return_type: UniversalType = field(default_factory=UniversalType.void)
    is_async: bool = False
    throws_types: list[UniversalType] = field(default_factory=list)


class TypeLattice:
    """Formal Type Lattice for cross-language semantic subtyping and unification."""

    _SIGNED_INT_WIDENING = ["i8", "i16", "i32", "i64"]
    _UNSIGNED_INT_WIDENING = ["u8", "u16", "u32", "u64"]
    _FLOAT_WIDENING = ["f32", "f64"]

    @classmethod
    def is_subtype_of(
        cls,
        sub: UniversalType,
        super_: UniversalType,
        class_hierarchy: Optional[Dict[str, List[str]]] = None
    ) -> bool:
        """Determines if sub is a subtype of super_ (sub <: super_)."""
        if sub == super_:
            return True

        sub_kind = getattr(sub, "kind", "primitive")
        sup_kind = getattr(super_, "kind", "primitive")
        sub_name = getattr(sub, "name", "")
        sup_name = getattr(super_, "name", "")

        # 1. Top and Bottom elements
        if sup_kind == ExtendedTypeKind.ANY.value or sup_name == "any":
            return True
        if sub_kind == ExtendedTypeKind.NEVER.value or sub_name == "never":
            return True

        # 2. Nullability constraint: non-nullable is subtype of nullable
        if sub.is_nullable and not super_.is_nullable:
            return False
        if not sub.is_nullable and super_.is_nullable:
            sub_copy = copy.deepcopy(sub)
            sub_copy.is_nullable = True
            if cls.is_subtype_of(sub_copy, super_, class_hierarchy):
                return True

        # 3. Numeric widening hierarchies
        if sub_kind == "primitive" and sup_kind == "primitive":
            if sub_name in cls._SIGNED_INT_WIDENING and sup_name in cls._SIGNED_INT_WIDENING:
                sub_idx = cls._SIGNED_INT_WIDENING.index(sub_name)
                sup_idx = cls._SIGNED_INT_WIDENING.index(sup_name)
                return sub_idx <= sup_idx

            if sub_name in cls._UNSIGNED_INT_WIDENING and sup_name in cls._UNSIGNED_INT_WIDENING:
                sub_idx = cls._UNSIGNED_INT_WIDENING.index(sub_name)
                sup_idx = cls._UNSIGNED_INT_WIDENING.index(sup_name)
                return sub_idx <= sup_idx

            if sub_name in cls._FLOAT_WIDENING and sup_name in cls._FLOAT_WIDENING:
                sub_idx = cls._FLOAT_WIDENING.index(sub_name)
                sup_idx = cls._FLOAT_WIDENING.index(sup_name)
                return sub_idx <= sup_idx

            # Integer widening into float
            if sub_name in ("i8", "i16", "i32") and sup_name == "f64":
                return True
            if sub_name in ("u8", "u16") and sup_name in ("f32", "f64"):
                return True

        # 4. Optional / Nullable lifting
        if sup_kind == "optional":
            if sub_kind == "optional":
                if sub.element_type and super_.element_type:
                    return cls.is_subtype_of(sub.element_type, super_.element_type, class_hierarchy)
            elif sub.element_type is None:
                if super_.element_type:
                    return cls.is_subtype_of(sub, super_.element_type, class_hierarchy)

        # 5. Generic collections with variance
        if sub_kind == sup_kind and sub_kind in ("list", "set"):
            if sub.element_type and super_.element_type:
                return cls.is_subtype_of(sub.element_type, super_.element_type, class_hierarchy)

        if sub_kind == sup_kind and sub_kind == "map":
            if sub.key_type and super_.key_type and sub.value_type and super_.value_type:
                key_match = sub.key_type == super_.key_type
                val_match = cls.is_subtype_of(sub.value_type, super_.value_type, class_hierarchy)
                return key_match and val_match

        # 6. Result<T, E> subtyping
        if sub_kind == sup_kind and sub_kind == "result":
            ok_sub = cls.is_subtype_of(sub.element_type, super_.element_type, class_hierarchy) if sub.element_type and super_.element_type else True
            err_sub = cls.is_subtype_of(sub.value_type, super_.value_type, class_hierarchy) if sub.value_type and super_.value_type else True
            return ok_sub and err_sub

        # 7. Pointer subtyping: unique_ptr <: raw_ptr, shared_ptr <: shared_ptr
        if sub_kind == "pointer" and sup_kind == "pointer":
            elem_match = True
            if sub.element_type and super_.element_type:
                elem_match = cls.is_subtype_of(sub.element_type, super_.element_type, class_hierarchy)
            if not elem_match:
                return False
            if sub.pointer_kind == "unique" and super_.pointer_kind == "raw":
                return True
            return sub.pointer_kind == super_.pointer_kind

        # 8. Class / Interface hierarchy
        if class_hierarchy and sub_name and sup_name:
            ancestors = class_hierarchy.get(sub_name, [])
            if sup_name in ancestors:
                return True
            for anc in ancestors:
                if cls.is_subtype_of(UniversalType.custom(anc), super_, class_hierarchy):
                    return True

        return False

    @classmethod
    def compute_lca(
        cls,
        t1: UniversalType,
        t2: UniversalType,
        class_hierarchy: Optional[Dict[str, List[str]]] = None
    ) -> UniversalType:
        """Computes Least Common Supertype (Join / LCA) in the type lattice."""
        if t1 == t2:
            return copy.deepcopy(t1)

        if getattr(t1, "name", "") == "never":
            return copy.deepcopy(t2)
        if getattr(t2, "name", "") == "never":
            return copy.deepcopy(t1)

        if getattr(t1, "name", "") == "any" or getattr(t2, "name", "") == "any":
            return UniversalType(kind="primitive", name="any")

        res_nullable = t1.is_nullable or t2.is_nullable
        n1 = getattr(t1, "name", "")
        n2 = getattr(t2, "name", "")

        if t1.kind == "primitive" and t2.kind == "primitive":
            if n1 in cls._SIGNED_INT_WIDENING and n2 in cls._SIGNED_INT_WIDENING:
                max_idx = max(cls._SIGNED_INT_WIDENING.index(n1), cls._SIGNED_INT_WIDENING.index(n2))
                return UniversalType.primitive(cls._SIGNED_INT_WIDENING[max_idx])
            if (n1 in cls._SIGNED_INT_WIDENING and n2 in cls._FLOAT_WIDENING) or (n2 in cls._SIGNED_INT_WIDENING and n1 in cls._FLOAT_WIDENING):
                return UniversalType.float64()
            if n1 in cls._FLOAT_WIDENING and n2 in cls._FLOAT_WIDENING:
                max_idx = max(cls._FLOAT_WIDENING.index(n1), cls._FLOAT_WIDENING.index(n2))
                return UniversalType.primitive(cls._FLOAT_WIDENING[max_idx])

        if t1.kind == t2.kind and t1.kind == "list":
            if t1.element_type and t2.element_type:
                elem_lca = cls.compute_lca(t1.element_type, t2.element_type, class_hierarchy)
                res = UniversalType.list_of(elem_lca)
                res.is_nullable = res_nullable
                return res

        if cls.is_subtype_of(t1, t2, class_hierarchy):
            res = copy.deepcopy(t2)
            res.is_nullable = res_nullable
            return res
        if cls.is_subtype_of(t2, t1, class_hierarchy):
            res = copy.deepcopy(t1)
            res.is_nullable = res_nullable
            return res

        if class_hierarchy and n1 and n2:
            a1 = class_hierarchy.get(n1, [])
            a2 = set(class_hierarchy.get(n2, []))
            for candidate in a1:
                if candidate in a2:
                    res = UniversalType.custom(candidate)
                    res.is_nullable = res_nullable
                    return res

        res = UniversalType(kind="primitive", name="any")
        res.is_nullable = res_nullable
        return res

    @classmethod
    def compute_glb(
        cls,
        t1: UniversalType,
        t2: UniversalType,
        class_hierarchy: Optional[Dict[str, List[str]]] = None
    ) -> UniversalType:
        """Computes Greatest Lower Bound (Meet / GLB) in the type lattice."""
        if t1 == t2:
            return copy.deepcopy(t1)

        if getattr(t1, "name", "") == "any":
            return copy.deepcopy(t2)
        if getattr(t2, "name", "") == "any":
            return copy.deepcopy(t1)
        if getattr(t1, "name", "") == "never" or getattr(t2, "name", "") == "never":
            return UniversalType(kind="primitive", name="never")

        if cls.is_subtype_of(t1, t2, class_hierarchy):
            return copy.deepcopy(t1)
        if cls.is_subtype_of(t2, t1, class_hierarchy):
            return copy.deepcopy(t2)

        return UniversalType(kind="primitive", name="never")

    @classmethod
    def substitute_generics(
        cls,
        target: UniversalType,
        mapping: Dict[str, UniversalType]
    ) -> UniversalType:
        """Recursively substitutes generic type variables with concrete types."""
        if target.kind == ExtendedTypeKind.GENERIC_PARAM.value or target.name in mapping:
            replacement = mapping.get(target.name)
            if replacement:
                new_t = copy.deepcopy(replacement)
                new_t.is_nullable = target.is_nullable or new_t.is_nullable
                return new_t

        res = copy.deepcopy(target)
        if res.element_type:
            res.element_type = cls.substitute_generics(res.element_type, mapping)
        if res.key_type:
            res.key_type = cls.substitute_generics(res.key_type, mapping)
        if res.value_type:
            res.value_type = cls.substitute_generics(res.value_type, mapping)
        if res.type_args:
            res.type_args = [cls.substitute_generics(arg, mapping) for arg in res.type_args]
        return res

    @classmethod
    def check_coercion(
        cls,
        from_type: UniversalType,
        to_type: UniversalType
    ) -> Tuple[bool, Optional[str]]:
        """Checks if from_type can be legally coerced to to_type and returns the strategy."""
        if from_type == to_type:
            return True, "identity"

        fn = getattr(from_type, "name", "")
        tn = getattr(to_type, "name", "")

        if fn in cls._SIGNED_INT_WIDENING and tn in cls._SIGNED_INT_WIDENING:
            if cls._SIGNED_INT_WIDENING.index(fn) < cls._SIGNED_INT_WIDENING.index(tn):
                return True, "implicit_widening"
            if cls._SIGNED_INT_WIDENING.index(fn) > cls._SIGNED_INT_WIDENING.index(tn):
                return True, "explicit_narrowing_cast"

        if to_type.kind == "optional" and from_type.kind != "optional":
            if to_type.element_type and (from_type == to_type.element_type or cls.is_subtype_of(from_type, to_type.element_type)):
                return True, "wrap_optional"

        if from_type.kind == "pointer" and to_type.kind == "pointer":
            if from_type.pointer_kind == "unique" and to_type.pointer_kind == "raw":
                return True, "get_raw_pointer"

        if fn in cls._SIGNED_INT_WIDENING and tn in cls._FLOAT_WIDENING:
            return True, "int_to_float_cast"

        if fn in cls._FLOAT_WIDENING and tn in cls._SIGNED_INT_WIDENING:
            return True, "float_to_int_truncation"

        if tn == "string":
            return True, "to_string_call"

        if cls.is_subtype_of(from_type, to_type):
            return True, "identity"

        return False, None
