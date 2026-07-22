package io.elmos.persistence;

import io.elmos.scm.WebhookIngestionService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;
import java.util.UUID;

@Repository
public final class JdbcWebhookDeliveryStore implements WebhookIngestionService.DeliveryStore {
    private final JdbcClient jdbc; private final ObjectMapper objectMapper;
    public JdbcWebhookDeliveryStore(JdbcClient jdbc, ObjectMapper objectMapper) { this.jdbc = jdbc; this.objectMapper = objectMapper; }

    @Override @Transactional public boolean recordAndEnqueueIfAbsent(WebhookIngestionService.Delivery delivery) {
        int rows = jdbc.sql("""
                insert into github_webhook_deliveries(webhook_delivery_id, github_delivery_id, event_type, action,
                    normalized_event_type, installation_external_id, repository_external_id, payload_sha256, received_at, processing_status)
                values (:id, :delivery, :event, :action, :normalized, :installation, :repository, :digest, :received, :status)
                on conflict (github_delivery_id) do nothing
                """).param("id", UUID.randomUUID().toString()).param("delivery", delivery.deliveryId())
                .param("event", delivery.eventType()).param("action", delivery.action()).param("normalized", delivery.normalizedEventType())
                .param("installation", delivery.installationExternalId()).param("repository", delivery.repositoryExternalId())
                .param("digest", delivery.payloadSha256()).param("received", delivery.receivedAt())
                .param("status", delivery.normalizedEventType() == null ? "UNSUPPORTED" : "RECEIVED").update();
        if (rows == 0) {
            jdbc.sql("update github_webhook_deliveries set duplicate_count = duplicate_count + 1 where github_delivery_id = :delivery")
                    .param("delivery", delivery.deliveryId()).update();
            return false;
        }
        if (delivery.normalizedEventType() == null) return true;
        try {
            String attributes = objectMapper.writeValueAsString(Map.of(
                    "deliveryId", delivery.deliveryId(), "eventType", delivery.eventType(), "payloadSha256", delivery.payloadSha256()));
            jdbc.sql("insert into outbox_events(event_id, aggregate_type, aggregate_id, event_type, occurred_at, attributes) values (:id, 'GITHUB_WEBHOOK', :aggregate, :event, :occurred, :attributes)")
                    .param("id", UUID.randomUUID().toString()).param("aggregate", delivery.deliveryId())
                    .param("event", delivery.normalizedEventType())
                    .param("occurred", delivery.receivedAt()).param("attributes", attributes).update();
            return true;
        } catch (JsonProcessingException exception) { throw new IllegalStateException("unable to normalize webhook outbox event", exception); }
    }
}
