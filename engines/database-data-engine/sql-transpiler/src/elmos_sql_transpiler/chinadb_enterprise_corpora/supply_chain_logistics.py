"""Enterprise Supply Chain & Logistics Corpus.

Provides warehouse stock structures, multi-echelon ATP inventory,
purchase order lifecycles, wave picking, freight rating, and inventory conservation tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any


@dataclass
class WarehouseRecord:
    """Warehouse fulfillment center facility."""

    wh_code: str
    wh_name: str
    region_code: str
    address: str
    total_capacity_sqm: float = 50000.0
    is_bonded: bool = False
    operating_status: str = "OPERATIONAL"


@dataclass
class SkuItemRecord:
    """Master product catalog SKU."""

    sku_id: str
    sku_name: str
    category: str
    unit_weight_kg: float
    unit_volume_cbm: float
    standard_cost: float
    is_hazardous: bool = False


@dataclass
class InventoryAtpRecord:
    """Available To Promise (ATP) inventory level."""

    wh_code: str
    sku_id: str
    on_hand_qty: int
    allocated_qty: int = 0
    in_transit_qty: int = 0
    reorder_point: int = 100

    @property
    def available_to_promise(self) -> int:
        """Compute net ATP available for new customer orders."""
        return max(0, self.on_hand_qty - self.allocated_qty)


@dataclass
class PurchaseOrderRecord:
    """Inbound procurement purchase order."""

    po_no: str
    vendor_id: str
    wh_code: str
    order_date: str
    expected_delivery_date: str
    total_cost: float
    status: str = "ISSUED"


@dataclass
class PoLineRecord:
    """Purchase order line item."""

    po_no: str
    line_no: int
    sku_id: str
    ordered_qty: int
    received_qty: int = 0
    unit_price: float = 0.0


@dataclass
class AsnHeaderRecord:
    """Advanced Shipping Notice (ASN) for inbound cargo."""

    asn_no: str
    po_no: str
    carrier_code: str
    tracking_no: str
    shipped_date: str
    status: str = "IN_TRANSIT"


@dataclass
class CustomerOrderRecord:
    """Omnichannel customer sales order."""

    order_no: str
    customer_id: str
    shipping_address: str
    order_status: str = "PENDING"
    total_amount: float = 0.0


@dataclass
class OrderLineRecord:
    """Customer order line item."""

    order_no: str
    line_no: int
    sku_id: str
    ordered_qty: int
    fulfilled_qty: int = 0
    unit_price: float = 0.0


@dataclass
class CarrierFreightRateRecord:
    """Third-party logistics carrier freight matrix."""

    rate_id: str
    carrier_code: str
    origin_region: str
    dest_region: str
    base_fee: float
    per_kg_rate: float


@dataclass
class CdcEvent:
    """Change Data Capture (CDC) streaming event."""

    event_id: str
    table_name: str
    operation: str  # INSERT, UPDATE, DELETE
    timestamp_ms: int
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)


class SupplyChainLogisticsCorpus:
    """Industrial Supply Chain & FIFO Allocation Workload Suite."""

    domain_name = "Supply Chain Logistics & Warehouse"
    primary_source_dialect = "oracle"

    @classmethod
    def get_raw_sql_path(cls) -> Path:
        """Return path to raw SQL corpus file."""
        return Path(__file__).with_name("supply_chain_logistics.sql")

    @classmethod
    def get_raw_sql(cls) -> str:
        """Load full raw SQL corpus text."""
        return cls.get_raw_sql_path().read_text(encoding="utf-8")

    @classmethod
    def parse_statements(cls) -> list[str]:
        """Split corpus into individual executable SQL statements."""
        raw = cls.get_raw_sql()
        stmts: list[str] = []
        cur: list[str] = []
        in_plsql = False

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue

            if any(
                stripped.upper().startswith(kw)
                for kw in ("CREATE OR REPLACE PROCEDURE", "CREATE OR REPLACE TRIGGER", "BEGIN")
            ):
                in_plsql = True

            cur.append(line)

            if in_plsql:
                if stripped == "/":
                    stmts.append("\n".join(cur[:-1]).strip())
                    cur = []
                    in_plsql = False
            else:
                if stripped.endswith(";"):
                    joined = "\n".join(cur).strip()
                    if joined.endswith(";"):
                        joined = joined[:-1].strip()
                    stmts.append(joined)
                    cur = []

        if cur:
            tail = "\n".join(cur).strip()
            if tail:
                stmts.append(tail)

        return [s for s in stmts if s]

    @classmethod
    def get_seed_warehouses(cls) -> list[WarehouseRecord]:
        """Generate deterministic distribution hubs."""
        return [
            WarehouseRecord(
                "WH_BJ_01", "North China Central DC", "REG_NC", "Beijing Park", 50000.0
            ),
            WarehouseRecord("WH_SH_01", "East China Super Hub", "REG_EC", "Shanghai Port", 80000.0),
            WarehouseRecord("WH_GZ_01", "South China Gateway", "REG_SC", "Guangzhou DC", 60000.0),
            WarehouseRecord("WH_CD_01", "West China Hub", "REG_WC", "Chengdu DC", 45000.0),
        ]


    @classmethod
    def get_seed_skus(cls, count: int = 50) -> list[SkuItemRecord]:
        """Generate master catalog SKUs."""
        skus: list[SkuItemRecord] = []
        categories = ["ELECTRONICS", "APPAREL", "HOME", "INDUSTRIAL", "FOOD"]
        for i in range(1, count + 1):
            skus.append(
                SkuItemRecord(
                    sku_id=f"SKU_{i:04d}",
                    sku_name=f"Standard Enterprise Item {i}",
                    category=categories[i % len(categories)],
                    unit_weight_kg=0.5 + ((i % 10) * 0.2),
                    unit_volume_cbm=0.002 + ((i % 5) * 0.001),
                    standard_cost=100.0 + (i * 5.0),
                )
            )
        return skus

    @classmethod
    def get_seed_inventory(
        cls, warehouses: list[WarehouseRecord], skus: list[SkuItemRecord]
    ) -> list[InventoryAtpRecord]:
        """Generate initial multi-warehouse inventory levels."""
        inv: list[InventoryAtpRecord] = []
        for wh in warehouses:
            for s in skus:
                inv.append(
                    InventoryAtpRecord(
                        wh_code=wh.wh_code,
                        sku_id=s.sku_id,
                        on_hand_qty=2000,
                        allocated_qty=150,
                        in_transit_qty=500,
                        reorder_point=300,
                    )
                )
        return inv

    @classmethod
    def get_seed_freight_rates(cls) -> list[CarrierFreightRateRecord]:
        """Generate 3PL freight rate schedules."""
        return [
            CarrierFreightRateRecord("FRT_001", "SF_EXPRESS", "REG_NC", "REG_EC", 18.0, 3.5),
            CarrierFreightRateRecord("FRT_002", "JD_LOGISTICS", "REG_NC", "REG_SC", 22.0, 4.2),
            CarrierFreightRateRecord("FRT_003", "DEPPON", "REG_EC", "REG_WC", 20.0, 3.8),
        ]

    @classmethod
    def generate_orders_workload(
        cls, skus: list[SkuItemRecord], count: int = 100
    ) -> list[dict[str, Any]]:
        """Generate batch sales orders for inventory reservation stress testing."""
        workload: list[dict[str, Any]] = []
        n = len(skus)
        for idx in range(count):
            order_skus: list[dict[str, Any]] = []
            for item_idx in range(1, 4):
                sku = skus[(idx * 3 + item_idx) % n]
                order_skus.append(
                    {
                        "sku_id": sku.sku_id,
                        "ordered_qty": 5 + (item_idx * 2),
                        "unit_price": sku.standard_cost * 1.25,
                    }
                )
            workload.append(
                {
                    "order_no": f"ORD_{idx + 1:06d}",
                    "customer_id": f"CUST_{idx + 1:04d}",
                    "wh_code": "WH_BJ_01",
                    "items": order_skus,
                }
            )
        return workload

    @classmethod
    def allocate_order_inventory_in_memory(
        cls,
        inv_map: dict[str, InventoryAtpRecord],
        wh_code: str,
        items: list[dict[str, Any]],
    ) -> tuple[bool, str, list[tuple[str, int]]]:
        """Atomically check ATP and allocate inventory for order items."""
        # Phase 1: check all items have sufficient ATP
        for it in items:
            sku_id = it["sku_id"]
            qty = it["ordered_qty"]
            key = f"{wh_code}_{sku_id}"
            rec = inv_map.get(key)
            if not rec or rec.available_to_promise < qty:
                return False, f"INSUFFICIENT_ATP_{sku_id}", []

        # Phase 2: allocate
        allocated_items: list[tuple[str, int]] = []
        for it in items:
            sku_id = it["sku_id"]
            qty = it["ordered_qty"]
            key = f"{wh_code}_{sku_id}"
            rec = inv_map[key]
            rec.allocated_qty += qty
            allocated_items.append((sku_id, qty))

        return True, "ALLOCATED_SUCCESS", allocated_items

    @classmethod
    def receive_inbound_asn_in_memory(
        cls,
        inv_map: dict[str, InventoryAtpRecord],
        wh_code: str,
        items: list[tuple[str, int]],
    ) -> None:
        """Receive ASN cargo into physical on-hand warehouse inventory."""
        for sku_id, qty in items:
            key = f"{wh_code}_{sku_id}"
            rec = inv_map.get(key)
            if rec:
                rec.on_hand_qty += qty
                rec.in_transit_qty = max(0, rec.in_transit_qty - qty)

    @classmethod
    def calculate_freight_cost(
        cls,
        rate: CarrierFreightRateRecord,
        weight_kg: float,
    ) -> float:
        """Compute exact freight delivery charges."""
        base = Decimal(str(rate.base_fee))
        per_kg = Decimal(str(rate.per_kg_rate))
        w = Decimal(str(weight_kg))
        charge = (base + (w * per_kg)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return float(charge)

    @classmethod
    def verify_inventory_conservation(
        cls,
        initial_inv: list[InventoryAtpRecord],
        final_inv: list[InventoryAtpRecord],
        inbound_received: int = 0,
        outbound_shipped: int = 0,
    ) -> tuple[bool, int, str]:
        """Verify physical inventory mass balance: Initial + Inbound - Outbound == Final."""
        init_total = sum(r.on_hand_qty for r in initial_inv)
        final_total = sum(r.on_hand_qty for r in final_inv)
        expected = init_total + inbound_received - outbound_shipped
        delta = abs(final_total - expected)
        conserved = delta == 0
        msg = (
            f"Init: {init_total}, Inbound: {inbound_received}, "
            f"Outbound: {outbound_shipped}, Expected: {expected}, "
            f"Final: {final_total}, Delta: {delta}"
        )
        return conserved, delta, msg

    @classmethod
    def verify_atp_non_negativity(
        cls, inv: list[InventoryAtpRecord]
    ) -> tuple[bool, list[str]]:
        """Verify that allocated quantity never exceeds physical on-hand stock."""
        errors: list[str] = []
        for r in inv:
            if r.allocated_qty > r.on_hand_qty:
                errors.append(
                    f"Over-allocated: {r.wh_code}_{r.sku_id} on_hand={r.on_hand_qty} "
                    f"< allocated={r.allocated_qty}"
                )
        return len(errors) == 0, errors

    @classmethod
    def simulate_cdc_stream(
        cls,
        allocations: list[tuple[str, str, int]],
    ) -> list[CdcEvent]:
        """Generate CDC change event stream for real-time replication verification."""
        events: list[CdcEvent] = []
        base_ts = int(time.time() * 1000)

        for idx, (wh, sku, qty) in enumerate(allocations):
            events.append(
                CdcEvent(
                    event_id=f"EVT_SCM_{idx + 1:08d}",
                    table_name="scm_inventory_atp",
                    operation="UPDATE",
                    timestamp_ms=base_ts + idx * 5,
                    before_state={"wh_code": wh, "sku_id": sku},
                    after_state={"wh_code": wh, "sku_id": sku, "allocated_qty_delta": qty},
                )
            )
        return events

    @classmethod
    def simulate_concurrent_order_allocation_stress(
        cls,
        concurrency: int = 16,
        orders_per_worker: int = 50,
    ) -> dict[str, Any]:
        """Simulate high-concurrency order placement and inventory reservation."""
        warehouses = cls.get_seed_warehouses()
        skus = cls.get_seed_skus(count=100)
        inv = cls.get_seed_inventory(warehouses, skus)
        inv_map = {f"{r.wh_code}_{r.sku_id}": r for r in inv}

        latencies_ms: list[float] = []
        success_count = 0
        insufficient_atp_count = 0
        total_items_allocated = 0

        start_time = time.time()
        for worker_id in range(concurrency):
            for o_idx in range(orders_per_worker):
                t0 = time.time()
                wh = warehouses[worker_id % len(warehouses)].wh_code
                sku_i = (worker_id * 3 + o_idx) % len(skus)
                items = [
                    {"sku_id": skus[sku_i].sku_id, "ordered_qty": 5},
                    {"sku_id": skus[(sku_i + 1) % len(skus)].sku_id, "ordered_qty": 10},
                ]

                ok, reason, allocated = cls.allocate_order_inventory_in_memory(
                    inv_map, wh, items
                )
                t1 = time.time()
                latencies_ms.append((t1 - t0) * 1000.0)

                if ok:
                    success_count += 1
                    total_items_allocated += sum(q for _, q in allocated)
                else:
                    insufficient_atp_count += 1

        total_duration = max(0.001, time.time() - start_time)
        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        atp_valid, atp_errors = cls.verify_atp_non_negativity(list(inv_map.values()))

        return {
            "total_orders_processed": len(latencies_ms),
            "success_count": success_count,
            "insufficient_atp_count": insufficient_atp_count,
            "total_items_allocated": total_items_allocated,
            "total_duration_sec": total_duration,
            "throughput_tps": len(latencies_ms) / total_duration,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "atp_valid": atp_valid,
            "atp_errors": atp_errors,
        }
