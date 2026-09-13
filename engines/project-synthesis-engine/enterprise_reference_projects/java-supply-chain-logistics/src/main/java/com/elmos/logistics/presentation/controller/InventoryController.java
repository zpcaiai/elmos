package com.elmos.logistics.presentation.controller;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.inventory.StockUnit;
import com.elmos.logistics.domain.service.InventoryAllocationEngine;
import com.elmos.logistics.presentation.dto.ApiResponse;
import com.elmos.logistics.presentation.dto.InventoryAllocationDto;

import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class InventoryController {
    private final InventoryAllocationEngine allocationEngine;

    public InventoryController(InventoryAllocationEngine allocationEngine) {
        this.allocationEngine = Objects.requireNonNull(allocationEngine, "allocationEngine must not be null");
    }

    public ApiResponse<InventoryAllocationDto.AllocationResponse> allocateInventory(InventoryAllocationDto.AllocationRequest request) {
        if (request.warehouseId == null || request.skuId == null || request.quantity <= 0) {
            return ApiResponse.error("INVALID_ARGUMENT", "warehouseId, skuId, and positive quantity required");
        }

        InventoryAllocationEngine.AllocationResult result = allocationEngine.allocateStock(
                request.warehouseId,
                request.orderId,
                request.skuId,
                request.quantity,
                request.policy,
                Coordinates3D.origin()
        );

        List<String> unitIds = result.getAllocatedUnits().stream()
                .map(StockUnit::getStockUnitId)
                .collect(Collectors.toList());

        InventoryAllocationDto.AllocationResponse response = new InventoryAllocationDto.AllocationResponse(
                result.getOrderId(),
                result.getSkuId(),
                result.getRequestedQuantity(),
                result.getAllocatedQuantity(),
                result.isFullyAllocated(),
                unitIds,
                result.getFailureReason()
        );

        if (result.isFullyAllocated()) {
            return ApiResponse.ok(response, "Stock successfully allocated");
        } else {
            return ApiResponse.error("INSUFFICIENT_STOCK", result.getFailureReason());
        }
    }
}
