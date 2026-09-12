package com.elmos.logistics.infrastructure.messaging;

import com.elmos.logistics.domain.model.outbox.OutboxEvent;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Event publisher representing an enterprise message broker (Kafka/RabbitMQ).
 */
public class OutboxEventPublisher {
    private final List<OutboxEvent> publishedLog = new CopyOnWriteArrayList<>();
    private boolean simulateBrokerFailure = false;

    public void setSimulateBrokerFailure(boolean fail) {
        this.simulateBrokerFailure = fail;
    }

    public void publish(OutboxEvent event) throws Exception {
        if (simulateBrokerFailure) {
            throw new RuntimeException("Simulated Kafka cluster broker connection timeout");
        }
        publishedLog.add(event);
    }

    public List<OutboxEvent> getPublishedLog() {
        return Collections.unmodifiableList(new ArrayList<>(publishedLog));
    }

    public void clear() {
        publishedLog.clear();
    }
}
