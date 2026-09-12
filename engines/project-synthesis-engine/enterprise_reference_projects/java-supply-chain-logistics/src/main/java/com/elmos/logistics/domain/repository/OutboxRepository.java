package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.model.outbox.OutboxStatus;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface OutboxRepository {
    Optional<OutboxEvent> findById(String eventId);
    List<OutboxEvent> findPendingEvents(Instant now, int limit);
    List<OutboxEvent> findByStatus(OutboxStatus status);
    void save(OutboxEvent event);
    void saveAll(List<OutboxEvent> events);
}
