package io.elmos.cas;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * PostgreSQL implementation of {@link CasCatalog} against the V65/V66 schema, using
 * {@code java.sql} only — no ORM, no Spring, no driver-specific API. The driver is supplied by
 * whoever builds the {@link DataSource}.
 *
 * <p>Every operation opens an explicit transaction and sets a transaction-local
 * {@code app.organization_id} before it touches a table. That is not belt-and-braces on top of the
 * explicit tenant parameters: the row level security policies read exactly that setting, so
 * a connection that forgets it sees nothing and writes nothing. Transaction-local scope is load
 * bearing for connection pools: a session-scoped setting would leak the previous organization to
 * the next, unrelated borrower of the same physical connection.
 */
public final class JdbcCasCatalog implements CasCatalog {

    private final DataSource dataSource;

    public JdbcCasCatalog(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    private interface Work<T> {
        T apply(Connection connection) throws SQLException;
    }

    private <T> T inTenant(String tenantId, Work<T> work) {
        CasText.required(tenantId, "tenantId");
        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            if (!originalAutoCommit) {
                // This adapter owns one transaction per catalogue operation. Committing a
                // connection that arrived inside an ambient transaction could commit unrelated
                // caller work and leave the tenant-local setting visible for that transaction.
                throw new IllegalStateException(
                        "CAS catalogue requires a fresh auto-commit connection");
            }
            Throwable failure = null;
            try {
                connection.setAutoCommit(false);
                try (PreparedStatement scope = connection.prepareStatement(
                        "SELECT set_config('app.organization_id', ?, true)")) {
                    scope.setString(1, tenantId);
                    scope.execute();
                }
                T result = work.apply(connection);
                connection.commit();
                return result;
            } catch (SQLException | RuntimeException error) {
                failure = error;
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    error.addSuppressed(rollbackFailure);
                }
                throw error;
            } finally {
                try {
                    if (connection.getAutoCommit() != originalAutoCommit) {
                        connection.setAutoCommit(originalAutoCommit);
                    }
                } catch (SQLException restoreFailure) {
                    if (failure != null) {
                        failure.addSuppressed(restoreFailure);
                    } else {
                        throw new IllegalStateException(
                                "CAS catalogue could not restore the pooled connection", restoreFailure);
                    }
                }
            }
        } catch (SQLException error) {
            throw new IllegalStateException("CAS catalogue operation failed for tenant " + tenantId, error);
        }
    }

    @Override
    public void record(CatalogEntry entry) {
        inTenant(entry.tenantId(), connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_object_catalog (organization_id, digest_hex, size_bytes,
                        object_kind, media_type, source_system, schema_version, sensitivity,
                        retention_class, data_residency, security_tier, provenance_digest_hex,
                        provenance_size_bytes, labels, legal_hold, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?, ?)
                    ON CONFLICT (organization_id, digest_hex) DO UPDATE SET
                        retention_class = CASE
                            WHEN cas_object_catalog.retention_class = 'REGULATORY'
                              OR EXCLUDED.retention_class = 'REGULATORY' THEN 'REGULATORY'
                            WHEN cas_object_catalog.retention_class = 'EVIDENCE'
                              OR EXCLUDED.retention_class = 'EVIDENCE' THEN 'EVIDENCE'
                            WHEN cas_object_catalog.retention_class = 'STANDARD'
                              OR EXCLUDED.retention_class = 'STANDARD' THEN 'STANDARD'
                            ELSE 'EPHEMERAL'
                        END,
                        legal_hold = cas_object_catalog.legal_hold OR EXCLUDED.legal_hold,
                        labels = cas_object_catalog.labels || EXCLUDED.labels,
                        last_referenced_at = now()
                    WHERE cas_object_catalog.size_bytes = EXCLUDED.size_bytes
                      AND cas_object_catalog.object_kind = EXCLUDED.object_kind
                      AND cas_object_catalog.media_type = EXCLUDED.media_type
                      AND cas_object_catalog.source_system = EXCLUDED.source_system
                      AND cas_object_catalog.schema_version = EXCLUDED.schema_version
                      AND cas_object_catalog.sensitivity = EXCLUDED.sensitivity
                      AND cas_object_catalog.data_residency = EXCLUDED.data_residency
                      AND cas_object_catalog.security_tier = EXCLUDED.security_tier
                      AND cas_object_catalog.provenance_digest_hex
                          IS NOT DISTINCT FROM EXCLUDED.provenance_digest_hex
                      AND cas_object_catalog.provenance_size_bytes
                          IS NOT DISTINCT FROM EXCLUDED.provenance_size_bytes
                    """)) {
                statement.setString(1, entry.tenantId());
                statement.setString(2, entry.digest().hex());
                statement.setLong(3, entry.digest().sizeBytes());
                statement.setString(4, entry.kind().name());
                statement.setString(5, entry.mediaType());
                statement.setString(6, entry.sourceSystem());
                statement.setString(7, entry.schemaVersion());
                statement.setString(8, entry.sensitivity().name());
                statement.setString(9, entry.retentionClass().name());
                statement.setString(10, entry.dataResidency());
                statement.setString(11, entry.securityTier().name());
                statement.setString(12, entry.provenanceDigest().map(CasDigest::hex).orElse(null));
                if (entry.provenanceDigest().isPresent()) {
                    statement.setLong(13, entry.provenanceDigest().orElseThrow().sizeBytes());
                } else {
                    statement.setNull(13, java.sql.Types.BIGINT);
                }
                statement.setString(14, CasLabelsJson.encode(entry.labels()));
                statement.setBoolean(15, entry.legalHold());
                statement.setTimestamp(16, new Timestamp(entry.createdAtEpochMillis()));
                if (statement.executeUpdate() == 0) {
                    throw new IllegalStateException(
                            "catalogued object identity cannot be rebound to different metadata");
                }
            }
            return null;
        });
    }

    @Override
    public Optional<CatalogEntry> find(String tenantId, CasDigest digest) {
        Objects.requireNonNull(digest, "digest");
        return inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT digest_hex, size_bytes, object_kind, media_type, source_system,
                           schema_version, sensitivity, retention_class, data_residency, security_tier,
                           provenance_digest_hex, provenance_size_bytes, labels::text AS labels_json,
                           legal_hold, created_at
                      FROM cas_object_catalog
                     WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, digest.hex());
                statement.setLong(3, digest.sizeBytes());
                try (ResultSet rows = statement.executeQuery()) {
                    return rows.next() ? Optional.of(readEntry(tenantId, rows)) : Optional.<CatalogEntry>empty();
                }
            }
        });
    }

    @Override
    public Optional<CatalogEntry> findBound(String tenantId, ResourceKind resourceKind,
                                            String resourceId, CasDigest digest) {
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        Objects.requireNonNull(digest, "digest");
        return inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT catalog_object.digest_hex, catalog_object.size_bytes,
                           catalog_object.object_kind, catalog_object.media_type,
                           catalog_object.source_system, catalog_object.schema_version,
                           catalog_object.sensitivity, catalog_object.retention_class,
                           catalog_object.data_residency, catalog_object.security_tier,
                           catalog_object.provenance_digest_hex,
                           catalog_object.provenance_size_bytes,
                           catalog_object.labels::text AS labels_json,
                           catalog_object.legal_hold, catalog_object.created_at
                      FROM cas_object_catalog catalog_object
                      JOIN cas_resource_bindings binding
                        ON binding.organization_id = catalog_object.organization_id
                       AND binding.digest_hex = catalog_object.digest_hex
                     WHERE catalog_object.organization_id = ?
                       AND binding.resource_kind = ?
                       AND binding.resource_id = ?
                       AND catalog_object.digest_hex = ?
                       AND catalog_object.size_bytes = ?
                       AND binding.released_at IS NULL
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, resourceKind.name());
                statement.setString(3, resourceId);
                statement.setString(4, digest.hex());
                statement.setLong(5, digest.sizeBytes());
                try (ResultSet rows = statement.executeQuery()) {
                    return rows.next() ? Optional.of(readEntry(tenantId, rows))
                            : Optional.<CatalogEntry>empty();
                }
            }
        });
    }

    @Override
    public void bindResource(ResourceBinding binding) {
        inTenant(binding.tenantId(), connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_resource_bindings (organization_id, resource_kind,
                        resource_id, digest_hex, bound_at)
                    SELECT organization_id, ?, ?, digest_hex, ?
                      FROM cas_object_catalog
                     WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                    ON CONFLICT (organization_id, resource_kind, resource_id, digest_hex)
                    DO UPDATE SET
                        bound_at = CASE
                            WHEN cas_resource_bindings.released_at IS NULL
                                THEN cas_resource_bindings.bound_at
                            ELSE EXCLUDED.bound_at
                        END,
                        released_at = NULL
                    """)) {
                statement.setString(1, binding.resourceKind().name());
                statement.setString(2, binding.resourceId());
                statement.setTimestamp(3, new Timestamp(binding.boundAtEpochMillis()));
                statement.setString(4, binding.tenantId());
                statement.setString(5, binding.digest().hex());
                statement.setLong(6, binding.digest().sizeBytes());
                if (statement.executeUpdate() == 0) {
                    throw new CasExceptions.CasNotFoundException(binding.digest());
                }
            }
            return null;
        });
    }

    @Override
    public void releaseResource(String tenantId, ResourceKind resourceKind, String resourceId,
                                CasDigest digest, long releasedAtEpochMillis) {
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        Objects.requireNonNull(digest, "digest");
        if (releasedAtEpochMillis < 0) {
            throw new IllegalArgumentException("releasedAtEpochMillis must not be negative");
        }
        inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE cas_resource_bindings binding SET released_at = ?
                     WHERE binding.organization_id = ?
                       AND binding.resource_kind = ?
                       AND binding.resource_id = ?
                       AND binding.digest_hex = ?
                       AND binding.released_at IS NULL
                       AND EXISTS (
                           SELECT 1 FROM cas_object_catalog catalog_object
                            WHERE catalog_object.organization_id = binding.organization_id
                              AND catalog_object.digest_hex = binding.digest_hex
                              AND catalog_object.size_bytes = ?)
                    """)) {
                statement.setTimestamp(1, new Timestamp(releasedAtEpochMillis));
                statement.setString(2, tenantId);
                statement.setString(3, resourceKind.name());
                statement.setString(4, resourceId);
                statement.setString(5, digest.hex());
                statement.setLong(6, digest.sizeBytes());
                statement.executeUpdate();
            }
            return null;
        });
    }

    @Override
    public List<ResourceBinding> activeResourceBindings(String tenantId, ResourceKind resourceKind,
                                                        String resourceId) {
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        return inTenant(tenantId, connection -> {
            List<ResourceBinding> bindings = new ArrayList<>();
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT binding.digest_hex, catalog_object.size_bytes, binding.bound_at
                      FROM cas_resource_bindings binding
                      JOIN cas_object_catalog catalog_object
                        ON catalog_object.organization_id = binding.organization_id
                       AND catalog_object.digest_hex = binding.digest_hex
                     WHERE binding.organization_id = ?
                       AND binding.resource_kind = ?
                       AND binding.resource_id = ?
                       AND binding.released_at IS NULL
                     ORDER BY binding.digest_hex
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, resourceKind.name());
                statement.setString(3, resourceId);
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        bindings.add(new ResourceBinding(tenantId, resourceKind, resourceId,
                                new CasDigest(CasDigest.ALGORITHM, rows.getString("digest_hex"),
                                        rows.getLong("size_bytes")),
                                rows.getTimestamp("bound_at").getTime()));
                    }
                }
            }
            return List.copyOf(bindings);
        });
    }

    @Override
    public Map<CasDigest, CasObjectModel.ObjectMetadata> load(String tenantId, Set<CasDigest> digests) {
        if (digests.isEmpty()) {
            return Map.of();
        }
        return inTenant(tenantId, connection -> {
            Map<CasDigest, CasObjectModel.ObjectMetadata> loaded = new LinkedHashMap<>();
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT digest_hex, size_bytes, object_kind, media_type, source_system,
                           schema_version, sensitivity, retention_class, data_residency, security_tier,
                           provenance_digest_hex, provenance_size_bytes, labels::text AS labels_json,
                           legal_hold, created_at
                      FROM cas_object_catalog
                     WHERE organization_id = ? AND digest_hex = ANY (?)
                    """)) {
                statement.setString(1, tenantId);
                statement.setArray(2, connection.createArrayOf("varchar",
                        digests.stream().map(CasDigest::hex).toArray()));
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        CatalogEntry entry = readEntry(tenantId, rows);
                        if (digests.contains(entry.digest())) {
                            loaded.put(entry.digest(), entry.metadata());
                        }
                    }
                }
            }
            return loaded;
        });
    }

    @Override
    public void placeObject(Placement placement) {
        inTenant(placement.tenantId(), connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_object_placement (organization_id, digest_hex, region,
                        placement_role, storage_tier)
                    SELECT organization_id, digest_hex, ?, ?, ?
                      FROM cas_object_catalog
                     WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                    ON CONFLICT (organization_id, digest_hex, region) DO UPDATE SET
                        placement_role = EXCLUDED.placement_role,
                        storage_tier = EXCLUDED.storage_tier,
                        verified_at = now()
                    """)) {
                statement.setString(1, placement.region());
                statement.setString(2, placement.role().name());
                statement.setString(3, placement.storageTier());
                statement.setString(4, placement.tenantId());
                statement.setString(5, placement.digest().hex());
                statement.setLong(6, placement.digest().sizeBytes());
                if (statement.executeUpdate() == 0) {
                    throw new IllegalStateException(
                            "cannot place an uncatalogued object: " + placement.digest());
                }
            }
            return null;
        });
    }

    @Override
    public List<Placement> placements(String tenantId, CasDigest digest) {
        return inTenant(tenantId, connection -> {
            List<Placement> found = new ArrayList<>();
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT placement.region, placement.placement_role, placement.storage_tier
                      FROM cas_object_placement placement
                      JOIN cas_object_catalog catalog_object
                        ON catalog_object.organization_id = placement.organization_id
                       AND catalog_object.digest_hex = placement.digest_hex
                     WHERE placement.organization_id = ? AND placement.digest_hex = ?
                       AND catalog_object.size_bytes = ?
                     ORDER BY placement_role, region
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, digest.hex());
                statement.setLong(3, digest.sizeBytes());
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        found.add(new Placement(tenantId, digest, rows.getString("region"),
                                PlacementRole.valueOf(rows.getString("placement_role")),
                                rows.getString("storage_tier")));
                    }
                }
            }
            return List.copyOf(found);
        });
    }

    @Override
    public void addReferenceRoot(ReferenceRoot root) {
        addReferenceRoots(List.of(root));
    }

    @Override
    public void addReferenceRoots(List<ReferenceRoot> requestedRoots) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Map<String, ReferenceRoot> requestedByHex = new LinkedHashMap<>();
        for (ReferenceRoot root : requestedRoots) {
            ReferenceRoot duplicate = requestedByHex.putIfAbsent(root.digest().hex(), root);
            if (duplicate != null && !duplicate.digest().equals(root.digest())) {
                throw new IllegalArgumentException("one digest hex cannot carry two sizes in a root set");
            }
        }
        inTenant(first.tenantId(), connection -> {
            // Row locks cannot serialize an as-yet absent root ID. A transaction advisory lock on
            // the exact logical root prevents two different first publications from interleaving
            // into an unauthorized union of their digest sets.
            try (PreparedStatement lock = connection.prepareStatement(
                    "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
                lock.setString(1, first.tenantId() + "\n" + first.kind() + "\n" + first.rootId());
                lock.execute();
            }
            try (PreparedStatement existing = connection.prepareStatement("""
                    SELECT digest_hex, size_bytes, released_at
                      FROM cas_reference_roots
                     WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                     ORDER BY digest_hex
                     FOR UPDATE
                    """)) {
                existing.setString(1, first.tenantId());
                existing.setString(2, first.kind().name());
                existing.setString(3, first.rootId());
                try (ResultSet rows = existing.executeQuery()) {
                    while (rows.next()) {
                        String digestHex = rows.getString("digest_hex");
                        ReferenceRoot requested = requestedByHex.get(digestHex);
                        if (requested != null
                                && requested.digest().sizeBytes() != rows.getLong("size_bytes")) {
                            throw new IllegalStateException(
                                    "reference root digest size conflicts with history");
                        }
                        if (rows.getTimestamp("released_at") == null && requested == null) {
                            throw new IllegalStateException(
                                    "active reference root conflicts with requested digest set");
                        }
                    }
                }
            }
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_reference_roots (organization_id, root_kind, root_id, digest_hex,
                        size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (organization_id, root_kind, root_id, digest_hex) DO UPDATE SET
                        created_at = CASE
                            WHEN cas_reference_roots.released_at IS NULL
                                THEN cas_reference_roots.created_at
                            ELSE EXCLUDED.created_at
                        END,
                        released_at = NULL
                    """)) {
                for (ReferenceRoot root : requestedByHex.values()) {
                    statement.setString(1, root.tenantId());
                    statement.setString(2, root.kind().name());
                    statement.setString(3, root.rootId());
                    statement.setString(4, root.digest().hex());
                    statement.setLong(5, root.digest().sizeBytes());
                    statement.setTimestamp(6, new Timestamp(root.createdAtEpochMillis()));
                    statement.addBatch();
                }
                statement.executeBatch();
            }
            return null;
        });
    }

    @Override
    public void releaseReferenceRoot(String tenantId, CasGarbageCollector.RootKind kind, String rootId,
                                     long releasedAtEpochMillis) {
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        if (releasedAtEpochMillis < 0) {
            throw new IllegalArgumentException("releasedAtEpochMillis must not be negative");
        }
        inTenant(tenantId, connection -> {
            try (PreparedStatement lock = connection.prepareStatement(
                    "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
                lock.setString(1, tenantId + "\n" + kind + "\n" + rootId);
                lock.execute();
            }
            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE cas_reference_roots SET released_at = ?
                     WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                       AND released_at IS NULL AND created_at <= ?
                    """)) {
                statement.setTimestamp(1, new Timestamp(releasedAtEpochMillis));
                statement.setString(2, tenantId);
                statement.setString(3, kind.name());
                statement.setString(4, rootId);
                statement.setTimestamp(5, new Timestamp(releasedAtEpochMillis));
                statement.executeUpdate();
            }
            try (PreparedStatement later = connection.prepareStatement("""
                    SELECT 1 FROM cas_reference_roots
                     WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                       AND released_at IS NULL AND created_at > ?
                     LIMIT 1
                    """)) {
                later.setString(1, tenantId);
                later.setString(2, kind.name());
                later.setString(3, rootId);
                later.setTimestamp(4, new Timestamp(releasedAtEpochMillis));
                try (ResultSet rows = later.executeQuery()) {
                    if (rows.next()) {
                        throw new IllegalArgumentException(
                                "release cannot precede reference root creation");
                    }
                }
            }
            return null;
        });
    }

    @Override
    public List<ReferenceRoot> activeReferenceRoots(String tenantId) {
        return inTenant(tenantId, connection -> {
            List<ReferenceRoot> roots = new ArrayList<>();
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT root_kind, root_id, digest_hex, size_bytes, created_at
                      FROM cas_reference_roots
                     WHERE organization_id = ? AND released_at IS NULL
                     ORDER BY root_kind, root_id, digest_hex
                    """)) {
                statement.setString(1, tenantId);
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        roots.add(new ReferenceRoot(tenantId,
                                CasGarbageCollector.RootKind.valueOf(rows.getString("root_kind")),
                                rows.getString("root_id"),
                                new CasDigest(CasDigest.ALGORITHM, rows.getString("digest_hex"),
                                        rows.getLong("size_bytes")),
                                rows.getTimestamp("created_at").getTime()));
                    }
                }
            }
            return List.copyOf(roots);
        });
    }

    @Override
    public void setLegalHold(String tenantId, CasDigest digest, boolean legalHold) {
        inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE cas_object_catalog SET legal_hold = ?
                     WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                    """)) {
                statement.setBoolean(1, legalHold);
                statement.setString(2, tenantId);
                statement.setString(3, digest.hex());
                statement.setLong(4, digest.sizeBytes());
                if (statement.executeUpdate() == 0) {
                    throw new CasExceptions.CasNotFoundException(digest);
                }
            }
            return null;
        });
    }

    @Override
    public void recordDeletionManifest(String tenantId, CasGarbageCollector.DeletionManifest manifest,
                                       String executedBy) {
        inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_deletion_manifests (organization_id, batch_id, dry_run,
                        collected_objects, retained_objects, unresolved_references, reclaimed_bytes,
                        manifest_digest_hex, executed_at, executed_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, manifest.batchId());
                statement.setBoolean(3, manifest.dryRun());
                statement.setInt(4, manifest.collected().size());
                statement.setInt(5, manifest.retained().size());
                statement.setInt(6, manifest.unresolvedReferences().size());
                statement.setLong(7, manifest.reclaimedBytes());
                statement.setString(8, manifest.digest().hex());
                statement.setTimestamp(9, new Timestamp(manifest.atEpochMillis()));
                statement.setString(10, executedBy);
                statement.executeUpdate();
            }
            return null;
        });
    }

    @Override
    public List<String> deletionBatchIds(String tenantId) {
        return inTenant(tenantId, connection -> {
            List<String> batches = new ArrayList<>();
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT batch_id FROM cas_deletion_manifests WHERE organization_id = ? ORDER BY batch_id")) {
                statement.setString(1, tenantId);
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        batches.add(rows.getString("batch_id"));
                    }
                }
            }
            return List.copyOf(batches);
        });
    }

    @Override
    public void recordQuarantine(String tenantId, String quarantineId, String subjectKind, String subject,
                                 Optional<CasDigest> declared, Optional<CasDigest> observed, String detail,
                                 long detectedAtEpochMillis) {
        inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_quarantine_events (organization_id, quarantine_id, subject_kind,
                        subject, declared_digest_hex, observed_digest_hex, detail, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, quarantineId);
                statement.setString(3, subjectKind);
                statement.setString(4, subject);
                statement.setString(5, declared.map(CasDigest::hex).orElse(null));
                statement.setString(6, observed.map(CasDigest::hex).orElse(null));
                statement.setString(7, detail);
                statement.setTimestamp(8, new Timestamp(detectedAtEpochMillis));
                statement.executeUpdate();
            }
            return null;
        });
    }

    @Override
    public int quarantineCount(String tenantId) {
        return inTenant(tenantId, connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT count(*) FROM cas_quarantine_events WHERE organization_id = ?")) {
                statement.setString(1, tenantId);
                try (ResultSet rows = statement.executeQuery()) {
                    rows.next();
                    return rows.getInt(1);
                }
            }
        });
    }

    static CatalogEntry readEntry(String tenantId, ResultSet rows) throws SQLException {
        String provenance = rows.getString("provenance_digest_hex");
        Object persistedProvenanceSize = rows.getObject("provenance_size_bytes");
        Optional<CasDigest> provenanceDigest;
        if (provenance == null) {
            if (persistedProvenanceSize != null) {
                throw new SQLException("catalog provenance size exists without its digest");
            }
            provenanceDigest = Optional.empty();
        } else {
            if (!(persistedProvenanceSize instanceof Number size)) {
                throw new SQLException("catalog provenance digest is missing its exact byte size");
            }
            provenanceDigest = Optional.of(new CasDigest(
                    CasDigest.ALGORITHM, provenance, size.longValue()));
        }
        Map<String, String> labels;
        try {
            labels = CasLabelsJson.decode(rows.getString("labels_json"));
        } catch (IllegalArgumentException error) {
            throw new SQLException("catalog labels are not a string-to-string JSON object", error);
        }
        return new CatalogEntry(tenantId,
                new CasDigest(CasDigest.ALGORITHM, rows.getString("digest_hex"), rows.getLong("size_bytes")),
                CasObjectModel.ObjectKind.valueOf(rows.getString("object_kind")),
                rows.getString("media_type"),
                rows.getString("source_system"),
                rows.getString("schema_version"),
                CasObjectModel.Sensitivity.valueOf(rows.getString("sensitivity")),
                CasObjectModel.RetentionClass.valueOf(rows.getString("retention_class")),
                rows.getString("data_residency"),
                CasAccessPolicy.SecurityTier.valueOf(rows.getString("security_tier")),
                provenanceDigest,
                labels,
                rows.getBoolean("legal_hold"),
                rows.getTimestamp("created_at").getTime());
    }

    private static ReferenceRoot requireOneRootSet(List<ReferenceRoot> requestedRoots) {
        if (requestedRoots == null || requestedRoots.isEmpty()) {
            throw new IllegalArgumentException("reference root batch must not be empty");
        }
        ReferenceRoot first = Objects.requireNonNull(requestedRoots.get(0), "reference root");
        for (ReferenceRoot root : requestedRoots) {
            Objects.requireNonNull(root, "reference root");
            if (!root.tenantId().equals(first.tenantId())
                    || root.kind() != first.kind()
                    || !root.rootId().equals(first.rootId())) {
                throw new IllegalArgumentException(
                        "reference root batch must share tenant, kind, and root ID");
            }
        }
        return first;
    }
}
