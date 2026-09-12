package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.model.outbox.OutboxStatus;
import com.elmos.logistics.domain.repository.OutboxRepository;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryOutboxRepository implements OutboxRepository {
    private final Map<String, OutboxEvent> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<OutboxEvent> findById(String eventId) {
        return Optional.ofNullable(storage.get(eventId));
    }

    @Override
    public List<OutboxEvent> findPendingEvents(Instant now, int limit) {
        return storage.values().stream()
                .filter(e -> (e.getStatus() == OutboxStatus.PENDING || e.getStatus() == OutboxStatus.FAILED_RETRYABLE)
                        && !e.getNextAttemptAfter().isAfter(now))
                .sorted(Comparator.comparing(OutboxEvent::getCreatedAt))
                .limit(limit)
                .collect(Collectors.toList());
    }

    @Override
    public List<OutboxEvent> findByStatus(OutboxStatus status) {
        return storage.values().stream()
                .filter(e -> e.getStatus() == status)
                .collect(Collectors.toList());
    }

    @Override
    public void save(OutboxEvent event) {
        storage.put(event.getEventId(), event);
    }

    @Override
    public void saveAll(List<OutboxEvent> events) {
        for (OutboxEvent e : events) {
            storage.put(e.getEventId(), e);
        }
    }
}
