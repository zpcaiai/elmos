package com.elmos.logistics.presentation.controller;

import com.elmos.logistics.domain.model.transfer.StockTransferOrder;
import com.elmos.logistics.domain.model.transfer.TransferLineItem;
import com.elmos.logistics.domain.repository.StockTransferRepository;
import com.elmos.logistics.presentation.dto.ApiResponse;
import com.elmos.logistics.presentation.dto.StockTransferDto;

import java.util.Objects;
import java.util.UUID;

public class StockTransferController {
    private final StockTransferRepository transferRepository;

    public StockTransferController(StockTransferRepository transferRepository) {
        this.transferRepository = Objects.requireNonNull(transferRepository, "transferRepository must not be null");
    }

    public ApiResponse<StockTransferDto.TransferSummaryResponse> createTransferOrder(StockTransferDto.CreateTransferRequest request) {
        if (request.sourceWarehouseId == null || request.destinationWarehouseId == null || request.orderNumber == null) {
            return ApiResponse.error("INVALID_ARGUMENT", "sourceWarehouseId, destinationWarehouseId, and orderNumber are required");
        }

        String orderId = UUID.randomUUID().toString();
        StockTransferOrder order = new StockTransferOrder(
                orderId,
                request.tenantId,
                request.sourceWarehouseId,
                request.destinationWarehouseId,
                request.orderNumber
        );

        if (request.items != null) {
            for (StockTransferDto.TransferLineItemDto itemDto : request.items) {
                String lineId = itemDto.lineItemId != null ? itemDto.lineItemId : UUID.randomUUID().toString();
                TransferLineItem item = new TransferLineItem(lineId, itemDto.skuId, itemDto.lotId, itemDto.requestedQuantity);
                order.addLineItem(item);
            }
        }

        transferRepository.save(order);

        StockTransferDto.TransferSummaryResponse response = new StockTransferDto.TransferSummaryResponse(
                order.getTransferOrderId(),
                order.getOrderNumber(),
                order.getSourceWarehouseId(),
                order.getDestinationWarehouseId(),
                order.getStatus(),
                order.getTotalRequestedUnits(),
                order.getTotalShippedUnits(),
                order.getTotalReceivedUnits(),
                order.getDiscrepancies().size()
        );

        return ApiResponse.ok(response, "Stock transfer order initiated");
    }
}
