package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.warehouse.BinStatus;

import java.util.List;
import java.util.Optional;

public interface BinRepository {
    Optional<Bin> findById(String binId);
    List<Bin> findByWarehouseId(String warehouseId);
    List<Bin> findByWarehouseIdAndZoneId(String warehouseId, String zoneId);
    List<Bin> findByWarehouseIdAndStatus(String warehouseId, BinStatus status);
    void save(Bin bin);
    void saveAll(List<Bin> bins);
}
