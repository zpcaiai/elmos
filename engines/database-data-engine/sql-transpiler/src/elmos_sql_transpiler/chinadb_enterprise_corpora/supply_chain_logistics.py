"""Enterprise Supply Chain & Logistics Corpus.

Provides warehouse stock structures, FIFO lot allocation procedures,
purchase order lifecycles, and inventory conservation tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class WarehouseRecord:
    """Warehouse facility record."""

    warehouse_id: str
    warehouse_name: str
    region_code: str
    capacity_cbm: float = 50000.0


@dataclass
class InventoryLotRecord:
    """Inventory lot with expiration date."""

    lot_id: str
    sku_code: str
    warehouse_id: str
    quantity_available: int
    quantity_allocated: int
    unit_cost: float
    expiry_date: str


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
    def get_seed_warehouses(cls) -> list[WarehouseRecord]:
        """Generate deterministic warehouses."""
        return [
            WarehouseRecord("WH_SH_01", "Shanghai Central DC", "CN_EAST"),
            WarehouseRecord("WH_BJ_01", "Beijing North DC", "CN_NORTH"),
            WarehouseRecord("WH_GZ_01", "Guangzhou South DC", "CN_SOUTH"),
            WarehouseRecord("WH_CD_01", "Chengdu West DC", "CN_WEST"),
        ]

    @classmethod
    def get_seed_lots(cls, count: int = 40) -> list[InventoryLotRecord]:
        """Generate inventory lots for FIFO allocation verification."""
        lots: list[InventoryLotRecord] = []
        skus = ["SKU_PHONE_01", "SKU_LAPTOP_02", "SKU_TABLET_03", "SKU_WATCH_04"]
        warehouses = ["WH_SH_01", "WH_BJ_01", "WH_GZ_01", "WH_CD_01"]
        for i in range(1, count + 1):
            sku = skus[i % len(skus)]
            wh = warehouses[i % len(warehouses)]
            qty = 100 * (1 + (i % 5))
            lots.append(
                InventoryLotRecord(
                    lot_id=f"LOT_{i:06d}",
                    sku_code=sku,
                    warehouse_id=wh,
                    quantity_available=qty,
                    quantity_allocated=0,
                    unit_cost=150.0 + (i * 2.5),
                    expiry_date=f"2027-{(i % 12) + 1:02d}-15",
                )
            )
        return lots
