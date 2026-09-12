"""Unit and Integration Tests for Universal Type Lattice, CFG, DFG, and Ownership Models."""

from __future__ import annotations

import pytest

from elmos_polyglot_route.ast_compiler.ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    BasicBlock,
    CfgBuilder,
    CfgEdgeKind,
    ControlFlowGraph,
    DataFlowGraph,
    ExtendedTypeKind,
    ExprStmt,
    FieldAccessExpr,
    FunctionSignature,
    GenericParam,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    MethodCallExpr,
    OwnershipAnalyzer,
    OwnershipKind,
    PrimitiveKind,
    ReturnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    TypeLattice,
    UniversalClass,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalParam,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
    Variance,
    WhileStmt,
)


def test_type_lattice_numeric_widening():
    """Verify numeric widening subtyping lattice (i8 < i16 < i32 < i64, f32 < f64)."""
    t_i8 = UniversalType.primitive("i8")
    t_i16 = UniversalType.primitive("i16")
    t_i32 = UniversalType.primitive("i32")
    t_i64 = UniversalType.int64()
    t_f32 = UniversalType.primitive("f32")
    t_f64 = UniversalType.float64()

    assert TypeLattice.is_subtype_of(t_i8, t_i16) is True
    assert TypeLattice.is_subtype_of(t_i16, t_i32) is True
    assert TypeLattice.is_subtype_of(t_i32, t_i64) is True
    assert TypeLattice.is_subtype_of(t_i8, t_i64) is True

    # Reverse is false
    assert TypeLattice.is_subtype_of(t_i64, t_i32) is False
    assert TypeLattice.is_subtype_of(t_i32, t_i8) is False

    # Int into Float widening
    assert TypeLattice.is_subtype_of(t_i32, t_f64) is True
    assert TypeLattice.is_subtype_of(t_f32, t_f64) is True
    assert TypeLattice.is_subtype_of(t_f64, t_f32) is False


def test_type_lattice_top_and_bottom():
    """Verify Any as top (universal supertype) and Never as bottom (universal subtype)."""
    t_any = UniversalType(kind="primitive", name="any")
    t_never = UniversalType(kind="primitive", name="never")
    t_str = UniversalType.string_type()
    t_bool = UniversalType.boolean()

    assert TypeLattice.is_subtype_of(t_never, t_str) is True
    assert TypeLattice.is_subtype_of(t_never, t_bool) is True
    assert TypeLattice.is_subtype_of(t_str, t_any) is True
    assert TypeLattice.is_subtype_of(t_bool, t_any) is True

    assert TypeLattice.is_subtype_of(t_any, t_str) is False
    assert TypeLattice.is_subtype_of(t_str, t_never) is False


def test_type_lattice_nullability_and_pointer_decay():
    """Verify non-nullable <: nullable, and unique_ptr <: raw_ptr."""
    t_str_non_null = UniversalType.string_type()
    t_str_null = UniversalType.string_type()
    t_str_null.is_nullable = True

    assert TypeLattice.is_subtype_of(t_str_non_null, t_str_null) is True
    assert TypeLattice.is_subtype_of(t_str_null, t_str_non_null) is False

    t_unique = UniversalType.unique_ptr_of(t_str_non_null)
    t_raw = UniversalType(kind="pointer", name="raw_ptr", element_type=t_str_non_null, pointer_kind="raw")

    assert TypeLattice.is_subtype_of(t_unique, t_raw) is True


def test_type_lattice_class_hierarchy_and_lca():
    """Verify nominated subtyping and Least Common Supertype (Join)."""
    hierarchy = {
        "Dog": ["Animal", "Object"],
        "Cat": ["Animal", "Object"],
        "Animal": ["Object"],
        "Object": []
    }
    t_dog = UniversalType.custom("Dog")
    t_cat = UniversalType.custom("Cat")
    t_animal = UniversalType.custom("Animal")
    t_object = UniversalType.custom("Object")

    assert TypeLattice.is_subtype_of(t_dog, t_animal, hierarchy) is True
    assert TypeLattice.is_subtype_of(t_dog, t_object, hierarchy) is True
    assert TypeLattice.is_subtype_of(t_cat, t_animal, hierarchy) is True
    assert TypeLattice.is_subtype_of(t_dog, t_cat, hierarchy) is False

    # LCA
    lca_dog_cat = TypeLattice.compute_lca(t_dog, t_cat, hierarchy)
    assert lca_dog_cat.name == "Animal"

    # LCA of numeric types
    lca_num = TypeLattice.compute_lca(UniversalType.primitive("i32"), UniversalType.int64())
    assert lca_num.name == "i64"

    lca_float = TypeLattice.compute_lca(UniversalType.primitive("i32"), UniversalType.float64())
    assert lca_float.name == "f64"


def test_type_lattice_generic_substitution():
    """Verify deep generic substitution."""
    # List<T> with {T: i64} -> List<i64>
    t_t = UniversalType(kind=ExtendedTypeKind.GENERIC_PARAM.value, name="T")
    list_t = UniversalType.list_of(t_t)

    subst_list = TypeLattice.substitute_generics(list_t, {"T": UniversalType.int64()})
    assert subst_list.kind == "list"
    assert subst_list.element_type is not None
    assert subst_list.element_type.name == "i64"

    # Map<K, List<V>> with {K: string, V: Dog}
    t_k = UniversalType(kind=ExtendedTypeKind.GENERIC_PARAM.value, name="K")
    t_v = UniversalType(kind=ExtendedTypeKind.GENERIC_PARAM.value, name="V")
    map_t = UniversalType.map_of(t_k, UniversalType.list_of(t_v))

    subst_map = TypeLattice.substitute_generics(map_t, {
        "K": UniversalType.string_type(),
        "V": UniversalType.custom("Dog")
    })
    assert subst_map.kind == "map"
    assert subst_map.key_type.name == "string"
    assert subst_map.value_type.kind == "list"
    assert subst_map.value_type.element_type.name == "Dog"


def test_type_coercion_analysis():
    """Verify automatic coercion determination."""
    ok1, strat1 = TypeLattice.check_coercion(UniversalType.primitive("i32"), UniversalType.int64())
    assert ok1 is True
    assert strat1 == "implicit_widening"

    ok2, strat2 = TypeLattice.check_coercion(UniversalType.int64(), UniversalType.primitive("i32"))
    assert ok2 is True
    assert strat2 == "explicit_narrowing_cast"

    ok3, strat3 = TypeLattice.check_coercion(UniversalType.custom("Order"), UniversalType.string_type())
    assert ok3 is True
    assert strat3 == "to_string_call"

    ok4, strat4 = TypeLattice.check_coercion(UniversalType.int64(), UniversalType.optional_of(UniversalType.int64()))
    assert ok4 is True
    assert strat4 == "wrap_optional"


def test_cfg_builder_and_dominator_analysis():
    """Verify CFG generation from structured method with If/Else and dominance calculation."""
    # Method:
    # def process(flag: bool) -> int:
    #     x = 10
    #     if flag:
    #         x = 20
    #     else:
    #         x = 30
    #     return x
    method = UniversalMethod(
        name="process",
        params=[UniversalParam(name="flag", type_info=UniversalType.boolean())],
        return_type=UniversalType.int64(),
        body=[
            VarDeclStmt(name="x", type_info=UniversalType.int64(), initial_value=LiteralExpr(value=10, type_kind="int")),
            IfElseStmt(
                condition=IdentifierExpr(name="flag"),
                then_body=[AssignStmt(target=IdentifierExpr(name="x"), value=LiteralExpr(value=20, type_kind="int"))],
                else_body=[AssignStmt(target=IdentifierExpr(name="x"), value=LiteralExpr(value=30, type_kind="int"))]
            ),
            ReturnStmt(value=IdentifierExpr(name="x"))
        ]
    )

    cfg = CfgBuilder.build_from_method(method)
    assert len(cfg.blocks) >= 4  # entry, then, else, join, exit
    assert any(e.kind == CfgEdgeKind.TRUE_BRANCH for e in cfg.edges)
    assert any(e.kind == CfgEdgeKind.FALSE_BRANCH for e in cfg.edges)

    # Dominance test
    dom = cfg.compute_dominance()
    # Entry block must dominate every block
    for b_id in cfg.blocks:
        assert cfg.entry_id in dom[b_id]

    idom = cfg.compute_immediate_dominators()
    assert len(idom) > 0


def test_cfg_while_loop_detection():
    """Verify natural loop detection in CFG with while loop."""
    # def count_down(n: int) -> int:
    #     while n > 0:
    #         n = n - 1
    #     return n
    method = UniversalMethod(
        name="count_down",
        params=[UniversalParam(name="n", type_info=UniversalType.int64())],
        return_type=UniversalType.int64(),
        body=[
            WhileStmt(
                condition=BinaryExpr(left=IdentifierExpr("n"), op=BinaryOperator.GT, right=LiteralExpr(0, "int")),
                body=[
                    AssignStmt(
                        target=IdentifierExpr("n"),
                        value=BinaryExpr(left=IdentifierExpr("n"), op=BinaryOperator.SUB, right=LiteralExpr(1, "int"))
                    )
                ]
            ),
            ReturnStmt(value=IdentifierExpr("n"))
        ]
    )

    cfg = CfgBuilder.build_from_method(method)
    loops = cfg.find_natural_loops()
    assert len(loops) == 1
    loop = loops[0]
    assert loop["header"] is not None
    assert len(loop["body"]) >= 2


def test_dfg_liveness_and_purity_analysis():
    """Verify backward liveness calculation and function purity determination."""
    pure_method = UniversalMethod(
        name="compute_area",
        params=[
            UniversalParam("w", UniversalType.int64()),
            UniversalParam("h", UniversalType.int64())
        ],
        return_type=UniversalType.int64(),
        body=[
            VarDeclStmt("area", UniversalType.int64(), BinaryExpr(IdentifierExpr("w"), BinaryOperator.MUL, IdentifierExpr("h"))),
            ReturnStmt(IdentifierExpr("area"))
        ]
    )

    cfg_pure = CfgBuilder.build_from_method(pure_method)
    dfg_pure = DataFlowGraph(cfg_pure)
    is_pure, reasons = DataFlowGraph.is_pure_method(pure_method)
    assert is_pure is True
    assert len(reasons) == 0

    # Impure method
    impure_method = UniversalMethod(
        name="log_and_mutate",
        params=[],
        body=[
            ExprStmt(MethodCallExpr(target=None, method_name="print_log", args=[LiteralExpr("event", "string")])),
            AssignStmt(target=FieldAccessExpr(target=IdentifierExpr("this"), field_name="count"), value=LiteralExpr(1, "int"))
        ]
    )
    is_pure_imp, reasons_imp = DataFlowGraph.is_pure_method(impure_method)
    assert is_pure_imp is False
    assert len(reasons_imp) == 2


def test_ownership_analyzer_and_borrow_checker():
    """Verify affine type moves, use-after-move detection, and borrowing conflicts."""
    analyzer = OwnershipAnalyzer()

    analyzer.declare_variable("buffer", OwnershipKind.OWNED)
    analyzer.record_move("buffer", "stmt_1")

    # Second move or use should trigger violation
    analyzer.record_move("buffer", "stmt_2")
    assert len(analyzer.violations) == 1
    assert analyzer.violations[0].violation_type == "USE_AFTER_MOVE"

    # Borrow conflicts: mutable borrow while shared borrow is active
    analyzer2 = OwnershipAnalyzer()
    analyzer2.declare_variable("data", OwnershipKind.OWNED)
    analyzer2.record_shared_borrow("data", "stmt_1")
    analyzer2.record_mutable_borrow("data", "stmt_2")

    assert len(analyzer2.violations) == 1
    assert analyzer2.violations[0].violation_type == "ALIASING_CONFLICT"
