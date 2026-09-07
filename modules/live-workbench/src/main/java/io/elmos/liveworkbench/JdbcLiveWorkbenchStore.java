package io.elmos.liveworkbench;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

/** PostgreSQL store with tenant-bound transactions, CAS versions, atomic quota admission and durable ledgers. */
public final class JdbcLiveWorkbenchStore implements LiveWorkbenchStore {
    private static final TypeReference<Map<String, String>> STRING_MAP = new TypeReference<>() {};
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {};
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;
    private final RowMapper<SessionView> sessionMapper = this::session;

    public JdbcLiveWorkbenchStore(JdbcTemplate jdbc, TransactionTemplate transactions, ObjectMapper json) {
        this.jdbc = jdbc; this.transactions = transactions; this.json = json;
    }

    @Override public Reservation reserve(PrincipalScope scope, CreateSessionRequest request, String sessionId,
                                         String idempotencyKey, String requestDigest, long now) {
        return tenant(scope.tenantId(), () -> {
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))::text", String.class,
                    scope.tenantId() + "|" + scope.accountId());
            List<SessionView> prior = jdbc.query("SELECT * FROM lw_sessions WHERE tenant_id=? AND account_id=? AND idempotency_key=?",
                    sessionMapper, scope.tenantId(), scope.accountId(), idempotencyKey);
            if (!prior.isEmpty()) {
                String stored = jdbc.queryForObject("SELECT request_digest FROM lw_sessions WHERE tenant_id=? AND session_id=?",
                        String.class, scope.tenantId(), prior.getFirst().sessionId());
                if (!requestDigest.equals(stored)) throw LiveWorkbenchException.conflict("IDEMPOTENCY_PAYLOAD_CONFLICT");
                return new Reservation(prior.getFirst(), false);
            }
            Integer used = jdbc.queryForObject("SELECT COALESCE(SUM(slot_weight),0) FROM lw_sessions WHERE tenant_id=? AND account_id=? AND state IN ('PREPARING','READY','CLEANUP_PENDING')",
                    Integer.class, scope.tenantId(), scope.accountId());
            if ((used == null ? 0 : used) + request.slotWeight() > MAX_ACCOUNT_SLOTS) throw LiveWorkbenchException.exhausted();
            jdbc.update("""
                    INSERT INTO lw_sessions(tenant_id,account_id,actor_id,environment_id,session_id,delivery_id,repository_id,snapshot_id,
                      runtime_profile_id,scenario,mode,generation,slot_weight,state,runtime_status,created_at_epoch,provider_hard_deadline_epoch,
                      resource_members,evidence_refs,request_digest,idempotency_key,version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'PREPARING','PENDING',?,0,'{}'::jsonb,'[]'::jsonb,?,?,0)
                    """, scope.tenantId(), scope.accountId(), scope.actorId(), scope.environmentId(), sessionId,
                    request.deliveryId(), request.repositoryId(), request.snapshotId(), request.runtimeProfileId(), request.scenario(),
                    request.mode(), 1, request.slotWeight(), now, requestDigest, idempotencyKey);
            audit(scope.tenantId(), scope.actorId(), sessionId, "SESSION_RESERVED", "PREPARING", requestDigest, now);
            return new Reservation(required(scope.tenantId(), sessionId), true);
        });
    }

    @Override public SessionView bindProvider(String tenantId, String sessionId, long expectedVersion, ProviderAllocation allocation) {
        return tenant(tenantId, () -> {
            int changed = jdbc.update("""
                    UPDATE lw_sessions SET provider_session_id=?,resource_lease_id=?,provider_hard_deadline_epoch=?,
                      resource_members=CAST(? AS jsonb),evidence_refs=CAST(? AS jsonb),version=version+1
                    WHERE tenant_id=? AND session_id=? AND state='PREPARING' AND version=?
                    """, allocation.providerSessionId(), allocation.resourceLeaseId(), allocation.hardDeadlineEpochSecond(),
                    encode(allocation.members()), encode(allocation.evidenceRefs()), tenantId, sessionId, expectedVersion);
            if (changed != 1) throw LiveWorkbenchException.conflict("SESSION_VERSION_CONFLICT");
            for (Map.Entry<String, String> member : allocation.members().entrySet()) {
                jdbc.update("""
                        INSERT INTO lw_resource_members(tenant_id,session_id,member_kind,provider_id,deadline_epoch,updated_at_epoch)
                        VALUES (?,?,?,?,?,EXTRACT(EPOCH FROM clock_timestamp())::bigint)
                        """, tenantId, sessionId, member.getKey(), member.getValue(), allocation.hardDeadlineEpochSecond());
            }
            return required(tenantId, sessionId);
        });
    }

    @Override public SessionView failPreparation(String tenantId, String sessionId, long expectedVersion, String failureCode, long now) {
        return tenant(tenantId, () -> {
            int changed = jdbc.update("UPDATE lw_sessions SET state='FAILED',runtime_status='STOPPED',failure_code=?,version=version+1 WHERE tenant_id=? AND session_id=? AND version=? AND state='PREPARING'",
                    failureCode, tenantId, sessionId, expectedVersion);
            if (changed != 1) throw LiveWorkbenchException.conflict("SESSION_VERSION_CONFLICT");
            audit(tenantId, "system", sessionId, "PREPARATION_FAILED", failureCode, LwDigest.sha256(failureCode), now);
            return required(tenantId, sessionId);
        });
    }

    @Override public Optional<SessionView> find(String tenantId, String sessionId) {
        return tenant(tenantId, () -> jdbc.query("SELECT * FROM lw_sessions WHERE tenant_id=? AND session_id=?", sessionMapper, tenantId, sessionId).stream().findFirst());
    }

    @Override public SessionView commitReady(String tenantId, String sessionId, long expectedVersion, ReadinessRequest readiness) {
        return tenant(tenantId, () -> {
            SessionView current = required(tenantId, sessionId);
            if (current.providerSessionId() == null || current.providerHardDeadlineEpochSecond() < readiness.verifiedAtEpochSecond() + PREVIEW_SECONDS + CLEANUP_SECONDS)
                throw LiveWorkbenchException.conflict("PROVIDER_LIFETIME_INSUFFICIENT");
            List<String> evidence = new ArrayList<>(current.evidenceRefs()); evidence.addAll(readiness.evidenceRefs());
            int changed = jdbc.update("""
                    UPDATE lw_sessions SET state='READY',runtime_status='RUNNING',first_ready_at_epoch=?,expires_at_epoch=?,
                      readiness_verifier_id=?,readiness_signature_ref=?,evidence_refs=CAST(? AS jsonb),version=version+1
                    WHERE tenant_id=? AND session_id=? AND state='PREPARING' AND first_ready_at_epoch IS NULL AND version=?
                    """, readiness.verifiedAtEpochSecond(), readiness.verifiedAtEpochSecond() + PREVIEW_SECONDS,
                    readiness.verifierId(), readiness.signatureRef(), encode(evidence), tenantId, sessionId, expectedVersion);
            if (changed != 1) throw LiveWorkbenchException.conflict("READINESS_ALREADY_COMMITTED_OR_STALE");
            audit(tenantId, readiness.verifierId(), sessionId, "READINESS_COMMITTED", "READY", readiness.artifactDigest(), readiness.verifiedAtEpochSecond());
            return required(tenantId, sessionId);
        });
    }

    @Override public SessionView requestCleanup(String tenantId, String sessionId, long expectedVersion, String reason, long now) {
        return tenant(tenantId, () -> {
            int changed = jdbc.update("""
                    UPDATE lw_sessions SET state='CLEANUP_PENDING',runtime_status='STOPPED',cleanup_reason=?,cleanup_requested_at_epoch=?,version=version+1
                    WHERE tenant_id=? AND session_id=? AND state IN ('PREPARING','READY','FAILED','QUARANTINED') AND version=?
                    """, reason, now, tenantId, sessionId, expectedVersion);
            if (changed != 1) {
                SessionView current = required(tenantId, sessionId);
                if (current.state() == SessionState.CLEANUP_PENDING || current.state() == SessionState.CLEANED) return current;
                throw LiveWorkbenchException.conflict("SESSION_VERSION_CONFLICT");
            }
            audit(tenantId, "system", sessionId, "CLEANUP_REQUESTED", reason, LwDigest.sha256(reason), now);
            return required(tenantId, sessionId);
        });
    }

    @Override public List<SessionView> claimExpired(long now, int limit) {
        return system(() -> {
            List<SessionView> expired = jdbc.query("""
                    SELECT * FROM lw_sessions
                    WHERE (state='READY' AND expires_at_epoch<=?)
                       OR (state IN ('CLEANUP_PENDING','QUARANTINED') AND cleanup_requested_at_epoch<=? AND COALESCE(cleanup_claim_until_epoch,0)<=?)
                    ORDER BY COALESCE(expires_at_epoch, cleanup_requested_at_epoch) FOR UPDATE SKIP LOCKED LIMIT ?
                    """, sessionMapper, now, now - 5, now, limit);
            for (SessionView item : expired) jdbc.update("""
                    UPDATE lw_sessions SET state='CLEANUP_PENDING',runtime_status='STOPPED',
                      cleanup_reason=COALESCE(cleanup_reason,'deadline'),cleanup_requested_at_epoch=COALESCE(cleanup_requested_at_epoch,?),
                      cleanup_claim_until_epoch=?,version=version+1
                    WHERE tenant_id=? AND session_id=? AND version=?
                    """, now, now + CLEANUP_SECONDS, item.tenantId(), item.sessionId(), item.version());
            return expired.stream().map(item -> required(item.tenantId(), item.sessionId())).toList();
        });
    }

    @Override public SessionView completeCleanup(String tenantId, String sessionId, long expectedVersion, CleanupOutcome outcome) {
        return tenant(tenantId, () -> {
            SessionView current = required(tenantId, sessionId);
            if (current.resourceMembers().isEmpty()) {
                if (!outcome.memberChecks().equals(Map.of("providerAllocationNeverCommitted", true)))
                    throw LiveWorkbenchException.conflict("CLEANUP_RESOURCE_COVERAGE_INVALID");
            } else if (!outcome.memberChecks().keySet().equals(current.resourceMembers().keySet())) {
                throw LiveWorkbenchException.conflict("CLEANUP_RESOURCE_COVERAGE_INVALID");
            }
            List<String> evidence = new ArrayList<>(current.evidenceRefs()); evidence.addAll(outcome.evidenceRefs());
            int changed = jdbc.update("""
                    UPDATE lw_sessions SET state=?,runtime_status='STOPPED',cleanup_observed_at_epoch=?,cleanup_verifier_id=?,cleanup_claim_until_epoch=NULL,
                      cleanup_checks=CAST(? AS jsonb),evidence_refs=CAST(? AS jsonb),version=version+1
                    WHERE tenant_id=? AND session_id=? AND state='CLEANUP_PENDING' AND version=?
                    """, outcome.status().name(), outcome.observedAtEpochSecond(), outcome.verifierId(), encode(outcome.memberChecks()),
                    encode(evidence), tenantId, sessionId, expectedVersion);
            if (changed != 1) throw LiveWorkbenchException.conflict("CLEANUP_VERSION_CONFLICT");
            jdbc.update("""
                    UPDATE lw_resource_members SET cleanup_state=CASE
                      WHEN COALESCE((CAST(? AS jsonb) ->> member_kind)::boolean,false) THEN 'CLEANED' ELSE 'QUARANTINED' END,
                      cleanup_evidence_refs=CAST(? AS jsonb),updated_at_epoch=?
                    WHERE tenant_id=? AND session_id=?
                    """, encode(outcome.memberChecks()), encode(outcome.evidenceRefs()), outcome.observedAtEpochSecond(), tenantId, sessionId);
            jdbc.update("""
                    INSERT INTO lw_cleanup_receipts(tenant_id,session_id,receipt_version,status,verifier_id,member_checks,evidence_refs,observed_at_epoch)
                    VALUES (?,?,?,?,?,CAST(? AS jsonb),CAST(? AS jsonb),?)
                    """, tenantId, sessionId, expectedVersion + 1, outcome.status().name(), outcome.verifierId(),
                    encode(outcome.memberChecks()), encode(outcome.evidenceRefs()), outcome.observedAtEpochSecond());
            audit(tenantId, outcome.verifierId(), sessionId, "CLEANUP_OBSERVED", outcome.status().name(),
                    LwDigest.sha256(encode(outcome.memberChecks())), outcome.observedAtEpochSecond());
            return required(tenantId, sessionId);
        });
    }

    @Override public CommandReservation reserveCommand(String tenantId, String sessionId, int generation, DebugRequest request,
                                                        String commandId, String idempotencyKey, String requestDigest, long now) {
        return tenant(tenantId, () -> {
            SessionView session = required(tenantId, sessionId);
            if (session.state() != SessionState.READY || session.expiresAtEpochSecond() == null || now >= session.expiresAtEpochSecond())
                throw LiveWorkbenchException.conflict("DEBUG_SESSION_EXPIRED_OR_NOT_READY");
            if (session.generation() != generation) throw LiveWorkbenchException.conflict("DEBUG_GENERATION_FENCED");
            List<DebugReceipt> prior = jdbc.query("SELECT command_id,idempotency_key,state,code,evidence_ref,version FROM lw_debug_commands WHERE tenant_id=? AND session_id=? AND idempotency_key=?",
                    (rs, row) -> command(rs), tenantId, sessionId, idempotencyKey);
            if (!prior.isEmpty()) {
                String stored = jdbc.queryForObject("SELECT request_digest FROM lw_debug_commands WHERE tenant_id=? AND session_id=? AND idempotency_key=?", String.class, tenantId, sessionId, idempotencyKey);
                if (!requestDigest.equals(stored)) throw LiveWorkbenchException.conflict("IDEMPOTENCY_PAYLOAD_CONFLICT");
                return new CommandReservation(prior.getFirst(), false);
            }
            jdbc.update("""
                    INSERT INTO lw_debug_commands(tenant_id,session_id,generation,command_id,idempotency_key,request_digest,command_name,
                      arguments_digest,stop_epoch,control_lease_id,state,code,created_at_epoch,version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING','PROVIDER_DISPATCH_PENDING',?,0)
                    """, tenantId, sessionId, generation, commandId, idempotencyKey, requestDigest, request.command(),
                    request.argumentsDigest(), request.stopEpoch(), request.controlLeaseId(), now);
            audit(tenantId, session.actorId(), sessionId, "DEBUG_COMMAND_RESERVED", request.command(), requestDigest, now);
            return new CommandReservation(new DebugReceipt(commandId, idempotencyKey, CommandState.PENDING,
                    "PROVIDER_DISPATCH_PENDING", null, 0), true);
        });
    }

    @Override public DebugReceipt completeCommand(String tenantId, String sessionId, String idempotencyKey,
                                                   CommandStateUpdate update, long now) {
        return tenant(tenantId, () -> {
            int changed = jdbc.update("""
                    UPDATE lw_debug_commands SET state=?,code=?,evidence_ref=?,response_digest=?,completed_at_epoch=?,version=version+1
                    WHERE tenant_id=? AND session_id=? AND idempotency_key=? AND state IN ('PENDING','UNKNOWN')
                    """, update.state().name(), update.code(), update.evidenceRef(), update.responseDigest(), now,
                    tenantId, sessionId, idempotencyKey);
            if (changed != 1) return jdbc.query("SELECT command_id,idempotency_key,state,code,evidence_ref,version FROM lw_debug_commands WHERE tenant_id=? AND session_id=? AND idempotency_key=?",
                    (rs, row) -> command(rs), tenantId, sessionId, idempotencyKey).stream().findFirst()
                    .orElseThrow(() -> LiveWorkbenchException.notFound());
            SessionView session = required(tenantId, sessionId);
            audit(tenantId, session.actorId(), sessionId, "DEBUG_COMMAND_RESOLVED", update.state().name(),
                    update.responseDigest() == null ? LwDigest.sha256(update.code()) : update.responseDigest(), now);
            return jdbc.queryForObject("SELECT command_id,idempotency_key,state,code,evidence_ref,version FROM lw_debug_commands WHERE tenant_id=? AND session_id=? AND idempotency_key=?",
                    (rs, row) -> command(rs), tenantId, sessionId, idempotencyKey);
        });
    }

    @Override public EventView appendEvent(String tenantId, String sessionId, RuntimeEventRequest request) {
        return tenant(tenantId, () -> {
            SessionView session = required(tenantId, sessionId);
            if (session.generation() != request.generation()) throw LiveWorkbenchException.conflict("EVENT_GENERATION_FENCED");
            try {
                jdbc.update("""
                        INSERT INTO lw_runtime_events(tenant_id,session_id,generation,event_id,stop_epoch,sequence,kind,payload_digest,
                          source_anchor_ids,redaction_status,server_time_epoch)
                        VALUES (?,?,?,?,?,?,?,?,CAST(? AS jsonb),?,?)
                        """, tenantId, sessionId, request.generation(), request.eventId(), request.stopEpoch(), request.sequence(),
                        request.kind(), request.payloadDigest(), encode(request.sourceAnchorIds()), request.redactionStatus(), request.serverTimeEpochSecond());
            } catch (DataIntegrityViolationException conflict) {
                throw LiveWorkbenchException.conflict("EVENT_SEQUENCE_OR_ID_CONFLICT");
            }
            return new EventView(request.eventId(), sessionId, request.generation(), request.stopEpoch(), request.sequence(), request.kind(),
                    request.payloadDigest(), request.sourceAnchorIds(), request.redactionStatus(), request.serverTimeEpochSecond());
        });
    }

    @Override public List<EventView> events(String tenantId, String sessionId, long afterSequence, int limit) {
        return tenant(tenantId, () -> {
            required(tenantId, sessionId);
            return jdbc.query("""
                    SELECT event_id,session_id,generation,stop_epoch,sequence,kind,payload_digest,source_anchor_ids,redaction_status,server_time_epoch
                    FROM lw_runtime_events WHERE tenant_id=? AND session_id=? AND sequence>? ORDER BY sequence LIMIT ?
                    """, (rs, row) -> event(rs), tenantId, sessionId, afterSequence, limit);
        });
    }

    @Override public void recordAudit(String tenantId, String actorId, String sessionId, String action,
                                      String outcome, String payloadDigest, long now) {
        tenant(tenantId, () -> { audit(tenantId, actorId, sessionId, action, outcome, payloadDigest, now); return null; });
    }

    private SessionView required(String tenantId, String sessionId) {
        return jdbc.query("SELECT * FROM lw_sessions WHERE tenant_id=? AND session_id=?", sessionMapper, tenantId, sessionId)
                .stream().findFirst().orElseThrow(LiveWorkbenchException::notFound);
    }

    private void audit(String tenantId, String actorId, String sessionId, String action, String outcome, String payloadDigest, long now) {
        // The parent row is an always-present serialization point, including the first audit entry.
        jdbc.queryForObject("SELECT session_id FROM lw_sessions WHERE tenant_id=? AND session_id=? FOR UPDATE",
                String.class, tenantId, sessionId);
        List<String> previous = jdbc.query("SELECT entry_hash FROM lw_audit_events WHERE tenant_id=? AND session_id=? ORDER BY sequence DESC LIMIT 1 FOR UPDATE",
                (rs, row) -> rs.getString(1), tenantId, sessionId);
        String previousHash = previous.isEmpty() ? "sha256:" + "0".repeat(64) : previous.getFirst();
        Long sequence = jdbc.queryForObject("SELECT COALESCE(MAX(sequence),0)+1 FROM lw_audit_events WHERE tenant_id=? AND session_id=?", Long.class, tenantId, sessionId);
        String entryHash = LwDigest.sha256(previousHash + "\n" + tenantId + "\n" + sessionId + "\n" + action + "\n" + outcome + "\n" + payloadDigest + "\n" + now);
        jdbc.update("INSERT INTO lw_audit_events(tenant_id,session_id,sequence,actor_id,action,outcome,payload_digest,observed_at_epoch,previous_hash,entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                tenantId, sessionId, sequence, actorId, action, outcome, payloadDigest, now, previousHash, entryHash);
        jdbc.update("INSERT INTO lw_outbox(tenant_id,event_id,session_id,event_type,payload_digest,created_at_epoch) VALUES (?,?,?,?,?,?)",
                tenantId, java.util.UUID.randomUUID().toString(), sessionId, action, entryHash, now);
    }

    private <T> T tenant(String tenantId, java.util.function.Supplier<T> operation) {
        return transactions.execute(status -> {
            jdbc.queryForObject("SELECT set_config('elmos.tenant_id', ?, true)", String.class, tenantId);
            jdbc.queryForObject("SELECT set_config('elmos.system_worker', 'false', true)", String.class);
            return operation.get();
        });
    }
    private <T> T system(java.util.function.Supplier<T> operation) {
        return transactions.execute(status -> {
            jdbc.queryForObject("SELECT set_config('elmos.system_worker', 'true', true)", String.class);
            return operation.get();
        });
    }

    private SessionView session(ResultSet rs, int row) throws SQLException {
        return new SessionView(rs.getString("tenant_id"), rs.getString("account_id"), rs.getString("actor_id"), rs.getString("session_id"),
                rs.getString("delivery_id"), rs.getString("repository_id"), rs.getString("snapshot_id"), rs.getString("runtime_profile_id"),
                rs.getString("scenario"), rs.getString("mode"), rs.getInt("generation"), rs.getInt("slot_weight"),
                SessionState.valueOf(rs.getString("state")), RuntimeStatus.valueOf(rs.getString("runtime_status")), rs.getLong("created_at_epoch"),
                nullableLong(rs, "first_ready_at_epoch"), nullableLong(rs, "expires_at_epoch"), rs.getLong("provider_hard_deadline_epoch"),
                rs.getString("provider_session_id"), rs.getString("resource_lease_id"), decode(rs.getString("resource_members"), STRING_MAP),
                decode(rs.getString("evidence_refs"), STRING_LIST), rs.getLong("version"));
    }
    private DebugReceipt command(ResultSet rs) throws SQLException {
        return new DebugReceipt(rs.getString("command_id"), rs.getString("idempotency_key"), CommandState.valueOf(rs.getString("state")),
                rs.getString("code"), rs.getString("evidence_ref"), rs.getLong("version"));
    }
    private EventView event(ResultSet rs) throws SQLException {
        return new EventView(rs.getString("event_id"), rs.getString("session_id"), rs.getInt("generation"), rs.getInt("stop_epoch"),
                rs.getLong("sequence"), rs.getString("kind"), rs.getString("payload_digest"),
                decode(rs.getString("source_anchor_ids"), STRING_LIST), rs.getString("redaction_status"), rs.getLong("server_time_epoch"));
    }
    private static Long nullableLong(ResultSet rs, String column) throws SQLException { long value = rs.getLong(column); return rs.wasNull() ? null : value; }
    private String encode(Object value) { try { return json.writeValueAsString(value); } catch (JsonProcessingException error) { throw new IllegalArgumentException("JSON encoding failed", error); } }
    private <T> T decode(String value, TypeReference<T> type) { try { return json.readValue(value, type); } catch (JsonProcessingException error) { throw new IllegalStateException("stored JSON invalid", error); } }
}
