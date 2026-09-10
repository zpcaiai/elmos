package com.elmos.logistics.presentation.controller;

import com.elmos.logistics.domain.model.wave.WaveBatch;
import com.elmos.logistics.domain.repository.WaveBatchRepository;
import com.elmos.logistics.presentation.dto.ApiResponse;
import com.elmos.logistics.presentation.dto.WavePickDto;

import java.util.Objects;
import java.util.UUID;

public class WavePickController {
    private final WaveBatchRepository waveRepository;

    public WavePickController(WaveBatchRepository waveRepository) {
        this.waveRepository = Objects.requireNonNull(waveRepository, "waveRepository must not be null");
    }

    public ApiResponse<WavePickDto.WaveSummaryResponse> createWave(WavePickDto.CreateWaveRequest request) {
        if (request.warehouseId == null || request.waveNumber == null) {
            return ApiResponse.error("INVALID_ARGUMENT", "warehouseId and waveNumber are required");
        }

        String waveId = UUID.randomUUID().toString();
        WaveBatch batch = new WaveBatch(waveId, request.tenantId, request.warehouseId, request.waveNumber);

        if (request.orderIds != null) {
            for (String orderId : request.orderIds) {
                batch.addOrder(orderId);
            }
        }

        waveRepository.save(batch);

        WavePickDto.WaveSummaryResponse response = new WavePickDto.WaveSummaryResponse(
                batch.getWaveBatchId(),
                batch.getWaveNumber(),
                batch.getWarehouseId(),
                batch.getStatus(),
                batch.getOrderIds().size(),
                batch.getTasks().size(),
                batch.getTotalUnits()
        );

        return ApiResponse.ok(response, "Wave batch created successfully");
    }
}
