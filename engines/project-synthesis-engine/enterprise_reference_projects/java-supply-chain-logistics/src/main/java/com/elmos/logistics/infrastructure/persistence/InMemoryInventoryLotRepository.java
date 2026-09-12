package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.inventory.InventoryLot;
import com.elmos.logistics.domain.repository.InventoryLotRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryInventoryLotRepository implements InventoryLotRepository {
    private final Map<String, InventoryLot> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<InventoryLot> findById(String lotId) {
        return Optional.ofNullable(storage.get(lotId));
    }

    @Override
    public Optional<InventoryLot> findByLotNumber(String skuId, String lotNumber) {
        return storage.values().stream()
                .filter(l -> l.getSkuId().equals(skuId) && l.getLotNumber().equalsIgnoreCase(lotNumber))
                .findFirst();
    }

    @Override
    public List<InventoryLot> findAvailableLotsBySkuId(String skuId) {
        return storage.values().stream()
                .filter(l -> l.getSkuId().equals(skuId) && l.getRemainingQuantity() > 0 && !l.isQuarantined())
                .collect(Collectors.toList());
    }

    @Override
    public void save(InventoryLot lot) {
        storage.put(lot.getLotId(), lot);
    }
}
