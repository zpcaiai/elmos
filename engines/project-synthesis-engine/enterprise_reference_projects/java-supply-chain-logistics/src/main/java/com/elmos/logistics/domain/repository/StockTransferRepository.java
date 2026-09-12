package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.transfer.StockTransferOrder;
import com.elmos.logistics.domain.model.transfer.TransferStatus;

import java.util.List;
import java.util.Optional;

public interface StockTransferRepository {
    Optional<StockTransferOrder> findById(String transferOrderId);
    Optional<StockTransferOrder> findByOrderNumber(String tenantId, String orderNumber);
    List<StockTransferOrder> findBySourceWarehouseId(String warehouseId);
    List<StockTransferOrder> findByDestinationWarehouseId(String warehouseId);
    List<StockTransferOrder> findByTenantIdAndStatus(String tenantId, TransferStatus status);
    void save(StockTransferOrder order);
}
