"""Five industrial corpora covering the four fatal semantic domains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elmos_polyglot_route.ast_compiler.ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    ChannelMakeStmt,
    ChannelRecvStmt,
    ChannelSendStmt,
    DropStmt,
    IdentifierExpr,
    IfElseStmt,
    IoReadStmt,
    IoWriteStmt,
    JoinStmt,
    LiteralExpr,
    LockStmt,
    MethodCallExpr,
    MoveStmt,
    ReturnStmt,
    SpawnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UniversalAnnotation,
    UniversalClass,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalType,
    VarDeclStmt,
    CatchClause,
)


def _i(name: str) -> IdentifierExpr:
    return IdentifierExpr(name)


def _n(value: int) -> LiteralExpr:
    return LiteralExpr(value=value, type_kind="int")


def _s(value: str) -> LiteralExpr:
    return LiteralExpr(value=value, type_kind="string")


def _bin(left: Any, op: BinaryOperator, right: Any) -> BinaryExpr:
    return BinaryExpr(left=left, op=op, right=right)


def _param(name: str, typ: str = "i64") -> UniversalParam:
    return UniversalParam(name=name, type_info=UniversalType.primitive(typ))


def _fn(name: str, params: list[UniversalParam], body: list[Any], http: str | None = None) -> UniversalMethod:
    return UniversalMethod(
        name=name,
        params=params,
        return_type=UniversalType.int64(),
        body=body,
        http_method=http,
        http_path="/{sku}" if http == "GET" else ("" if http == "POST" else None),
    )


@dataclass(frozen=True)
class BehaviorCase:
    args: list[Any]
    expected: Any
    expect_error: str | None = None


@dataclass(frozen=True)
class IndustrialCorpus:
    corpus_id: str
    domain: str
    entrypoint: str
    module: UniversalModule
    cases: tuple[BehaviorCase, ...]
    invariant: str


def payment_clearing_corpus() -> IndustrialCorpus:
    """Concurrent debit/credit under a mutex. Result is left - right."""
    body = [
        VarDeclStmt(name="balance", type_info=UniversalType.int64(), initial_value=_n(0)),
        VarDeclStmt(name="mu", type_info=UniversalType.custom("Mutex"), initial_value=_s("mu")),
        SpawnStmt(
            join_handle="h1",
            body=[
                LockStmt(
                    lock_expr=_i("mu"),
                    body=[
                        AssignStmt(
                            target=_i("balance"),
                            value=_bin(_i("balance"), BinaryOperator.ADD, _i("left")),
                        )
                    ],
                )
            ],
        ),
        SpawnStmt(
            join_handle="h2",
            body=[
                LockStmt(
                    lock_expr=_i("mu"),
                    body=[
                        AssignStmt(
                            target=_i("balance"),
                            value=_bin(_i("balance"), BinaryOperator.SUB, _i("right")),
                        )
                    ],
                )
            ],
        ),
        JoinStmt(handle="h1"),
        JoinStmt(handle="h2"),
        ReturnStmt(value=_i("balance")),
    ]
    module = UniversalModule(
        name="PaymentClearing",
        free_functions=[_fn("clear_payments", [_param("left"), _param("right")], body)],
        metadata={"corpus_id": "payment-clearing", "domain": "async-concurrency"},
    )
    return IndustrialCorpus(
        corpus_id="payment-clearing",
        domain="async-concurrency",
        entrypoint="clear_payments",
        module=module,
        cases=(
            BehaviorCase([40, 15], 25),
            BehaviorCase([100, 1], 99),
            BehaviorCase([7, 7], 0),
        ),
        invariant="locked_balance == left - right",
    )


def order_pipeline_corpus() -> IndustrialCorpus:
    """Producer/consumer channel. Result is triangular number of count."""
    body = [
        ChannelMakeStmt(name="orders", element_type=UniversalType.int64(), capacity=16),
        SpawnStmt(
            join_handle="prod",
            body=[
                VarDeclStmt(name="i", type_info=UniversalType.int64(), initial_value=_n(1)),
                # Unrolled 3-iteration producer driven by count via a single send of count
                ChannelSendStmt(channel="orders", value=_i("count")),
            ],
        ),
        SpawnStmt(
            join_handle="cons",
            body=[
                ChannelRecvStmt(channel="orders", target="n"),
                AssignStmt(
                    target=_i("n"),
                    value=_bin(
                        _bin(_i("n"), BinaryOperator.MUL, _bin(_i("n"), BinaryOperator.ADD, _n(1))),
                        BinaryOperator.DIV,
                        _n(2),
                    ),
                ),
                ChannelMakeStmt(name="done", element_type=UniversalType.int64(), capacity=1),
                ChannelSendStmt(channel="done", value=_i("n")),
            ],
        ),
        JoinStmt(handle="prod"),
        JoinStmt(handle="cons"),
        ChannelRecvStmt(channel="done", target="sum"),
        ReturnStmt(value=_i("sum")),
    ]
    # The consumer creates `done` after recv; parent then recvs. Race: parent might recv before done exists.
    # Rebuild with parent-owned done channel.
    body = [
        ChannelMakeStmt(name="orders", element_type=UniversalType.int64(), capacity=8),
        ChannelMakeStmt(name="done", element_type=UniversalType.int64(), capacity=1),
        SpawnStmt(
            join_handle="prod",
            body=[ChannelSendStmt(channel="orders", value=_i("count"))],
        ),
        SpawnStmt(
            join_handle="cons",
            body=[
                ChannelRecvStmt(channel="orders", target="n"),
                ChannelSendStmt(
                    channel="done",
                    value=_bin(
                        _bin(_i("n"), BinaryOperator.MUL, _bin(_i("n"), BinaryOperator.ADD, _n(1))),
                        BinaryOperator.DIV,
                        _n(2),
                    ),
                ),
            ],
        ),
        JoinStmt(handle="prod"),
        JoinStmt(handle="cons"),
        ChannelRecvStmt(channel="done", target="sum"),
        ReturnStmt(value=_i("sum")),
    ]
    module = UniversalModule(
        name="OrderPipeline",
        free_functions=[_fn("pipeline_orders", [_param("count")], body)],
        metadata={"corpus_id": "order-pipeline", "domain": "async-concurrency"},
    )
    return IndustrialCorpus(
        corpus_id="order-pipeline",
        domain="async-concurrency",
        entrypoint="pipeline_orders",
        module=module,
        cases=(
            BehaviorCase([4], 10),
            BehaviorCase([5], 15),
            BehaviorCase([10], 55),
        ),
        invariant="channel_sum == n*(n+1)/2",
    )


def asset_ledger_corpus() -> IndustrialCorpus:
    """Unique move of an owned value, then drop the source. Result is moved value + addend."""
    body = [
        MoveStmt(source="owned", target="holder"),
        VarDeclStmt(name="scratch", type_info=UniversalType.int64(), initial_value=_i("addend")),
        MoveStmt(source="scratch", target="bonus"),
        DropStmt(name="scratch", kind="owned"),
        ReturnStmt(value=_bin(_i("holder"), BinaryOperator.ADD, _i("bonus"))),
    ]
    module = UniversalModule(
        name="AssetLedger",
        free_functions=[_fn("ledger_move", [_param("owned"), _param("addend")], body)],
        metadata={"corpus_id": "asset-ledger", "domain": "object-graph-lifecycle"},
    )
    return IndustrialCorpus(
        corpus_id="asset-ledger",
        domain="object-graph-lifecycle",
        entrypoint="ledger_move",
        module=module,
        cases=(
            BehaviorCase([9, 1], 10),
            BehaviorCase([20, 5], 25),
            BehaviorCase([0, 3], 3),
        ),
        invariant="moved_owner + moved_bonus; source is dropped",
    )


def file_settlement_corpus() -> IndustrialCorpus:
    """Write two integers, read them back, return a+b after checksum verification."""
    body = [
        VarDeclStmt(
            name="path",
            type_info=UniversalType.string_type(),
            initial_value=MethodCallExpr(target=None, method_name="temp_path", args=[]),
        ),
        VarDeclStmt(
            name="payload",
            type_info=UniversalType.string_type(),
            initial_value=_bin(_i("left"), BinaryOperator.ADD, _s("|")),
        ),
        AssignStmt(target=_i("payload"), value=_bin(_i("payload"), BinaryOperator.ADD, _i("right"))),
        IoWriteStmt(path=_i("path"), value=_i("payload")),
        IoReadStmt(path=_i("path"), target="echo"),
        VarDeclStmt(
            name="digest",
            type_info=UniversalType.int64(),
            initial_value=MethodCallExpr(target=None, method_name="checksum", args=[_i("echo")]),
        ),
        IfElseStmt(
            condition=_bin(_i("digest"), BinaryOperator.EQ, _n(0)),
            then_body=[ThrowStmt(exception_class="IntegrityError", message="zero checksum")],
            else_body=[],
        ),
        ReturnStmt(value=_bin(_i("left"), BinaryOperator.ADD, _i("right"))),
    ]
    module = UniversalModule(
        name="FileSettlement",
        free_functions=[_fn("settle_checksum", [_param("left"), _param("right")], body)],
        metadata={"corpus_id": "file-settlement", "domain": "system-io"},
    )
    return IndustrialCorpus(
        corpus_id="file-settlement",
        domain="system-io",
        entrypoint="settle_checksum",
        module=module,
        cases=(
            BehaviorCase([3, 4], 7),
            BehaviorCase([11, 8], 19),
            BehaviorCase([0, 1], 1),
        ),
        invariant="read(write(a|b)) checksum != 0 and result == a+b",
    )


def rest_inventory_corpus() -> IndustrialCorpus:
    """REST GET with exception channel. sku_len<=0 raises; else sku_len * 10."""
    get_body = [
        TryCatchFinallyStmt(
            try_body=[
                IfElseStmt(
                    condition=_bin(_i("sku_len"), BinaryOperator.LE, _n(0)),
                    then_body=[ThrowStmt(exception_class="ValidationError", message="sku required")],
                    else_body=[ReturnStmt(value=_bin(_i("sku_len"), BinaryOperator.MUL, _n(10)))],
                )
            ],
            catch_clauses=[
                CatchClause(
                    exception_type="Exception",
                    variable_name="ex",
                    body=[ReturnStmt(value=_n(-1))],
                )
            ],
        )
    ]
    post_body = [
        IfElseStmt(
            condition=_bin(_i("qty"), BinaryOperator.LE, _n(0)),
            then_body=[ThrowStmt(exception_class="ValidationError", message="qty required")],
            else_body=[ReturnStmt(value=_i("qty"))],
        )
    ]
    controller = UniversalClass(
        name="InventoryController",
        is_controller=True,
        base_route="/api/v1/inventory",
        annotations=[UniversalAnnotation(name="RestController")],
        methods=[
            _fn("get_item", [_param("sku_len")], get_body, http="GET"),
            _fn("create_item", [_param("qty")], post_body, http="POST"),
        ],
    )
    module = UniversalModule(
        name="RestInventory",
        classes=[controller],
        metadata={"corpus_id": "rest-inventory", "domain": "complex-framework-and-ui"},
    )
    return IndustrialCorpus(
        corpus_id="rest-inventory",
        domain="complex-framework-and-ui",
        entrypoint="get_item",
        module=module,
        cases=(
            BehaviorCase([4], 40),
            BehaviorCase([0], -1),
            BehaviorCase([9], 90),
        ),
        invariant="invalid sku maps to -1; valid sku returns qty*10",
    )


def all_corpora() -> tuple[IndustrialCorpus, ...]:
    return (
        payment_clearing_corpus(),
        order_pipeline_corpus(),
        asset_ledger_corpus(),
        file_settlement_corpus(),
        rest_inventory_corpus(),
    )
