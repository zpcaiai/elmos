package io.elmos.liveworkbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.liveworkbench.LiveWorkbenchService.*;
import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named = "ELMOS_LW_TEST_DATABASE_URL", matches = "jdbc:postgresql:.*")
class JdbcLiveWorkbenchStorePostgresTest {
    @Test void durableLifecycleUsesRealPostgresConstraintsRlsFencingAndReceipts() {
        String url = System.getenv("ELMOS_LW_TEST_DATABASE_URL");
        DriverManagerDataSource dataSource = new DriverManagerDataSource(url,
                System.getenv().getOrDefault("ELMOS_LW_TEST_DATABASE_USER", ""),
                System.getenv().getOrDefault("ELMOS_LW_TEST_DATABASE_PASSWORD", ""));
        Flyway.configure().dataSource(dataSource).locations("classpath:db/migration").load().migrate();
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        TransactionTemplate transactions = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        ObjectMapper json = new ObjectMapper();
        JdbcLiveWorkbenchCatalogStore catalog = new JdbcLiveWorkbenchCatalogStore(jdbc, transactions, json);
        JdbcLiveWorkbenchStore store = new JdbcLiveWorkbenchStore(jdbc, transactions, json);
        String snapshot = LwDigest.sha256("snapshot");
        RuntimeProfile profile = new RuntimeProfile("node-ts", "typescript", "next", "node-24", "linux", "amd64",
                "dap", "1", LwDigest.sha256("runtime"), "web", Qualification.QUALIFIED, Set.of("debug"),
                List.of("profile-evidence"), List.of(), false);
        catalog.registerProfile("tenant-a", profile, 10);
        CapabilityStatus available = new CapabilityStatus(SkillStatus.AVAILABLE, "qualified", List.of("evidence"));
        ArtifactDelivery delivery = new ArtifactDelivery("delivery-a", "tenant-a", "repo-a", snapshot, "generated", null,
                LwDigest.sha256("artifact"), LwDigest.sha256("lock"), profile.profileId(), "main", "web",
                Map.of("read", available, "teach", available, "build", available, "preview", available,
                        "debug", available, "compare", available), List.of(), List.of("demo-db"));
        catalog.registerDelivery("tenant-a", delivery, 11);
        PrincipalScope scope = new PrincipalScope("tenant-a", "account-a", "actor-a", "env-a", Set.of());
        CreateSessionRequest request = new CreateSessionRequest(delivery.deliveryId(), delivery.repositoryId(), snapshot,
                profile.profileId(), "smoke", "debug", 1, true);
        String requestDigest = LwDigest.sha256("request");
        LiveWorkbenchStore.Reservation reserved = store.reserve(scope, request, "session-a", "idempotency-1", requestDigest, 20);
        assertTrue(reserved.created());
        assertFalse(store.reserve(scope, request, "ignored", "idempotency-1", requestDigest, 21).created());
        assertTrue(store.find("tenant-b", "session-a").isEmpty());

        ProviderAllocation allocation = new ProviderAllocation("provider-a", "lease-a", 1_000,
                Map.of("sandbox", "sandbox-a", "volume", "volume-a"), List.of("allocation-evidence"));
        SessionView bound = store.bindProvider("tenant-a", "session-a", reserved.session().version(), allocation);
        ReadinessRequest readiness = new ReadinessRequest(delivery.buildArtifactDigest(), "verifier-a", "signature-ref", 100,
                Map.of("authenticated", true, "capacity", true, "businessSmoke", true), List.of("readiness-evidence"));
        SessionView ready = store.commitReady("tenant-a", "session-a", bound.version(), readiness);
        assertEquals(700, ready.expiresAtEpochSecond());
        assertThrows(LiveWorkbenchException.class, () -> store.commitReady("tenant-a", "session-a", ready.version(), readiness));

        RuntimeEventRequest event = new RuntimeEventRequest("event-a", 1, 1, 1, "stopped", LwDigest.sha256("event"),
                List.of("anchor-a"), "redacted", 110);
        store.appendEvent("tenant-a", "session-a", event);
        assertThrows(LiveWorkbenchException.class, () -> store.appendEvent("tenant-a", "session-a", event));
        SessionView pending = store.requestCleanup("tenant-a", "session-a", ready.version(), "test", 120);
        assertThrows(LiveWorkbenchException.class, () -> store.completeCleanup("tenant-a", "session-a", pending.version(),
                new CleanupOutcome(SessionState.CLEANED, Map.of("sandbox", true), "cleanup-verifier",
                        List.of("incomplete-cleanup-evidence"), 121)));
        SessionView cleaned = store.completeCleanup("tenant-a", "session-a", pending.version(),
                new CleanupOutcome(SessionState.CLEANED, Map.of("sandbox", true, "volume", true), "cleanup-verifier",
                        List.of("cleanup-evidence"), 121));
        assertEquals(SessionState.CLEANED, cleaned.state());
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM lw_resource_members", Integer.class));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM lw_cleanup_receipts", Integer.class));
        assertTrue(jdbc.queryForObject("SELECT count(*) FROM lw_outbox", Integer.class) >= 4);
    }
}
