package com.elmos.logistics.presentation.dto;

import com.elmos.logistics.domain.model.inventory.AllocationPolicy;

import java.util.List;

public class InventoryAllocationDto {
    public static class AllocationRequest {
        public String warehouseId;
        public String orderId;
        public String skuId;
        public int quantity;
        public AllocationPolicy policy;
    }

    public static class AllocationResponse {
        public String orderId;
        public String skuId;
        public int requestedQuantity;
        public int allocatedQuantity;
        public boolean fullyAllocated;
        public List<String> allocatedStockUnitIds;
        public String failureReason;

        public AllocationResponse(String orderId, String skuId, int requestedQuantity, int allocatedQuantity, boolean fullyAllocated, List<String> allocatedStockUnitIds, String failureReason) {
            this.orderId = orderId;
            this.skuId = skuId;
            this.requestedQuantity = requestedQuantity;
            this.allocatedQuantity = allocatedQuantity;
            this.fullyAllocated = fullyAllocated;
            this.allocatedStockUnitIds = allocatedStockUnitIds;
            this.failureReason = failureReason;
        }
    }
}
