"""Industrial Multi-Warehouse Supply Chain & Logistics Network Archetype Engine.

Provides multi-warehouse topology, precision bin-level inventory allocation,
lot traceability, pick-pack-ship FSM workflows, and carrier dispatch reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import enum
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# ==============================================================================
# 1. Enums and Value Objects
# ==============================================================================

class StorageZoneType(str, enum.Enum):
    """Physical climate and security zones within a warehouse."""
    AMBIENT = "AMBIENT"
    COLD_STORAGE = "COLD_STORAGE"      # 2C to 8C
    DEEP_FREEZE = "DEEP_FREEZE"        # -20C
    HAZARDOUS_MATERIAL = "HAZMAT"
    HIGH_VALUE_SECURE = "HIGH_VALUE"
    RECEIVING_DOCK = "RECEIVING"
    SHIPPING_STAGING = "SHIPPING"


class InventoryStatus(str, enum.Enum):
    """Status of inventory at lot/bin level."""
    AVAILABLE = "AVAILABLE"
    ALLOCATED = "ALLOCATED"
    PICKED = "PICKED"
    QUARANTINED = "QUARANTINED"
    DAMAGED = "DAMAGED"
    EXPIRED = "EXPIRED"


class TransferStatus(str, enum.Enum):
    """Lifecycle states of an inter-warehouse or inter-bin stock transfer."""
    REQUESTED = "REQUESTED"
    ALLOCATED = "ALLOCATED"
    PICKED = "PICKED"
    DISPATCHED = "DISPATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    RECONCILED = "RECONCILED"
    DISCREPANCY_FLAGGED = "DISCREPANCY_FLAGGED"
    CANCELLED = "CANCELLED"


class FulfillmentFsmState(str, enum.Enum):
    """Order fulfillment workflow states."""
    PENDING_ALLOCATION = "PENDING_ALLOCATION"
    INVENTORY_ALLOCATED = "INVENTORY_ALLOCATED"
    WAVE_RELEASED = "WAVE_RELEASED"
    PICKING = "PICKING"
    PICKED = "PICKED"
    PACKING = "PACKING"
    PACKED_VERIFIED = "PACKED_VERIFIED"
    MANIFEST_GENERATED = "MANIFEST_GENERATED"
    CARRIER_DISPATCHED = "CARRIER_DISPATCHED"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"


@dataclass(frozen=True)
class Sku:
    """Stock Keeping Unit value object with strict format validation."""
    code: str
    name: str
    category: str
    barcode: str = ""

    def __post_init__(self) -> None:
        norm = self.code.strip().upper()
        if not re.fullmatch(r"^[A-Z0-9_-]{3,32}$", norm):
            raise ValueError(f"Invalid SKU format: {self.code}")
        object.__setattr__(self, "code", norm)


@dataclass(frozen=True)
class BinLocation:
    """Precise Aisle-Rack-Shelf-Bin physical coordinates in warehouse."""
    aisle: str
    rack: str
    shelf: str
    bin: str
    zone: StorageZoneType = StorageZoneType.AMBIENT

    @property
    def coordinate(self) -> str:
        return f"{self.aisle.upper()}-{self.rack.upper()}-{self.shelf.upper()}-{self.bin.upper()}"


@dataclass(frozen=True)
class LotNumber:
    """Manufacturing batch lot for FIFO / FEFO tracking and expiration safety."""
    lot_code: str
    manufacture_date: dt.date
    expiration_date: dt.date
    supplier_code: str

    def is_expired(self, as_of: Optional[dt.date] = None) -> bool:
        check_date = as_of or dt.date.today()
        return check_date > self.expiration_date


@dataclass(frozen=True)
class PhysicalDimension:
    """Carton or pallet physical dimensions."""
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal

    @property
    def volume_m3(self) -> Decimal:
        return (self.length_cm * self.width_cm * self.height_cm / Decimal("1000000")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )


@dataclass(frozen=True)
class PhysicalWeight:
    """Gross / Net weight value object with unit conversions."""
    value: Decimal
    unit: str = "KG"

    def to_kg(self) -> Decimal:
        if self.unit.upper() == "KG":
            return self.value
        elif self.unit.upper() == "G":
            return self.value / Decimal("1000")
        elif self.unit.upper() in ("LB", "LBS"):
            return self.value * Decimal("0.45359237")
        raise ValueError(f"Unsupported weight unit: {self.unit}")


# ==============================================================================
# 2. Aggregates and Invariants
# ==============================================================================

class SupplyChainDomainError(Exception):
    """Base exception for supply chain domain invariants."""
    pass


class InventoryAllocationError(SupplyChainDomainError):
    """Raised when requested stock exceeds available quantities."""
    pass


class StorageZoneIncompatibleError(SupplyChainDomainError):
    """Raised when product storage requirements conflict with bin zone."""
    pass


@dataclass
class InventoryBinAggregate:
    """Granular physical storage location and stock allocation aggregate root."""
    bin_id: str
    warehouse_id: str
    location: BinLocation
    max_weight_kg: Decimal
    sku_quantities: Dict[str, Decimal] = field(default_factory=dict)         # SKU -> on_hand
    allocated_quantities: Dict[str, Decimal] = field(default_factory=dict)   # SKU -> allocated
    quarantined_quantities: Dict[str, Decimal] = field(default_factory=dict) # SKU -> quarantined
    lot_assignments: Dict[str, str] = field(default_factory=dict)            # SKU -> lot_code
    version: int = 1
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def get_on_hand(self, sku_code: str) -> Decimal:
        return self.sku_quantities.get(sku_code, Decimal("0"))

    def get_allocated(self, sku_code: str) -> Decimal:
        return self.allocated_quantities.get(sku_code, Decimal("0"))

    def get_quarantined(self, sku_code: str) -> Decimal:
        return self.quarantined_quantities.get(sku_code, Decimal("0"))

    def get_available(self, sku_code: str) -> Decimal:
        """Available = On-Hand - Allocated - Quarantined."""
        on_hand = self.get_on_hand(sku_code)
        allocated = self.get_allocated(sku_code)
        quarantined = self.get_quarantined(sku_code)
        return max(Decimal("0"), on_hand - allocated - quarantined)

    def receive_stock(self, sku: Sku, qty: Decimal, lot: LotNumber, unit_weight_kg: Decimal = Decimal("1.0")) -> None:
        """Inbound putaway: receive physical stock into bin."""
        if qty <= Decimal("0"):
            raise ValueError("Receive quantity must be strictly positive")
        if lot.is_expired():
            raise SupplyChainDomainError(f"Cannot receive expired stock for SKU {sku.code}")

        current = self.sku_quantities.get(sku.code, Decimal("0"))
        self.sku_quantities[sku.code] = current + qty
        self.lot_assignments[sku.code] = lot.lot_code
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)

    def allocate_stock(self, sku_code: str, qty: Decimal) -> None:
        """Reserve stock for an active pick list or order."""
        if qty <= Decimal("0"):
            raise ValueError("Allocation quantity must be strictly positive")
        available = self.get_available(sku_code)
        if qty > available:
            raise InventoryAllocationError(
                f"Insufficient stock in bin {self.location.coordinate} for SKU {sku_code}. "
                f"Requested: {qty}, Available: {available}"
            )
        current_allocated = self.allocated_quantities.get(sku_code, Decimal("0"))
        self.allocated_quantities[sku_code] = current_allocated + qty
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)

    def pick_stock(self, sku_code: str, qty: Decimal) -> None:
        """Physically pick allocated stock from bin during wave execution."""
        allocated = self.get_allocated(sku_code)
        on_hand = self.get_on_hand(sku_code)
        if qty > allocated:
            raise InventoryAllocationError(f"Cannot pick {qty}: only {allocated} allocated in bin")
        if qty > on_hand:
            raise InventoryAllocationError(f"Cannot pick {qty}: physical on-hand is only {on_hand}")

        self.allocated_quantities[sku_code] = allocated - qty
        self.sku_quantities[sku.code if hasattr(sku_code, "code") else sku_code] = on_hand - qty
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)

    def quarantine_stock(self, sku_code: str, qty: Decimal, reason: str) -> None:
        """Isolate damaged or suspect stock into quarantine balance."""
        available = self.get_available(sku_code)
        if qty > available:
            raise InventoryAllocationError(f"Cannot quarantine {qty}: available is only {available}")
        curr_q = self.quarantined_quantities.get(sku_code, Decimal("0"))
        self.quarantined_quantities[sku_code] = curr_q + qty
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)


@dataclass
class StockTransferAggregate:
    """Inter-Warehouse or Inter-Facility Stock Transfer Aggregate."""
    transfer_id: str
    tenant_id: str
    source_warehouse_id: str
    target_warehouse_id: str
    sku_code: str
    requested_qty: Decimal
    shipped_qty: Decimal = Decimal("0")
    received_qty: Decimal = Decimal("0")
    lot_code: str = ""
    status: TransferStatus = TransferStatus.REQUESTED
    carrier_code: str = ""
    tracking_number: str = ""
    version: int = 1
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def mark_allocated(self) -> None:
        if self.status != TransferStatus.REQUESTED:
            raise SupplyChainDomainError(f"Cannot allocate transfer in status {self.status}")
        self.status = TransferStatus.ALLOCATED
        self.version += 1

    def mark_picked(self) -> None:
        if self.status != TransferStatus.ALLOCATED:
            raise SupplyChainDomainError(f"Cannot mark picked in status {self.status}")
        self.status = TransferStatus.PICKED
        self.version += 1

    def dispatch(self, carrier: str, tracking: str, shipped_qty: Decimal) -> None:
        if self.status != TransferStatus.PICKED:
            raise SupplyChainDomainError(f"Cannot dispatch transfer in status {self.status}")
        if shipped_qty <= Decimal("0"):
            raise ValueError("Shipped quantity must be positive")
        self.carrier_code = carrier
        self.tracking_number = tracking
        self.shipped_qty = shipped_qty
        self.status = TransferStatus.IN_TRANSIT
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)

    def receive_at_destination(self, actual_received_qty: Decimal) -> None:
        if self.status != TransferStatus.IN_TRANSIT:
            raise SupplyChainDomainError(f"Cannot receive transfer in status {self.status}")
        self.received_qty = actual_received_qty
        if self.received_qty == self.shipped_qty:
            self.status = TransferStatus.RECONCILED
        else:
            self.status = TransferStatus.DISCREPANCY_FLAGGED
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)


@dataclass
class FulfillmentOrderAggregate:
    """Outbound pick-pack-ship order fulfillment workflow aggregate root."""
    order_id: str
    tenant_id: str
    customer_id: str
    items: List[Dict[str, Any]] = field(default_factory=list) # [{sku, qty, allocated_bin}]
    state: FulfillmentFsmState = FulfillmentFsmState.PENDING_ALLOCATION
    expected_weight_kg: Decimal = Decimal("0.00")
    actual_weight_kg: Optional[Decimal] = None
    manifest_id: Optional[str] = None
    carrier_tracking: Optional[str] = None
    version: int = 1
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def record_allocation(self, allocations: List[Dict[str, Any]], total_weight_kg: Decimal) -> None:
        if self.state != FulfillmentFsmState.PENDING_ALLOCATION:
            raise SupplyChainDomainError(f"Invalid transition from {self.state}")
        self.items = allocations
        self.expected_weight_kg = total_weight_kg
        self.state = FulfillmentFsmState.INVENTORY_ALLOCATED
        self.version += 1

    def release_to_wave(self) -> None:
        if self.state != FulfillmentFsmState.INVENTORY_ALLOCATED:
            raise SupplyChainDomainError(f"Cannot release to wave from {self.state}")
        self.state = FulfillmentFsmState.WAVE_RELEASED
        self.version += 1

    def start_picking(self) -> None:
        if self.state != FulfillmentFsmState.WAVE_RELEASED:
            raise SupplyChainDomainError(f"Cannot start picking from {self.state}")
        self.state = FulfillmentFsmState.PICKING
        self.version += 1

    def complete_picking(self) -> None:
        if self.state != FulfillmentFsmState.PICKING:
            raise SupplyChainDomainError(f"Cannot complete picking from {self.state}")
        self.state = FulfillmentFsmState.PICKED
        self.version += 1

    def start_packing(self) -> None:
        if self.state != FulfillmentFsmState.PICKED:
            raise SupplyChainDomainError(f"Cannot start packing from {self.state}")
        self.state = FulfillmentFsmState.PACKING
        self.version += 1

    def verify_packed_weight(self, scale_weight_kg: Decimal, tolerance_pct: Decimal = Decimal("0.03")) -> bool:
        """Anti-theft & error prevention: verify carton scale weight against BOM sum."""
        if self.state != FulfillmentFsmState.PACKING:
            raise SupplyChainDomainError(f"Cannot verify weight in state {self.state}")

        self.actual_weight_kg = scale_weight_kg
        margin = self.expected_weight_kg * tolerance_pct
        diff = abs(scale_weight_kg - self.expected_weight_kg)

        if diff > margin:
            raise SupplyChainDomainError(
                f"Weight mismatch! Expected: {self.expected_weight_kg}kg, Measured: {scale_weight_kg}kg (Diff: {diff}kg > {margin}kg)"
            )

        self.state = FulfillmentFsmState.PACKED_VERIFIED
        self.version += 1
        return True

    def generate_carrier_manifest(self, carrier: str, tracking_code: str) -> str:
        if self.state != FulfillmentFsmState.PACKED_VERIFIED:
            raise SupplyChainDomainError(f"Cannot manifest order before packing verification (current: {self.state})")

        self.carrier_tracking = tracking_code
        self.manifest_id = f"MAN-{self.order_id}-{carrier.upper()}"
        self.state = FulfillmentFsmState.MANIFEST_GENERATED
        self.version += 1
        return self.manifest_id

    def handoff_to_carrier(self) -> None:
        if self.state != FulfillmentFsmState.MANIFEST_GENERATED:
            raise SupplyChainDomainError(f"Cannot handoff unmanifested order from {self.state}")
        self.state = FulfillmentFsmState.CARRIER_DISPATCHED
        self.version += 1
        self.updated_at = dt.datetime.now(dt.timezone.utc)
