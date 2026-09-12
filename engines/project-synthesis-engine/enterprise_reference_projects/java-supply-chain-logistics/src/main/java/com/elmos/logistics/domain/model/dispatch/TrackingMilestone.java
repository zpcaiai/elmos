package com.elmos.logistics.domain.model.dispatch;

import java.time.Instant;
import java.util.Objects;

/**
 * An immutable checkpoint event recorded by the carrier network.
 */
public class TrackingMilestone {
    private final String milestoneId;
    private final Instant timestamp;
    private final String location;
    private final DeliveryStatus status;
    private final String description;

    public TrackingMilestone(String milestoneId,
                             Instant timestamp,
                             String location,
                             DeliveryStatus status,
                             String description) {
        this.milestoneId = Objects.requireNonNull(milestoneId, "milestoneId must not be null");
        this.timestamp = Objects.requireNonNull(timestamp, "timestamp must not be null");
        this.location = Objects.requireNonNull(location, "location must not be null");
        this.status = Objects.requireNonNull(status, "status must not be null");
        this.description = Objects.requireNonNull(description, "description must not be null");
    }

    public String getMilestoneId() {
        return milestoneId;
    }

    public Instant getTimestamp() {
        return timestamp;
    }

    public String getLocation() {
        return location;
    }

    public DeliveryStatus getStatus() {
        return status;
    }

    public String getDescription() {
        return description;
    }

    @Override
    public String toString() {
        return String.format("[%s] %s @ %s - %s", timestamp, status, location, description);
    }
}
