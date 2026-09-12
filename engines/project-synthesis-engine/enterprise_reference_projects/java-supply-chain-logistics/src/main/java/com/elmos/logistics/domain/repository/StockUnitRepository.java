package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.inventory.AllocationStatus;
import com.elmos.logistics.domain.model.inventory.StockUnit;

import java.util.List;
import java.util.Optional;

public interface StockUnitRepository {
    Optional<StockUnit> findById(String stockUnitId);
    Optional<StockUnit> findBySerialNumber(String tenantId, String serialNumber);
    List<StockUnit> findByWarehouseIdAndSkuId(String warehouseId, String skuId);
    List<StockUnit> findAvailableUnits(String warehouseId, String skuId);
    List<StockUnit> findAvailableUnitsForLot(String warehouseId, String skuId, String lotId);
    List<StockUnit> findByBinId(String binId);
    List<StockUnit> findByOrderId(String orderId);
    List<StockUnit> findByWaveId(String waveId);
    void save(StockUnit unit);
    void saveAll(List<StockUnit> units);
    long countAvailable(String warehouseId, String skuId);
}
