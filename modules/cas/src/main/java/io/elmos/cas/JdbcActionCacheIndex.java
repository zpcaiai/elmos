package io.elmos.cas;

import javax.sql.DataSource;
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/** PostgreSQL-backed, tenant-RLS-scoped {@link ActionCacheIndex}. */
public final class JdbcActionCacheIndex implements ActionCacheIndex {

    private static final String ACTIVE_ENTRY_SELECT = """
            SELECT * FROM cas_action_cache_entries
            WHERE organization_id = ? AND action_key_hex = ? AND invalidated_at IS NULL
            """;

    private static final String UPSERT = """
            INSERT INTO cas_action_cache_entries (
              organization_id, action_key_hex, action_key_bytes,
              action_component_names, action_component_values,
              project_id, action_id, receipt_id, attempt, lease_generation,
              result_status, exit_code, failure_class, failure_message, validation_status,
              output_manifest_hex, output_manifest_bytes,
              provenance_digest_hex, provenance_digest_bytes,
              stdout_digest_hex, stdout_digest_bytes, stderr_digest_hex, stderr_digest_bytes,
              result_schema_version, result_started_at, result_finished_at,
              toolchain_image, producer_permission_scope, producer_residency,
              producer_security_tier, producer_sensitivity,
              producer_provenance_digest_hex, producer_provenance_digest_bytes,
              risk_tier, writer_service_id, writer_trust_domain, writer_node_id,
              writer_attested,
              attestation_key_id, attestation_algorithm,
              attestation_signature_hex, attestation_signature_bytes,
              attestation_signature_value,
              attestation_envelope_version,
              attestation_envelope_hex, attestation_envelope_bytes,
              attestation_signed_at_epoch_millis,
              attestation_verified,
              wall_seconds, cpu_seconds, max_memory_mb, read_bytes, written_bytes, gpu_seconds,
              cost_names, cost_values, stored_at, expires_at, invalidated_at, invalidation_reason
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL
            )
            ON CONFLICT (organization_id, action_key_hex) DO UPDATE SET
              action_key_bytes = EXCLUDED.action_key_bytes,
              action_component_names = EXCLUDED.action_component_names,
              action_component_values = EXCLUDED.action_component_values,
              project_id = EXCLUDED.project_id,
              action_id = EXCLUDED.action_id,
              receipt_id = EXCLUDED.receipt_id,
              attempt = EXCLUDED.attempt,
              lease_generation = EXCLUDED.lease_generation,
              result_status = EXCLUDED.result_status,
              exit_code = EXCLUDED.exit_code,
              failure_class = EXCLUDED.failure_class,
              failure_message = EXCLUDED.failure_message,
              validation_status = EXCLUDED.validation_status,
              output_manifest_hex = EXCLUDED.output_manifest_hex,
              output_manifest_bytes = EXCLUDED.output_manifest_bytes,
              provenance_digest_hex = EXCLUDED.provenance_digest_hex,
              provenance_digest_bytes = EXCLUDED.provenance_digest_bytes,
              stdout_digest_hex = EXCLUDED.stdout_digest_hex,
              stdout_digest_bytes = EXCLUDED.stdout_digest_bytes,
              stderr_digest_hex = EXCLUDED.stderr_digest_hex,
              stderr_digest_bytes = EXCLUDED.stderr_digest_bytes,
              result_schema_version = EXCLUDED.result_schema_version,
              result_started_at = EXCLUDED.result_started_at,
              result_finished_at = EXCLUDED.result_finished_at,
              toolchain_image = EXCLUDED.toolchain_image,
              producer_permission_scope = EXCLUDED.producer_permission_scope,
              producer_residency = EXCLUDED.producer_residency,
              producer_security_tier = EXCLUDED.producer_security_tier,
              producer_sensitivity = EXCLUDED.producer_sensitivity,
              producer_provenance_digest_hex = EXCLUDED.producer_provenance_digest_hex,
              producer_provenance_digest_bytes = EXCLUDED.producer_provenance_digest_bytes,
              risk_tier = EXCLUDED.risk_tier,
              writer_service_id = EXCLUDED.writer_service_id,
              writer_trust_domain = EXCLUDED.writer_trust_domain,
              writer_node_id = EXCLUDED.writer_node_id,
              writer_attested = EXCLUDED.writer_attested,
              attestation_key_id = EXCLUDED.attestation_key_id,
              attestation_algorithm = EXCLUDED.attestation_algorithm,
              attestation_signature_hex = EXCLUDED.attestation_signature_hex,
              attestation_signature_bytes = EXCLUDED.attestation_signature_bytes,
              attestation_signature_value = EXCLUDED.attestation_signature_value,
              attestation_envelope_version = EXCLUDED.attestation_envelope_version,
              attestation_envelope_hex = EXCLUDED.attestation_envelope_hex,
              attestation_envelope_bytes = EXCLUDED.attestation_envelope_bytes,
              attestation_signed_at_epoch_millis = EXCLUDED.attestation_signed_at_epoch_millis,
              attestation_verified = EXCLUDED.attestation_verified,
              wall_seconds = EXCLUDED.wall_seconds,
              cpu_seconds = EXCLUDED.cpu_seconds,
              max_memory_mb = EXCLUDED.max_memory_mb,
              read_bytes = EXCLUDED.read_bytes,
              written_bytes = EXCLUDED.written_bytes,
              gpu_seconds = EXCLUDED.gpu_seconds,
              cost_names = EXCLUDED.cost_names,
              cost_values = EXCLUDED.cost_values,
              stored_at = EXCLUDED.stored_at,
              expires_at = EXCLUDED.expires_at,
              invalidated_at = NULL,
              invalidation_reason = NULL
            WHERE cas_action_cache_entries.invalidated_at IS NOT NULL
               OR (cas_action_cache_entries.expires_at IS NOT NULL
                   AND cas_action_cache_entries.expires_at < EXCLUDED.stored_at)
            """;

    private final DataSource dataSource;

    public JdbcActionCacheIndex(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    @Override
    public Optional<ActionCache.Entry> find(ActionKey key) {
        Objects.requireNonNull(key, "key");
        return inTenantTransaction(key.tenantId(), connection -> find(connection, key));
    }

    @Override
    public void store(ActionCache.Entry entry) {
        Objects.requireNonNull(entry, "entry");
        inTenantTransaction(entry.key().tenantId(), connection -> {
            int changed;
            try (PreparedStatement statement = connection.prepareStatement(UPSERT)) {
                bindEntry(connection, statement, entry);
                changed = statement.executeUpdate();
            }
            if (changed == 0) {
                ActionCache.Entry current = find(connection, entry.key()).orElseThrow(() ->
                        new IllegalStateException("active action-cache conflict row disappeared"));
                if (!ActionCacheIndex.isIdempotentReplay(current, entry)) {
                    throw new CasExceptions.CasAccessDeniedException(
                            "ACTION_KEY_RESULT_CONFLICT", entry.key().shortForm());
                }
            }
            return null;
        });
    }

    @Override
    public boolean invalidate(ActionKey key, String reason, long atEpochMillis) {
        String detail = boundedReason(reason);
        return inTenantTransaction(key.tenantId(), connection -> {
            recordInvalidation(connection, key.tenantId(), key.digest().hex(), detail,
                    atEpochMillis, null);
            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE cas_action_cache_entries
                    SET invalidated_at = ?, invalidation_reason = ?
                    WHERE organization_id = ? AND action_key_hex = ? AND invalidated_at IS NULL
                    """)) {
                statement.setTimestamp(1, timestamp(atEpochMillis));
                statement.setString(2, detail);
                statement.setString(3, key.tenantId());
                statement.setString(4, key.digest().hex());
                return statement.executeUpdate() > 0;
            }
        });
    }

    @Override
    public int invalidateByWriter(String tenantId, String nodeId, String reason, long atEpochMillis) {
        String tenant = CasText.required(tenantId, "tenantId");
        String node = CasText.required(nodeId, "nodeId");
        String detail = boundedReason(reason);
        return inTenantTransaction(tenant, connection -> {
            try (PreparedStatement audit = connection.prepareStatement("""
                    INSERT INTO cas_action_cache_invalidations
                      (organization_id, action_key_hex, invalidated_at, reason, writer_node_id)
                    SELECT organization_id, action_key_hex, ?, ?, writer_node_id
                    FROM cas_action_cache_entries
                    WHERE organization_id = ? AND writer_node_id = ? AND invalidated_at IS NULL
                    ON CONFLICT DO NOTHING
                    """)) {
                audit.setTimestamp(1, timestamp(atEpochMillis));
                audit.setString(2, detail);
                audit.setString(3, tenant);
                audit.setString(4, node);
                audit.executeUpdate();
            }
            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE cas_action_cache_entries
                    SET invalidated_at = ?, invalidation_reason = ?
                    WHERE organization_id = ? AND writer_node_id = ? AND invalidated_at IS NULL
                    """)) {
                statement.setTimestamp(1, timestamp(atEpochMillis));
                statement.setString(2, detail);
                statement.setString(3, tenant);
                statement.setString(4, node);
                return statement.executeUpdate();
            }
        });
    }

    @Override
    public void quarantineNode(String tenantId, String nodeId, String reason, long atEpochMillis) {
        String tenant = CasText.required(tenantId, "tenantId");
        String node = CasText.required(nodeId, "nodeId");
        String detail = CasText.required(reason, "reason");
        if (detail.length() > 512) {
            throw new IllegalArgumentException("quarantine reason exceeds 512 characters");
        }
        inTenantTransaction(tenant, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cas_action_cache_quarantined_nodes
                      (organization_id, writer_node_id, reason, quarantined_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (organization_id, writer_node_id) DO NOTHING
                    """)) {
                statement.setString(1, tenant);
                statement.setString(2, node);
                statement.setString(3, detail);
                statement.setTimestamp(4, timestamp(atEpochMillis));
                statement.executeUpdate();
            }
            return null;
        });
    }

    @Override
    public boolean isNodeQuarantined(String tenantId, String nodeId) {
        String tenant = CasText.required(tenantId, "tenantId");
        String node = CasText.required(nodeId, "nodeId");
        return inTenantTransaction(tenant, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT 1 FROM cas_action_cache_quarantined_nodes
                    WHERE organization_id = ? AND writer_node_id = ?
                    """)) {
                statement.setString(1, tenant);
                statement.setString(2, node);
                try (ResultSet rows = statement.executeQuery()) {
                    return rows.next();
                }
            }
        });
    }

    @Override
    public Map<CasDigest, CasDigest> liveOutputManifests(String tenantId) {
        String tenant = CasText.required(tenantId, "tenantId");
        return inTenantTransaction(tenant, connection -> {
            Map<CasDigest, CasDigest> live = new LinkedHashMap<>();
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT action_key_hex, action_key_bytes,
                           output_manifest_hex, output_manifest_bytes
                    FROM cas_action_cache_entries
                    WHERE organization_id = ? AND invalidated_at IS NULL
                      AND (expires_at IS NULL OR expires_at >= now())
                    ORDER BY action_key_hex
                    """)) {
                statement.setString(1, tenant);
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        live.put(digest(rows, "action_key_hex", "action_key_bytes"),
                                digest(rows, "output_manifest_hex", "output_manifest_bytes"));
                    }
                }
            }
            return Map.copyOf(live);
        });
    }

    @Override
    public int size(String tenantId) {
        String tenant = CasText.required(tenantId, "tenantId");
        return inTenantTransaction(tenant, connection -> {
            try (PreparedStatement statement = connection.prepareStatement("""
                    SELECT count(*) FROM cas_action_cache_entries
                    WHERE organization_id = ? AND invalidated_at IS NULL
                      AND (expires_at IS NULL OR expires_at >= now())
                    """)) {
                statement.setString(1, tenant);
                try (ResultSet rows = statement.executeQuery()) {
                    if (!rows.next()) {
                        throw new IllegalStateException("action-cache count returned no row");
                    }
                    return rows.getInt(1);
                }
            }
        });
    }

    private Optional<ActionCache.Entry> find(Connection connection, ActionKey requested) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(ACTIVE_ENTRY_SELECT)) {
            statement.setString(1, requested.tenantId());
            statement.setString(2, requested.digest().hex());
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                ActionCache.Entry entry = readEntry(rows);
                if (!entry.key().equals(requested)) {
                    throw new CasExceptions.CasAccessDeniedException(
                            "ACTION_KEY_METADATA_MISMATCH", requested.shortForm());
                }
                return Optional.of(entry);
            }
        }
    }

    private static ActionCache.Entry readEntry(ResultSet rows) throws SQLException {
        String tenant = rows.getString("organization_id");
        ActionKey key = new ActionKey(
                digest(rows, "action_key_hex", "action_key_bytes"), tenant,
                pairedMap(textArray(rows, "action_component_names"),
                        textArray(rows, "action_component_values"), "action components"));

        Optional<CasDigest> stdout = optionalDigest(rows, "stdout_digest_hex", "stdout_digest_bytes");
        Optional<CasDigest> stderr = optionalDigest(rows, "stderr_digest_hex", "stderr_digest_bytes");
        Map<String, Double> cost = pairedDoubleMap(textArray(rows, "cost_names"),
                numberArray(rows, "cost_values"), "cost");
        String failureClass = rows.getString("failure_class");
        String failureMessage = rows.getString("failure_message");
        ActionResultRecord result = new ActionResultRecord(
                requireColumn(rows, "result_schema_version"),
                rows.getString("action_id"), rows.getInt("attempt"), rows.getInt("lease_generation"),
                rows.getString("receipt_id"),
                ActionResultRecord.Status.valueOf(rows.getString("result_status")),
                requireColumn(rows, "result_started_at"), requireColumn(rows, "result_finished_at"),
                rows.getInt("exit_code"),
                digest(rows, "output_manifest_hex", "output_manifest_bytes"), stdout, stderr,
                new ActionResultRecord.ResourceUsage(
                        rows.getDouble("cpu_seconds"), rows.getDouble("max_memory_mb"),
                        rows.getLong("read_bytes"), rows.getLong("written_bytes"),
                        rows.getDouble("gpu_seconds"), rows.getDouble("wall_seconds")),
                cost,
                Optional.ofNullable(failureClass).map(ActionResultRecord.FailureClass::valueOf),
                Optional.ofNullable(failureMessage),
                ActionResultRecord.ValidationStatus.valueOf(rows.getString("validation_status")),
                digest(rows, "provenance_digest_hex", "provenance_digest_bytes"));

        CasAccessPolicy.ProducerContext producer = new CasAccessPolicy.ProducerContext(
                tenant, rows.getString("project_id"), new LinkedHashSet<>(textArray(rows,
                "producer_permission_scope")), rows.getString("producer_residency"),
                CasAccessPolicy.SecurityTier.valueOf(rows.getString("producer_security_tier")),
                CasObjectModel.Sensitivity.valueOf(rows.getString("producer_sensitivity")),
                rows.getString("toolchain_image"),
                optionalDigest(rows, "producer_provenance_digest_hex",
                        "producer_provenance_digest_bytes"));

        String attestationKey = rows.getString("attestation_key_id");
        Optional<ActionCache.ResultAttestation> attestation = attestationKey == null
                ? Optional.empty()
                : Optional.of(readAttestation(rows, attestationKey));
        if (attestationKey == null && hasAnyAttestationMetadata(rows)) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:attestation");
        }
        Timestamp expiry = rows.getTimestamp("expires_at");
        // Entry's compact constructor recomputes the v2 envelope digest over every reconstructed
        // subject field. No active row escapes the index when any persisted result, producer,
        // writer or risk metadata has drifted away from the verified receipt.
        return new ActionCache.Entry(key, result, producer,
                new ActionCache.WriterIdentity(rows.getString("writer_service_id"),
                        rows.getString("writer_trust_domain"), rows.getString("writer_node_id"),
                        requiredBoolean(rows, "writer_attested")),
                attestation, ActionCache.RiskTier.valueOf(rows.getString("risk_tier")),
                rows.getTimestamp("stored_at").toInstant().toEpochMilli(),
                expiry == null ? Optional.empty() : Optional.of(expiry.toInstant().toEpochMilli()));
    }

    private static void bindEntry(Connection connection, PreparedStatement statement,
                                  ActionCache.Entry entry) throws SQLException {
        ActionKey key = entry.key();
        ActionResultRecord result = entry.result();
        CasAccessPolicy.ProducerContext producer = entry.producer();
        List<String> componentNames = new ArrayList<>(key.components().keySet());
        List<String> componentValues = componentNames.stream().map(key.components()::get).toList();
        List<String> costNames = new ArrayList<>(result.cost().keySet());
        Double[] costValues = costNames.stream().map(result.cost()::get).toArray(Double[]::new);
        int parameter = 1;
        statement.setString(parameter++, key.tenantId());
        statement.setString(parameter++, key.digest().hex());
        statement.setLong(parameter++, key.digest().sizeBytes());
        statement.setArray(parameter++, textArray(connection, componentNames));
        statement.setArray(parameter++, textArray(connection, componentValues));
        statement.setString(parameter++, producer.projectId());
        statement.setString(parameter++, result.actionId());
        statement.setString(parameter++, result.receiptId());
        statement.setInt(parameter++, result.attempt());
        statement.setInt(parameter++, result.leaseGeneration());
        statement.setString(parameter++, result.status().name());
        statement.setInt(parameter++, result.exitCode());
        statement.setString(parameter++, result.failureClass().map(Enum::name).orElse(null));
        statement.setString(parameter++, result.failureMessage().orElse(null));
        statement.setString(parameter++, result.validationStatus().name());
        parameter = bindDigest(statement, parameter, result.outputManifestDigest());
        parameter = bindDigest(statement, parameter, result.provenanceDigest());
        parameter = bindOptionalDigest(statement, parameter, result.stdoutDigest());
        parameter = bindOptionalDigest(statement, parameter, result.stderrDigest());
        statement.setString(parameter++, result.schemaVersion());
        statement.setString(parameter++, result.startedAt());
        statement.setString(parameter++, result.finishedAt());
        statement.setString(parameter++, producer.toolchainImage());
        statement.setArray(parameter++, textArray(connection, producer.permissionScope().stream().sorted().toList()));
        statement.setString(parameter++, producer.dataResidency());
        statement.setString(parameter++, producer.classification().name());
        statement.setString(parameter++, producer.sensitivity().name());
        parameter = bindOptionalDigest(statement, parameter, producer.provenanceDigest());
        statement.setString(parameter++, entry.riskTier().name());
        statement.setString(parameter++, entry.writer().serviceId());
        statement.setString(parameter++, entry.writer().trustDomain());
        statement.setString(parameter++, entry.writer().nodeId());
        statement.setBoolean(parameter++, entry.writer().attested());
        statement.setString(parameter++, entry.attestation().map(ActionCache.ResultAttestation::signerId).orElse(null));
        statement.setString(parameter++, entry.attestation().map(ActionCache.ResultAttestation::algorithm).orElse(null));
        parameter = bindOptionalDigest(statement, parameter,
                entry.attestation().map(ActionCache.ResultAttestation::signatureDigest));
        if (entry.attestation().isPresent()) {
            statement.setBytes(parameter++, entry.attestation().orElseThrow()
                    .signatureValue().orElse(null));
        } else {
            statement.setBytes(parameter++, null);
        }
        statement.setString(parameter++, entry.attestation()
                .map(ActionCache.ResultAttestation::envelopeVersion).orElse(null));
        parameter = bindOptionalDigest(statement, parameter,
                entry.attestation().map(ActionCache.ResultAttestation::envelopeDigest));
        if (entry.attestation().isPresent()) {
            statement.setLong(parameter++, entry.attestation().orElseThrow().signedAtEpochMillis());
        } else {
            statement.setObject(parameter++, null);
        }
        if (entry.attestation().isPresent()) {
            statement.setBoolean(parameter++, entry.attestation().orElseThrow().verified());
        } else {
            statement.setObject(parameter++, null);
        }
        statement.setDouble(parameter++, result.resourceUsage().wallSeconds());
        statement.setDouble(parameter++, result.resourceUsage().cpuSeconds());
        statement.setDouble(parameter++, result.resourceUsage().maxMemoryMb());
        statement.setLong(parameter++, result.resourceUsage().readBytes());
        statement.setLong(parameter++, result.resourceUsage().writtenBytes());
        statement.setDouble(parameter++, result.resourceUsage().gpuSeconds());
        statement.setArray(parameter++, textArray(connection, costNames));
        statement.setArray(parameter++, connection.createArrayOf("float8", costValues));
        statement.setTimestamp(parameter++, timestamp(entry.storedAtEpochMillis()));
        if (entry.expiresAtEpochMillis().isPresent()) {
            statement.setTimestamp(parameter, timestamp(entry.expiresAtEpochMillis().orElseThrow()));
        } else {
            statement.setTimestamp(parameter, null);
        }
    }

    private static ActionCache.ResultAttestation readAttestation(ResultSet rows,
                                                                  String attestationKey)
            throws SQLException {
        if (!requiredBoolean(rows, "attestation_verified")) {
            throw new IllegalStateException(
                    "ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:attestation_verified");
        }
        long signedAt = rows.getLong("attestation_signed_at_epoch_millis");
        if (rows.wasNull()) {
            throw new IllegalStateException(
                    "ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:attestation_signed_at_epoch_millis");
        }
        return ActionCache.ResultAttestation.verifiedFromPersistence(attestationKey,
                requireColumn(rows, "attestation_algorithm"),
                digest(rows, "attestation_signature_hex", "attestation_signature_bytes"),
                rows.getBytes("attestation_signature_value"),
                requireColumn(rows, "attestation_envelope_version"),
                digest(rows, "attestation_envelope_hex", "attestation_envelope_bytes"),
                signedAt);
    }

    private static boolean hasAnyAttestationMetadata(ResultSet rows) throws SQLException {
        return rows.getString("attestation_algorithm") != null
                || rows.getString("attestation_signature_hex") != null
                || rows.getObject("attestation_signature_bytes") != null
                || rows.getBytes("attestation_signature_value") != null
                || rows.getString("attestation_envelope_version") != null
                || rows.getString("attestation_envelope_hex") != null
                || rows.getObject("attestation_envelope_bytes") != null
                || rows.getObject("attestation_signed_at_epoch_millis") != null
                || nullableBoolean(rows, "attestation_verified").isPresent();
    }

    private static int bindDigest(PreparedStatement statement, int parameter, CasDigest digest)
            throws SQLException {
        statement.setString(parameter++, digest.hex());
        statement.setLong(parameter++, digest.sizeBytes());
        return parameter;
    }

    private static int bindOptionalDigest(PreparedStatement statement, int parameter,
                                          Optional<CasDigest> digest) throws SQLException {
        if (digest.isPresent()) {
            return bindDigest(statement, parameter, digest.orElseThrow());
        }
        statement.setString(parameter++, null);
        statement.setObject(parameter++, null);
        return parameter;
    }

    private static void recordInvalidation(Connection connection, String tenantId, String keyHex,
                                           String reason, long atEpochMillis, String writerNodeId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement("""
                INSERT INTO cas_action_cache_invalidations
                  (organization_id, action_key_hex, invalidated_at, reason, writer_node_id)
                SELECT organization_id, action_key_hex, ?, ?, ?
                FROM cas_action_cache_entries
                WHERE organization_id = ? AND action_key_hex = ? AND invalidated_at IS NULL
                ON CONFLICT DO NOTHING
                """)) {
            statement.setTimestamp(1, timestamp(atEpochMillis));
            statement.setString(2, reason);
            statement.setString(3, writerNodeId);
            statement.setString(4, tenantId);
            statement.setString(5, keyHex);
            statement.executeUpdate();
        }
    }

    private static CasDigest digest(ResultSet rows, String hexColumn, String sizeColumn)
            throws SQLException {
        String hex = requireColumn(rows, hexColumn);
        long size = rows.getLong(sizeColumn);
        if (rows.wasNull()) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:" + sizeColumn);
        }
        return new CasDigest(CasDigest.ALGORITHM, hex, size);
    }

    private static Optional<CasDigest> optionalDigest(ResultSet rows, String hexColumn,
                                                       String sizeColumn) throws SQLException {
        String hex = rows.getString(hexColumn);
        long size = rows.getLong(sizeColumn);
        boolean sizeMissing = rows.wasNull();
        if (hex == null && sizeMissing) {
            return Optional.empty();
        }
        if (hex == null || sizeMissing) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:" + hexColumn);
        }
        return Optional.of(new CasDigest(CasDigest.ALGORITHM, hex, size));
    }

    private static String requireColumn(ResultSet rows, String column) throws SQLException {
        String value = rows.getString(column);
        if (value == null) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:" + column);
        }
        return value;
    }

    private static boolean requiredBoolean(ResultSet rows, String column) throws SQLException {
        boolean value = rows.getBoolean(column);
        if (rows.wasNull()) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:" + column);
        }
        return value;
    }

    private static Optional<Boolean> nullableBoolean(ResultSet rows, String column)
            throws SQLException {
        boolean value = rows.getBoolean(column);
        return rows.wasNull() ? Optional.empty() : Optional.of(value);
    }

    private static List<String> textArray(ResultSet rows, String column) throws SQLException {
        Array array = rows.getArray(column);
        if (array == null) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:" + column);
        }
        Object raw = array.getArray();
        if (!(raw instanceof Object[] values)) {
            throw new IllegalStateException("unexpected SQL array for " + column);
        }
        List<String> result = new ArrayList<>(values.length);
        for (Object value : values) {
            if (value == null) {
                throw new IllegalStateException("null SQL array value for " + column);
            }
            result.add(value.toString());
        }
        return List.copyOf(result);
    }

    private static List<Double> numberArray(ResultSet rows, String column) throws SQLException {
        Array array = rows.getArray(column);
        if (array == null) {
            throw new IllegalStateException("ACTION_CACHE_ENTRY_METADATA_INCOMPLETE:" + column);
        }
        Object raw = array.getArray();
        if (!(raw instanceof Object[] values)) {
            throw new IllegalStateException("unexpected SQL array for " + column);
        }
        List<Double> result = new ArrayList<>(values.length);
        for (Object value : values) {
            if (!(value instanceof Number number)) {
                throw new IllegalStateException("non-numeric SQL array value for " + column);
            }
            result.add(number.doubleValue());
        }
        return List.copyOf(result);
    }

    private static Map<String, String> pairedMap(List<String> names, List<String> values,
                                                  String label) {
        if (names.size() != values.size()) {
            throw new IllegalStateException(label + " names/values length mismatch");
        }
        Map<String, String> result = new LinkedHashMap<>();
        for (int index = 0; index < names.size(); index++) {
            if (result.put(names.get(index), values.get(index)) != null) {
                throw new IllegalStateException(label + " contains duplicate name " + names.get(index));
            }
        }
        return result;
    }

    private static Map<String, Double> pairedDoubleMap(List<String> names, List<Double> values,
                                                        String label) {
        if (names.size() != values.size()) {
            throw new IllegalStateException(label + " names/values length mismatch");
        }
        Map<String, Double> result = new LinkedHashMap<>();
        for (int index = 0; index < names.size(); index++) {
            if (result.put(names.get(index), values.get(index)) != null) {
                throw new IllegalStateException(label + " contains duplicate name " + names.get(index));
            }
        }
        return result;
    }

    private static java.sql.Array textArray(Connection connection, List<String> values)
            throws SQLException {
        return connection.createArrayOf("text", values.toArray(String[]::new));
    }

    private static Timestamp timestamp(long epochMillis) {
        return Timestamp.from(Instant.ofEpochMilli(epochMillis));
    }

    private static String boundedReason(String reason) {
        String value = CasText.required(reason, "reason");
        if (value.length() > 128) {
            throw new IllegalArgumentException("invalidation reason exceeds 128 characters");
        }
        return value;
    }

    @FunctionalInterface
    private interface SqlWork<T> {
        T run(Connection connection) throws SQLException;
    }

    private <T> T inTenantTransaction(String tenantId, SqlWork<T> work) {
        String tenant = CasText.required(tenantId, "tenantId");
        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new IllegalStateException(
                        "JdbcActionCacheIndex requires an owned auto-commit connection; ambient transaction refused");
            }
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement scope = connection.prepareStatement(
                        "SELECT set_config('app.organization_id', ?, true)")) {
                    scope.setString(1, tenant);
                    scope.execute();
                }
                T result = work.run(connection);
                connection.commit();
                return result;
            } catch (RuntimeException | SQLException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                connection.setAutoCommit(true);
            }
        } catch (SQLException error) {
            throw new IllegalStateException("action-cache index SQL failure", error);
        }
    }
}
