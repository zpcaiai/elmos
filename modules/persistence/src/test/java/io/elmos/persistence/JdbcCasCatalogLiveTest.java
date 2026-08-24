package io.elmos.persistence;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasCatalog;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasGarbageCollector;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.JdbcCasCatalog;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Holds {@link JdbcCasCatalog} to the same contract as the in-memory implementation, against the
 * real V65 schema.
 *
 * <p>This is the half the cloud build cannot run: the constraints, the row level security policy
 * and the append-only triggers only exist inside PostgreSQL. `CasCatalogTest` in `modules/cas`
 * covers the same behaviours against the heap implementation, and the two agreeing is the point —
 * a rule that only one of them enforces is a rule that gets violated in whichever environment the
 * other one runs in.
 */
@Testcontainers(disabledWithoutDocker = true)
class JdbcCasCatalogLiveTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static DataSource dataSource;

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    @BeforeAll
    static void migrate() {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();
        DriverManagerDataSource source = new DriverManagerDataSource(POSTGRES.getJdbcUrl(),
                POSTGRES.getUsername(), POSTGRES.getPassword());
        source.setDriverClassName("org.postgresql.Driver");
        dataSource = source;
    }

    private static CasCatalog.CatalogEntry entry(String tenant, CasDigest digest,
                                                 CasObjectModel.Sensitivity sensitivity,
                                                 Optional<CasDigest> provenance) {
        return new CasCatalog.CatalogEntry(tenant, digest, "project-a", CasObjectModel.ObjectKind.BLOB,
                "application/octet-stream", "elmos", "1.0", sensitivity,
                CasObjectModel.RetentionClass.STANDARD, "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, provenance, Map.of("stage", "baseline"), false,
                1_800_000_000_000L);
    }

    @Test void anEntryRoundTripsThroughTheRealSchema() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("jdbc payload");
        catalog.record(entry("tenant-jdbc-1", object, CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                Optional.of(digest("provenance"))));

        var found = catalog.find("tenant-jdbc-1", object).orElseThrow();
        assertEquals(object.hex(), found.digest().hex());
        assertEquals(object.sizeBytes(), found.digest().sizeBytes());
        assertEquals(CasObjectModel.Sensitivity.GENERATED_OUTPUT, found.sensitivity());
        assertEquals(CasAccessPolicy.SecurityTier.INTERNAL, found.securityTier());
    }

    @Test void recordingTheSameObjectTwiceIsIdempotent() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("recorded twice");
        catalog.record(entry("tenant-jdbc-2", object, CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                Optional.empty()));
        catalog.record(entry("tenant-jdbc-2", object, CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                Optional.empty()));
        assertEquals(1, catalog.load("tenant-jdbc-2", Set.of(object)).size());
    }

    @Test void rowLevelSecurityHidesOtherTenants() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest shared = digest("byte identical across tenants");
        catalog.record(entry("tenant-jdbc-3", shared, CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                Optional.empty()));

        assertTrue(catalog.find("tenant-jdbc-3", shared).isPresent());
        assertTrue(catalog.find("tenant-jdbc-4", shared).isEmpty(),
                "the policy reads app.organization_id, which the catalogue sets per connection");
    }

    @Test void theDatabaseRefusesASecondPrimaryRegion() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("placed by jdbc");
        catalog.record(entry("tenant-jdbc-5", object, CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                Optional.empty()));
        catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-5", object, "eu-west-1",
                CasCatalog.PlacementRole.PRIMARY, "L2"));
        catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-5", object, "eu-central-1",
                CasCatalog.PlacementRole.REPLICA, "L2"));

        assertEquals(2, catalog.placements("tenant-jdbc-5", object).size());
        assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-5", object, "us-east-1",
                        CasCatalog.PlacementRole.PRIMARY, "L2")));
    }

    @Test void theDatabaseRefusesPlacementOfAnUncataloguedObject() {
        var catalog = new JdbcCasCatalog(dataSource);
        assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-6", digest("ghost"),
                        "eu-west-1", CasCatalog.PlacementRole.PRIMARY, "L2")));
    }

    @Test void referenceRootsAreActiveUntilReleased() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("referenced by jdbc");
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-jdbc-7",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-1", object, 1_800_000_000_000L));
        assertEquals(1, catalog.activeReferenceRoots("tenant-jdbc-7").size());

        catalog.releaseReferenceRoot("tenant-jdbc-7", CasGarbageCollector.RootKind.SNAPSHOT, "snap-1",
                1_800_000_100_000L);
        assertTrue(catalog.activeReferenceRoots("tenant-jdbc-7").isEmpty());
    }

    @Test void aDeletionManifestCannotBeRewritten() {
        var catalog = new JdbcCasCatalog(dataSource);
        var manifest = new CasGarbageCollector.DeletionManifest("jdbc-batch-1", false, List.of(),
                List.of(), List.of(), 0, 1_800_000_000_000L);
        catalog.recordDeletionManifest("tenant-jdbc-8", manifest, "gc");
        assertEquals(List.of("jdbc-batch-1"), catalog.deletionBatchIds("tenant-jdbc-8"));
        assertThrows(IllegalStateException.class,
                () -> catalog.recordDeletionManifest("tenant-jdbc-8", manifest, "gc"));
    }

    @Test void aContentQuarantineNeedsBothDigests() {
        var catalog = new JdbcCasCatalog(dataSource);
        assertThrows(IllegalStateException.class,
                () -> catalog.recordQuarantine("tenant-jdbc-9", "q-1", "OBJECT", "subject",
                        Optional.of(digest("declared")), Optional.empty(), "half a record",
                        1_800_000_000_000L));
        catalog.recordQuarantine("tenant-jdbc-9", "q-2", "NODE", "ns/runners/sa/n1",
                Optional.empty(), Optional.empty(), "nondeterministic output", 1_800_000_000_000L);
        assertEquals(1, catalog.quarantineCount("tenant-jdbc-9"));
    }
}
