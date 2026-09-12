package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.warehouse.BinStatus;
import com.elmos.logistics.domain.repository.BinRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryBinRepository implements BinRepository {
    private final Map<String, Bin> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<Bin> findById(String binId) {
        return Optional.ofNullable(storage.get(binId));
    }

    @Override
    public List<Bin> findByWarehouseId(String warehouseId) {
        return storage.values().stream()
                .filter(b -> b.getWarehouseId().equals(warehouseId))
                .collect(Collectors.toList());
    }

    @Override
    public List<Bin> findByWarehouseIdAndZoneId(String warehouseId, String zoneId) {
        return storage.values().stream()
                .filter(b -> b.getWarehouseId().equals(warehouseId) && b.getZoneId().equals(zoneId))
                .collect(Collectors.toList());
    }

    @Override
    public List<Bin> findByWarehouseIdAndStatus(String warehouseId, BinStatus status) {
        return storage.values().stream()
                .filter(b -> b.getWarehouseId().equals(warehouseId) && b.getStatus() == status)
                .collect(Collectors.toList());
    }

    @Override
    public void save(Bin bin) {
        storage.put(bin.getBinId(), bin);
    }

    @Override
    public void saveAll(List<Bin> bins) {
        for (Bin b : bins) {
            storage.put(b.getBinId(), b);
        }
    }
}
