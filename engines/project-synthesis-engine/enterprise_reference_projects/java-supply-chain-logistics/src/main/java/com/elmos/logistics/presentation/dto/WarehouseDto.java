package com.elmos.logistics.presentation.dto;

public class WarehouseDto {
    public static class CreateWarehouseRequest {
        public String warehouseId;
        public String tenantId;
        public String code;
        public String name;
        public String address;
        public int dockXMm;
        public int dockYMm;
        public int dockZMm;
        public int bayXMm;
        public int bayYMm;
        public int bayZMm;
    }

    public static class WarehouseSummaryResponse {
        public String warehouseId;
        public String code;
        public String name;
        public String address;
        public int zoneCount;
        public long totalBins;
        public long availableBins;
        public boolean active;

        public WarehouseSummaryResponse(String warehouseId, String code, String name, String address, int zoneCount, long totalBins, long availableBins, boolean active) {
            this.warehouseId = warehouseId;
            this.code = code;
            this.name = name;
            this.address = address;
            this.zoneCount = zoneCount;
            this.totalBins = totalBins;
            this.availableBins = availableBins;
            this.active = active;
        }
    }
}
