package io.elmos.commercial;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

/**
 * Dependency-free, bounded local reference runtime for the financial core of the
 * Pricing and Billing Skill package.
 *
 * <p>The runtime models source facts as append-only events and derives balances,
 * usage, invoice state and margin observations by replay. It deliberately has
 * no provider, bank, tax-authority or accounting-system adapter. The PostgreSQL
 * durability contract lives in migration V65. Local execution is engineering
 * evidence only and never constitutes accounting, tax, payment, management
 * reporting or production certification.</p>
 */
public final class PricingBillingFinancialRuntime {
    private static final Set<String> FINANCIAL_CATEGORIES = Set.of(
            "REVENUE", "SUBSCRIPTION_REVENUE", "USAGE_REVENUE", "PROVIDER",
            "RUNNER", "STORAGE", "EGRESS", "HUMAN_REVIEW", "SUPPORT", "OTHER_COGS");

    private PricingBillingFinancialRuntime() {
    }

    public static final String CERTIFICATION_STATE = "NOT_CERTIFIED";

    /** Exact local ownership map for EB04, EB05, EB09 and EB13. */
    public static final Map<String, String> REQUIREMENT_BINDINGS = requirementBindings();

    public record Scope(String tenantId, String legalEntityId) {
        public Scope {
            tenantId = required(tenantId, "tenantId");
            legalEntityId = required(legalEntityId, "legalEntityId");
        }
    }

    public record Money(String currency, BigDecimal amount) {
        public Money {
            currency = required(currency, "currency").toUpperCase(Locale.ROOT);
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("currency must be an ISO-style three-letter code");
            }
            amount = exact(amount, "amount");
        }

        public Money add(Money other) {
            sameCurrency(other);
            return new Money(currency, amount.add(other.amount));
        }

        public Money subtract(Money other) {
            sameCurrency(other);
            return new Money(currency, amount.subtract(other.amount));
        }

        public Money multiply(BigDecimal quantity) {
            return new Money(currency, amount.multiply(exact(quantity, "quantity")));
        }

        private void sameCurrency(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("currency mismatch");
            }
        }
    }

    public enum EvidenceState {
        RECONCILED,
        FINAL,
        UNKNOWN,
        DISPUTED
    }

    public record OutboxFact(long sequence, Scope scope, String aggregateType,
                             String aggregateId, long aggregateVersion,
                             String eventType, String sourceFactId, Instant occurredAt) {
        public OutboxFact {
            Objects.requireNonNull(scope, "scope");
            aggregateType = required(aggregateType, "aggregateType");
            aggregateId = required(aggregateId, "aggregateId");
            eventType = required(eventType, "eventType");
            sourceFactId = required(sourceFactId, "sourceFactId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            if (sequence <= 0 || aggregateVersion <= 0) {
                throw new IllegalArgumentException("outbox sequence and aggregateVersion must be positive");
            }
        }
    }

    public enum CreditKind {
        PROMOTIONAL,
        PAID
    }

    public enum WalletEventType {
        GRANT,
        RESERVE,
        COMMIT,
        RELEASE,
        EXPIRE
    }

    public enum ReservationState {
        RESERVED,
        COMMITTED,
        RELEASED
    }

    public record WalletEvent(String eventId, Scope scope, String walletId, long version,
                              WalletEventType type, String lotId, String reservationId,
                              CreditKind creditKind, BigDecimal amount, String unit,
                              String debitAccount, String creditAccount, String commandId,
                              Instant effectiveAt, Instant expiresAt, String reasonCode) {
        public WalletEvent {
            eventId = required(eventId, "eventId");
            Objects.requireNonNull(scope, "scope");
            walletId = required(walletId, "walletId");
            Objects.requireNonNull(type, "type");
            lotId = required(lotId, "lotId");
            amount = positive(amount, "amount");
            unit = required(unit, "unit").toUpperCase(Locale.ROOT);
            debitAccount = required(debitAccount, "debitAccount");
            creditAccount = required(creditAccount, "creditAccount");
            commandId = required(commandId, "commandId");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            reasonCode = required(reasonCode, "reasonCode");
            if (version <= 0) {
                throw new IllegalArgumentException("version must be positive");
            }
            if (debitAccount.equals(creditAccount)) {
                throw new IllegalArgumentException("double-entry accounts must differ");
            }
            if (type == WalletEventType.GRANT && creditKind == null) {
                throw new IllegalArgumentException("grant requires creditKind");
            }
            if ((type == WalletEventType.RESERVE || type == WalletEventType.COMMIT
                    || type == WalletEventType.RELEASE) && isBlank(reservationId)) {
                throw new IllegalArgumentException("reservation event requires reservationId");
            }
        }
    }

    public record LotView(String lotId, CreditKind kind, BigDecimal available,
                          BigDecimal reserved, Instant expiresAt) {
    }

    public record ReservationView(String reservationId, ReservationState state,
                                  BigDecimal amount, Map<String, BigDecimal> allocations) {
        public ReservationView {
            allocations = Collections.unmodifiableMap(new LinkedHashMap<>(allocations));
        }
    }

    public record WalletProjection(Scope scope, String walletId, String unit, long version,
                                   BigDecimal available, BigDecimal reserved,
                                   List<LotView> lots, Map<String, ReservationView> reservations) {
        public WalletProjection {
            lots = List.copyOf(lots);
            reservations = Collections.unmodifiableMap(new LinkedHashMap<>(reservations));
        }
    }

    /**
     * Append-only, replay-derived credit wallet. Synchronized commands plus an
     * expected version provide the local concurrency contract; V65 supplies the
     * durable unique constraints and row locking contract.
     */
    public static final class WalletLedger {
        private final List<WalletEvent> events = new ArrayList<>();
        private final List<OutboxFact> outbox = new ArrayList<>();
        private final Map<String, CommandReceipt<WalletProjection>> commands = new HashMap<>();
        private long eventSequence;
        private long outboxSequence;

        public synchronized WalletProjection grant(Scope scope, String walletId, String lotId,
                                                    CreditKind kind, BigDecimal amount, String unit,
                                                    Instant effectiveAt, Instant expiresAt,
                                                    String commandId, long expectedVersion,
                                                    String reasonCode) {
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            if (expiresAt != null && !expiresAt.isAfter(effectiveAt)) {
                throw new IllegalArgumentException("expiresAt must be after effectiveAt");
            }
            String fingerprint = fingerprint("grant", scope, walletId, lotId, kind, amount, unit,
                    effectiveAt, expiresAt, reasonCode);
            Optional<WalletProjection> replay = replayCommand(scope, walletId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            WalletProjection before = project(scope, walletId, effectiveAt);
            requireVersion(before.version(), expectedVersion);
            if (before.version() > 0) {
                requireUnit(before, unit);
            }
            if (events.stream().anyMatch(event -> event.scope().equals(scope)
                    && event.walletId().equals(walletId) && event.lotId().equals(lotId))) {
                throw new IllegalStateException("lot already exists in wallet");
            }
            appendWalletEvent(scope, walletId, WalletEventType.GRANT, lotId, null, kind,
                    positive(amount, "amount"), unit, "funding:" + kind.name().toLowerCase(Locale.ROOT),
                    "wallet:" + walletId + ":" + lotId, commandId, effectiveAt, expiresAt, reasonCode);
            return remember(scope, walletId, commandId, fingerprint, project(scope, walletId, effectiveAt));
        }

        public synchronized WalletProjection reserve(Scope scope, String walletId, String reservationId,
                                                      BigDecimal amount, String unit, Instant effectiveAt,
                                                      String commandId, long expectedVersion) {
            BigDecimal requested = positive(amount, "amount");
            String fingerprint = fingerprint("reserve", scope, walletId, reservationId, requested, unit,
                    effectiveAt);
            Optional<WalletProjection> replay = replayCommand(scope, walletId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            WalletProjection before = project(scope, walletId, effectiveAt);
            requireVersion(before.version(), expectedVersion);
            requireUnit(before, unit);
            if (before.reservations().containsKey(reservationId)) {
                throw new IllegalStateException("reservation already exists");
            }
            if (before.available().compareTo(requested) < 0) {
                throw new IllegalStateException("insufficient available credit");
            }
            BigDecimal remaining = requested;
            List<LotView> ordered = new ArrayList<>(before.lots());
            ordered.sort(Comparator
                    .comparing(LotView::expiresAt, Comparator.nullsLast(Comparator.naturalOrder()))
                    .thenComparing(lot -> lot.kind() == CreditKind.PROMOTIONAL ? 0 : 1)
                    .thenComparing(LotView::lotId));
            for (LotView lot : ordered) {
                if (remaining.signum() == 0 || lot.available().signum() == 0) {
                    continue;
                }
                BigDecimal allocation = lot.available().min(remaining);
                appendWalletEvent(scope, walletId, WalletEventType.RESERVE, lot.lotId(), reservationId,
                        lot.kind(), allocation, unit, "wallet:" + walletId + ":" + lot.lotId(),
                        "wallet-hold:" + walletId + ":" + reservationId, commandId, effectiveAt,
                        lot.expiresAt(), "RESERVATION_CREATED");
                remaining = remaining.subtract(allocation);
            }
            if (remaining.signum() != 0) {
                throw new IllegalStateException("reservation allocation invariant failed");
            }
            return remember(scope, walletId, commandId, fingerprint, project(scope, walletId, effectiveAt));
        }

        public synchronized WalletProjection commit(Scope scope, String walletId, String reservationId,
                                                     Instant effectiveAt, String commandId,
                                                     long expectedVersion) {
            return finishReservation(scope, walletId, reservationId, effectiveAt, commandId,
                    expectedVersion, WalletEventType.COMMIT);
        }

        public synchronized WalletProjection release(Scope scope, String walletId, String reservationId,
                                                      Instant effectiveAt, String commandId,
                                                      long expectedVersion) {
            return finishReservation(scope, walletId, reservationId, effectiveAt, commandId,
                    expectedVersion, WalletEventType.RELEASE);
        }

        public synchronized WalletProjection expire(Scope scope, String walletId, Instant asOf,
                                                     String commandId, long expectedVersion) {
            String fingerprint = fingerprint("expire", scope, walletId, asOf);
            Optional<WalletProjection> replay = replayCommand(scope, walletId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            WalletProjection beforeExpiry = project(scope, walletId, asOf, false);
            requireVersion(beforeExpiry.version(), expectedVersion);
            if (beforeExpiry.version() == 0) {
                throw new IllegalStateException("wallet not found");
            }
            for (LotView lot : beforeExpiry.lots()) {
                if (lot.expiresAt() != null && !lot.expiresAt().isAfter(asOf)
                        && lot.available().signum() > 0) {
                    appendWalletEvent(scope, walletId, WalletEventType.EXPIRE, lot.lotId(), null,
                            lot.kind(), lot.available(), beforeExpiry.unit(),
                            "wallet:" + walletId + ":" + lot.lotId(), "expired-credit:" + walletId,
                            commandId, asOf, lot.expiresAt(), "LOT_EXPIRED");
                }
            }
            return remember(scope, walletId, commandId, fingerprint, project(scope, walletId, asOf));
        }

        public synchronized WalletProjection balance(Scope scope, String walletId, Instant asOf) {
            return project(scope, walletId, asOf);
        }

        public synchronized List<WalletEvent> journal(Scope scope, String walletId) {
            return events.stream().filter(event -> event.scope().equals(scope)
                    && event.walletId().equals(walletId)).toList();
        }

        public synchronized List<OutboxFact> outbox() {
            return List.copyOf(outbox);
        }

        private WalletProjection finishReservation(Scope scope, String walletId, String reservationId,
                                                    Instant effectiveAt, String commandId,
                                                    long expectedVersion, WalletEventType type) {
            String fingerprint = fingerprint(type.name(), scope, walletId, reservationId, effectiveAt);
            Optional<WalletProjection> replay = replayCommand(scope, walletId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            WalletProjection before = project(scope, walletId, effectiveAt);
            requireVersion(before.version(), expectedVersion);
            ReservationView reservation = before.reservations().get(reservationId);
            if (reservation == null || reservation.state() != ReservationState.RESERVED) {
                throw new IllegalStateException("reservation is not open");
            }
            Map<String, LotView> lots = new HashMap<>();
            before.lots().forEach(lot -> lots.put(lot.lotId(), lot));
            for (Map.Entry<String, BigDecimal> allocation : reservation.allocations().entrySet()) {
                LotView lot = Objects.requireNonNull(lots.get(allocation.getKey()), "reservation lot");
                String debit = "wallet-hold:" + walletId + ":" + reservationId;
                String credit = type == WalletEventType.COMMIT
                        ? "credit-consumption:" + walletId : "wallet:" + walletId + ":" + lot.lotId();
                appendWalletEvent(scope, walletId, type, lot.lotId(), reservationId, lot.kind(),
                        allocation.getValue(), before.unit(), debit, credit, commandId, effectiveAt,
                        lot.expiresAt(), type == WalletEventType.COMMIT
                                ? "RESERVATION_COMMITTED" : "RESERVATION_RELEASED");
            }
            return remember(scope, walletId, commandId, fingerprint, project(scope, walletId, effectiveAt));
        }

        private void appendWalletEvent(Scope scope, String walletId, WalletEventType type,
                                       String lotId, String reservationId, CreditKind creditKind,
                                       BigDecimal amount, String unit, String debitAccount,
                                       String creditAccount, String commandId, Instant effectiveAt,
                                       Instant expiresAt, String reasonCode) {
            long version = currentVersion(scope, walletId) + 1;
            String eventId = "wallet-event-" + ++eventSequence;
            WalletEvent event = new WalletEvent(eventId, scope, walletId, version, type, lotId,
                    reservationId, creditKind, amount, unit, debitAccount, creditAccount,
                    commandId, effectiveAt, expiresAt, reasonCode);
            events.add(event);
            outbox.add(new OutboxFact(++outboxSequence, scope, "CREDIT_WALLET", walletId,
                    version, type.name(), eventId, effectiveAt));
        }

        private Optional<WalletProjection> replayCommand(Scope scope, String walletId,
                                                         String commandId, String fingerprint) {
            String key = scopedKey(scope, walletId, required(commandId, "commandId"));
            CommandReceipt<WalletProjection> receipt = commands.get(key);
            if (receipt == null) {
                return Optional.empty();
            }
            if (!receipt.fingerprint().equals(fingerprint)) {
                throw new IllegalStateException("idempotency key reused with different wallet command");
            }
            return Optional.of(receipt.result());
        }

        private WalletProjection remember(Scope scope, String walletId, String commandId,
                                          String fingerprint, WalletProjection result) {
            commands.put(scopedKey(scope, walletId, commandId), new CommandReceipt<>(fingerprint, result));
            return result;
        }

        private long currentVersion(Scope scope, String walletId) {
            return events.stream().filter(event -> event.scope().equals(scope)
                            && event.walletId().equals(walletId))
                    .mapToLong(WalletEvent::version).max().orElse(0);
        }

        private WalletProjection project(Scope scope, String walletId, Instant asOf) {
            return project(scope, walletId, asOf, true);
        }

        private WalletProjection project(Scope scope, String walletId, Instant asOf,
                                         boolean hideExpiredAvailability) {
            Objects.requireNonNull(scope, "scope");
            walletId = required(walletId, "walletId");
            Objects.requireNonNull(asOf, "asOf");
            Map<String, MutableLot> lots = new LinkedHashMap<>();
            Map<String, MutableReservation> reservations = new LinkedHashMap<>();
            String unit = null;
            long version = 0;
            for (WalletEvent event : events) {
                if (!event.scope().equals(scope) || !event.walletId().equals(walletId)) {
                    continue;
                }
                version = event.version();
                if (event.effectiveAt().isAfter(asOf)) {
                    continue;
                }
                unit = unit == null ? event.unit() : unit;
                if (!unit.equals(event.unit())) {
                    throw new IllegalStateException("wallet unit invariant failed");
                }
                MutableLot lot = lots.computeIfAbsent(event.lotId(), ignored ->
                        new MutableLot(event.lotId(), event.creditKind(), event.expiresAt()));
                switch (event.type()) {
                    case GRANT -> lot.available = lot.available.add(event.amount());
                    case RESERVE -> {
                        lot.available = lot.available.subtract(event.amount());
                        lot.reserved = lot.reserved.add(event.amount());
                        MutableReservation reservation = reservations.computeIfAbsent(event.reservationId(),
                                MutableReservation::new);
                        reservation.amount = reservation.amount.add(event.amount());
                        reservation.allocations.merge(event.lotId(), event.amount(), BigDecimal::add);
                    }
                    case COMMIT -> {
                        lot.reserved = lot.reserved.subtract(event.amount());
                        MutableReservation reservation = reservationForTerminalEvent(
                                reservations, event.reservationId(), ReservationState.COMMITTED);
                        reservation.state = ReservationState.COMMITTED;
                    }
                    case RELEASE -> {
                        lot.reserved = lot.reserved.subtract(event.amount());
                        lot.available = lot.available.add(event.amount());
                        MutableReservation reservation = reservationForTerminalEvent(
                                reservations, event.reservationId(), ReservationState.RELEASED);
                        reservation.state = ReservationState.RELEASED;
                    }
                    case EXPIRE -> lot.available = lot.available.subtract(event.amount());
                }
                if (lot.available.signum() < 0 || lot.reserved.signum() < 0) {
                    throw new IllegalStateException("wallet projection cannot be negative");
                }
            }
            List<LotView> lotViews = new ArrayList<>();
            BigDecimal available = BigDecimal.ZERO;
            BigDecimal reserved = BigDecimal.ZERO;
            for (MutableLot lot : lots.values()) {
                BigDecimal visibleAvailable = hideExpiredAvailability && lot.expiresAt != null
                        && !lot.expiresAt.isAfter(asOf)
                        ? BigDecimal.ZERO : lot.available;
                lotViews.add(new LotView(lot.lotId, lot.kind, visibleAvailable, lot.reserved, lot.expiresAt));
                available = available.add(visibleAvailable);
                reserved = reserved.add(lot.reserved);
            }
            Map<String, ReservationView> reservationViews = new LinkedHashMap<>();
            reservations.forEach((id, reservation) -> reservationViews.put(id,
                    new ReservationView(id, reservation.state, reservation.amount, reservation.allocations)));
            return new WalletProjection(scope, walletId, unit == null ? "CREDIT" : unit,
                    version, available, reserved, lotViews, reservationViews);
        }

        private static MutableReservation reservationForTerminalEvent(
                Map<String, MutableReservation> reservations, String reservationId,
                ReservationState targetState) {
            MutableReservation reservation = reservations.get(reservationId);
            if (reservation == null || (reservation.state != ReservationState.RESERVED
                    && reservation.state != targetState)) {
                throw new IllegalStateException("invalid reservation event order");
            }
            return reservation;
        }

        private static void requireUnit(WalletProjection projection, String unit) {
            if (!projection.unit().equals(required(unit, "unit").toUpperCase(Locale.ROOT))) {
                throw new IllegalArgumentException("wallet unit mismatch");
            }
        }

        private static final class MutableLot {
            private final String lotId;
            private final CreditKind kind;
            private final Instant expiresAt;
            private BigDecimal available = BigDecimal.ZERO;
            private BigDecimal reserved = BigDecimal.ZERO;

            private MutableLot(String lotId, CreditKind kind, Instant expiresAt) {
                this.lotId = lotId;
                this.kind = kind;
                this.expiresAt = expiresAt;
            }
        }

        private static final class MutableReservation {
            private final String reservationId;
            private ReservationState state = ReservationState.RESERVED;
            private BigDecimal amount = BigDecimal.ZERO;
            private final Map<String, BigDecimal> allocations = new LinkedHashMap<>();

            private MutableReservation(String reservationId) {
                this.reservationId = reservationId;
            }
        }
    }

    public enum UsageFactType {
        ORIGINAL,
        CORRECTION
    }

    public enum UsageDecision {
        ACCEPTED,
        LATE_REVIEW
    }

    public record UsageCommand(String idempotencyKey, Scope scope, String recordId,
                               String source, String sourceEventId, String meterKey,
                               BigDecimal quantity, String unit, UsageFactType factType,
                               String correctionOf, String correctionReason,
                               Instant eventTime, Instant receivedAt,
                               Instant windowStart, Instant windowEnd,
                               Duration allowedLateness, String normalizationVersion,
                               Map<String, String> dimensions) {
        public UsageCommand {
            idempotencyKey = required(idempotencyKey, "idempotencyKey");
            Objects.requireNonNull(scope, "scope");
            recordId = required(recordId, "recordId");
            source = required(source, "source");
            sourceEventId = required(sourceEventId, "sourceEventId");
            meterKey = required(meterKey, "meterKey");
            quantity = exact(quantity, "quantity");
            unit = required(unit, "unit").toUpperCase(Locale.ROOT);
            Objects.requireNonNull(factType, "factType");
            Objects.requireNonNull(eventTime, "eventTime");
            Objects.requireNonNull(receivedAt, "receivedAt");
            Objects.requireNonNull(windowStart, "windowStart");
            Objects.requireNonNull(windowEnd, "windowEnd");
            Objects.requireNonNull(allowedLateness, "allowedLateness");
            normalizationVersion = required(normalizationVersion, "normalizationVersion");
            dimensions = dimensions == null ? Map.of() : Map.copyOf(dimensions);
            if (!windowEnd.isAfter(windowStart) || eventTime.isBefore(windowStart)
                    || !eventTime.isBefore(windowEnd) || allowedLateness.isNegative()) {
                throw new IllegalArgumentException("invalid usage window or lateness");
            }
            if (factType == UsageFactType.ORIGINAL && quantity.signum() <= 0) {
                throw new IllegalArgumentException("original usage quantity must be positive");
            }
            if (factType == UsageFactType.CORRECTION
                    && (quantity.signum() == 0 || isBlank(correctionOf) || isBlank(correctionReason))) {
                throw new IllegalArgumentException("correction requires non-zero delta, source fact and reason");
            }
            if (factType == UsageFactType.ORIGINAL && (!isBlank(correctionOf) || !isBlank(correctionReason))) {
                throw new IllegalArgumentException("original usage cannot be a correction");
            }
        }
    }

    public record UsageRecord(String fingerprint, UsageCommand command, UsageDecision decision,
                              boolean billable, long sequence, Instant recordedAt) {
    }

    /** Append-only usage ingestion, deduplication, correction and late-event policy. */
    public static final class UsageMeter {
        private final List<UsageRecord> records = new ArrayList<>();
        private final List<OutboxFact> outbox = new ArrayList<>();
        private final Map<String, UsageRecord> dedupe = new HashMap<>();
        private final Map<String, UsageRecord> commands = new HashMap<>();
        private long sequence;
        private long outboxSequence;

        public synchronized UsageRecord ingest(UsageCommand command) {
            Objects.requireNonNull(command, "command");
            String fingerprint = fingerprint("usage", command.scope(), command.recordId(),
                    command.source(), command.sourceEventId(), command.meterKey(),
                    command.quantity(), command.unit(),
                    command.factType(), command.correctionOf(), command.correctionReason(),
                    command.eventTime(), command.receivedAt(), command.windowStart(), command.windowEnd(),
                    command.allowedLateness(),
                    command.normalizationVersion(), new java.util.TreeMap<>(command.dimensions()));
            String commandKey = scopedKey(command.scope(), "usage-command", command.idempotencyKey());
            UsageRecord priorCommand = commands.get(commandKey);
            if (priorCommand != null) {
                if (!priorCommand.fingerprint().equals(fingerprint)) {
                    throw new IllegalStateException("idempotency key reused with different usage command");
                }
                return priorCommand;
            }
            String sourceKey = scopedKey(command.scope(), command.source(), command.sourceEventId());
            UsageRecord priorSource = dedupe.get(sourceKey);
            if (priorSource != null) {
                if (!priorSource.fingerprint().equals(fingerprint)) {
                    throw new IllegalStateException("source event identity collision");
                }
                commands.put(commandKey, priorSource);
                return priorSource;
            }
            if (records.stream().anyMatch(record -> record.command().scope().equals(command.scope())
                    && record.command().recordId().equals(command.recordId()))) {
                throw new IllegalStateException("usage recordId already exists in scope");
            }
            if (command.factType() == UsageFactType.CORRECTION) {
                UsageRecord corrected = records.stream().filter(record ->
                                record.command().scope().equals(command.scope())
                                        && record.command().recordId().equals(command.correctionOf()))
                        .findFirst().orElseThrow(() -> new IllegalStateException("correction source not found"));
                if (!corrected.command().meterKey().equals(command.meterKey())
                        || !corrected.command().unit().equals(command.unit())
                        || !corrected.command().windowStart().equals(command.windowStart())
                        || !corrected.command().windowEnd().equals(command.windowEnd())) {
                    throw new IllegalStateException("correction must preserve meter, unit and window");
                }
            }
            UsageDecision decision = command.receivedAt().isAfter(
                    command.windowEnd().plus(command.allowedLateness()))
                    ? UsageDecision.LATE_REVIEW : UsageDecision.ACCEPTED;
            UsageRecord record = new UsageRecord(fingerprint, command, decision,
                    decision == UsageDecision.ACCEPTED, ++sequence, command.receivedAt());
            records.add(record);
            dedupe.put(sourceKey, record);
            commands.put(commandKey, record);
            outbox.add(new OutboxFact(++outboxSequence, command.scope(), "USAGE_FACT",
                    command.recordId(), record.sequence(), "USAGE_" + decision.name(),
                    command.recordId(), command.receivedAt()));
            return record;
        }

        public synchronized BigDecimal billableQuantity(Scope scope, String meterKey,
                                                        Instant windowStart, Instant windowEnd,
                                                        String unit) {
            BigDecimal total = records.stream().filter(record -> record.billable()
                            && record.command().scope().equals(scope)
                            && record.command().meterKey().equals(meterKey)
                            && record.command().windowStart().equals(windowStart)
                            && record.command().windowEnd().equals(windowEnd)
                            && record.command().unit().equals(unit.toUpperCase(Locale.ROOT)))
                    .map(record -> record.command().quantity())
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
            if (total.signum() < 0) {
                throw new IllegalStateException("usage corrections cannot make a window negative");
            }
            return total;
        }

        public synchronized List<UsageRecord> records(Scope scope) {
            return records.stream().filter(record -> record.command().scope().equals(scope)).toList();
        }

        public synchronized List<OutboxFact> outbox() {
            return List.copyOf(outbox);
        }
    }

    public enum TaxState {
        CALCULATED,
        EXEMPT,
        UNKNOWN
    }

    public record TaxDecision(TaxState state, Money amount, String jurisdiction,
                              String policyVersion, String evidenceRef) {
        public TaxDecision {
            Objects.requireNonNull(state, "state");
            Objects.requireNonNull(amount, "amount");
            jurisdiction = required(jurisdiction, "jurisdiction");
            policyVersion = required(policyVersion, "policyVersion");
            if (state != TaxState.UNKNOWN) {
                evidenceRef = required(evidenceRef, "evidenceRef");
            }
            if (amount.amount().signum() < 0) {
                throw new IllegalArgumentException("tax amount cannot be negative");
            }
        }
    }

    public record InvoiceLine(String lineId, String description, BigDecimal quantity,
                              Money unitPrice, TaxDecision tax, String pricingVersion,
                              Instant servicePeriodStart, Instant servicePeriodEnd,
                              Set<String> sourceFactRefs) {
        public InvoiceLine {
            lineId = required(lineId, "lineId");
            description = required(description, "description");
            quantity = positive(quantity, "quantity");
            Objects.requireNonNull(unitPrice, "unitPrice");
            Objects.requireNonNull(tax, "tax");
            pricingVersion = required(pricingVersion, "pricingVersion");
            Objects.requireNonNull(servicePeriodStart, "servicePeriodStart");
            Objects.requireNonNull(servicePeriodEnd, "servicePeriodEnd");
            sourceFactRefs = sourceFactRefs == null ? Set.of()
                    : Collections.unmodifiableSet(new TreeSet<>(sourceFactRefs));
            if (!servicePeriodEnd.isAfter(servicePeriodStart) || sourceFactRefs.isEmpty()) {
                throw new IllegalArgumentException("invoice line requires a valid period and lineage");
            }
            if (unitPrice.amount().signum() < 0) {
                throw new IllegalArgumentException("unit price cannot be negative");
            }
            if (!unitPrice.currency().equals(tax.amount().currency())) {
                throw new IllegalArgumentException("line and tax currencies must match");
            }
        }

        public Money total() {
            return unitPrice.multiply(quantity).add(tax.amount());
        }
    }

    public enum InvoiceState {
        DRAFT,
        REVIEW_REQUIRED,
        FINALIZED,
        ISSUED,
        PARTIALLY_PAID,
        PAID,
        CREDITED,
        VOID
    }

    public enum InvoiceEventType {
        CREATED,
        SUBMITTED_FOR_REVIEW,
        FINALIZED,
        ISSUED,
        PAYMENT_RECONCILED,
        CREDIT_NOTE_ISSUED,
        VOIDED
    }

    public record PaymentEvidence(String paymentRef, Money amount, EvidenceState providerState,
                                  EvidenceState bankState, String providerEvidenceRef,
                                  String bankEvidenceRef, Instant settledAt) {
        public PaymentEvidence {
            paymentRef = required(paymentRef, "paymentRef");
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(providerState, "providerState");
            Objects.requireNonNull(bankState, "bankState");
            Objects.requireNonNull(settledAt, "settledAt");
        }

        public boolean reconciled() {
            return providerState == EvidenceState.RECONCILED && bankState == EvidenceState.RECONCILED
                    && !isBlank(providerEvidenceRef) && !isBlank(bankEvidenceRef);
        }
    }

    public record InvoiceEvent(String eventId, Scope scope, String invoiceId, long version,
                               InvoiceEventType type, String commandId, String actorId,
                               Instant occurredAt, Money amount, String reference,
                               List<InvoiceLine> initialLines, PaymentEvidence paymentEvidence) {
        public InvoiceEvent {
            eventId = required(eventId, "eventId");
            Objects.requireNonNull(scope, "scope");
            invoiceId = required(invoiceId, "invoiceId");
            Objects.requireNonNull(type, "type");
            commandId = required(commandId, "commandId");
            actorId = required(actorId, "actorId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            initialLines = initialLines == null ? List.of() : List.copyOf(initialLines);
            if (version <= 0) {
                throw new IllegalArgumentException("version must be positive");
            }
            if ((type == InvoiceEventType.PAYMENT_RECONCILED) != (paymentEvidence != null)) {
                throw new IllegalArgumentException("payment reconciliation event must retain payment evidence");
            }
        }
    }

    public record InvoiceSnapshot(Scope scope, String invoiceId, InvoiceState state,
                                  long version, String currency, Money total,
                                  Money paid, Money credited, Money balanceDue,
                                  List<InvoiceLine> lines, String makerId,
                                  Set<String> paymentRefs, Set<String> creditNoteRefs) {
        public InvoiceSnapshot {
            lines = List.copyOf(lines);
            paymentRefs = Collections.unmodifiableSet(new TreeSet<>(paymentRefs));
            creditNoteRefs = Collections.unmodifiableSet(new TreeSet<>(creditNoteRefs));
        }
    }

    /** Append-only invoice state machine with tax and payment evidence fail-closed. */
    public static final class InvoiceBook {
        private final List<InvoiceEvent> events = new ArrayList<>();
        private final List<OutboxFact> outbox = new ArrayList<>();
        private final Map<String, CommandReceipt<InvoiceSnapshot>> commands = new HashMap<>();
        private long eventSequence;
        private long outboxSequence;

        public synchronized InvoiceSnapshot createDraft(Scope scope, String invoiceId,
                                                        List<InvoiceLine> lines, String makerId,
                                                        String commandId, Instant at) {
            if (lines == null || lines.isEmpty()) {
                throw new IllegalArgumentException("invoice requires at least one line");
            }
            String fingerprint = fingerprint("invoice-create", scope, invoiceId, lines, makerId, at);
            Optional<InvoiceSnapshot> replay = replayCommand(scope, invoiceId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            if (version(scope, invoiceId) != 0) {
                throw new IllegalStateException("invoice already exists");
            }
            String currency = lines.get(0).unitPrice().currency();
            if (lines.stream().anyMatch(line -> !line.unitPrice().currency().equals(currency))) {
                throw new IllegalArgumentException("invoice cannot mix currencies");
            }
            appendInvoiceEvent(scope, invoiceId, InvoiceEventType.CREATED, commandId, makerId,
                    at, null, null, lines, null);
            return remember(scope, invoiceId, commandId, fingerprint, project(scope, invoiceId));
        }

        public synchronized InvoiceSnapshot submitForReview(Scope scope, String invoiceId,
                                                             long expectedVersion, String commandId,
                                                             String actorId, Instant at) {
            return transition(scope, invoiceId, expectedVersion, commandId, actorId, at,
                    InvoiceEventType.SUBMITTED_FOR_REVIEW, null, null);
        }

        public synchronized InvoiceSnapshot finalizeInvoice(Scope scope, String invoiceId,
                                                             long expectedVersion, String commandId,
                                                             String approverId, Instant at) {
            String fingerprint = transitionFingerprint(scope, invoiceId, expectedVersion,
                    approverId, at, InvoiceEventType.FINALIZED, null, "TAX_EVIDENCE_VERIFIED");
            Optional<InvoiceSnapshot> replay = replayCommand(scope, invoiceId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            InvoiceSnapshot before = project(scope, invoiceId);
            if (before.state() != InvoiceState.REVIEW_REQUIRED) {
                throw new IllegalStateException("invoice must be reviewed before finalization");
            }
            if (before.makerId().equals(required(approverId, "approverId"))) {
                throw new IllegalStateException("maker cannot approve the invoice");
            }
            if (before.lines().stream().anyMatch(line -> line.tax().state() == TaxState.UNKNOWN)) {
                throw new IllegalStateException("unknown tax blocks invoice finalization");
            }
            return transition(scope, invoiceId, expectedVersion, commandId, approverId, at,
                    InvoiceEventType.FINALIZED, null, "TAX_EVIDENCE_VERIFIED");
        }

        public synchronized InvoiceSnapshot issue(Scope scope, String invoiceId,
                                                  long expectedVersion, String commandId,
                                                  String actorId, Instant at) {
            return transition(scope, invoiceId, expectedVersion, commandId, actorId, at,
                    InvoiceEventType.ISSUED, null, null);
        }

        public synchronized InvoiceSnapshot recordPayment(Scope scope, String invoiceId,
                                                          long expectedVersion, String commandId,
                                                          String actorId, PaymentEvidence evidence) {
            Objects.requireNonNull(evidence, "evidence");
            String fingerprint = fingerprint("invoice-payment", scope, invoiceId, expectedVersion,
                    commandId, actorId, evidence);
            Optional<InvoiceSnapshot> replay = replayCommand(scope, invoiceId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            InvoiceSnapshot before = project(scope, invoiceId);
            requireVersion(before.version(), expectedVersion);
            if (before.state() != InvoiceState.ISSUED && before.state() != InvoiceState.PARTIALLY_PAID) {
                throw new IllegalStateException("invoice is not payable");
            }
            if (!evidence.reconciled()) {
                throw new IllegalStateException("unknown or unreconciled payment blocks posting");
            }
            if (!before.currency().equals(evidence.amount().currency())
                    || evidence.amount().amount().signum() <= 0
                    || evidence.amount().amount().compareTo(before.balanceDue().amount()) > 0) {
                throw new IllegalArgumentException("invalid payment amount or currency");
            }
            if (events.stream().anyMatch(event -> event.scope().equals(scope)
                    && event.paymentEvidence() != null
                    && event.paymentEvidence().paymentRef().equals(evidence.paymentRef()))) {
                throw new IllegalStateException("payment reference already posted");
            }
            appendInvoiceEvent(scope, invoiceId, InvoiceEventType.PAYMENT_RECONCILED,
                    commandId, actorId, evidence.settledAt(), evidence.amount(),
                    evidence.paymentRef(), List.of(), evidence);
            return remember(scope, invoiceId, commandId, fingerprint, project(scope, invoiceId));
        }

        public synchronized InvoiceSnapshot issueCreditNote(Scope scope, String invoiceId,
                                                            long expectedVersion, String commandId,
                                                            String approverId, String creditNoteRef,
                                                            Money amount, Instant at) {
            creditNoteRef = required(creditNoteRef, "creditNoteRef");
            String fingerprint = fingerprint("invoice-credit-note", scope, invoiceId,
                    expectedVersion, commandId, approverId, creditNoteRef, amount, at);
            Optional<InvoiceSnapshot> replay = replayCommand(scope, invoiceId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            InvoiceSnapshot before = project(scope, invoiceId);
            requireVersion(before.version(), expectedVersion);
            if (before.state() == InvoiceState.DRAFT || before.state() == InvoiceState.REVIEW_REQUIRED
                    || before.state() == InvoiceState.VOID) {
                throw new IllegalStateException("invoice cannot receive a credit note in current state");
            }
            if (!before.currency().equals(amount.currency()) || amount.amount().signum() <= 0
                    || before.credited().amount().add(amount.amount()).compareTo(before.total().amount()) > 0) {
                throw new IllegalArgumentException("credit note exceeds invoice total or currency differs");
            }
            if (before.makerId().equals(required(approverId, "approverId"))) {
                throw new IllegalStateException("maker cannot approve the credit note");
            }
            if (before.creditNoteRefs().contains(creditNoteRef)) {
                throw new IllegalStateException("credit note reference already posted");
            }
            appendInvoiceEvent(scope, invoiceId, InvoiceEventType.CREDIT_NOTE_ISSUED,
                    commandId, approverId, at, amount, creditNoteRef, List.of(), null);
            return remember(scope, invoiceId, commandId, fingerprint, project(scope, invoiceId));
        }

        public synchronized InvoiceSnapshot invoice(Scope scope, String invoiceId) {
            return project(scope, invoiceId);
        }

        public synchronized List<InvoiceEvent> events(Scope scope, String invoiceId) {
            return events.stream().filter(event -> event.scope().equals(scope)
                    && event.invoiceId().equals(invoiceId)).toList();
        }

        public synchronized List<OutboxFact> outbox() {
            return List.copyOf(outbox);
        }

        private InvoiceSnapshot transition(Scope scope, String invoiceId, long expectedVersion,
                                           String commandId, String actorId, Instant at,
                                           InvoiceEventType type, Money amount, String reference) {
            String fingerprint = transitionFingerprint(scope, invoiceId, expectedVersion,
                    actorId, at, type, amount, reference);
            Optional<InvoiceSnapshot> replay = replayCommand(scope, invoiceId, commandId, fingerprint);
            if (replay.isPresent()) {
                return replay.get();
            }
            InvoiceSnapshot before = project(scope, invoiceId);
            requireVersion(before.version(), expectedVersion);
            validateTransition(before.state(), type);
            appendInvoiceEvent(scope, invoiceId, type, commandId, actorId, at, amount,
                    reference, List.of(), null);
            return remember(scope, invoiceId, commandId, fingerprint, project(scope, invoiceId));
        }

        private void appendInvoiceEvent(Scope scope, String invoiceId, InvoiceEventType type,
                                        String commandId, String actorId, Instant at,
                                        Money amount, String reference, List<InvoiceLine> lines,
                                        PaymentEvidence paymentEvidence) {
            long nextVersion = version(scope, invoiceId) + 1;
            String eventId = "invoice-event-" + ++eventSequence;
            InvoiceEvent event = new InvoiceEvent(eventId, scope, invoiceId, nextVersion, type,
                    commandId, actorId, at, amount, reference, lines, paymentEvidence);
            events.add(event);
            outbox.add(new OutboxFact(++outboxSequence, scope, "INVOICE", invoiceId,
                    nextVersion, type.name(), eventId, at));
        }

        private Optional<InvoiceSnapshot> replayCommand(Scope scope, String invoiceId,
                                                        String commandId, String fingerprint) {
            String key = scopedKey(scope, invoiceId, required(commandId, "commandId"));
            CommandReceipt<InvoiceSnapshot> receipt = commands.get(key);
            if (receipt == null) {
                return Optional.empty();
            }
            if (!receipt.fingerprint().equals(fingerprint)) {
                throw new IllegalStateException("idempotency key reused with different invoice command");
            }
            return Optional.of(receipt.result());
        }

        private InvoiceSnapshot remember(Scope scope, String invoiceId, String commandId,
                                         String fingerprint, InvoiceSnapshot result) {
            commands.put(scopedKey(scope, invoiceId, commandId), new CommandReceipt<>(fingerprint, result));
            return result;
        }

        private long version(Scope scope, String invoiceId) {
            return events.stream().filter(event -> event.scope().equals(scope)
                            && event.invoiceId().equals(invoiceId))
                    .mapToLong(InvoiceEvent::version).max().orElse(0);
        }

        private static String transitionFingerprint(Scope scope, String invoiceId,
                                                    long expectedVersion, String actorId,
                                                    Instant at, InvoiceEventType type,
                                                    Money amount, String reference) {
            return fingerprint("invoice-transition", scope, invoiceId, expectedVersion,
                    actorId, at, type, amount, reference);
        }

        private InvoiceSnapshot project(Scope scope, String invoiceId) {
            List<InvoiceEvent> invoiceEvents = events.stream().filter(event -> event.scope().equals(scope)
                    && event.invoiceId().equals(invoiceId)).toList();
            if (invoiceEvents.isEmpty()) {
                throw new IllegalStateException("invoice not found in tenant and legal entity scope");
            }
            InvoiceEvent created = invoiceEvents.get(0);
            List<InvoiceLine> lines = created.initialLines();
            String currency = lines.get(0).unitPrice().currency();
            Money total = new Money(currency, lines.stream().map(line -> line.total().amount())
                    .reduce(BigDecimal.ZERO, BigDecimal::add));
            Money paid = new Money(currency, BigDecimal.ZERO);
            Money credited = new Money(currency, BigDecimal.ZERO);
            Set<String> paymentRefs = new LinkedHashSet<>();
            Set<String> creditRefs = new LinkedHashSet<>();
            InvoiceState state = InvoiceState.DRAFT;
            for (InvoiceEvent event : invoiceEvents) {
                switch (event.type()) {
                    case CREATED -> state = InvoiceState.DRAFT;
                    case SUBMITTED_FOR_REVIEW -> state = InvoiceState.REVIEW_REQUIRED;
                    case FINALIZED -> state = InvoiceState.FINALIZED;
                    case ISSUED -> state = InvoiceState.ISSUED;
                    case PAYMENT_RECONCILED -> {
                        paid = paid.add(event.amount());
                        paymentRefs.add(event.reference());
                        state = paid.amount().add(credited.amount()).compareTo(total.amount()) >= 0
                                ? InvoiceState.PAID : InvoiceState.PARTIALLY_PAID;
                    }
                    case CREDIT_NOTE_ISSUED -> {
                        credited = credited.add(event.amount());
                        creditRefs.add(event.reference());
                        if (paid.amount().add(credited.amount()).compareTo(total.amount()) >= 0) {
                            state = InvoiceState.CREDITED;
                        }
                    }
                    case VOIDED -> state = InvoiceState.VOID;
                }
            }
            BigDecimal due = total.amount().subtract(paid.amount()).subtract(credited.amount())
                    .max(BigDecimal.ZERO);
            return new InvoiceSnapshot(scope, invoiceId, state,
                    invoiceEvents.get(invoiceEvents.size() - 1).version(), currency, total,
                    paid, credited, new Money(currency, due), lines, created.actorId(), paymentRefs, creditRefs);
        }

        private static void validateTransition(InvoiceState state, InvoiceEventType type) {
            boolean valid = switch (type) {
                case SUBMITTED_FOR_REVIEW -> state == InvoiceState.DRAFT;
                case FINALIZED -> state == InvoiceState.REVIEW_REQUIRED;
                case ISSUED -> state == InvoiceState.FINALIZED;
                case PAYMENT_RECONCILED -> state == InvoiceState.ISSUED
                        || state == InvoiceState.PARTIALLY_PAID;
                case CREDIT_NOTE_ISSUED -> state == InvoiceState.FINALIZED
                        || state == InvoiceState.ISSUED || state == InvoiceState.PARTIALLY_PAID
                        || state == InvoiceState.PAID || state == InvoiceState.CREDITED;
                case VOIDED -> state == InvoiceState.FINALIZED;
                case CREATED -> false;
            };
            if (!valid) {
                throw new IllegalStateException("invalid invoice transition " + state + " -> " + type);
            }
        }
    }

    public record FxRate(String fromCurrency, String toCurrency, BigDecimal rate,
                         Instant effectiveFrom, Instant effectiveUntil,
                         String sourceRef, EvidenceState evidenceState) {
        public FxRate {
            fromCurrency = required(fromCurrency, "fromCurrency").toUpperCase(Locale.ROOT);
            toCurrency = required(toCurrency, "toCurrency").toUpperCase(Locale.ROOT);
            rate = positive(rate, "rate");
            Objects.requireNonNull(effectiveFrom, "effectiveFrom");
            Objects.requireNonNull(effectiveUntil, "effectiveUntil");
            sourceRef = required(sourceRef, "sourceRef");
            Objects.requireNonNull(evidenceState, "evidenceState");
            if (!effectiveUntil.isAfter(effectiveFrom)) {
                throw new IllegalArgumentException("FX effectiveUntil must follow effectiveFrom");
            }
        }

        public boolean applies(String from, String to, Instant at) {
            return fromCurrency.equals(from) && toCurrency.equals(to)
                    && !at.isBefore(effectiveFrom) && at.isBefore(effectiveUntil)
                    && evidenceState == EvidenceState.RECONCILED;
        }
    }

    public record FinancialFact(String factId, Scope scope, String category, Money amount,
                                Instant periodStart, Instant periodEnd, Instant effectiveAt,
                                String sourceRef, EvidenceState evidenceState,
                                BigDecimal allocationCoverage) {
        public FinancialFact {
            factId = required(factId, "factId");
            Objects.requireNonNull(scope, "scope");
            category = required(category, "category").toUpperCase(Locale.ROOT);
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(periodStart, "periodStart");
            Objects.requireNonNull(periodEnd, "periodEnd");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            sourceRef = required(sourceRef, "sourceRef");
            Objects.requireNonNull(evidenceState, "evidenceState");
            allocationCoverage = exact(allocationCoverage, "allocationCoverage");
            if (!FINANCIAL_CATEGORIES.contains(category)) {
                throw new IllegalArgumentException("unsupported financial fact category");
            }
            if (!periodEnd.isAfter(periodStart) || allocationCoverage.signum() < 0
                    || allocationCoverage.compareTo(BigDecimal.ONE) > 0) {
                throw new IllegalArgumentException("invalid period or allocation coverage");
            }
        }
    }

    public record MetricDefinition(String metricId, String version, String grain,
                                   String denominatorName, int scale,
                                   RoundingMode roundingMode) {
        public MetricDefinition {
            metricId = required(metricId, "metricId");
            version = required(version, "version");
            grain = required(grain, "grain");
            denominatorName = required(denominatorName, "denominatorName");
            Objects.requireNonNull(roundingMode, "roundingMode");
            if (scale < 0 || scale > 18) {
                throw new IllegalArgumentException("metric scale must be between 0 and 18");
            }
        }
    }

    public enum MetricState {
        AVAILABLE,
        UNKNOWN
    }

    public record MetricObservation(Scope scope, MetricDefinition definition,
                                    MetricState state, BigDecimal value,
                                    String reportingCurrency, BigDecimal denominator,
                                    Instant asOf, String reason,
                                    Set<String> sourceRefs) {
        public MetricObservation {
            Objects.requireNonNull(scope, "scope");
            Objects.requireNonNull(definition, "definition");
            Objects.requireNonNull(state, "state");
            reportingCurrency = required(reportingCurrency, "reportingCurrency").toUpperCase(Locale.ROOT);
            Objects.requireNonNull(denominator, "denominator");
            Objects.requireNonNull(asOf, "asOf");
            reason = required(reason, "reason");
            sourceRefs = sourceRefs == null ? Set.of()
                    : Collections.unmodifiableSet(new TreeSet<>(sourceRefs));
            if (state == MetricState.AVAILABLE && value == null) {
                throw new IllegalArgumentException("available metric requires value");
            }
            if (state == MetricState.UNKNOWN && value != null) {
                throw new IllegalArgumentException("unknown metric cannot carry a value");
            }
        }
    }

    /** Exact-decimal margin and COGS computation with explicit unknown outcomes. */
    public static final class MarginAnalyzer {
        public MetricObservation grossMargin(Scope scope, MetricDefinition definition,
                                             List<FinancialFact> revenueFacts,
                                             List<FinancialFact> costFacts,
                                             List<FxRate> fxRates, String reportingCurrency,
                                             BigDecimal denominator, Instant asOf) {
            Objects.requireNonNull(scope, "scope");
            Objects.requireNonNull(definition, "definition");
            Objects.requireNonNull(revenueFacts, "revenueFacts");
            Objects.requireNonNull(costFacts, "costFacts");
            Objects.requireNonNull(fxRates, "fxRates");
            reportingCurrency = required(reportingCurrency, "reportingCurrency").toUpperCase(Locale.ROOT);
            denominator = exact(denominator, "denominator");
            Objects.requireNonNull(asOf, "asOf");
            Set<String> refs = new LinkedHashSet<>();
            if (revenueFacts.isEmpty()) {
                return unknown(scope, definition, reportingCurrency, denominator, asOf,
                        "REVENUE_FACTS_MISSING", refs);
            }
            List<FinancialFact> all = new ArrayList<>(revenueFacts);
            all.addAll(costFacts);
            for (FinancialFact fact : all) {
                if (!fact.scope().equals(scope)) {
                    throw new IllegalArgumentException("cross-tenant or cross-legal-entity fact");
                }
                refs.add(fact.sourceRef());
                if (asOf.isBefore(fact.effectiveAt())) {
                    return unknown(scope, definition, reportingCurrency, denominator, asOf,
                            "SOURCE_FACT_NOT_EFFECTIVE", refs);
                }
                if (fact.evidenceState() != EvidenceState.RECONCILED
                        && fact.evidenceState() != EvidenceState.FINAL) {
                    return unknown(scope, definition, reportingCurrency, denominator, asOf,
                            "UNRECONCILED_SOURCE_FACT", refs);
                }
                if (fact.allocationCoverage().compareTo(BigDecimal.ONE) != 0) {
                    return unknown(scope, definition, reportingCurrency, denominator, asOf,
                            "INCOMPLETE_COST_ALLOCATION", refs);
                }
            }
            if (denominator.signum() <= 0) {
                return unknown(scope, definition, reportingCurrency, denominator, asOf,
                        "DENOMINATOR_NOT_POSITIVE", refs);
            }
            Conversion revenue = convert(revenueFacts, fxRates, reportingCurrency, asOf, refs);
            if (!revenue.known()) {
                return unknown(scope, definition, reportingCurrency, denominator, asOf,
                        revenue.reason(), refs);
            }
            Conversion costs = convert(costFacts, fxRates, reportingCurrency, asOf, refs);
            if (!costs.known()) {
                return unknown(scope, definition, reportingCurrency, denominator, asOf,
                        costs.reason(), refs);
            }
            if (revenue.amount().signum() <= 0) {
                return unknown(scope, definition, reportingCurrency, denominator, asOf,
                        "REVENUE_NOT_POSITIVE", refs);
            }
            BigDecimal value = revenue.amount().subtract(costs.amount())
                    .divide(revenue.amount(), definition.scale(), definition.roundingMode());
            return new MetricObservation(scope, definition, MetricState.AVAILABLE, value,
                    reportingCurrency, denominator, asOf, "CALCULATED_FROM_RECONCILED_FACTS", refs);
        }

        private static Conversion convert(List<FinancialFact> facts, List<FxRate> fxRates,
                                          String reportingCurrency, Instant asOf, Set<String> refs) {
            BigDecimal total = BigDecimal.ZERO;
            for (FinancialFact fact : facts) {
                if (fact.amount().currency().equals(reportingCurrency)) {
                    total = total.add(fact.amount().amount());
                    continue;
                }
                List<FxRate> applicableRates = fxRates.stream().filter(candidate ->
                                candidate.applies(fact.amount().currency(), reportingCurrency, asOf))
                        .toList();
                if (applicableRates.size() != 1) {
                    return new Conversion(false, null, "FX_RATE_MISSING_OR_UNRECONCILED");
                }
                FxRate rate = applicableRates.get(0);
                refs.add(rate.sourceRef());
                total = total.add(fact.amount().amount().multiply(rate.rate()));
            }
            return new Conversion(true, total, "CONVERTED");
        }

        private static MetricObservation unknown(Scope scope, MetricDefinition definition,
                                                 String currency, BigDecimal denominator,
                                                 Instant asOf, String reason, Set<String> refs) {
            return new MetricObservation(scope, definition, MetricState.UNKNOWN, null,
                    currency, denominator, asOf, reason, refs);
        }
    }

    private record Conversion(boolean known, BigDecimal amount, String reason) {
    }

    private record CommandReceipt<T>(String fingerprint, T result) {
    }

    private static String required(String value, String field) {
        if (isBlank(value)) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.trim();
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static BigDecimal exact(BigDecimal value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value;
    }

    private static BigDecimal positive(BigDecimal value, String field) {
        BigDecimal exact = exact(value, field);
        if (exact.signum() <= 0) {
            throw new IllegalArgumentException(field + " must be positive");
        }
        return exact;
    }

    private static void requireVersion(long actual, long expected) {
        if (actual != expected) {
            throw new IllegalStateException("optimistic version mismatch: expected "
                    + expected + " but was " + actual);
        }
    }

    private static String scopedKey(Scope scope, String aggregateId, String commandId) {
        Objects.requireNonNull(scope, "scope");
        return scope.tenantId() + '\u001f' + scope.legalEntityId() + '\u001f'
                + required(aggregateId, "aggregateId") + '\u001f' + required(commandId, "commandId");
    }

    private static String fingerprint(Object... values) {
        StringBuilder canonical = new StringBuilder();
        for (Object value : values) {
            String rendered = value == null ? "<null>" : value.toString();
            canonical.append(rendered.length()).append(':').append(rendered).append('|');
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.toString().getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("JDK lacks SHA-256", impossible);
        }
    }

    private static Map<String, String> requirementBindings() {
        Map<String, String> bindings = new LinkedHashMap<>();
        bind(bindings, "EB04", List.of(
                "tenant/legal-entity-scoped credit wallet aggregate",
                "exact-decimal paid and promotional credit lots",
                "append-only balanced double-entry journal",
                "expiry-aware deterministic lot consumption order",
                "atomic reservation with optimistic concurrency",
                "reservation commit state transition",
                "reservation release state transition",
                "command idempotency with payload collision rejection",
                "replay-derived balance and reservation projections",
                "transactional-outbox-compatible wallet events"));
        bind(bindings, "EB05", List.of(
                "tenant/legal-entity-scoped immutable usage source facts",
                "versioned deterministic usage normalization",
                "source identity and canonical fingerprint deduplication",
                "idempotent ingestion with collision rejection",
                "append-only corrections linked to source facts",
                "exact quantity and explicit unit semantics",
                "event-time billing windows and ingestion timestamps",
                "late-event quarantine instead of silent billing",
                "replay-safe billable quantity projection",
                "transactional-outbox-compatible usage decisions"));
        bind(bindings, "EB09", List.of(
                "append-only invoice lifecycle state machine",
                "exact currency totals and explicit rounding inputs",
                "line-level usage/pricing/service-period lineage",
                "unknown tax fail-closed before finalization",
                "maker-checker invoice finalization",
                "immutable finalized and issued invoice transitions",
                "provider and bank reconciliation before cash posting",
                "partial and full payment state separation",
                "immutable credit notes bounded by invoice total",
                "idempotent invoice commands and outbox events"));
        bind(bindings, "EB13", List.of(
                "tenant/legal-entity-scoped revenue and COGS facts",
                "exact-decimal multi-currency money model",
                "effective-dated reconciled FX conversion",
                "versioned metric definitions",
                "explicit metric grain and denominator",
                "provider, runner, storage and human-review cost categories",
                "allocation coverage blocks incomplete margin",
                "unreconciled inputs produce UNKNOWN",
                "source-linked reproducible margin observations",
                "bounded local analytics without management-report certification"));
        return Collections.unmodifiableMap(new LinkedHashMap<>(bindings));
    }

    private static void bind(Map<String, String> target, String batch, List<String> descriptions) {
        for (int index = 0; index < descriptions.size(); index++) {
            target.put("elmos.pricing-billing.v1/" + batch + "-"
                            + String.format(Locale.ROOT, "%03d", index + 1),
                    descriptions.get(index));
        }
    }
}
