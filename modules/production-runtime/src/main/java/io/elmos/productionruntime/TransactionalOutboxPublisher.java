package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.OutboxMessage;

import java.time.Duration;
import java.util.List;
import java.util.Objects;

/** Publishes only after an external transport acknowledges each claimed event. */
public final class TransactionalOutboxPublisher {
    private final ProductionRuntimeStore store;
    private final Transport transport;

    public TransactionalOutboxPublisher(ProductionRuntimeStore store, Transport transport) {
        this.store = Objects.requireNonNull(store, "store");
        this.transport = Objects.requireNonNull(transport, "transport");
    }

    public PublishReport publish(int limit, Duration claimDuration) {
        List<OutboxMessage> events = store.claimOutbox(limit, claimDuration);
        int published = 0;
        int failed = 0;
        for (OutboxMessage event : events) {
            try {
                transport.publish(event);
                store.markOutboxPublished(event.claimToken(), event.id());
                published++;
            } catch (RuntimeException ex) {
                store.markOutboxFailed(event.claimToken(), event.id(), ex.getMessage());
                failed++;
            }
        }
        return new PublishReport(events.size(), published, failed);
    }

    public interface Transport { void publish(OutboxMessage event); }
    public record PublishReport(int claimed, int published, int failed) {}
}
