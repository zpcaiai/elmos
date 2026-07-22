package io.elmos.domain;

import java.time.Instant;
import java.util.Map;

public record DomainEvent(String eventId, String eventType, String aggregateId, Instant occurredAt, Map<String, String> attributes) {
    public DomainEvent {
        eventId = Identifiers.require(eventId, "eventId");
        eventType = Identifiers.require(eventType, "eventType");
        aggregateId = Identifiers.require(aggregateId, "aggregateId");
        if (occurredAt == null) throw new IllegalArgumentException("occurredAt is required");
        attributes = Map.copyOf(attributes == null ? Map.of() : attributes);
    }
}

