package io.elmos.persistence;

import static io.elmos.persistence.SqlTimestamps.offset;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.scm.WebhookIngestionService;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@Repository
public class JdbcWebhookDeliveryStore implements WebhookIngestionService.DeliveryStore {
    private final JdbcClient jdbc;
    private final ObjectMapper objectMapper;

    public JdbcWebhookDeliveryStore(JdbcClient jdbc, ObjectMapper objectMapper) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
    }

    @Override
    @Transactional
    public boolean recordAndEnqueueIfAbsent(WebhookIngestionService.Delivery delivery) {
        Objects.requireNonNull(delivery, "delivery");
        String organizationId = resolveOrganization(delivery);
        setTenant(organizationId);
        String recordId = UUID.randomUUID().toString();
        int rows = jdbc.sql("""
                insert into github_webhook_deliveries(
                    organization_id, webhook_delivery_id, github_delivery_id, event_type, action,
                    normalized_event_type, installation_external_id, repository_external_id,
                    payload_sha256, received_at, processing_status)
                values (
                    :organization, :id, :delivery, :event, :action,
                    :normalized, :installation, :repository,
                    :digest, :received, :status)
                on conflict (github_delivery_id) do nothing
                """)
                .param("organization", organizationId)
                .param("id", recordId)
                .param("delivery", delivery.deliveryId())
                .param("event", delivery.eventType())
                .param("action", delivery.action())
                .param("normalized", delivery.normalizedEventType())
                .param("installation", delivery.installationExternalId())
                .param("repository", delivery.repositoryExternalId())
                .param("digest", delivery.payloadSha256())
                .param("received", offset(delivery.receivedAt()))
                .param("status", delivery.normalizedEventType() == null ? "UNSUPPORTED" : "RECEIVED")
                .update();
        if (rows == 0) {
            int duplicates = jdbc.sql("""
                    update github_webhook_deliveries
                       set duplicate_count = duplicate_count + 1
                     where organization_id = :organization
                       and github_delivery_id = :delivery
                       and payload_sha256 = :digest
                    """)
                    .param("organization", organizationId)
                    .param("delivery", delivery.deliveryId())
                    .param("digest", delivery.payloadSha256())
                    .update();
            if (duplicates != 1) {
                throw new WebhookIngestionService.ResourceBindingException();
            }
            return false;
        }
        if (delivery.normalizedEventType() == null) {
            return true;
        }
        try {
            String attributes = objectMapper.writeValueAsString(Map.of(
                    "deliveryId", delivery.deliveryId(),
                    "eventType", delivery.eventType(),
                    "payloadSha256", delivery.payloadSha256()));
            jdbc.sql("""
                    insert into outbox_events(
                        organization_id, event_id, aggregate_type, aggregate_id,
                        event_type, occurred_at, attributes)
                    values (
                        :organization, :id, 'GITHUB_WEBHOOK', :aggregate,
                        :event, :occurred, :attributes)
                    """)
                    .param("organization", organizationId)
                    .param("id", UUID.randomUUID().toString())
                    .param("aggregate", recordId)
                    .param("event", delivery.normalizedEventType())
                    .param("occurred", offset(delivery.receivedAt()))
                    .param("attributes", attributes)
                    .update();
            return true;
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "unable to normalize webhook outbox event", exception);
        }
    }

    private String resolveOrganization(WebhookIngestionService.Delivery delivery) {
        try {
            String organizationId = jdbc.sql("""
                    select public.elmos_resolve_github_webhook_organization(
                        :installation, :repository)
                    """)
                    .param("installation", delivery.installationExternalId())
                    .param("repository", delivery.repositoryExternalId())
                    .query(String.class)
                    .single();
            if (organizationId == null
                    || !organizationId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
                throw new WebhookIngestionService.ResourceBindingException();
            }
            return organizationId;
        } catch (DataAccessException exception) {
            throw new WebhookIngestionService.ResourceBindingException();
        }
    }

    private void setTenant(String organizationId) {
        jdbc.sql("select set_config('app.organization_id', :organization, true)")
                .param("organization", organizationId)
                .query(String.class)
                .single();
    }
}
