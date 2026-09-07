package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.*;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public final class UsageAndAuditGovernance {
    private final Map<String, BigDecimal> availableByOrganization = new HashMap<>();
    private final Map<String, UsageReservation> reservationsByIdempotencyKey = new HashMap<>();
    private final Map<String, UsageEvent> usageByIdempotencyKey = new HashMap<>();
    private final List<LedgerEntry> ledger = new ArrayList<>();

    public synchronized void openCreditAccount(String organizationId, BigDecimal available) {
        EnterpriseModels.require(organizationId, "organizationId");
        if (available.signum() < 0) throw new IllegalArgumentException("credit cannot be negative");
        if (availableByOrganization.putIfAbsent(organizationId, available) != null) {
            throw new IllegalStateException("CREDIT_ACCOUNT_ALREADY_EXISTS");
        }
        ledger.add(entry(organizationId, available, "OPENING_BALANCE", "account:" + organizationId, null));
    }

    public synchronized UsageReservation reserve(String organizationId, BigDecimal amount,
                                                  String idempotencyKey, Instant expiresAt) {
        EnterpriseModels.require(organizationId, "organizationId");
        EnterpriseModels.require(idempotencyKey, "idempotencyKey");
        if (amount == null || amount.signum() <= 0) throw new IllegalArgumentException("reservation amount must be positive");
        String scopedKey = scopedKey(organizationId, idempotencyKey);
        UsageReservation existing = reservationsByIdempotencyKey.get(scopedKey);
        if (existing != null) return existing;
        BigDecimal available = availableByOrganization.getOrDefault(organizationId, BigDecimal.ZERO);
        if (available.compareTo(amount) < 0) {
            UsageReservation rejected = new UsageReservation("reservation-" + stableId(idempotencyKey), organizationId,
                    amount, ReservationStatus.REJECTED, idempotencyKey, expiresAt);
            reservationsByIdempotencyKey.put(scopedKey, rejected);
            return rejected;
        }
        availableByOrganization.put(organizationId, available.subtract(amount));
        UsageReservation reservation = new UsageReservation("reservation-" + stableId(idempotencyKey), organizationId,
                amount, ReservationStatus.RESERVED, idempotencyKey, expiresAt);
        reservationsByIdempotencyKey.put(scopedKey, reservation);
        ledger.add(entry(organizationId, amount.negate(), "RESERVE", reservation.reservationId(), null));
        return reservation;
    }

    public synchronized UsageReservation settle(String organizationId, String idempotencyKey, BigDecimal consumed, Instant now,
                                                 String costSnapshotId) {
        UsageReservation reservation = reservationsByIdempotencyKey.get(scopedKey(organizationId, idempotencyKey));
        if (reservation == null || reservation.status() != ReservationStatus.RESERVED) {
            throw new IllegalStateException("ACTIVE_RESERVATION_REQUIRED");
        }
        if (!now.isBefore(reservation.expiresAt())) throw new IllegalStateException("RESERVATION_EXPIRED");
        if (consumed == null || consumed.signum() < 0 || consumed.compareTo(reservation.amount()) > 0) {
            throw new IllegalArgumentException("invalid consumed amount");
        }
        EnterpriseModels.require(costSnapshotId, "costSnapshotId");
        BigDecimal release = reservation.amount().subtract(consumed);
        availableByOrganization.merge(reservation.organizationId(), release, BigDecimal::add);
        UsageReservation committed = new UsageReservation(reservation.reservationId(), reservation.organizationId(),
                reservation.amount(), ReservationStatus.COMMITTED, reservation.idempotencyKey(), reservation.expiresAt());
        reservationsByIdempotencyKey.put(scopedKey(organizationId, idempotencyKey), committed);
        ledger.add(entry(reservation.organizationId(), release, "RELEASE_UNUSED", reservation.reservationId(), null));
        ledger.add(entry(reservation.organizationId(), consumed, "CONSUME@" + costSnapshotId, reservation.reservationId(), null));
        return committed;
    }

    public synchronized UsageReservation release(String organizationId, String idempotencyKey) {
        UsageReservation reservation = reservationsByIdempotencyKey.get(scopedKey(organizationId, idempotencyKey));
        if (reservation == null || reservation.status() != ReservationStatus.RESERVED) {
            throw new IllegalStateException("ACTIVE_RESERVATION_REQUIRED");
        }
        availableByOrganization.merge(reservation.organizationId(), reservation.amount(), BigDecimal::add);
        UsageReservation released = new UsageReservation(reservation.reservationId(), reservation.organizationId(),
                reservation.amount(), ReservationStatus.RELEASED, reservation.idempotencyKey(), reservation.expiresAt());
        reservationsByIdempotencyKey.put(scopedKey(organizationId, idempotencyKey), released);
        ledger.add(entry(reservation.organizationId(), reservation.amount(), "RELEASE", reservation.reservationId(), null));
        return released;
    }

    public synchronized boolean recordUsage(UsageEvent event) {
        if (event.quantity() == null || event.quantity().signum() < 0) throw new IllegalArgumentException("usage must be non-negative");
        EnterpriseModels.require(event.costSnapshotId(), "costSnapshotId");
        String scopedKey = scopedKey(event.organizationId(), event.idempotencyKey());
        if (usageByIdempotencyKey.containsKey(scopedKey)) return false;
        usageByIdempotencyKey.put(scopedKey, event);
        ledger.add(entry(event.organizationId(), event.quantity(), "USAGE:" + event.resourceType(), event.eventId(), null));
        return true;
    }

    public synchronized BigDecimal available(String organizationId) {
        return availableByOrganization.getOrDefault(organizationId, BigDecimal.ZERO);
    }
    public synchronized List<LedgerEntry> ledger(String organizationId) {
        return ledger.stream().filter(entry -> entry.organizationId().equals(organizationId)).toList();
    }

    public AuditEvent appendAudit(List<AuditEvent> existingChain, AuditDraft draft, boolean auditWriterAvailable,
                                  boolean highRisk) {
        if (!auditWriterAvailable && highRisk) throw new IllegalStateException("AUDIT_REQUIRED_FAIL_CLOSED");
        validateAuditDraft(draft);
        String previous = existingChain.isEmpty() ? "0".repeat(64) : existingChain.getLast().eventHash();
        return new AuditEvent(draft, previous, sha256(previous + "\n" + canonical(draft)));
    }

    public AuditVerification verifyAudit(List<AuditEvent> chain) {
        List<String> reasons = new ArrayList<>();
        String previous = "0".repeat(64);
        Set<String> ids = new HashSet<>();
        int verified = 0;
        for (AuditEvent event : chain) {
            if (!ids.add(event.event().eventId())) reasons.add("DUPLICATE_EVENT:" + event.event().eventId());
            if (!previous.equals(event.previousHash())) reasons.add("CHAIN_GAP:" + event.event().eventId());
            String expected = sha256(previous + "\n" + canonical(event.event()));
            if (!expected.equals(event.eventHash())) reasons.add("HASH_MISMATCH:" + event.event().eventId());
            previous = event.eventHash(); verified++;
        }
        return new AuditVerification(reasons.isEmpty(), verified, reasons);
    }

    private static void validateAuditDraft(AuditDraft draft) {
        EnterpriseModels.require(draft.eventId(), "eventId"); EnterpriseModels.require(draft.organizationId(), "organizationId");
        EnterpriseModels.require(draft.actorId(), "actorId"); EnterpriseModels.require(draft.action(), "action");
        for (Map.Entry<String, String> entry : draft.metadata().entrySet()) {
            String key = entry.getKey().toLowerCase(Locale.ROOT);
            String value = String.valueOf(entry.getValue());
            if (key.contains("password") || key.contains("secretvalue") || key.equals("token") || key.contains("apikey")) {
                throw new SecurityException("SECRET_FIELD_IN_AUDIT");
            }
            if (value.contains("-----BEGIN PRIVATE KEY-----") || value.matches("gh[pousr]_[A-Za-z0-9_]{20,}")) {
                throw new SecurityException("SECRET_VALUE_IN_AUDIT");
            }
        }
    }

    private static String canonical(AuditDraft draft) {
        StringJoiner metadata = new StringJoiner(";");
        draft.metadata().entrySet().stream().sorted(Map.Entry.comparingByKey())
                .forEach(entry -> metadata.add(entry.getKey() + "=" + entry.getValue()));
        return String.join("|", draft.eventId(), draft.organizationId(), draft.actorType(), draft.actorId(),
                draft.action(), draft.resourceType(), draft.resourceId(), draft.decision(), draft.policyVersion(),
                nullToEmpty(draft.beforeHash()), nullToEmpty(draft.afterHash()), draft.correlationId(),
                draft.occurredAt().toString(), metadata.toString());
    }

    private LedgerEntry entry(String organizationId, BigDecimal amount, String type, String source, String reversal) {
        return new LedgerEntry("ledger-" + (ledger.size() + 1), organizationId, amount, type, source, reversal, Instant.now());
    }
    private static String scopedKey(String organizationId, String idempotencyKey) {
        EnterpriseModels.require(organizationId, "organizationId");
        EnterpriseModels.require(idempotencyKey, "idempotencyKey");
        return organizationId + "\u0000" + idempotencyKey;
    }
    private static String stableId(String value) { return sha256(value).substring(0, 24); }
    private static String nullToEmpty(String value) { return value == null ? "" : value; }
    private static String sha256(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
