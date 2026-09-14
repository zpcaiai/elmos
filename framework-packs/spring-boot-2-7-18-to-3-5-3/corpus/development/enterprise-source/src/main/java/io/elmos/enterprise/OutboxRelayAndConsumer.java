package io.elmos.enterprise;

import java.time.Instant;
import java.sql.Timestamp;
import java.util.List;
import javax.persistence.EntityManager;
import javax.persistence.LockModeType;
import javax.persistence.PersistenceContext;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
class OutboxRelay {
    private final RabbitTemplate rabbitTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    OutboxRelay(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Transactional
    public int publishPending() {
        List<OutboxEvent> events = entityManager.createQuery(
                "select e from OutboxEvent e where e.published = false order by e.createdAt",
                OutboxEvent.class)
            .setLockMode(LockModeType.PESSIMISTIC_WRITE)
            .setMaxResults(100)
            .getResultList();
        for (OutboxEvent event : events) {
            rabbitTemplate.invoke(operations -> {
                operations.convertAndSend(
                    MessagingConfiguration.EXCHANGE,
                    MessagingConfiguration.ROUTING_KEY,
                    event.payload(),
                    message -> {
                        message.getMessageProperties().setMessageId(event.id());
                        message.getMessageProperties().setContentType(MessageProperties.CONTENT_TYPE_JSON);
                        return message;
                    });
                if (!operations.waitForConfirms(10_000)) {
                    throw new AmqpException("BROKER_CONFIRM_NOT_RECEIVED");
                }
                return null;
            });
            event.markPublished();
        }
        return events.size();
    }
}

@Component
class OrderEventConsumer {
    private final JdbcTemplate jdbcTemplate;

    OrderEventConsumer(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @RabbitListener(queues = MessagingConfiguration.QUEUE)
    @Transactional
    public void consume(String payload, Message message) {
        String messageId = message.getMessageProperties().getMessageId();
        if (messageId == null || messageId.isBlank()) {
            throw new IllegalArgumentException("MESSAGE_ID_REQUIRED");
        }
        jdbcTemplate.update(
            "insert into enterprise_consumed_events "
                + "(message_id, payload, handled_count, consumed_at) values (?, ?, 1, ?) "
                + "on conflict (message_id) do nothing",
            messageId,
            payload,
            Timestamp.from(Instant.now()));
    }
}
