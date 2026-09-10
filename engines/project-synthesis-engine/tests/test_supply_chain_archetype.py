"""Unit and integration tests for Industrial Multi-Warehouse Supply Chain Archetype."""
from decimal import Decimal
import datetime as dt
import pytest

from elmos_project_synthesis.domain_archetypes.supply_chain_archetype import (
    StorageZoneType,
    InventoryStatus,
    TransferStatus,
    FulfillmentFsmState,
    Sku,
    BinLocation,
    LotNumber,
    PhysicalDimension,
    PhysicalWeight,
    InventoryBinAggregate,
    StockTransferAggregate,
    FulfillmentOrderAggregate,
    SupplyChainDomainError,
    InventoryAllocationError,
)


def test_sku_and_location_validation():
    sku = Sku("SKU-PROD-99", "Industrial Sensor", "Sensors", "012345678901")
    assert sku.code == "SKU-PROD-99"

    with pytest.raises(ValueError, match="Invalid SKU format"):
        _ = Sku("invalid*sku", "Bad Sku", "Misc")

    loc = BinLocation("A01", "R05", "S02", "B09", StorageZoneType.COLD_STORAGE)
    assert loc.coordinate == "A01-R05-S02-B09"
    assert loc.zone == StorageZoneType.COLD_STORAGE

    dim = PhysicalDimension(Decimal("10.0"), Decimal("20.0"), Decimal("30.0"))
    assert dim.volume_m3 == Decimal("0.0060")

    wt_kg = PhysicalWeight(Decimal("5.5"), "KG")
    assert wt_kg.to_kg() == Decimal("5.5")
    wt_lb = PhysicalWeight(Decimal("10.0"), "LB")
    assert wt_lb.to_kg().quantize(Decimal("0.01")) == Decimal("4.54")


def test_bin_stock_receiving_allocation_and_picking():
    loc = BinLocation("A01", "R01", "S01", "B01")
    bin_agg = InventoryBinAggregate(
        bin_id="bin-101",
        warehouse_id="wh-east",
        location=loc,
        max_weight_kg=Decimal("500.0"),
    )

    sku = Sku("SKU-101", "Widget A", "Hardware")
    valid_lot = LotNumber("LOT-2026A", dt.date.today(), dt.date.today() + dt.timedelta(days=180), "SUPP-1")

    # Inbound receipt
    bin_agg.receive_stock(sku, Decimal("100"), valid_lot)
    assert bin_agg.get_on_hand(sku.code) == Decimal("100")
    assert bin_agg.get_available(sku.code) == Decimal("100")

    # Stock reservation/allocation
    bin_agg.allocate_stock(sku.code, Decimal("30"))
    assert bin_agg.get_allocated(sku.code) == Decimal("30")
    assert bin_agg.get_available(sku.code) == Decimal("70")

    # Excessive allocation
    with pytest.raises(InventoryAllocationError, match="Insufficient stock"):
        bin_agg.allocate_stock(sku.code, Decimal("80"))

    # Pick stock during fulfillment
    bin_agg.pick_stock(sku.code, Decimal("30"))
    assert bin_agg.get_allocated(sku.code) == Decimal("0")
    assert bin_agg.get_on_hand(sku.code) == Decimal("70")
    assert bin_agg.get_available(sku.code) == Decimal("70")

    # Quarantine damaged stock
    bin_agg.quarantine_stock(sku.code, Decimal("10"), "Water damage")
    assert bin_agg.get_quarantined(sku.code) == Decimal("10")
    assert bin_agg.get_available(sku.code) == Decimal("60")


def test_inter_warehouse_stock_transfer_lifecycle():
    xfer = StockTransferAggregate(
        transfer_id="xfer-001",
        tenant_id="tenant-1",
        source_warehouse_id="wh-east",
        target_warehouse_id="wh-west",
        sku_code="SKU-101",
        requested_qty=Decimal("50"),
    )

    assert xfer.status == TransferStatus.REQUESTED
    xfer.mark_allocated()
    assert xfer.status == TransferStatus.ALLOCATED
    xfer.mark_picked()
    assert xfer.status == TransferStatus.PICKED

    xfer.dispatch("FEDEX_FREIGHT", "TRACK-998877", Decimal("50"))
    assert xfer.status == TransferStatus.IN_TRANSIT

    # Perfect reconciliation at destination
    xfer.receive_at_destination(Decimal("50"))
    assert xfer.status == TransferStatus.RECONCILED

    # Discrepancy case
    xfer2 = StockTransferAggregate("xfer-002", "t1", "wh1", "wh2", "SKU-102", Decimal("100"))
    xfer2.mark_allocated()
    xfer2.mark_picked()
    xfer2.dispatch("UPS", "TRACK-1122", Decimal("100"))
    xfer2.receive_at_destination(Decimal("95")) # 5 missing
    assert xfer2.status == TransferStatus.DISCREPANCY_FLAGGED


def test_fulfillment_pick_pack_ship_fsm():
    order = FulfillmentOrderAggregate(
        order_id="order-ful-01",
        tenant_id="t1",
        customer_id="cust-88",
    )

    assert order.state == FulfillmentFsmState.PENDING_ALLOCATION

    order.record_allocation([{"sku": "SKU-A", "qty": 2, "bin": "bin-101"}], total_weight_kg=Decimal("10.00"))
    assert order.state == FulfillmentFsmState.INVENTORY_ALLOCATED

    order.release_to_wave()
    assert order.state == FulfillmentFsmState.WAVE_RELEASED

    order.start_picking()
    assert order.state == FulfillmentFsmState.PICKING

    order.complete_picking()
    assert order.state == FulfillmentFsmState.PICKED

    order.start_packing()
    assert order.state == FulfillmentFsmState.PACKING

    # Weight verification within 3% tolerance
    verified = order.verify_packed_weight(Decimal("10.15")) # +1.5% ok
    assert verified
    assert order.state == FulfillmentFsmState.PACKED_VERIFIED

    # Weight verification mismatch (> 3%)
    order_bad = FulfillmentOrderAggregate("o2", "t1", "c1")
    order_bad.record_allocation([], total_weight_kg=Decimal("10.00"))
    order_bad.release_to_wave()
    order_bad.start_picking()
    order_bad.complete_picking()
    order_bad.start_packing()
    with pytest.raises(SupplyChainDomainError, match="Weight mismatch"):
        order_bad.verify_packed_weight(Decimal("11.50")) # 15% discrepancy

    # Manifest and carrier handoff
    manifest_id = order.generate_carrier_manifest("DHL_EXPRESS", "DHL-99220011")
    assert "MAN-order-ful-01" in manifest_id
    assert order.state == FulfillmentFsmState.MANIFEST_GENERATED

    order.handoff_to_carrier()
    assert order.state == FulfillmentFsmState.CARRIER_DISPATCHED
