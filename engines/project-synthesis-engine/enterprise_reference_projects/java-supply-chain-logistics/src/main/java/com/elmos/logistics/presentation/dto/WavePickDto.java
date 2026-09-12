package com.elmos.logistics.presentation.dto;

import com.elmos.logistics.domain.model.wave.WaveStatus;

import java.util.List;

public class WavePickDto {
    public static class CreateWaveRequest {
        public String tenantId;
        public String warehouseId;
        public String waveNumber;
        public List<String> orderIds;
    }

    public static class WaveSummaryResponse {
        public String waveBatchId;
        public String waveNumber;
        public String warehouseId;
        public WaveStatus status;
        public int orderCount;
        public int taskCount;
        public int totalUnits;

        public WaveSummaryResponse(String waveBatchId, String waveNumber, String warehouseId, WaveStatus status, int orderCount, int taskCount, int totalUnits) {
            this.waveBatchId = waveBatchId;
            this.waveNumber = waveNumber;
            this.warehouseId = warehouseId;
            this.status = status;
            this.orderCount = orderCount;
            this.taskCount = taskCount;
            this.totalUnits = totalUnits;
        }
    }
}
