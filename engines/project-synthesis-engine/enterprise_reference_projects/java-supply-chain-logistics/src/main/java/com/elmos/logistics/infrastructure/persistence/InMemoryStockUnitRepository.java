package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.inventory.AllocationStatus;
import com.elmos.logistics.domain.model.inventory.StockUnit;
import com.elmos.logistics.domain.repository.StockUnitRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.stream.Collectors;

/**
 * Thread-safe in-memory repository for StockUnits.
 * Employs ReentrantReadWriteLock to prevent concurrent reservation races.
 */
public class InMemoryStockUnitRepository implements StockUnitRepository {
    private final Map<String, StockUnit> storage = new ConcurrentHashMap<>();
    private final ReentrantReadWriteLock rwLock = new ReentrantReadWriteLock();

    @Override
    public Optional<StockUnit> findById(String stockUnitId) {
        rwLock.readLock().lock();
        try {
            return Optional.ofNullable(storage.get(stockUnitId));
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public Optional<StockUnit> findBySerialNumber(String tenantId, String serialNumber) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> u.getTenantId().equals(tenantId) && serialNumber.equals(u.getSerialNumber()))
                    .findFirst();
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public List<StockUnit> findByWarehouseIdAndSkuId(String warehouseId, String skuId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> u.getWarehouseId().equals(warehouseId) && u.getSkuId().equals(skuId))
                    .collect(Collectors.toList());
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public List<StockUnit> findAvailableUnits(String warehouseId, String skuId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> u.getWarehouseId().equals(warehouseId)
                            && u.getSkuId().equals(skuId)
                            && u.getStatus() == AllocationStatus.AVAILABLE)
                    .collect(Collectors.toList());
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public List<StockUnit> findAvailableUnitsForLot(String warehouseId, String skuId, String lotId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> u.getWarehouseId().equals(warehouseId)
                            && u.getSkuId().equals(skuId)
                            && u.getLotId().equals(lotId)
                            && u.getStatus() == AllocationStatus.AVAILABLE)
                    .collect(Collectors.toList());
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public List<StockUnit> findByBinId(String binId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> binId.equals(u.getCurrentBinId()))
                    .collect(Collectors.toList());
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public List<StockUnit> findByOrderId(String orderId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> orderId.equals(u.getReservedForOrderId()))
                    .collect(Collectors.toList());
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public List<StockUnit> findByWaveId(String waveId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> waveId.equals(u.getAllocatedWaveId()))
                    .collect(Collectors.toList());
        } finally {
            rwLock.readLock().unlock();
        }
    }

    @Override
    public void save(StockUnit unit) {
        rwLock.writeLock().lock();
        try {
            storage.put(unit.getStockUnitId(), unit);
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    @Override
    public void saveAll(List<StockUnit> units) {
        rwLock.writeLock().lock();
        try {
            for (StockUnit u : units) {
                storage.put(u.getStockUnitId(), u);
            }
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    @Override
    public long countAvailable(String warehouseId, String skuId) {
        rwLock.readLock().lock();
        try {
            return storage.values().stream()
                    .filter(u -> u.getWarehouseId().equals(warehouseId)
                            && u.getSkuId().equals(skuId)
                            && u.getStatus() == AllocationStatus.AVAILABLE)
                    .count();
        } finally {
            rwLock.readLock().unlock();
        }
    }
}
