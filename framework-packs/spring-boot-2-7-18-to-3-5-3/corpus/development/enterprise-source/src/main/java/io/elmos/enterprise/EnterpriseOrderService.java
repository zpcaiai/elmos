package io.elmos.enterprise;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import javax.persistence.EntityManager;
import javax.persistence.LockModeType;
import javax.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnterpriseOrderService {
    private final ObjectMapper objectMapper;

    @PersistenceContext
    private EntityManager entityManager;

    EnterpriseOrderService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Transactional
    public OrderView create(String requestId, long amountCents, boolean failAfterOutbox) {
        if (requestId == null || requestId.isBlank() || requestId.length() > 80) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }
        if (amountCents <= 0) {
            throw new IllegalArgumentException("INVALID_AMOUNT");
        }

        List<EnterpriseOrder> existing = entityManager.createQuery(
                "select o from EnterpriseOrder o where o.requestId = :requestId",
                EnterpriseOrder.class)
            .setParameter("requestId", requestId)
            .setMaxResults(1)
            .getResultList();
        if (!existing.isEmpty()) {
            return existing.get(0).view();
        }

        String orderId = UUID.nameUUIDFromBytes(requestId.getBytes(StandardCharsets.UTF_8)).toString();
        EnterpriseOrder order = new EnterpriseOrder(orderId, requestId, amountCents);
        String eventId = UUID.nameUUIDFromBytes(("order-created:" + requestId)
            .getBytes(StandardCharsets.UTF_8)).toString();
        String payload;
        try {
            payload = objectMapper.writeValueAsString(Map.of(
                "eventId", eventId,
                "orderId", orderId,
                "requestId", requestId));
        } catch (JsonProcessingException error) {
            throw new IllegalStateException("ORDER_EVENT_SERIALIZATION_FAILED", error);
        }

        entityManager.persist(order);
        entityManager.persist(new OutboxEvent(eventId, orderId, "ORDER_CREATED", payload));
        entityManager.flush();
        if (failAfterOutbox) {
            throw new IllegalStateException("FORCED_TRANSACTION_ROLLBACK");
        }
        return order.view();
    }

    @Transactional(readOnly = true)
    public OrderView findByRequestId(String requestId) {
        return entityManager.createQuery(
                "select o from EnterpriseOrder o where o.requestId = :requestId",
                EnterpriseOrder.class)
            .setParameter("requestId", requestId)
            .getSingleResult()
            .view();
    }

    @Transactional
    public void reserveInventory(String sku, long quantity) {
        InventoryItem item = entityManager.find(InventoryItem.class, sku, LockModeType.PESSIMISTIC_WRITE);
        if (item == null) {
            throw new IllegalStateException("INVENTORY_NOT_FOUND");
        }
        item.reserve(quantity);
    }
}
