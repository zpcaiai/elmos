package com.elmos.logistics.presentation.dto;

import com.elmos.logistics.domain.model.transfer.TransferStatus;

import java.util.List;

public class StockTransferDto {
    public static class CreateTransferRequest {
        public String tenantId;
        public String sourceWarehouseId;
        public String destinationWarehouseId;
        public String orderNumber;
        public List<TransferLineItemDto> items;
    }

    public static class TransferLineItemDto {
        public String lineItemId;
        public String skuId;
        public String lotId;
        public int requestedQuantity;

        public TransferLineItemDto() {}

        public TransferLineItemDto(String lineItemId, String skuId, String lotId, int requestedQuantity) {
            this.lineItemId = lineItemId;
            this.skuId = skuId;
            this.lotId = lotId;
            this.requestedQuantity = requestedQuantity;
        }
    }

    public static class TransferSummaryResponse {
        public String transferOrderId;
        public String orderNumber;
        public String sourceWarehouseId;
        public String destinationWarehouseId;
        public TransferStatus status;
        public int totalRequested;
        public int totalShipped;
        public int totalReceived;
        public int discrepancyCount;

        public TransferSummaryResponse(String transferOrderId, String orderNumber, String sourceWarehouseId, String destinationWarehouseId, TransferStatus status, int totalRequested, int totalShipped, int totalReceived, int discrepancyCount) {
            this.transferOrderId = transferOrderId;
            this.orderNumber = orderNumber;
            this.sourceWarehouseId = sourceWarehouseId;
            this.destinationWarehouseId = destinationWarehouseId;
            this.status = status;
            this.totalRequested = totalRequested;
            this.totalShipped = totalShipped;
            this.totalReceived = totalReceived;
            this.discrepancyCount = discrepancyCount;
        }
    }
}
