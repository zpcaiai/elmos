package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.wave.WaveBatch;
import com.elmos.logistics.domain.model.wave.WaveStatus;
import com.elmos.logistics.domain.repository.WaveBatchRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryWaveBatchRepository implements WaveBatchRepository {
    private final Map<String, WaveBatch> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<WaveBatch> findById(String waveBatchId) {
        return Optional.ofNullable(storage.get(waveBatchId));
    }

    @Override
    public Optional<WaveBatch> findByWaveNumber(String tenantId, String waveNumber) {
        return storage.values().stream()
                .filter(w -> w.getTenantId().equals(tenantId) && w.getWaveNumber().equalsIgnoreCase(waveNumber))
                .findFirst();
    }

    @Override
    public List<WaveBatch> findByWarehouseIdAndStatus(String warehouseId, WaveStatus status) {
        return storage.values().stream()
                .filter(w -> w.getWarehouseId().equals(warehouseId) && w.getStatus() == status)
                .collect(Collectors.toList());
    }

    @Override
    public List<WaveBatch> findAllByWarehouseId(String warehouseId) {
        return storage.values().stream()
                .filter(w -> w.getWarehouseId().equals(warehouseId))
                .collect(Collectors.toList());
    }

    @Override
    public void save(WaveBatch waveBatch) {
        storage.put(waveBatch.getWaveBatchId(), waveBatch);
    }
}
