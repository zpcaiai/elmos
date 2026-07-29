package io.elmos.persistence;

import io.elmos.workflow.RunnerRegistrationPort;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Supplier;

/**
 * PostgreSQL runner enrollment adapter.
 *
 * <p>The plaintext enrollment credential is hashed before the database call and
 * is never persisted. A non-RLS authentication projection contains only runner,
 * pool, tenant and credential identifiers; customer payload stays behind tenant
 * RLS in {@code runner_nodes}.</p>
 */
public final class JdbcRunnerRegistrationStore implements RunnerRegistrationPort {
    private static final SecureRandom RANDOM = new SecureRandom();
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcRunnerRegistrationStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public NodeCredential register(
            String runnerNodeId,
            String poolId,
            String agentVersion,
            List<String> capabilities,
            int maxConcurrency,
            String enrollmentToken,
            String nodeTokenSha256,
            boolean rootlessDeclared,
            boolean readOnlyRootDeclared,
            boolean capabilitiesDroppedDeclared,
            boolean networkDefaultDenyDeclared,
            String imageAllowlistVersion
    ) {
        requireRunnerId(runnerNodeId);
        requireRunnerId(poolId);
        if (capabilities == null || capabilities.isEmpty() || capabilities.size() > 32) {
            throw rejected("ELMOS_RUNNER_CAPABILITIES_INVALID");
        }
        String hash = sha256(enrollmentToken);
        requireSha256(nodeTokenSha256, "ELMOS_RUNNER_NODE_TOKEN_INVALID");
        Instant expiresAt = Instant.now().plusSeconds(86400);
        return transactions.execute(status -> mapErrors(() -> {
            String organizationId = jdbc.sql("""
                    SELECT organization_id
                      FROM runner_enrollment_credentials
                     WHERE runner_pool_id = :pool
                       AND token_sha256 = :hash
                       AND credential_state = 'ACTIVE'
                       AND not_before <= now()
                       AND expires_at > now()
                       AND (claimed_by_runner_node_id IS NULL
                            OR claimed_by_runner_node_id = :node)
                     FOR UPDATE
                    """)
                    .param("pool", poolId)
                    .param("hash", hash)
                    .param("node", runnerNodeId)
                    .query(String.class)
                    .optional()
                    .orElseThrow(() -> rejected("ELMOS_RUNNER_ENROLLMENT_REJECTED"));
            bindTenant(organizationId);
            Integer poolExists = jdbc.sql("""
                    SELECT count(*) FROM runner_pools
                     WHERE runner_pool_id = :pool
                       AND organization_id = :organization
                       AND status = 'ACTIVE'
                    """)
                    .param("pool", poolId)
                    .param("organization", organizationId)
                    .query(Integer.class)
                    .single();
            if (poolExists == null || poolExists != 1) {
                throw rejected("ELMOS_RUNNER_POOL_NOT_ACTIVE");
            }
            jdbc.sql("""
                    UPDATE runner_enrollment_credentials
                       SET claimed_by_runner_node_id = coalesce(
                               claimed_by_runner_node_id, :node),
                           claimed_at = coalesce(claimed_at, now())
                     WHERE runner_pool_id = :pool AND token_sha256 = :hash
                    """)
                    .param("node", runnerNodeId)
                    .param("pool", poolId)
                    .param("hash", hash)
                    .update();
            jdbc.sql("""
                    INSERT INTO runner_nodes (
                        runner_node_id, organization_id, schema_version, status,
                        idempotency_key, payload, runner_pool_ref, agent_version,
                        fleet_status, capabilities, max_concurrency,
                        image_allowlist_version, last_heartbeat_at
                    ) VALUES (
                        :node, :organization, '2.0', 'ACTIVE', :node,
                        jsonb_build_object(
                            'selfAttestation', jsonb_build_object(
                                'rootless', :rootless,
                                'readOnlyRoot', :readOnlyRoot,
                                'capabilitiesDropped', :capabilitiesDropped,
                                'networkDefaultDeny', :networkDefaultDeny
                            )
                        ),
                        :pool, :version, 'REGISTERED', cast(:capabilities AS text[]),
                        :maxConcurrency, :allowlist, now()
                    )
                    ON CONFLICT (runner_node_id) DO UPDATE SET
                        agent_version = EXCLUDED.agent_version,
                        capabilities = EXCLUDED.capabilities,
                        max_concurrency = EXCLUDED.max_concurrency,
                        image_allowlist_version = EXCLUDED.image_allowlist_version,
                        last_heartbeat_at = now(),
                        payload = EXCLUDED.payload,
                        fleet_status = CASE
                            WHEN runner_nodes.fleet_status IN ('QUARANTINED', 'RETIRED')
                                THEN runner_nodes.fleet_status
                            ELSE 'REGISTERED'
                        END
                    """)
                    .param("node", runnerNodeId)
                    .param("organization", organizationId)
                    .param("pool", poolId)
                    .param("version", safeVersion(agentVersion))
                    .param("capabilities", pgArray(capabilities))
                    .param("maxConcurrency", Math.min(Math.max(maxConcurrency, 1), 16))
                    .param("allowlist", requireText(imageAllowlistVersion, "ELMOS_RUNNER_ALLOWLIST_REQUIRED"))
                    .param("rootless", rootlessDeclared)
                    .param("readOnlyRoot", readOnlyRootDeclared)
                    .param("capabilitiesDropped", capabilitiesDroppedDeclared)
                    .param("networkDefaultDeny", networkDefaultDenyDeclared)
                    .update();
            jdbc.sql("""
                    INSERT INTO runner_node_authentication (
                        runner_node_id, organization_id, runner_pool_id,
                        enrollment_credential_id, bound_at,
                        node_token_sha256, node_token_issued_at,
                        node_token_expires_at, credential_generation
                    )
                    SELECT :node, :organization, :pool, enrollment_credential_id, now(),
                           :nodeTokenHash, now(), :nodeTokenExpiresAt, 0
                      FROM runner_enrollment_credentials
                     WHERE runner_pool_id = :pool AND token_sha256 = :hash
                    ON CONFLICT (runner_node_id) DO UPDATE SET
                        organization_id = EXCLUDED.organization_id,
                        runner_pool_id = EXCLUDED.runner_pool_id,
                        enrollment_credential_id = EXCLUDED.enrollment_credential_id,
                        bound_at = now(),
                        node_token_sha256 = EXCLUDED.node_token_sha256,
                        node_token_issued_at = now(),
                        node_token_expires_at = EXCLUDED.node_token_expires_at,
                        previous_node_token_sha256 = NULL,
                        previous_token_valid_until = NULL,
                        last_rotation_request_id = NULL,
                        revoked_at = NULL
                    """)
                    .param("node", runnerNodeId)
                    .param("organization", organizationId)
                    .param("pool", poolId)
                    .param("hash", hash)
                    .param("nodeTokenHash", nodeTokenSha256)
                    .param("nodeTokenExpiresAt", expiresAt.atOffset(ZoneOffset.UTC))
                    .update();
            return new NodeCredential(runnerNodeId, expiresAt);
        }));
    }

    @Override
    public NodeCredential resume(String runnerNodeId, String nodeToken) {
        requireRunnerId(runnerNodeId);
        String hash = sha256(nodeToken);
        return mapErrors(() -> jdbc.sql("""
                SELECT runner_node_id, node_token_expires_at
                  FROM runner_node_authentication
                 WHERE runner_node_id = :node
                   AND revoked_at IS NULL
                   AND node_token_sha256 = :hash
                   AND node_token_expires_at > now()
                """)
                .param("node", runnerNodeId)
                .param("hash", hash)
                .query((rs, row) -> new NodeCredential(
                        rs.getString("runner_node_id"),
                        rs.getTimestamp("node_token_expires_at").toInstant()))
                .optional()
                .orElseThrow(() -> rejected(
                        "ELMOS_RUNNER_NODE_TOKEN_REJECTED")));
    }

    @Override
    public EnrollmentCredential issueEnrollment(
            String organizationId,
            String poolId,
            String actorId,
            int ttlSeconds) {
        requireRunnerId(poolId);
        String operator = requireText(actorId, "ELMOS_RUNNER_ACTOR_REQUIRED");
        int ttl = Math.min(Math.max(ttlSeconds, 60), 3600);
        String credentialId = "runner-enroll-" + java.util.UUID.randomUUID();
        String token = opaqueToken();
        String tokenHash = sha256(token);
        Instant expiresAt = Instant.now().plusSeconds(ttl);

        transactions.executeWithoutResult(status -> mapErrors(() -> {
            bindTenant(organizationId);
            jdbc.sql("""
                    INSERT INTO runner_pools (
                        runner_pool_id, organization_id, schema_version, status,
                        idempotency_key, payload
                    ) VALUES (
                        :pool, :organization, '2.0', 'ACTIVE',
                        'runner-pool:' || :pool,
                        jsonb_build_object('provisionedBy', :actor)
                    )
                    ON CONFLICT (organization_id, idempotency_key) DO UPDATE
                       SET status = 'ACTIVE', updated_at = now()
                    """)
                    .param("pool", poolId)
                    .param("organization", organizationId)
                    .param("actor", operator)
                    .update();
            jdbc.sql("""
                    INSERT INTO runner_enrollment_credentials (
                        enrollment_credential_id, organization_id, runner_pool_id,
                        token_sha256, credential_state, not_before, expires_at,
                        issued_by_actor_id
                    ) VALUES (
                        :credential, :organization, :pool, :hash, 'ACTIVE',
                        now(), :expiresAt, :actor
                    )
                    """)
                    .param("credential", credentialId)
                    .param("organization", organizationId)
                    .param("pool", poolId)
                    .param("hash", tokenHash)
                    .param("expiresAt", expiresAt.atOffset(ZoneOffset.UTC))
                    .param("actor", operator)
                    .update();
            return null;
        }));
        return new EnrollmentCredential(credentialId, poolId, token, expiresAt);
    }

    @Override
    public void revokeEnrollment(
            String organizationId,
            String credentialId,
            String actorId) {
        transactions.executeWithoutResult(status -> mapErrors(() -> {
            bindTenant(organizationId);
            int updated = jdbc.sql("""
                    UPDATE runner_enrollment_credentials
                       SET credential_state = 'REVOKED', revoked_at = now(),
                           revoked_by_actor_id = :actor
                     WHERE enrollment_credential_id = :credential
                       AND organization_id = :organization
                       AND credential_state = 'ACTIVE'
                    """)
                    .param("actor", requireText(actorId, "ELMOS_RUNNER_ACTOR_REQUIRED"))
                    .param("credential", requireText(
                            credentialId, "ELMOS_RUNNER_ENROLLMENT_ID_REQUIRED"))
                    .param("organization", organizationId)
                    .update();
            if (updated != 1) {
                throw rejected("ELMOS_RUNNER_ENROLLMENT_UNKNOWN");
            }
            jdbc.sql("""
                    UPDATE runner_node_authentication
                       SET revoked_at = coalesce(revoked_at, now())
                     WHERE enrollment_credential_id = :credential
                    """)
                    .param("credential", credentialId)
                    .update();
            return null;
        }));
    }

    @Override
    public Instant rotateNodeCredential(
            String runnerNodeId,
            String presentedNodeToken,
            String nextTokenSha256,
            String rotationRequestId) {
        requireRunnerId(runnerNodeId);
        String currentHash = sha256(presentedNodeToken);
        requireSha256(nextTokenSha256, "ELMOS_RUNNER_NODE_TOKEN_INVALID");
        if (rotationRequestId == null
                || !rotationRequestId.matches("^[A-Za-z0-9][A-Za-z0-9._:-]{7,95}$")) {
            throw rejected("ELMOS_RUNNER_ROTATION_REQUEST_INVALID");
        }
        Instant expiresAt = Instant.now().plusSeconds(86400);
        return transactions.execute(status -> mapErrors(() -> {
            int updated = jdbc.sql("""
                    UPDATE runner_node_authentication
                       SET previous_node_token_sha256 = node_token_sha256,
                           previous_token_valid_until = now() + interval '5 minutes',
                           node_token_sha256 = :nextHash,
                           node_token_issued_at = now(),
                           node_token_expires_at = :expiresAt,
                           credential_generation = credential_generation + 1,
                           last_rotation_request_id = :requestId
                     WHERE runner_node_id = :node
                       AND revoked_at IS NULL
                       AND node_token_sha256 = :currentHash
                       AND node_token_expires_at > now()
                    """)
                    .param("nextHash", nextTokenSha256)
                    .param("expiresAt", expiresAt.atOffset(ZoneOffset.UTC))
                    .param("requestId", rotationRequestId)
                    .param("node", runnerNodeId)
                    .param("currentHash", currentHash)
                    .update();
            if (updated == 1) {
                return expiresAt;
            }
            return jdbc.sql("""
                    SELECT node_token_expires_at
                      FROM runner_node_authentication
                     WHERE runner_node_id = :node
                       AND revoked_at IS NULL
                       AND previous_node_token_sha256 = :currentHash
                       AND previous_token_valid_until > now()
                       AND node_token_sha256 = :nextHash
                       AND last_rotation_request_id = :requestId
                    """)
                    .param("node", runnerNodeId)
                    .param("currentHash", currentHash)
                    .param("nextHash", nextTokenSha256)
                    .param("requestId", rotationRequestId)
                    .query(OffsetDateTime.class)
                    .optional()
                    .map(OffsetDateTime::toInstant)
                    .orElseThrow(() -> rejected("ELMOS_RUNNER_NODE_TOKEN_REJECTED"));
        }));
    }

    @Override
    public boolean heartbeat(String runnerNodeId, String nodeToken) {
        String organizationId = authorize(runnerNodeId, nodeToken);
        return inTenant(organizationId, () -> {
            int updated = jdbc.sql("""
                    UPDATE runner_nodes SET last_heartbeat_at = now()
                     WHERE runner_node_id = :node
                       AND fleet_status NOT IN ('QUARANTINED', 'LOST', 'RETIRED')
                    """)
                    .param("node", runnerNodeId)
                    .update();
            if (updated != 1) {
                throw rejected("ELMOS_RUNNER_NOT_ACTIVE");
            }
            return jdbc.sql("""
                    SELECT drain_requested_at IS NOT NULL
                      FROM runner_nodes WHERE runner_node_id = :node
                    """)
                    .param("node", runnerNodeId)
                    .query(Boolean.class)
                    .single();
        });
    }

    @Override
    public void authorizeNode(String runnerNodeId, String nodeToken) {
        authorize(runnerNodeId, nodeToken);
    }

    @Override
    public void verifyAttestation(String runnerNodeId, String verifierActorId) {
        String organizationId = organizationForNode(runnerNodeId);
        inTenant(organizationId, () -> {
            int updated = jdbc.sql("""
                    UPDATE runner_nodes SET
                        rootless_attested = true,
                        readonly_root_attested = true,
                        capability_drop_attested = true,
                        network_default_deny_attested = true,
                        attestation_verified_at = now(),
                        attestation_verifier_actor_id = :actor,
                        fleet_status = 'READY'
                     WHERE runner_node_id = :node
                       AND fleet_status = 'REGISTERED'
                       AND payload #>> '{selfAttestation,rootless}' = 'true'
                       AND payload #>> '{selfAttestation,readOnlyRoot}' = 'true'
                       AND payload #>> '{selfAttestation,capabilitiesDropped}' = 'true'
                       AND payload #>> '{selfAttestation,networkDefaultDeny}' = 'true'
                    """)
                    .param("node", runnerNodeId)
                    .param("actor", requireText(verifierActorId, "ELMOS_RUNNER_VERIFIER_REQUIRED"))
                    .update();
            if (updated != 1) {
                throw rejected("ELMOS_RUNNER_ATTESTATION_INCOMPLETE");
            }
            return null;
        });
    }

    @Override
    public void requestDrain(String runnerNodeId, String actorId) {
        String organizationId = organizationForNode(runnerNodeId);
        inTenant(organizationId, () -> {
            int updated = jdbc.sql("""
                    UPDATE runner_nodes
                       SET drain_requested_at = coalesce(drain_requested_at, now()),
                           fleet_status = CASE WHEN fleet_status = 'READY' THEN 'DRAINING' ELSE fleet_status END,
                           payload = payload || jsonb_build_object('drainRequestedBy', :actor)
                     WHERE runner_node_id = :node
                       AND fleet_status IN ('READY', 'DRAINING')
                    """)
                    .param("node", runnerNodeId)
                    .param("actor", requireText(actorId, "ELMOS_RUNNER_ACTOR_REQUIRED"))
                    .update();
            if (updated != 1) {
                throw rejected("ELMOS_RUNNER_NOT_READY");
            }
            return null;
        });
    }

    private String authorize(String runnerNodeId, String nodeToken) {
        requireRunnerId(runnerNodeId);
        String hash = sha256(nodeToken);
        return mapErrors(() -> jdbc.sql("""
                SELECT a.organization_id
                  FROM runner_node_authentication a
                 WHERE a.runner_node_id = :node
                   AND a.revoked_at IS NULL
                   AND a.node_token_sha256 = :hash
                   AND a.node_token_expires_at > now()
                """)
                .param("node", runnerNodeId)
                .param("hash", hash)
                .query(String.class)
                .optional()
                .orElseThrow(() -> rejected("ELMOS_RUNNER_NODE_TOKEN_REJECTED")));
    }

    private String organizationForNode(String runnerNodeId) {
        return jdbc.sql("""
                SELECT organization_id FROM runner_node_authentication
                 WHERE runner_node_id = :node AND revoked_at IS NULL
                """)
                .param("node", runnerNodeId)
                .query(String.class)
                .optional()
                .orElseThrow(() -> rejected("ELMOS_RUNNER_UNKNOWN"));
    }

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        return transactions.execute(status -> {
            bindTenant(organizationId);
            return mapErrors(work);
        });
    }

    private void bindTenant(String organizationId) {
        jdbc.sql("SELECT set_config('app.organization_id', :organization, true)")
                .param("organization", organizationId)
                .query(String.class)
                .single();
    }

    private static <T> T mapErrors(Supplier<T> work) {
        try {
            return work.get();
        } catch (RunnerAuthenticationException ex) {
            throw ex;
        } catch (RuntimeException ex) {
            String message = ex.getMessage();
            int marker = message == null ? -1 : message.indexOf("ELMOS_");
            if (marker >= 0) {
                String tail = message.substring(marker);
                int end = tail.indexOf(' ');
                throw rejected(end > 0 ? tail.substring(0, end) : tail);
            }
            throw ex;
        }
    }

    private static RunnerAuthenticationException rejected(String code) {
        return new RunnerAuthenticationException(code);
    }

    private static String sha256(String value) {
        if (value == null || value.length() < 32 || value.length() > 4096) {
            throw rejected("ELMOS_RUNNER_ENROLLMENT_REJECTED");
        }
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)))
                    .toLowerCase(Locale.ROOT);
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static String opaqueToken() {
        byte[] bytes = new byte[48];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static void requireSha256(String value, String code) {
        if (value == null || !value.matches("^[0-9a-f]{64}$")) {
            throw rejected(code);
        }
    }

    private static void requireRunnerId(String value) {
        if (value == null || !value.matches("^[a-z0-9][a-z0-9._-]{2,95}$")) {
            throw rejected("ELMOS_RUNNER_ID_INVALID");
        }
    }

    private static String safeVersion(String value) {
        String version = requireText(value, "ELMOS_RUNNER_VERSION_REQUIRED");
        if (!version.matches("^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")) {
            throw rejected("ELMOS_RUNNER_VERSION_INVALID");
        }
        return version;
    }

    private static String requireText(String value, String code) {
        if (value == null || value.isBlank()) {
            throw rejected(code);
        }
        return value;
    }

    private static String pgArray(List<String> values) {
        StringBuilder out = new StringBuilder("{");
        for (int i = 0; i < values.size(); i++) {
            String value = values.get(i);
            if (!value.matches("^[a-z0-9][a-z0-9:._-]{1,95}$")) {
                throw rejected("ELMOS_RUNNER_CAPABILITIES_INVALID");
            }
            if (i > 0) out.append(',');
            out.append('"').append(value).append('"');
        }
        return out.append('}').toString();
    }
}
