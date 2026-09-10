package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.wave.WaveBatch;
import com.elmos.logistics.domain.model.wave.WaveStatus;

import java.util.List;
import java.util.Optional;

public interface WaveBatchRepository {
    Optional<WaveBatch> findById(String waveBatchId);
    Optional<WaveBatch> findByWaveNumber(String tenantId, String waveNumber);
    List<WaveBatch> findByWarehouseIdAndStatus(String warehouseId, WaveStatus status);
    List<WaveBatch> findAllByWarehouseId(String warehouseId);
    void save(WaveBatch waveBatch);
}
