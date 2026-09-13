package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.warehouse.BinStatus;
import com.elmos.logistics.domain.model.warehouse.Warehouse;

import java.util.List;
import java.util.Optional;

public interface WarehouseRepository {
    Optional<Warehouse> findById(String warehouseId);
    Optional<Warehouse> findByCode(String tenantId, String code);
    List<Warehouse> findAllByTenantId(String tenantId);
    void save(Warehouse warehouse);
}
