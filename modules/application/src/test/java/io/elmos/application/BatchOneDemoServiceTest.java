package io.elmos.application;

import io.elmos.domain.MigrationState;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class BatchOneDemoServiceTest {
    @Test void persistsCompleteEvidenceBackedDemo() {
        var saved=new AtomicReference<DemoRecord>();
        var service=new BatchOneDemoService(saved::set, Clock.fixed(Instant.parse("2026-07-20T12:00:00Z"), ZoneOffset.UTC));
        var result=service.execute();
        assertEquals(MigrationState.DELIVERED,result.state());
        assertTrue(result.simulated());
        assertNotNull(saved.get());
        assertEquals(result.evidenceId(),saved.get().step().evidenceIds().getFirst().value());
        assertFalse(saved.get().domainEvents().isEmpty());
    }
}

