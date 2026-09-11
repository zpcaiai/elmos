package io.elmos.worker.messaging;

import io.elmos.worker.messaging.SpringAsyncMessagingDifferentialComparator.MessageEvent;
import io.elmos.worker.messaging.SpringAsyncMessagingDifferentialComparator.MessagingEquivalenceVerdict;
import org.junit.jupiter.api.Test;

import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class SpringAsyncMessagingDifferentialComparatorTest {

    private final SpringAsyncMessagingDifferentialComparator comparator = new SpringAsyncMessagingDifferentialComparator();

    @Test
    void shouldPassWhenStreamsAreIdentical() {
        MessageEvent e1 = new MessageEvent(
                "msg-1", "order-topic", "order-1001",
                Map.of("Content-Type", "application/json"),
                "{\"orderId\": 1001, \"status\": \"PAID\", \"amount\": 99.50}",
                System.currentTimeMillis()
        );

        MessagingEquivalenceVerdict verdict = comparator.compareStreams(List.of(e1), List.of(e1));

        assertThat(verdict.isEquivalent()).isTrue();
        assertThat(verdict.matchedCount()).isEqualTo(1);
        assertThat(verdict.mismatches()).isEmpty();
        assertThat(verdict.equivalenceScore()).isEqualTo(100.0);
    }

    @Test
    void shouldMaskEphemeralNoiseFields() {
        MessageEvent baseline = new MessageEvent(
                "msg-base-001", "payment-events", "user-888",
                Map.of(),
                "{\"userId\": 888, \"action\": \"DEPOSIT\", \"timestamp\": 1600000000, \"traceId\": \"trace-old-1\", \"uuid\": \"uuid-old\"}",
                1600000000L
        );

        MessageEvent modernized = new MessageEvent(
                "msg-mod-999", "payment-events", "user-888",
                Map.of(),
                "{\"userId\": 888, \"action\": \"DEPOSIT\", \"timestamp\": 1750000000, \"traceId\": \"trace-new-2\", \"uuid\": \"uuid-new\"}",
                1750000000L
        );

        MessagingEquivalenceVerdict verdict = comparator.compareStreams(List.of(baseline), List.of(modernized));

        assertThat(verdict.isEquivalent()).isTrue();
        assertThat(verdict.matchedCount()).isEqualTo(1);
        assertThat(verdict.mismatches()).isEmpty();
        assertThat(verdict.equivalenceScore()).isEqualTo(100.0);
    }

    @Test
    void shouldRespectFloatingPointTolerance() {
        MessageEvent baseline = new MessageEvent(
                "msg-1", "telemetry", "k1", Map.of(),
                "{\"metric\": \"cpu_load\", \"value\": 0.75001}", 0L
        );
        MessageEvent modernized = new MessageEvent(
                "msg-1", "telemetry", "k1", Map.of(),
                "{\"metric\": \"cpu_load\", \"value\": 0.75002}", 0L
        );

        MessagingEquivalenceVerdict verdict = comparator.compareStreams(List.of(baseline), List.of(modernized));

        assertThat(verdict.isEquivalent()).isTrue();
        assertThat(verdict.mismatches()).isEmpty();
    }

    @Test
    void shouldDetectTopicAndPartitionMismatches() {
        MessageEvent baseline = new MessageEvent(
                "msg-1", "order-topic-v1", "key-A", Map.of(),
                "{\"amount\": 100}", 0L
        );
        MessageEvent modernized = new MessageEvent(
                "msg-1", "order-topic-v2", "key-B", Map.of(),
                "{\"amount\": 100}", 0L
        );

        MessagingEquivalenceVerdict verdict = comparator.compareStreams(List.of(baseline), List.of(modernized));

        assertThat(verdict.isEquivalent()).isFalse();
        assertThat(verdict.mismatches()).hasSize(2);
        assertThat(verdict.mismatches()).anyMatch(m -> m.fieldName().equals("topic"));
        assertThat(verdict.mismatches()).anyMatch(m -> m.fieldName().equals("partitionKey"));
    }

    @Test
    void shouldDetectBusinessPayloadDivergence() {
        MessageEvent baseline = new MessageEvent(
                "msg-1", "trade-events", "trade-99", Map.of(),
                "{\"tradeId\": 99, \"price\": 450.0, \"currency\": \"CNY\"}", 0L
        );
        MessageEvent modernized = new MessageEvent(
                "msg-1", "trade-events", "trade-99", Map.of(),
                "{\"tradeId\": 99, \"price\": 460.0, \"currency\": \"USD\"}", 0L
        );

        MessagingEquivalenceVerdict verdict = comparator.compareStreams(List.of(baseline), List.of(modernized));

        assertThat(verdict.isEquivalent()).isFalse();
        assertThat(verdict.mismatches()).hasSize(2);
        assertThat(verdict.mismatches()).anyMatch(m -> m.fieldName().equals("price"));
        assertThat(verdict.mismatches()).anyMatch(m -> m.fieldName().equals("currency"));
    }

    @Test
    void shouldHandleEmptyOrNullStreams() {
        var v1 = comparator.compareStreams(Collections.emptyList(), Collections.emptyList());
        assertThat(v1.isEquivalent()).isTrue();
        assertThat(v1.totalMessagesCompared()).isZero();

        var v2 = comparator.compareStreams(
                List.of(new MessageEvent("1", "t", "k", Map.of(), "{}", 0L)),
                Collections.emptyList()
        );
        assertThat(v2.isEquivalent()).isFalse();
        assertThat(v2.mismatches()).isNotEmpty();
    }
}
