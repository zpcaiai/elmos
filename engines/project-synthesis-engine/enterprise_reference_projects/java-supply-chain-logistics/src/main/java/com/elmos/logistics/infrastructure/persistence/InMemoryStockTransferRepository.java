package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.transfer.StockTransferOrder;
import com.elmos.logistics.domain.model.transfer.TransferStatus;
import com.elmos.logistics.domain.repository.StockTransferRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryStockTransferRepository implements StockTransferRepository {
    private final Map<String, StockTransferOrder> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<StockTransferOrder> findById(String transferOrderId) {
        return Optional.ofNullable(storage.get(transferOrderId));
    }

    @Override
    public Optional<StockTransferOrder> findByOrderNumber(String tenantId, String orderNumber) {
        return storage.values().stream()
                .filter(o -> o.getTenantId().equals(tenantId) && o.getOrderNumber().equalsIgnoreCase(orderNumber))
                .findFirst();
    }

    @Override
    public List<StockTransferOrder> findBySourceWarehouseId(String warehouseId) {
        return storage.values().stream()
                .filter(o -> o.getSourceWarehouseId().equals(warehouseId))
                .collect(Collectors.toList());
    }

    @Override
    public List<StockTransferOrder> findByDestinationWarehouseId(String warehouseId) {
        return storage.values().stream()
                .filter(o -> o.getDestinationWarehouseId().equals(warehouseId))
                .collect(Collectors.toList());
    }

    @Override
    public List<StockTransferOrder> findByTenantIdAndStatus(String tenantId, TransferStatus status) {
        return storage.values().stream()
                .filter(o -> o.getTenantId().equals(tenantId) && o.getStatus() == status)
                .collect(Collectors.toList());
    }

    @Override
    public void save(StockTransferOrder order) {
        storage.put(order.getTransferOrderId(), order);
    }
}
