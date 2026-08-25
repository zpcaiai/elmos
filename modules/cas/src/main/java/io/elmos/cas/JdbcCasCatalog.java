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
import java.util.concurrent.Executor;

/**
 * PostgreSQL implementation of {@link CasCatalog} against the V65-V76 CAS schema, using
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

    private static final Executor DIRECT_ABORT_EXECUTOR = Runnable::run;
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
            boolean transactionResolved = false;
            try {
                connection.setAutoCommit(false);
                try (PreparedStatement scope = connection.prepareStatement(
                        "SELECT set_config('app.organization_id', ?, true)")) {
                    scope.setString(1, tenantId);
                    scope.execute();
                }
                T result = work.apply(connection);
                connection.commit();
                transactionResolved = true;
                return result;
            } catch (SQLException | RuntimeException | Error error) {
                failure = error;
                try {
                    connection.rollback();
                    transactionResolved = true;
                } catch (SQLException rollbackFailure) {
                    error.addSuppressed(rollbackFailure);
                    try {
                        // Never return an unresolved transaction to a pool and never restore
                        // auto-commit: some drivers commit the active transaction on that
                        // transition. abort() is the JDBC contract for discarding the physical
                        // connection after an indeterminate rollback.
                        connection.abort(DIRECT_ABORT_EXECUTOR);
                    } catch (SQLException | RuntimeException abortFailure) {
                        error.addSuppressed(abortFailure);
                    }
                }
                throw error;
            } finally {
                try {
                    if (transactionResolved
                            && connection.getAutoCommit() != originalAutoCommit) {
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
            ensureActiveTenant(connection, entry.tenantId());
            lockObjectLifecycles(connection, entry.tenantId(), List.of(entry.digest()));
            if (entry.legalHold()) {
                ensureNoDeletionTombstones(
                        connection, entry.tenantId(), List.of(entry.digest()));
            }
            record(connection, entry);
            return null;
        });
    }

    @Override
    public long recordAndAddReferenceRoots(
            CatalogEntry entry, List<ReferenceRoot> requestedRoots
    ) {
        ReferenceRoot first = requireEntryRootSet(entry, requestedRoots);
        Map<String, ReferenceRoot> requestedByHex = requestedRootMap(requestedRoots);
        return inTenant(entry.tenantId(), connection -> {
            ensureActiveTenant(connection, entry.tenantId());
            List<CasDigest> digests = requestedRoots.stream()
                    .map(ReferenceRoot::digest).distinct().toList();
            lockObjectLifecycles(connection, entry.tenantId(), digests);
            ensureNoDeletionTombstones(connection, entry.tenantId(), digests);
            record(connection, entry);
            return addReferenceRoots(connection, first, requestedByHex);
        });
    }

    @Override
    public long recordAndPublishDurableReferenceRoots(
            CatalogEntry entry,
            List<ReferenceRoot> requestedRoots,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        ReferenceRoot first = requireEntryRootSet(entry, requestedRoots);
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        Map<String, ReferenceRoot> requestedByHex = requestedRootMap(requestedRoots);
        return inTenant(entry.tenantId(), connection -> {
            ensureActiveTenant(connection, entry.tenantId());
            List<CasDigest> digests = requestedRoots.stream()
                    .map(ReferenceRoot::digest).distinct().toList();
            lockObjectLifecycles(connection, entry.tenantId(), digests);
            ensureNoActiveDeletionTombstones(connection, entry.tenantId(), digests);
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(connection, entry.tenantId(), digests);
            record(connection, entry);
            return addReferenceRoots(connection, first, requestedByHex);
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
            ResourceLifecycle resource = ensureActiveResource(
                    connection, binding.tenantId(), binding.resourceKind(), binding.resourceId());
            lockObjectLifecycles(
                    connection, binding.tenantId(), List.of(binding.digest()));
            ensureNoDeletionTombstones(
                    connection, binding.tenantId(), List.of(binding.digest()));
            bindResource(connection, binding, resource);
            return null;
        });
    }

    @Override
    public ResourceLifecycle ensureActiveResource(
            String tenantId, ResourceKind resourceKind, String resourceId) {
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        return inTenant(tenantId, connection ->
                ensureActiveResource(connection, tenantId, resourceKind, resourceId));
    }

    @Override
    public ResourceLifecycle beginResourceRetirement(
            String tenantId, ResourceKind resourceKind, String resourceId,
            long transitionedAtEpochMillis) {
        requireTransitionTime(transitionedAtEpochMillis);
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        return inTenant(tenantId, connection -> {
            ensureActiveTenant(connection, tenantId);
            lockResourceLifecycle(connection, tenantId, resourceKind, resourceId);
            ResourceLifecycle current = findResourceLifecycle(
                    connection, tenantId, resourceKind, resourceId);
            if (current == null) {
                current = ensureActiveResource(
                        connection, tenantId, resourceKind, resourceId);
            }
            if (current.state() == ResourceLifecycleState.RETIRING) {
                return current;
            }
            if (current.state() != ResourceLifecycleState.ACTIVE) {
                throw new IllegalStateException("CAS resource is already RETIRED");
            }
            try (PreparedStatement update = connection.prepareStatement("""
                    UPDATE cas_resource_lifecycles
                       SET lifecycle_state = 'RETIRING', transitioned_at = ?,
                           released_binding_count = 0
                     WHERE organization_id = ? AND resource_kind = ? AND resource_id = ?
                       AND tenant_epoch = ? AND resource_epoch = ?
                       AND lifecycle_state = 'ACTIVE'
                    """)) {
                update.setTimestamp(1, new Timestamp(transitionedAtEpochMillis));
                update.setString(2, tenantId);
                update.setString(3, resourceKind.name());
                update.setString(4, resourceId);
                update.setLong(5, current.tenantEpoch());
                update.setLong(6, current.resourceEpoch());
                if (update.executeUpdate() != 1) {
                    throw new IllegalStateException("resource lifecycle changed during retirement");
                }
            }
            return new ResourceLifecycle(tenantId, resourceKind, resourceId,
                    current.tenantEpoch(), current.resourceEpoch(),
                    ResourceLifecycleState.RETIRING, transitionedAtEpochMillis, 0);
        });
    }

    @Override
    public ResourceLifecycle finalizeResourceRetirement(
            ResourceLifecycle retiring, long transitionedAtEpochMillis) {
        Objects.requireNonNull(retiring, "retiring");
        requireTransitionTime(transitionedAtEpochMillis);
        if (retiring.state() != ResourceLifecycleState.RETIRING) {
            throw new IllegalStateException("resource retirement token is not RETIRING");
        }
        return inTenant(retiring.tenantId(), connection -> {
            lockTenantLifecycle(connection, retiring.tenantId());
            lockResourceLifecycle(connection, retiring.tenantId(),
                    retiring.resourceKind(), retiring.resourceId());
            ResourceLifecycle current = findResourceLifecycle(connection,
                    retiring.tenantId(), retiring.resourceKind(), retiring.resourceId());
            requireExactLifecycleToken(current, retiring);
            try (PreparedStatement roots = connection.prepareStatement("""
                    SELECT 1
                      FROM cas_reference_roots root
                     WHERE root.organization_id = ? AND root.released_at IS NULL
                       AND ((root.resource_kind = ? AND root.resource_id = ?
                             AND root.tenant_epoch = ? AND root.resource_epoch = ?)
                         OR (root.resource_kind IS NULL AND EXISTS (
                             SELECT 1 FROM cas_resource_bindings binding
                              WHERE binding.organization_id = root.organization_id
                                AND binding.resource_kind = ? AND binding.resource_id = ?
                                AND binding.tenant_epoch = ? AND binding.resource_epoch = ?
                                AND binding.digest_hex = root.digest_hex
                                AND binding.released_at IS NULL)))
                     LIMIT 1
                    """)) {
                roots.setString(1, retiring.tenantId());
                roots.setString(2, retiring.resourceKind().name());
                roots.setString(3, retiring.resourceId());
                roots.setLong(4, retiring.tenantEpoch());
                roots.setLong(5, retiring.resourceEpoch());
                roots.setString(6, retiring.resourceKind().name());
                roots.setString(7, retiring.resourceId());
                roots.setLong(8, retiring.tenantEpoch());
                roots.setLong(9, retiring.resourceEpoch());
                try (ResultSet rows = roots.executeQuery()) {
                    if (rows.next()) {
                        throw new IllegalStateException(
                                "resource retirement has unreconciled active snapshot roots");
                    }
                }
            }
            int released;
            try (PreparedStatement release = connection.prepareStatement("""
                    UPDATE cas_resource_bindings SET released_at = ?
                     WHERE organization_id = ? AND resource_kind = ? AND resource_id = ?
                       AND tenant_epoch = ? AND resource_epoch = ?
                       AND released_at IS NULL AND bound_at <= ?
                    """)) {
                Timestamp at = new Timestamp(transitionedAtEpochMillis);
                release.setTimestamp(1, at);
                release.setString(2, retiring.tenantId());
                release.setString(3, retiring.resourceKind().name());
                release.setString(4, retiring.resourceId());
                release.setLong(5, retiring.tenantEpoch());
                release.setLong(6, retiring.resourceEpoch());
                release.setTimestamp(7, at);
                released = release.executeUpdate();
            }
            try (PreparedStatement future = connection.prepareStatement("""
                    SELECT 1 FROM cas_resource_bindings
                     WHERE organization_id = ? AND resource_kind = ? AND resource_id = ?
                       AND tenant_epoch = ? AND resource_epoch = ?
                       AND released_at IS NULL LIMIT 1
                    """)) {
                future.setString(1, retiring.tenantId());
                future.setString(2, retiring.resourceKind().name());
                future.setString(3, retiring.resourceId());
                future.setLong(4, retiring.tenantEpoch());
                future.setLong(5, retiring.resourceEpoch());
                try (ResultSet rows = future.executeQuery()) {
                    if (rows.next()) {
                        throw new IllegalArgumentException(
                                "retirement cannot precede resource binding");
                    }
                }
            }
            try (PreparedStatement update = connection.prepareStatement("""
                    UPDATE cas_resource_lifecycles
                       SET lifecycle_state = 'RETIRED', transitioned_at = ?,
                           released_binding_count = ?
                     WHERE organization_id = ? AND resource_kind = ? AND resource_id = ?
                       AND tenant_epoch = ? AND resource_epoch = ?
                       AND lifecycle_state = 'RETIRING'
                    """)) {
                update.setTimestamp(1, new Timestamp(transitionedAtEpochMillis));
                update.setLong(2, released);
                update.setString(3, retiring.tenantId());
                update.setString(4, retiring.resourceKind().name());
                update.setString(5, retiring.resourceId());
                update.setLong(6, retiring.tenantEpoch());
                update.setLong(7, retiring.resourceEpoch());
                if (update.executeUpdate() != 1) {
                    throw new IllegalStateException("resource lifecycle changed during finalization");
                }
            }
            return new ResourceLifecycle(retiring.tenantId(), retiring.resourceKind(),
                    retiring.resourceId(), retiring.tenantEpoch(), retiring.resourceEpoch(),
                    ResourceLifecycleState.RETIRED, transitionedAtEpochMillis, released);
        });
    }

    @Override
    public ResourceLifecycle reactivateResource(
            ResourceLifecycle retired, long transitionedAtEpochMillis) {
        Objects.requireNonNull(retired, "retired");
        requireTransitionTime(transitionedAtEpochMillis);
        if (retired.state() != ResourceLifecycleState.RETIRED) {
            throw new IllegalStateException("resource reactivation token is not RETIRED");
        }
        return inTenant(retired.tenantId(), connection -> {
            long tenantEpoch = ensureActiveTenant(connection, retired.tenantId());
            lockResourceLifecycle(connection, retired.tenantId(),
                    retired.resourceKind(), retired.resourceId());
            ResourceLifecycle current = findResourceLifecycle(connection,
                    retired.tenantId(), retired.resourceKind(), retired.resourceId());
            requireExactLifecycleToken(current, retired);
            long nextEpoch = Math.addExact(retired.resourceEpoch(), 1);
            try (PreparedStatement update = connection.prepareStatement("""
                    UPDATE cas_resource_lifecycles
                       SET tenant_epoch = ?, resource_epoch = ?, lifecycle_state = 'ACTIVE',
                           transitioned_at = ?, released_binding_count = 0
                     WHERE organization_id = ? AND resource_kind = ? AND resource_id = ?
                       AND tenant_epoch = ? AND resource_epoch = ?
                       AND lifecycle_state = 'RETIRED'
                    """)) {
                update.setLong(1, tenantEpoch);
                update.setLong(2, nextEpoch);
                update.setTimestamp(3, new Timestamp(transitionedAtEpochMillis));
                update.setString(4, retired.tenantId());
                update.setString(5, retired.resourceKind().name());
                update.setString(6, retired.resourceId());
                update.setLong(7, retired.tenantEpoch());
                update.setLong(8, retired.resourceEpoch());
                if (update.executeUpdate() != 1) {
                    throw new IllegalStateException("resource lifecycle changed during reactivation");
                }
            }
            return new ResourceLifecycle(retired.tenantId(), retired.resourceKind(),
                    retired.resourceId(), tenantEpoch, nextEpoch,
                    ResourceLifecycleState.ACTIVE, transitionedAtEpochMillis, 0);
        });
    }

    @Override
    public void recordAndBindDurableResource(
            CatalogEntry entry,
            ResourceBinding binding,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        Objects.requireNonNull(binding, "binding");
        ResourceLifecycle resource = ensureActiveResource(
                binding.tenantId(), binding.resourceKind(), binding.resourceId());
        recordAndBindDurableResource(entry, binding, resource, durableObjectEnsurer);
    }

    @Override
    public void recordAndBindDurableResource(
            CatalogEntry entry,
            ResourceBinding binding,
            ResourceLifecycle resource,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        Objects.requireNonNull(entry, "entry");
        Objects.requireNonNull(binding, "binding");
        Objects.requireNonNull(resource, "resource");
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        if (!entry.tenantId().equals(binding.tenantId())
                || !entry.digest().equals(binding.digest())) {
            throw new IllegalArgumentException(
                    "catalogue entry and resource binding must identify the same tenant object");
        }
        inTenant(entry.tenantId(), connection -> {
            lockTenantLifecycle(connection, entry.tenantId());
            lockResourceLifecycle(connection, entry.tenantId(),
                    binding.resourceKind(), binding.resourceId());
            requireExactActiveResource(connection, resource);
            requireBindingResource(binding, resource);
            lockObjectLifecycles(connection, entry.tenantId(), List.of(entry.digest()));
            ensureNoActiveDeletionTombstones(
                    connection, entry.tenantId(), List.of(entry.digest()));
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(
                    connection, entry.tenantId(), List.of(entry.digest()));
            record(connection, entry);
            bindResource(connection, binding, resource);
            return null;
        });
    }

    private static void bindResource(Connection connection, ResourceBinding binding,
                                     ResourceLifecycle resource)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement("""
                INSERT INTO cas_resource_bindings (organization_id, resource_kind,
                    resource_id, digest_hex, bound_at, tenant_epoch, resource_epoch)
                SELECT organization_id, ?, ?, digest_hex, ?, ?, ?
                  FROM cas_object_catalog
                 WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                ON CONFLICT (organization_id, resource_kind, resource_id, digest_hex)
                DO UPDATE SET
                    bound_at = CASE
                        WHEN cas_resource_bindings.released_at IS NULL
                            THEN cas_resource_bindings.bound_at
                        ELSE EXCLUDED.bound_at
                    END,
                    tenant_epoch = EXCLUDED.tenant_epoch,
                    resource_epoch = EXCLUDED.resource_epoch,
                    released_at = NULL
                """)) {
            statement.setString(1, binding.resourceKind().name());
            statement.setString(2, binding.resourceId());
            statement.setTimestamp(3, new Timestamp(binding.boundAtEpochMillis()));
            statement.setLong(4, resource.tenantEpoch());
            statement.setLong(5, resource.resourceEpoch());
            statement.setString(6, binding.tenantId());
            statement.setString(7, binding.digest().hex());
            statement.setLong(8, binding.digest().sizeBytes());
            if (statement.executeUpdate() == 0) {
                throw new CasExceptions.CasNotFoundException(binding.digest());
            }
        }
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
    public long addReferenceRoots(List<ReferenceRoot> requestedRoots) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Map<String, ReferenceRoot> requestedByHex = requestedRootMap(requestedRoots);
        return inTenant(first.tenantId(), connection -> {
            ensureActiveTenant(connection, first.tenantId());
            List<CasDigest> digests = requestedRoots.stream()
                    .map(ReferenceRoot::digest).distinct().toList();
            lockObjectLifecycles(connection, first.tenantId(), digests);
            ensureNoDeletionTombstones(connection, first.tenantId(), digests);
            return addReferenceRoots(connection, first, requestedByHex);
        });
    }

    @Override
    public long publishDurableReferenceRoots(
            List<ReferenceRoot> requestedRoots,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        Map<String, ReferenceRoot> requestedByHex = requestedRootMap(requestedRoots);
        return inTenant(first.tenantId(), connection -> {
            ensureActiveTenant(connection, first.tenantId());
            List<CasDigest> digests = requestedRoots.stream()
                    .map(ReferenceRoot::digest).distinct().toList();
            lockObjectLifecycles(connection, first.tenantId(), digests);
            ensureNoActiveDeletionTombstones(connection, first.tenantId(), digests);
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(connection, first.tenantId(), digests);
            return addReferenceRoots(connection, first, requestedByHex);
        });
    }

    @Override
    public long publishDurableResourceReferenceRoots(
            ResourceLifecycle resource,
            List<ReferenceRoot> requestedRoots,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        Objects.requireNonNull(resource, "resource");
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        if (!resource.tenantId().equals(first.tenantId())) {
            throw new IllegalArgumentException("resource and roots must share a tenant");
        }
        Map<String, ReferenceRoot> requestedByHex = requestedRootMap(requestedRoots);
        return inTenant(first.tenantId(), connection -> {
            lockTenantLifecycle(connection, resource.tenantId());
            lockResourceLifecycle(connection, resource.tenantId(),
                    resource.resourceKind(), resource.resourceId());
            requireExactActiveResource(connection, resource);
            List<CasDigest> digests = requestedRoots.stream()
                    .map(ReferenceRoot::digest).distinct().toList();
            lockObjectLifecycles(connection, first.tenantId(), digests);
            ensureNoActiveDeletionTombstones(connection, first.tenantId(), digests);
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(connection, first.tenantId(), digests);
            return addReferenceRoots(connection, first, requestedByHex, resource);
        });
    }

    private long addReferenceRoots(
            Connection connection,
            ReferenceRoot first,
            Map<String, ReferenceRoot> requestedByHex
    ) throws SQLException {
        return addReferenceRoots(connection, first, requestedByHex, null);
    }

    private long addReferenceRoots(
            Connection connection,
            ReferenceRoot first,
            Map<String, ReferenceRoot> requestedByHex,
            ResourceLifecycle resource
    ) throws SQLException {
        // Row locks cannot serialize an as-yet absent root ID. A transaction advisory lock on
        // the exact logical root prevents two different first publications from interleaving
        // into an unauthorized union of their digest sets.
        lockReferenceRoot(connection, first.tenantId(), first.kind(), first.rootId());
        boolean hasHistory = false;
        boolean hasActive = false;
        long historicalGeneration = -1;
        long activeGeneration = -1;
        try (PreparedStatement existing = connection.prepareStatement("""
                SELECT digest_hex, size_bytes, created_at, released_at,
                       resource_kind, resource_id, tenant_epoch, resource_epoch
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
                    hasHistory = true;
                    historicalGeneration = Math.max(
                            historicalGeneration,
                            rows.getTimestamp("created_at").getTime());
                    String digestHex = rows.getString("digest_hex");
                    ReferenceRoot requested = requestedByHex.get(digestHex);
                    if (requested != null
                            && requested.digest().sizeBytes() != rows.getLong("size_bytes")) {
                        throw new IllegalStateException(
                                "reference root digest size conflicts with history");
                    }
                    if (rows.getTimestamp("released_at") == null) {
                        long generation = rows.getTimestamp("created_at").getTime();
                        if (hasActive && activeGeneration != generation) {
                            throw new IllegalStateException(
                                    "active reference root spans multiple generations");
                        }
                        hasActive = true;
                        activeGeneration = generation;
                    }
                    if (rows.getTimestamp("released_at") == null && requested == null) {
                        throw new IllegalStateException(
                                "active reference root conflicts with requested digest set");
                    }
                    String existingKind = rows.getString("resource_kind");
                    if (resource == null && existingKind != null) {
                        throw new IllegalStateException(
                                "resource-scoped root requires its lifecycle context");
                    }
                    if (resource != null && rows.getTimestamp("released_at") == null
                            && (existingKind == null
                            || !existingKind.equals(resource.resourceKind().name())
                            || !Objects.equals(rows.getString("resource_id"), resource.resourceId())
                            || rows.getLong("tenant_epoch") != resource.tenantEpoch()
                            || rows.getLong("resource_epoch") != resource.resourceEpoch())) {
                        throw new IllegalStateException(
                                "active root is owned by another resource incarnation");
                    }
                }
            }
        }
        long requestedGeneration = requestedByHex.values().stream()
                .mapToLong(ReferenceRoot::createdAtEpochMillis)
                .max().orElseThrow();
        long publicationGeneration = requestedGeneration;
        if (hasActive) {
            publicationGeneration = activeGeneration;
        } else if (hasHistory) {
            publicationGeneration = Math.max(
                    requestedGeneration, Math.addExact(historicalGeneration, 1L));
        }
        try (PreparedStatement statement = connection.prepareStatement("""
                INSERT INTO cas_reference_roots (organization_id, root_kind, root_id, digest_hex,
                    size_bytes, created_at, resource_kind, resource_id,
                    tenant_epoch, resource_epoch)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (organization_id, root_kind, root_id, digest_hex) DO UPDATE SET
                    created_at = CASE
                        WHEN cas_reference_roots.released_at IS NULL
                            THEN cas_reference_roots.created_at
                        ELSE EXCLUDED.created_at
                    END,
                    resource_kind = CASE
                        WHEN cas_reference_roots.released_at IS NULL
                            THEN cas_reference_roots.resource_kind
                        ELSE EXCLUDED.resource_kind
                    END,
                    resource_id = CASE
                        WHEN cas_reference_roots.released_at IS NULL
                            THEN cas_reference_roots.resource_id
                        ELSE EXCLUDED.resource_id
                    END,
                    tenant_epoch = CASE
                        WHEN cas_reference_roots.released_at IS NULL
                            THEN cas_reference_roots.tenant_epoch
                        ELSE EXCLUDED.tenant_epoch
                    END,
                    resource_epoch = CASE
                        WHEN cas_reference_roots.released_at IS NULL
                            THEN cas_reference_roots.resource_epoch
                        ELSE EXCLUDED.resource_epoch
                    END,
                    released_at = NULL
                """)) {
            for (ReferenceRoot root : requestedByHex.values()) {
                statement.setString(1, root.tenantId());
                statement.setString(2, root.kind().name());
                statement.setString(3, root.rootId());
                statement.setString(4, root.digest().hex());
                statement.setLong(5, root.digest().sizeBytes());
                statement.setTimestamp(6, new Timestamp(publicationGeneration));
                statement.setObject(7, resource == null ? null : resource.resourceKind().name());
                statement.setObject(8, resource == null ? null : resource.resourceId());
                statement.setObject(9, resource == null ? null : resource.tenantEpoch());
                statement.setObject(10, resource == null ? null : resource.resourceEpoch());
                statement.addBatch();
            }
            statement.executeBatch();
        }
        try (PreparedStatement active = connection.prepareStatement("""
                SELECT max(created_at) AS active_generation
                  FROM cas_reference_roots
                 WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                   AND released_at IS NULL
                """)) {
            active.setString(1, first.tenantId());
            active.setString(2, first.kind().name());
            active.setString(3, first.rootId());
            try (ResultSet rows = active.executeQuery()) {
                if (!rows.next() || rows.getTimestamp("active_generation") == null) {
                    throw new IllegalStateException(
                            "reference root publication produced no active generation");
                }
                return rows.getTimestamp("active_generation").getTime();
            }
        }
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
            lockReferenceRoot(connection, tenantId, kind, rootId);
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
    public boolean releaseReferenceRootGeneration(
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId,
            long expectedGeneration,
            long releasedAtEpochMillis
    ) {
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        if (expectedGeneration < 0 || releasedAtEpochMillis < expectedGeneration) {
            throw new IllegalArgumentException("reference root generation/release is invalid");
        }
        return inTenant(tenantId, connection -> {
            lockReferenceRoot(connection, tenantId, kind, rootId);
            int activeCount = 0;
            try (PreparedStatement active = connection.prepareStatement("""
                    SELECT created_at
                      FROM cas_reference_roots
                     WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                       AND released_at IS NULL
                     FOR UPDATE
                    """)) {
                active.setString(1, tenantId);
                active.setString(2, kind.name());
                active.setString(3, rootId);
                try (ResultSet rows = active.executeQuery()) {
                    while (rows.next()) {
                        activeCount++;
                        if (rows.getTimestamp("created_at").getTime() != expectedGeneration) {
                            return false;
                        }
                    }
                }
            }
            if (activeCount == 0) {
                return false;
            }
            try (PreparedStatement release = connection.prepareStatement("""
                    UPDATE cas_reference_roots SET released_at = ?
                     WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                       AND released_at IS NULL AND created_at = ?
                    """)) {
                release.setTimestamp(1, new Timestamp(releasedAtEpochMillis));
                release.setString(2, tenantId);
                release.setString(3, kind.name());
                release.setString(4, rootId);
                release.setTimestamp(5, new Timestamp(expectedGeneration));
                int releasedCount = release.executeUpdate();
                if (releasedCount != activeCount) {
                    throw new IllegalStateException(
                            "reference root generation changed during compare-and-release");
                }
                return true;
            }
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
    public List<ReferenceRoot> activeReferenceRoots(
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId
    ) {
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        return inTenant(tenantId, connection -> {
            List<ReferenceRoot> roots = new ArrayList<>();
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT digest_hex, size_bytes, created_at
                      FROM cas_reference_roots
                     WHERE organization_id = ? AND root_kind = ? AND root_id = ?
                       AND released_at IS NULL
                     ORDER BY digest_hex
                    """)) {
                statement.setString(1, tenantId);
                statement.setString(2, kind.name());
                statement.setString(3, rootId);
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        roots.add(new ReferenceRoot(
                                tenantId,
                                kind,
                                rootId,
                                new CasDigest(CasDigest.ALGORITHM,
                                        rows.getString("digest_hex"),
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
            // V76's legal-hold trigger takes tenant then object.  Take the same prefix here even
            // when removing a hold so no catalog path can invert tenant->resource->object order.
            lockTenantLifecycle(connection, tenantId);
            lockObjectLifecycles(connection, tenantId, List.of(digest));
            if (legalHold) {
                ensureNoDeletionTombstones(connection, tenantId, List.of(digest));
            }
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

    private enum DeletionStart {
        READY,
        LIVE_REFERENCE_OR_HOLD,
        UNAVAILABLE
    }

    @Override
    public CasGarbageCollector.AtomicDeletionOutcome deleteIfUnreferenced(
            CasGarbageCollector.Candidate candidate,
            TenantCasStore tenantStore
    ) {
        Objects.requireNonNull(candidate, "candidate");
        Objects.requireNonNull(tenantStore, "tenantStore");
        if (tenantStore.deletionScope() != TenantCasStore.DeletionScope.TENANT_ISOLATED) {
            // RLS deliberately prevents this tenant-scoped adapter from proving that a globally
            // shared digest has no roots in another tenant. A privileged cross-tenant service is
            // required for GLOBAL_SHARED stores.
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
        final CasStore store;
        try {
            store = tenantStore.forTenant(candidate.tenantId());
        } catch (RuntimeException unavailableStore) {
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }

        DeletionStart start;
        try {
            start = beginDeletion(candidate);
        } catch (RuntimeException unavailableCatalog) {
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
        if (start == DeletionStart.LIVE_REFERENCE_OR_HOLD) {
            return CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD;
        }
        if (start != DeletionStart.READY) {
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }

        CasGarbageCollector.AtomicDeletionOutcome outcome;
        String tombstoneState;
        try {
            boolean deleted = store.delete(candidate.digest());
            boolean stillPresent = store.contains(candidate.digest());
            if (!deleted) {
                outcome = stillPresent
                        ? CasGarbageCollector.AtomicDeletionOutcome.FAILED
                        : CasGarbageCollector.AtomicDeletionOutcome.NOT_FOUND;
                tombstoneState = stillPresent ? "FAILED" : "MISSING";
            } else if (stillPresent) {
                outcome = CasGarbageCollector.AtomicDeletionOutcome.FAILED;
                tombstoneState = "FAILED";
            } else {
                outcome = CasGarbageCollector.AtomicDeletionOutcome.DELETED;
                tombstoneState = "DELETED";
            }
        } catch (RuntimeException ambiguousDelete) {
            outcome = CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
            tombstoneState = "OUTCOME_UNKNOWN";
        }
        try {
            finalizeDeletionTombstone(candidate, tombstoneState);
        } catch (RuntimeException unavailableCatalog) {
            // The already-committed PENDING tombstone remains and blocks every publication. Do
            // not count bytes as reclaimed without the durable final audit transition.
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
        return outcome;
    }

    private DeletionStart beginDeletion(CasGarbageCollector.Candidate candidate) {
        return inTenant(candidate.tenantId(), connection -> {
            lockObjectLifecycles(
                    connection, candidate.tenantId(), List.of(candidate.digest()));
            try (PreparedStatement existingTombstone = connection.prepareStatement("""
                    SELECT deletion_state
                      FROM cas_object_deletion_tombstones
                     WHERE organization_id = ? AND digest_hex = ?
                     FOR UPDATE
                    """)) {
                existingTombstone.setString(1, candidate.tenantId());
                existingTombstone.setString(2, candidate.digest().hex());
                try (ResultSet rows = existingTombstone.executeQuery()) {
                    if (rows.next() && Set.of("PENDING", "OUTCOME_UNKNOWN")
                            .contains(rows.getString("deletion_state"))) {
                        // One physical attempt at a time. OUTCOME_UNKNOWN additionally requires
                        // provider reconciliation before either retry or durable repair.
                        return DeletionStart.UNAVAILABLE;
                    }
                }
            }
            boolean legalHold;
            try (PreparedStatement object = connection.prepareStatement("""
                    SELECT size_bytes, legal_hold
                      FROM cas_object_catalog
                     WHERE organization_id = ? AND digest_hex = ?
                     FOR UPDATE
                    """)) {
                object.setString(1, candidate.tenantId());
                object.setString(2, candidate.digest().hex());
                try (ResultSet rows = object.executeQuery()) {
                    if (!rows.next()
                            || rows.getLong("size_bytes") != candidate.digest().sizeBytes()) {
                        return DeletionStart.UNAVAILABLE;
                    }
                    legalHold = rows.getBoolean("legal_hold");
                }
            }
            boolean activeReference;
            try (PreparedStatement root = connection.prepareStatement("""
                    SELECT 1
                      FROM cas_reference_roots
                     WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                       AND released_at IS NULL
                    UNION ALL
                    SELECT 1
                      FROM cas_resource_bindings
                     WHERE organization_id = ? AND digest_hex = ?
                       AND released_at IS NULL
                    LIMIT 1
                    """)) {
                root.setString(1, candidate.tenantId());
                root.setString(2, candidate.digest().hex());
                root.setLong(3, candidate.digest().sizeBytes());
                root.setString(4, candidate.tenantId());
                root.setString(5, candidate.digest().hex());
                try (ResultSet rows = root.executeQuery()) {
                    activeReference = rows.next();
                }
            }
            if (legalHold || activeReference) {
                return DeletionStart.LIVE_REFERENCE_OR_HOLD;
            }
            try (PreparedStatement tombstone = connection.prepareStatement("""
                    INSERT INTO cas_object_deletion_tombstones (
                        organization_id, digest_hex, size_bytes, deletion_state,
                        created_at, updated_at)
                    VALUES (?, ?, ?, 'PENDING', now(), now())
                    ON CONFLICT (organization_id, digest_hex) DO UPDATE SET
                        size_bytes = EXCLUDED.size_bytes,
                        deletion_state = 'PENDING',
                        updated_at = now()
                    """)) {
                tombstone.setString(1, candidate.tenantId());
                tombstone.setString(2, candidate.digest().hex());
                tombstone.setLong(3, candidate.digest().sizeBytes());
                tombstone.executeUpdate();
            }
            return DeletionStart.READY;
        });
    }

    private void finalizeDeletionTombstone(
            CasGarbageCollector.Candidate candidate,
            String deletionState
    ) {
        inTenant(candidate.tenantId(), connection -> {
            lockObjectLifecycles(
                    connection, candidate.tenantId(), List.of(candidate.digest()));
            try (PreparedStatement tombstone = connection.prepareStatement("""
                    UPDATE cas_object_deletion_tombstones
                       SET deletion_state = ?, updated_at = now()
                     WHERE organization_id = ? AND digest_hex = ? AND size_bytes = ?
                    """)) {
                tombstone.setString(1, deletionState);
                tombstone.setString(2, candidate.tenantId());
                tombstone.setString(3, candidate.digest().hex());
                tombstone.setLong(4, candidate.digest().sizeBytes());
                if (tombstone.executeUpdate() != 1) {
                    throw new IllegalStateException("CAS deletion tombstone disappeared");
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

    private static long ensureActiveTenant(Connection connection, String tenantId)
            throws SQLException {
        lockTenantLifecycle(connection, tenantId);
        try (PreparedStatement insert = connection.prepareStatement("""
                INSERT INTO cas_tenant_lifecycles (
                    organization_id, tenant_epoch, lifecycle_state, transitioned_at)
                VALUES (?, 1, 'ACTIVE', ?)
                ON CONFLICT (organization_id) DO NOTHING
                """)) {
            insert.setString(1, tenantId);
            insert.setTimestamp(2, new Timestamp(0));
            insert.executeUpdate();
        }
        try (PreparedStatement select = connection.prepareStatement("""
                SELECT tenant_epoch, lifecycle_state
                  FROM cas_tenant_lifecycles
                 WHERE organization_id = ? FOR UPDATE
                """)) {
            select.setString(1, tenantId);
            try (ResultSet rows = select.executeQuery()) {
                if (!rows.next() || !"ACTIVE".equals(rows.getString("lifecycle_state"))) {
                    throw new IllegalStateException("CAS tenant is not ACTIVE");
                }
                return rows.getLong("tenant_epoch");
            }
        }
    }

    private static ResourceLifecycle ensureActiveResource(
            Connection connection, String tenantId, ResourceKind resourceKind, String resourceId)
            throws SQLException {
        long tenantEpoch = ensureActiveTenant(connection, tenantId);
        lockResourceLifecycle(connection, tenantId, resourceKind, resourceId);
        try (PreparedStatement insert = connection.prepareStatement("""
                INSERT INTO cas_resource_lifecycles (
                    organization_id, resource_kind, resource_id, tenant_epoch, resource_epoch,
                    lifecycle_state, transitioned_at, released_binding_count)
                VALUES (?, ?, ?, ?, 1, 'ACTIVE', ?, 0)
                ON CONFLICT (organization_id, resource_kind, resource_id) DO NOTHING
                """)) {
            insert.setString(1, tenantId);
            insert.setString(2, resourceKind.name());
            insert.setString(3, resourceId);
            insert.setLong(4, tenantEpoch);
            insert.setTimestamp(5, new Timestamp(0));
            insert.executeUpdate();
        }
        ResourceLifecycle current = findResourceLifecycle(
                connection, tenantId, resourceKind, resourceId);
        if (current == null || current.state() != ResourceLifecycleState.ACTIVE
                || current.tenantEpoch() != tenantEpoch) {
            throw new IllegalStateException("CAS resource is not ACTIVE");
        }
        return current;
    }

    private static ResourceLifecycle findResourceLifecycle(
            Connection connection, String tenantId, ResourceKind resourceKind, String resourceId)
            throws SQLException {
        try (PreparedStatement select = connection.prepareStatement("""
                SELECT tenant_epoch, resource_epoch, lifecycle_state, transitioned_at,
                       released_binding_count
                  FROM cas_resource_lifecycles
                 WHERE organization_id = ? AND resource_kind = ? AND resource_id = ?
                 FOR UPDATE
                """)) {
            select.setString(1, tenantId);
            select.setString(2, resourceKind.name());
            select.setString(3, resourceId);
            try (ResultSet rows = select.executeQuery()) {
                if (!rows.next()) return null;
                return new ResourceLifecycle(tenantId, resourceKind, resourceId,
                        rows.getLong("tenant_epoch"), rows.getLong("resource_epoch"),
                        ResourceLifecycleState.valueOf(rows.getString("lifecycle_state")),
                        rows.getTimestamp("transitioned_at").getTime(),
                        rows.getLong("released_binding_count"));
            }
        }
    }

    private static void requireExactActiveResource(
            Connection connection, ResourceLifecycle supplied) throws SQLException {
        supplied.requireActive();
        ResourceLifecycle current = findResourceLifecycle(connection, supplied.tenantId(),
                supplied.resourceKind(), supplied.resourceId());
        requireExactLifecycleToken(current, supplied);
    }

    private static void requireExactLifecycleToken(
            ResourceLifecycle current, ResourceLifecycle supplied) {
        if (current == null
                || current.tenantEpoch() != supplied.tenantEpoch()
                || current.resourceEpoch() != supplied.resourceEpoch()
                || current.state() != supplied.state()
                || current.transitionedAtEpochMillis() != supplied.transitionedAtEpochMillis()
                || current.releasedBindingCount() != supplied.releasedBindingCount()) {
            throw new IllegalStateException("resource lifecycle token is stale or invalid");
        }
    }

    private static void requireBindingResource(
            ResourceBinding binding, ResourceLifecycle resource) {
        if (!binding.tenantId().equals(resource.tenantId())
                || binding.resourceKind() != resource.resourceKind()
                || !binding.resourceId().equals(resource.resourceId())) {
            throw new IllegalArgumentException(
                    "binding and resource lifecycle identify different resources");
        }
    }

    private static void lockTenantLifecycle(Connection connection, String tenantId)
            throws SQLException {
        try (PreparedStatement lock = connection.prepareStatement(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
            lock.setString(1, "elmos-cas-tenant-lifecycle/1\n" + tenantId);
            lock.execute();
        }
    }

    private static void lockResourceLifecycle(
            Connection connection, String tenantId, ResourceKind resourceKind, String resourceId)
            throws SQLException {
        try (PreparedStatement lock = connection.prepareStatement(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
            lock.setString(1, "elmos-cas-resource-lifecycle/1\n" + tenantId + '\n'
                    + resourceKind.name() + '\n' + resourceId);
            lock.execute();
        }
    }

    private static void requireTransitionTime(long transitionedAtEpochMillis) {
        if (transitionedAtEpochMillis < 0) {
            throw new IllegalArgumentException("lifecycle transition time must not be negative");
        }
    }

    private static void record(Connection connection, CatalogEntry entry) throws SQLException {
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
    }

    private static void lockReferenceRoot(
            Connection connection,
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId
    ) throws SQLException {
        try (PreparedStatement lock = connection.prepareStatement(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
            lock.setString(1, tenantId + "\n" + kind + "\n" + rootId);
            lock.execute();
        }
    }

    private static void lockObjectLifecycles(
            Connection connection,
            String tenantId,
            List<CasDigest> digests
    ) throws SQLException {
        List<CasDigest> ordered = digests.stream().distinct()
                .sorted(java.util.Comparator.comparing(CasDigest::compact)).toList();
        if (ordered.isEmpty()) {
            throw new IllegalArgumentException("object lifecycle lock set must not be empty");
        }
        try (PreparedStatement lock = connection.prepareStatement(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
            for (CasDigest digest : ordered) {
                lock.setString(1, objectLifecycleLockKey(tenantId, digest));
                lock.addBatch();
            }
            lock.executeBatch();
        }
    }

    private static String objectLifecycleLockKey(String tenantId, CasDigest digest) {
        return "elmos-cas-object-lifecycle/1\n" + tenantId + '\n' + digest.hex();
    }

    private static void ensureNoDeletionTombstones(
            Connection connection,
            String tenantId,
            List<CasDigest> digests
    ) throws SQLException {
        try (PreparedStatement tombstones = connection.prepareStatement("""
                SELECT digest_hex
                  FROM cas_object_deletion_tombstones
                 WHERE organization_id = ? AND digest_hex = ANY (?)
                 LIMIT 1
                """)) {
            tombstones.setString(1, tenantId);
            tombstones.setArray(2, connection.createArrayOf(
                    "varchar", digests.stream().map(CasDigest::hex).distinct().toArray()));
            try (ResultSet rows = tombstones.executeQuery()) {
                if (rows.next()) {
                    throw new IllegalStateException(
                            "reference publication is blocked by an unresolved deletion");
                }
            }
        }
    }

    private static void ensureNoActiveDeletionTombstones(
            Connection connection,
            String tenantId,
            List<CasDigest> digests
    ) throws SQLException {
        try (PreparedStatement tombstones = connection.prepareStatement("""
                SELECT digest_hex, deletion_state
                  FROM cas_object_deletion_tombstones
                 WHERE organization_id = ? AND digest_hex = ANY (?)
                   AND deletion_state IN ('PENDING', 'OUTCOME_UNKNOWN')
                 LIMIT 1
                """)) {
            tombstones.setString(1, tenantId);
            tombstones.setArray(2, connection.createArrayOf(
                    "varchar", digests.stream().map(CasDigest::hex).distinct().toArray()));
            try (ResultSet rows = tombstones.executeQuery()) {
                if (rows.next()) {
                    throw new IllegalStateException(
                            "durable publication is blocked by active or ambiguous deletion state "
                                    + rows.getString("deletion_state"));
                }
            }
        }
    }

    private static void clearRepairableDeletionTombstones(
            Connection connection,
            String tenantId,
            List<CasDigest> digests
    ) throws SQLException {
        try (PreparedStatement tombstones = connection.prepareStatement("""
                DELETE FROM cas_object_deletion_tombstones
                 WHERE organization_id = ? AND digest_hex = ANY (?)
                   AND deletion_state IN ('DELETED', 'MISSING', 'FAILED')
                """)) {
            tombstones.setString(1, tenantId);
            tombstones.setArray(2, connection.createArrayOf(
                    "varchar", digests.stream().map(CasDigest::hex).distinct().toArray()));
            tombstones.executeUpdate();
        }
        // PENDING and OUTCOME_UNKNOWN are persistent fences, not repair hints. This second check
        // is load-bearing even though callers already hold the lifecycle advisory lock: it makes
        // a schema/trigger drift fail before any root or resource binding can become active.
        ensureNoDeletionTombstones(connection, tenantId, digests);
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

    private static ReferenceRoot requireEntryRootSet(
            CatalogEntry entry, List<ReferenceRoot> requestedRoots
    ) {
        Objects.requireNonNull(entry, "entry");
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        if (!entry.tenantId().equals(first.tenantId())
                || requestedRoots.stream().noneMatch(root -> root.digest().equals(entry.digest()))) {
            throw new IllegalArgumentException(
                    "catalogue entry and root set must share tenant and contain the object");
        }
        return first;
    }

    private static Map<String, ReferenceRoot> requestedRootMap(List<ReferenceRoot> requestedRoots) {
        Map<String, ReferenceRoot> requestedByHex = new LinkedHashMap<>();
        for (ReferenceRoot root : requestedRoots) {
            ReferenceRoot duplicate = requestedByHex.putIfAbsent(root.digest().hex(), root);
            if (duplicate != null && !duplicate.digest().equals(root.digest())) {
                throw new IllegalArgumentException("one digest hex cannot carry two sizes in a root set");
            }
        }
        return requestedByHex;
    }
}
