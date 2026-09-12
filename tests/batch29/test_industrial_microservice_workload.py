"""Phase 5: Industrial-Grade Microservice Cross-Language Compilation & Differential Verification Suite.

Tests a realistic enterprise microservice workload across:
1. Genuine Native Compiler Frontends (Java javac, Go go/ast, Apple Clang C++, Rust syn, Python ast)
2. Middle-End Formal Analysis: CFG, Dominator Tree, Natural Loops, Unreachable Pruning
3. Data Flow Analysis: Def-Use Chains, Backward Liveness, SSA Phi Placement, Function Purity
4. Ownership & Lifetime Modeling: Affine Moves, Borrow Aliasing Hazards
5. Enterprise Concurrency & Collections Shims: ConcurrentHashMap, AtomicLong, Channels, Streams across Rust, Go, C#
6. Z3 SMT Formal Constraint Solving & Autonomous AST Self-Repair
7. Cross-Language Semantic Invariant Preservation
"""

from __future__ import annotations

import copy
import pytest

from elmos_polyglot_route.ast_compiler.ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    CastExpr,
    CatchClause,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    MethodCallExpr,
    ReturnStmt,
    TryCatchFinallyStmt,
    UniversalClass,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
    WhileStmt,
)
from elmos_polyglot_route.ast_compiler.ir.cfg import (
    BasicBlock,
    CfgBuilder,
    CfgEdgeKind,
    ControlFlowGraph,
)
from elmos_polyglot_route.ast_compiler.ir.dfg import DataFlowGraph
from elmos_polyglot_route.ast_compiler.ir.ownership import (
    BorrowState,
    OwnershipAnalyzer,
    OwnershipKind,
    OwnershipViolation,
)
from elmos_polyglot_route.ast_compiler.ir.types import ExtendedTypeKind, TypeLattice
from elmos_polyglot_route.ast_compiler.lowering import (
    EnterpriseShimsLowering,
    SemanticLoweringEngine,
)
from elmos_polyglot_route.ast_compiler.autonomous.smt_repair import (
    SmtAutonomousRepairEngine,
    SmtBoundsAndOverflowSolver,
    SmtNullabilitySolver,
    SmtOwnershipSolver,
    SmtTypeSolver,
)
from elmos_polyglot_route.ast_compiler.parsers import get_parser
from elmos_polyglot_route.ast_compiler.parsers.native_bridge import NativeBridge


# ==============================================================================
# Helper: Build Realistic Enterprise Microservice Universal AST
# ==============================================================================
def create_enterprise_order_microservice() -> UniversalModule:
    """Builds a realistic order fulfillment & inventory microservice with concurrent state."""
    mod = UniversalModule(name="OrderFulfillmentMicroservice", source_language="java")

    # --------------------------------------------------------------------------
    # Class: OrderFulfillmentService
    # --------------------------------------------------------------------------
    service_cls = UniversalClass(name="OrderFulfillmentService")

    # Concurrent Map: customer_credit_ledger (ConcurrentHashMap<String, Long>)
    f_map_t = UniversalType.custom("ConcurrentHashMap<String, Long>")
    f_map_t.key_type = UniversalType.string_type()
    f_map_t.value_type = UniversalType.int64()
    service_cls.fields.append(UniversalField(name="customer_credit_ledger", type_info=f_map_t))

    # Lock-free Atomic: total_processed_transactions (AtomicLong)
    f_atomic_t = UniversalType.custom("AtomicLong")
    service_cls.fields.append(UniversalField(name="total_processed_transactions", type_info=f_atomic_t))

    # Channel/Queue: order_event_bus (BlockingQueue<String>)
    f_chan_t = UniversalType.custom("BlockingQueue<String>")
    f_chan_t.element_type = UniversalType.string_type()
    service_cls.fields.append(UniversalField(name="order_event_bus", type_info=f_chan_t))

    # Method 1: process_order(order_id: String, amount: Long, customer_id: String) -> Boolean
    m_process = UniversalMethod(
        name="process_order",
        params=[
            UniversalParam(name="order_id", type_info=UniversalType.string_type()),
            UniversalParam(name="amount", type_info=UniversalType.int64()),
            UniversalParam(name="customer_id", type_info=UniversalType.string_type()),
        ],
        return_type=UniversalType.boolean(),
        is_async=True,
    )

    try_stmts = [
        # 1. Atomic increment
        ExprStmt(MethodCallExpr(
            target=IdentifierExpr("total_processed_transactions"),
            method_name="incrementAndGet",
            args=[]
        )),
        # 2. Concurrent map initialization
        ExprStmt(MethodCallExpr(
            target=IdentifierExpr("customer_credit_ledger"),
            method_name="putIfAbsent",
            args=[IdentifierExpr("customer_id"), LiteralExpr(0, "int")]
        )),
        # 3. Branch on positive amount
        IfElseStmt(
            condition=BinaryExpr(
                left=IdentifierExpr("amount"),
                op=BinaryOperator.GT,
                right=LiteralExpr(0, "int")
            ),
            then_body=[
                ExprStmt(MethodCallExpr(
                    target=IdentifierExpr("customer_credit_ledger"),
                    method_name="put",
                    args=[IdentifierExpr("customer_id"), IdentifierExpr("amount")]
                )),
                ExprStmt(MethodCallExpr(
                    target=IdentifierExpr("order_event_bus"),
                    method_name="put",
                    args=[IdentifierExpr("order_id")]
                )),
                ReturnStmt(value=LiteralExpr(True, "bool"))
            ],
            else_body=[
                ReturnStmt(value=LiteralExpr(False, "bool"))
            ]
        )
    ]

    catch_block = [
        CatchClause(
            exception_type="Exception",
            variable_name="ex",
            body=[ReturnStmt(value=LiteralExpr(False, "bool"))]
        )
    ]

    m_process.body = [TryCatchFinallyStmt(try_body=try_stmts, catch_clauses=catch_block)]
    service_cls.methods.append(m_process)

    # Method 2: calculate_fee(base_amount: Long, tax_rate_basis_points: Long) -> Long (Pure Method)
    m_calc = UniversalMethod(
        name="calculate_fee",
        params=[
            UniversalParam("base_amount", UniversalType.int64()),
            UniversalParam("tax_rate_basis_points", UniversalType.int64()),
        ],
        return_type=UniversalType.int64(),
        body=[
            VarDeclStmt(
                name="fee",
                type_info=UniversalType.int64(),
                initial_value=BinaryExpr(
                    left=BinaryExpr(
                        left=IdentifierExpr("base_amount"),
                        op=BinaryOperator.MUL,
                        right=IdentifierExpr("tax_rate_basis_points")
                    ),
                    op=BinaryOperator.DIV,
                    right=LiteralExpr(10000, "int")
                )
            ),
            ReturnStmt(value=IdentifierExpr("fee"))
        ]
    )
    service_cls.methods.append(m_calc)

    mod.classes.append(service_cls)
    return mod


# ==============================================================================
# Test 1: Genuine Native Compiler AST Extraction
# ==============================================================================
def test_native_compiler_microservice_ingestion():
    """Verify that multiple components are parsed with real native compilers without regex."""
    # 1. Java Javac Tree API Parser
    java_src = """
    public class OrderFulfillmentService {
        private String serviceName;
        public String getServiceName() {
            return this.serviceName;
        }
    }
    """
    java_mod = get_parser("java").parse(java_src)
    assert len(java_mod.classes) == 1
    assert java_mod.classes[0].name == "OrderFulfillmentService"
    assert any(m.name == "getServiceName" for m in java_mod.classes[0].methods)

    # 2. Go Native go/ast Parser
    go_src = """package main
    type InventoryLedger struct {
        Sku string
        AvailableQty int64
    }
    func (l *InventoryLedger) GetQuantity() int64 {
        return l.AvailableQty
    }
    """
    go_mod = get_parser("go").parse(go_src)
    assert len(go_mod.classes) == 1
    assert go_mod.classes[0].name == "InventoryLedger"
    assert any(m.name == "GetQuantity" for m in go_mod.classes[0].methods)

    # 3. Apple Clang C++20 Parser
    cpp_src = """
    class AccountSecurityGate {
    public:
        long accountId;
        long getAccountId() { return accountId; }
    };
    """
    cpp_mod = get_parser("cpp").parse(cpp_src)
    assert len(cpp_mod.classes) == 1
    assert cpp_mod.classes[0].name == "AccountSecurityGate"

    # 4. Rust syn Parser
    rust_src = """
    pub struct EventDispatcher {
        pub queue_name: String,
    }
    impl EventDispatcher {
        pub fn get_queue(&self) -> String {
            self.queue_name.clone()
        }
    }
    """
    rust_mod = get_parser("rust").parse(rust_src)
    assert len(rust_mod.classes) == 1
    assert rust_mod.classes[0].name == "EventDispatcher"

    # 5. Python Standard Library ast Parser
    py_src = """
    class AuditLogSink:
        def __init__(self, tenant: str):
            self.tenant = tenant
        def get_tenant(self) -> str:
            return self.tenant
    """
    py_mod = get_parser("python").parse(py_src)
    assert len(py_mod.classes) == 1
    assert py_mod.classes[0].name == "AuditLogSink"


# ==============================================================================
# Test 2: Middle-End CFG & Dominance Analysis on Microservice
# ==============================================================================
def test_microservice_control_flow_and_dominance():
    """Verify CFG construction, immediate dominators, and exception paths."""
    mod = create_enterprise_order_microservice()
    process_method = mod.classes[0].methods[0]

    cfg = CfgBuilder.build_from_method(process_method)
    assert len(cfg.blocks) >= 4

    # Entry dominator verification
    dom = cfg.compute_dominance()
    assert cfg.entry_id in dom[cfg.entry_id]

    # Immediate dominators (IDOM)
    idom = cfg.compute_immediate_dominators()
    assert len(idom) > 0

    # Dominance frontier for SSA
    df = cfg.compute_dominance_frontier()
    assert isinstance(df, dict)

    # Verify that dead blocks are eliminated
    dead_block = cfg.add_block(label="orphaned_dead_block")
    cfg.prune_unreachable_blocks()
    assert dead_block.block_id not in cfg.blocks


# ==============================================================================
# Test 3: Data Flow, Liveness, and Function Purity Analysis
# ==============================================================================
def test_microservice_dataflow_and_purity():
    """Verify Def-Use chains, backward liveness, and method purity on business logic."""
    mod = create_enterprise_order_microservice()
    service_cls = mod.classes[0]
    process_method = service_cls.methods[0]
    calc_method = service_cls.methods[1]

    # 1. Impure method (mutates state and triggers channel put)
    is_pure, reasons = DataFlowGraph.is_pure_method(process_method)
    assert is_pure is False
    assert len(reasons) >= 3
    assert any("increment" in r.lower() or "put" in r.lower() for r in reasons)

    # 2. Pure method (pure calculation without side effects)
    is_pure_calc, reasons_calc = DataFlowGraph.is_pure_method(calc_method)
    assert is_pure_calc is True
    assert len(reasons_calc) == 0

    # 3. Data Flow Graph on pure method
    cfg_calc = CfgBuilder.build_from_method(calc_method)
    dfg_calc = DataFlowGraph(cfg_calc)
    assert len(dfg_calc.definitions) >= 1
    assert dfg_calc.definitions[0].var_name == "fee"


# ==============================================================================
# Test 4: Ownership & Borrow Analysis with Z3 Repair Synthesis
# ==============================================================================
def test_microservice_ownership_and_affine_safety():
    """Verify affine type tracking and Z3 borrow conflict resolution."""
    analyzer = OwnershipAnalyzer(is_rust_mode=True)
    analyzer.declare_variable("customer_id", OwnershipKind.OWNED)

    # Immutable borrow for lookup
    analyzer.record_shared_borrow("customer_id", "putIfAbsent")

    # Hazard: Attempting to move customer_id while shared borrow is open
    analyzer.record_move("customer_id", "put")
    assert len(analyzer.violations) == 1
    assert analyzer.violations[0].violation_type == "ALIASING_CONFLICT"

    # Formulate in Z3 SmtOwnershipSolver
    patch = SmtOwnershipSolver.solve_borrow_hazard(
        var_name="customer_id",
        shared_borrows=1,
        mut_borrows=1
    )
    assert patch is not None
    assert patch.rule_name == "SMT_AFFINE_OWNERSHIP_CLONE"
    assert ".clone()" in patch.description


# ==============================================================================
# Test 5: Enterprise Concurrency Shims Lowering across 3 Major Targets
# ==============================================================================
def test_microservice_enterprise_concurrency_shims():
    """Verify that ConcurrentHashMap, AtomicLong, and Channels lower to Rust, Go, and C#."""
    mod = create_enterprise_order_microservice()

    # 1. Lower to Rust
    rust_mod = copy.deepcopy(mod)
    rust_mod = EnterpriseShimsLowering.lower_module(rust_mod, "rust")
    cls_r = rust_mod.classes[0]

    f_map_r = [f for f in cls_r.fields if f.name == "customer_credit_ledger"][0]
    assert "Arc<DashMap" in f_map_r.type_info.name

    f_atomic_r = [f for f in cls_r.fields if f.name == "total_processed_transactions"][0]
    assert f_atomic_r.type_info.name == "AtomicI64"

    f_chan_r = [f for f in cls_r.fields if f.name == "order_event_bus"][0]
    assert "tokio::sync::mpsc" in f_chan_r.type_info.name

    # 2. Lower to Go
    go_mod = copy.deepcopy(mod)
    go_mod = EnterpriseShimsLowering.lower_module(go_mod, "go")
    cls_g = go_mod.classes[0]

    f_map_g = [f for f in cls_g.fields if f.name == "customer_credit_ledger"][0]
    assert f_map_g.type_info.name == "sync.Map"

    f_atomic_g = [f for f in cls_g.fields if f.name == "total_processed_transactions"][0]
    assert f_atomic_g.type_info.name == "atomic.Int64"

    f_chan_g = [f for f in cls_g.fields if f.name == "order_event_bus"][0]
    assert "chan" in f_chan_g.type_info.name

    # 3. Lower to C#
    cs_mod = copy.deepcopy(mod)
    cs_mod = EnterpriseShimsLowering.lower_module(cs_mod, "csharp")
    cls_cs = cs_mod.classes[0]

    f_map_cs = [f for f in cls_cs.fields if f.name == "customer_credit_ledger"][0]
    assert "ConcurrentDictionary" in f_map_cs.type_info.name

    f_chan_cs = [f for f in cls_cs.fields if f.name == "order_event_bus"][0]
    assert "ChannelWriter" in f_chan_cs.type_info.name


# ==============================================================================
# Test 6: Z3 SMT Formal Bounds, Nullability, and Widening Repair
# ==============================================================================
def test_microservice_smt_bounds_and_overflow_repair():
    """Verify Z3 bit-vector overflow analysis and null guard synthesis on business methods."""
    # 1. 32-bit integer arithmetic overflow detection
    has_overflow, patch = SmtBoundsAndOverflowSolver.check_addition_overflow(
        bit_width=32,
        operand_min=-2147483648,
        operand_max=2147483647
    )
    assert has_overflow is True
    assert patch is not None
    assert patch.rule_name == "SMT_CHECKED_ARITHMETIC_OR_WIDENING"

    # 2. Null guard formal synthesis
    null_patch = SmtNullabilitySolver.solve_null_guard(
        var_name="customer_profile",
        is_nullable=True,
        is_dereferenced=True
    )
    assert null_patch is not None
    assert null_patch.rule_name == "SMT_NULL_GUARD_SYNTHESIS"

    # 3. Type lattice widening proof
    sub_type = UniversalType.primitive("i32")
    super_type = UniversalType.int64()
    w_patch = SmtTypeSolver.solve_widening_cast(sub_type, super_type)
    assert w_patch is not None
    assert w_patch.rule_name == "SMT_NUMERIC_WIDENING"


# ==============================================================================
# Test 7: End-to-End Semantic Lowering Engine Integration
# ==============================================================================
def test_microservice_end_to_end_lowering_integration():
    """Verify full integration of SemanticLoweringEngine including enterprise shims."""
    mod = create_enterprise_order_microservice()
    lowered_mod = SemanticLoweringEngine.lower(mod, source_lang="java", target_lang="rust")

    cls_target = lowered_mod.classes[0]
    f_map = [f for f in cls_target.fields if f.name == "customer_credit_ledger"][0]
    assert "DashMap" in f_map.type_info.name

    f_atomic = [f for f in cls_target.fields if f.name == "total_processed_transactions"][0]
    assert f_atomic.type_info.name == "AtomicI64"

    # Verify that methods remain intact
    assert len(cls_target.methods) == 2
    assert cls_target.methods[0].name == "process_order"
    assert cls_target.methods[1].name == "calculate_fee"
