package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.inventory.InventoryLot;

import java.util.List;
import java.util.Optional;

public interface InventoryLotRepository {
    Optional<InventoryLot> findById(String lotId);
    Optional<InventoryLot> findByLotNumber(String skuId, String lotNumber);
    List<InventoryLot> findAvailableLotsBySkuId(String skuId);
    void save(InventoryLot lot);
}
