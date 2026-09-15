package io.elmos.enterprise;

import java.time.Instant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "enterprise_orders")
class EnterpriseOrder {
    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "request_id", nullable = false, unique = true, length = 80)
    private String requestId;

    @Column(name = "amount_cents", nullable = false)
    private long amountCents;

    @Column(nullable = false, length = 24)
    private String status;

    protected EnterpriseOrder() {}

    EnterpriseOrder(String id, String requestId, long amountCents) {
        this.id = id;
        this.requestId = requestId;
        this.amountCents = amountCents;
        this.status = "CREATED";
    }

    OrderView view() {
        return new OrderView(id, requestId, amountCents, status);
    }
}

@Entity
@Table(name = "enterprise_inventory")
class InventoryItem {
    @Id
    @Column(length = 80)
    private String sku;

    @Column(nullable = false)
    private long available;

    protected InventoryItem() {}

    void reserve(long quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalStateException("INVENTORY_NOT_AVAILABLE");
        }
        available -= quantity;
    }
}

@Entity
@Table(name = "enterprise_outbox")
class OutboxEvent {
    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "aggregate_id", nullable = false, length = 36)
    private String aggregateId;

    @Column(name = "event_type", nullable = false, length = 80)
    private String eventType;

    @Column(nullable = false, columnDefinition = "text")
    private String payload;

    @Column(nullable = false)
    private boolean published;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected OutboxEvent() {}

    OutboxEvent(String id, String aggregateId, String eventType, String payload) {
        this.id = id;
        this.aggregateId = aggregateId;
        this.eventType = eventType;
        this.payload = payload;
        this.published = false;
        this.createdAt = Instant.now();
    }

    String id() {
        return id;
    }

    String payload() {
        return payload;
    }

    void markPublished() {
        published = true;
    }
}

record OrderView(String id, String requestId, long amountCents, String status) {}
