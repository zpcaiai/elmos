package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.warehouse.Warehouse;
import com.elmos.logistics.domain.repository.WarehouseRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryWarehouseRepository implements WarehouseRepository {
    private final Map<String, Warehouse> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<Warehouse> findById(String warehouseId) {
        return Optional.ofNullable(storage.get(warehouseId));
    }

    @Override
    public Optional<Warehouse> findByCode(String tenantId, String code) {
        return storage.values().stream()
                .filter(w -> w.getTenantId().equals(tenantId) && w.getCode().equalsIgnoreCase(code))
                .findFirst();
    }

    @Override
    public List<Warehouse> findAllByTenantId(String tenantId) {
        return storage.values().stream()
                .filter(w -> w.getTenantId().equals(tenantId))
                .collect(Collectors.toList());
    }

    @Override
    public void save(Warehouse warehouse) {
        storage.put(warehouse.getWarehouseId(), warehouse);
    }
}
