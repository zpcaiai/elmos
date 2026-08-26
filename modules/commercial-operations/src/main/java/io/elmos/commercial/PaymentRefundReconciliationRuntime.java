package io.elmos.commercial;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Currency;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Provider-neutral payment, reconciliation, refund, and dispute reference runtime.
 *
 * <p>This class deliberately stops at canonical commands and posting instructions. Provider DTOs are
 * normalized by an adapter, credentials remain opaque {@link SecretReference}s, and no provider,
 * bank, invoice, or wallet success is manufactured locally. Unknown external outcomes are durable
 * blocking states that require reconciliation evidence.</p>
 */
public final class PaymentRefundReconciliationRuntime {

    private PaymentRefundReconciliationRuntime() {
    }

    public enum PaymentEnvironment {
        SANDBOX,
        PRODUCTION
    }

    public enum ExternalFactStatus {
        CONFIRMED,
        FAILED,
        UNKNOWN
    }

    public enum PaymentStatus {
        CREATED,
        AUTHORIZED,
        PARTIALLY_CAPTURED,
        CAPTURED,
        CANCELLED,
        SETTLED,
        BLOCKED_UNKNOWN,
        FAILED
    }

    public enum PaymentPurpose {
        WALLET_TOP_UP,
        INVOICE_PAYMENT,
        PROJECT_PAYMENT
    }

    public enum PostingTarget {
        INVOICE,
        WALLET
    }

    public enum WebhookStatus {
        ACCEPTED,
        DUPLICATE,
        OUT_OF_ORDER,
        REJECTED
    }

    public enum ProviderEventType {
        AUTHORIZED,
        CAPTURED,
        CANCELLED,
        SETTLED,
        FAILED,
        REFUNDED,
        DISPUTED
    }

    public enum ReconciliationStatus {
        MATCHED,
        SUSPENSE,
        BLOCKED_UNKNOWN
    }

    public enum ReconciliationCaseStatus {
        OPEN,
        RESOLVED
    }

    public enum Responsibility {
        PLATFORM,
        CUSTOMER,
        SHARED,
        PROVIDER,
        UNKNOWN
    }

    public enum CustomerValue {
        NONE,
        PARTIAL,
        FULL,
        UNKNOWN
    }

    public enum ScopeDisposition {
        IN_SCOPE,
        OUT_OF_SCOPE,
        UNKNOWN
    }

    public enum AcceptanceDisposition {
        ACCEPTED,
        PARTIALLY_ACCEPTED,
        REJECTED,
        UNKNOWN
    }

    public enum PaymentConfirmationSource {
        VERIFIED_PROVIDER_WEBHOOK,
        RECONCILED_SETTLEMENT,
        FRONTEND_SUCCESS_PAGE
    }

    public enum RefundEvidenceType {
        QUOTE,
        USAGE,
        LEDGER,
        PAYMENT,
        OUTCOME
    }

    public enum RefundMode {
        NO_CHARGE,
        PROVIDER_REFUND,
        WALLET_CREDIT,
        INVOICE_CREDIT_NOTE
    }

    public enum RefundLeg {
        PROVIDER,
        LEDGER,
        INVOICE
    }

    public enum RefundSagaStatus {
        AWAITING_APPROVAL,
        APPROVED,
        IN_PROGRESS,
        PARTIALLY_COMPLETED,
        BLOCKED_UNKNOWN,
        FAILED,
        COMPLETED,
        CANCELLED
    }

    public enum DisputeResolution {
        ACCEPT_CHARGEBACK,
        CHALLENGE_WITH_EVIDENCE,
        CUSTOMER_CREDIT,
        UNKNOWN
    }

    public enum DisputeStatus {
        OPEN,
        AWAITING_APPROVAL,
        BLOCKED_UNKNOWN,
        RESOLVED
    }

    /** Exact decimal amount with an explicit ISO-4217 currency. Signed amounts are permitted. */
    public record Money(BigDecimal amount, String currency) {
        public Money {
            Objects.requireNonNull(amount, "amount");
            currency = requireText(currency, "currency").toUpperCase(Locale.ROOT);
            Currency unit = Currency.getInstance(currency);
            int fractionDigits = unit.getDefaultFractionDigits();
            if (fractionDigits >= 0) {
                amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
            }
        }

        public static Money of(String amount, String currency) {
            return new Money(new BigDecimal(amount), currency);
        }

        public Money requireNonNegative(String field) {
            if (amount.signum() < 0) {
                throw new IllegalArgumentException(field + " must be non-negative");
            }
            return this;
        }

        public Money requirePositive(String field) {
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException(field + " must be positive");
            }
            return this;
        }

        public Money add(Money other) {
            requireSameCurrency(other);
            return new Money(amount.add(other.amount), currency);
        }

        public Money subtract(Money other) {
            requireSameCurrency(other);
            return new Money(amount.subtract(other.amount), currency);
        }

        public boolean sameValue(Money other) {
            return other != null
                    && currency.equals(other.currency)
                    && amount.compareTo(other.amount) == 0;
        }

        public boolean isGreaterThan(Money other) {
            requireSameCurrency(other);
            return amount.compareTo(other.amount) > 0;
        }

        public boolean isLessThan(Money other) {
            requireSameCurrency(other);
            return amount.compareTo(other.amount) < 0;
        }

        private void requireSameCurrency(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("currency mismatch: " + currency + " != " + other.currency);
            }
        }
    }

    /** Opaque credential locator. A secret value or token is never accepted by this contract. */
    public record SecretReference(
            String providerId,
            PaymentEnvironment environment,
            String uri,
            long rotationVersion) {
        public SecretReference(String providerId, PaymentEnvironment environment, String uri) {
            this(providerId, environment, uri, 1L);
        }

        public SecretReference {
            providerId = requireText(providerId, "providerId");
            Objects.requireNonNull(environment, "environment");
            uri = requireText(uri, "uri");
            if (!uri.startsWith("secret://") || uri.length() <= "secret://".length()) {
                throw new IllegalArgumentException("uri must be an opaque secret:// reference");
            }
            if (uri.indexOf('?') >= 0 || uri.indexOf('#') >= 0 || uri.indexOf('@') >= 0
                    || uri.chars().anyMatch(Character::isWhitespace)) {
                throw new IllegalArgumentException("secret reference must not embed credentials or query data");
            }
            if (rotationVersion <= 0) {
                throw new IllegalArgumentException("rotationVersion must be positive");
            }
        }

        public SecretReference rotateTo(String nextUri, long nextRotationVersion) {
            if (nextRotationVersion <= rotationVersion) {
                throw new IllegalArgumentException("secret rotation version must increase");
            }
            return new SecretReference(providerId, environment, nextUri, nextRotationVersion);
        }
    }

    public record PaymentIntent(
            String paymentId,
            String tenantId,
            String legalEntityId,
            PaymentPurpose purpose,
            String commercialReferenceId,
            Money amount,
            Instant createdAt) {
        public PaymentIntent {
            paymentId = requireText(paymentId, "paymentId");
            tenantId = requireText(tenantId, "tenantId");
            legalEntityId = requireText(legalEntityId, "legalEntityId");
            Objects.requireNonNull(purpose, "purpose");
            commercialReferenceId = requireText(commercialReferenceId, "commercialReferenceId");
            Objects.requireNonNull(amount, "amount").requirePositive("amount");
            Objects.requireNonNull(createdAt, "createdAt");
        }
    }

    public record WebhookEnvelope(
            String providerId,
            PaymentEnvironment environment,
            String eventId,
            String paymentId,
            long sequence,
            Instant occurredAt,
            String payloadDigest,
            String signature) {
        public WebhookEnvelope {
            providerId = requireText(providerId, "providerId");
            Objects.requireNonNull(environment, "environment");
            eventId = requireText(eventId, "eventId");
            paymentId = requireText(paymentId, "paymentId");
            if (sequence <= 0) {
                throw new IllegalArgumentException("sequence must be positive");
            }
            Objects.requireNonNull(occurredAt, "occurredAt");
            payloadDigest = requireText(payloadDigest, "payloadDigest");
            signature = requireText(signature, "signature");
        }
    }

    /** Canonical event; provider-specific DTOs must not cross this boundary. */
    public record ProviderEvent(
            String providerId,
            String eventId,
            String paymentId,
            ProviderEventType type,
            Money amount,
            Instant effectiveAt,
            String providerReference) {
        public ProviderEvent {
            providerId = requireText(providerId, "providerId");
            eventId = requireText(eventId, "eventId");
            paymentId = requireText(paymentId, "paymentId");
            Objects.requireNonNull(type, "type");
            if (amount != null) {
                amount.requireNonNegative("amount");
            }
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            providerReference = requireText(providerReference, "providerReference");
        }
    }

    /**
     * Adapter boundary keeps provider DTO types and signature algorithms outside the canonical model.
     * Implementations receive only an opaque secret reference and must never return credentials.
     */
    public interface PaymentProviderAdapter<D> {
        String providerId();

        PaymentEnvironment environment();

        boolean authenticate(WebhookEnvelope envelope, SecretReference secretReference);

        ProviderEvent normalize(D providerDto);
    }

    public record WebhookDecision(WebhookStatus status, String reason, ProviderEvent event) {
        public WebhookDecision {
            Objects.requireNonNull(status, "status");
            reason = requireText(reason, "reason");
            if (status == WebhookStatus.ACCEPTED && event == null) {
                throw new IllegalArgumentException("accepted webhook requires canonical event");
            }
        }
    }

    public record PaymentConfirmationEvidence(
            PaymentConfirmationSource source,
            ExternalFactStatus externalStatus,
            String evidenceId,
            Instant effectiveAt) {
        public PaymentConfirmationEvidence {
            Objects.requireNonNull(source, "source");
            Objects.requireNonNull(externalStatus, "externalStatus");
            evidenceId = requireText(evidenceId, "evidenceId");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
        }
    }

    /** A browser redirect is presentation only and can never confirm money movement. */
    public static final class PaymentConfirmationPolicy {
        private PaymentConfirmationPolicy() {
        }

        public static PaymentConfirmationEvidence requireAuthoritative(
                PaymentConfirmationEvidence evidence) {
            Objects.requireNonNull(evidence, "evidence");
            if (evidence.source() == PaymentConfirmationSource.FRONTEND_SUCCESS_PAGE) {
                throw new IllegalArgumentException(
                        "frontend success is not authoritative payment evidence");
            }
            if (evidence.externalStatus() != ExternalFactStatus.CONFIRMED) {
                throw new IllegalStateException(
                        "authoritative payment evidence must have a confirmed external result");
            }
            return evidence;
        }
    }

    /** Authenticates, orders, and deduplicates callbacks before exposing a canonical event. */
    public static final class WebhookGateway {
        private final Set<String> allowedProviders;
        private final Duration maximumAge;
        private final Map<String, String> processedDigests = new HashMap<>();
        private final Map<String, Long> lastSequence = new HashMap<>();

        public WebhookGateway(Set<String> allowedProviders, Duration maximumAge) {
            if (allowedProviders == null || allowedProviders.isEmpty()) {
                throw new IllegalArgumentException("allowedProviders must not be empty");
            }
            LinkedHashSet<String> normalized = new LinkedHashSet<>();
            allowedProviders.forEach(value -> normalized.add(requireText(value, "providerId")));
            this.allowedProviders = Collections.unmodifiableSet(normalized);
            this.maximumAge = Objects.requireNonNull(maximumAge, "maximumAge");
            if (maximumAge.isNegative() || maximumAge.isZero()) {
                throw new IllegalArgumentException("maximumAge must be positive");
            }
        }

        public synchronized <D> WebhookDecision accept(
                WebhookEnvelope envelope,
                D providerDto,
                PaymentProviderAdapter<D> adapter,
                SecretReference secretReference,
                Instant receivedAt) {
            Objects.requireNonNull(envelope, "envelope");
            Objects.requireNonNull(adapter, "adapter");
            Objects.requireNonNull(secretReference, "secretReference");
            Objects.requireNonNull(receivedAt, "receivedAt");

            if (!allowedProviders.contains(envelope.providerId())) {
                return rejected("UNKNOWN_PROVIDER");
            }
            if (!envelope.providerId().equals(adapter.providerId())
                    || envelope.environment() != adapter.environment()) {
                return rejected("ADAPTER_BINDING_MISMATCH");
            }
            if (!envelope.providerId().equals(secretReference.providerId())
                    || envelope.environment() != secretReference.environment()) {
                return rejected("SECRET_BINDING_MISMATCH");
            }
            Duration age = Duration.between(envelope.occurredAt(), receivedAt);
            if (age.isNegative() || age.compareTo(maximumAge) > 0) {
                return rejected("STALE_OR_FUTURE_EVENT");
            }
            if (!adapter.authenticate(envelope, secretReference)) {
                return rejected("INVALID_SIGNATURE");
            }

            String eventKey = envelope.providerId() + "/" + envelope.environment() + "/" + envelope.eventId();
            String existingDigest = processedDigests.get(eventKey);
            if (existingDigest != null) {
                if (!existingDigest.equals(envelope.payloadDigest())) {
                    return rejected("IDEMPOTENCY_CONFLICT");
                }
                return new WebhookDecision(WebhookStatus.DUPLICATE, "ALREADY_APPLIED", null);
            }

            String streamKey = envelope.providerId() + "/" + envelope.environment() + "/" + envelope.paymentId();
            long expected = lastSequence.getOrDefault(streamKey, 0L) + 1L;
            if (envelope.sequence() != expected) {
                return new WebhookDecision(WebhookStatus.OUT_OF_ORDER, "EXPECTED_SEQUENCE_" + expected, null);
            }

            ProviderEvent normalized = Objects.requireNonNull(adapter.normalize(providerDto), "normalized event");
            if (!envelope.providerId().equals(normalized.providerId())
                    || !envelope.eventId().equals(normalized.eventId())
                    || !envelope.paymentId().equals(normalized.paymentId())) {
                return rejected("NORMALIZED_EVENT_BINDING_MISMATCH");
            }
            processedDigests.put(eventKey, envelope.payloadDigest());
            lastSequence.put(streamKey, envelope.sequence());
            return new WebhookDecision(WebhookStatus.ACCEPTED, "VERIFIED", normalized);
        }

        private static WebhookDecision rejected(String reason) {
            return new WebhookDecision(WebhookStatus.REJECTED, reason, null);
        }
    }

    public record SettlementFacts(
            String providerId,
            String settlementId,
            Money gross,
            Money fee,
            Money fxAdjustment,
            Money net,
            BigDecimal fxRate,
            Instant effectiveAt,
            ExternalFactStatus providerResult,
            ExternalFactStatus bankResult) {
        public SettlementFacts {
            providerId = requireText(providerId, "providerId");
            settlementId = requireText(settlementId, "settlementId");
            Objects.requireNonNull(gross, "gross").requireNonNegative("gross");
            Objects.requireNonNull(fee, "fee").requireNonNegative("fee");
            Objects.requireNonNull(fxAdjustment, "fxAdjustment");
            Objects.requireNonNull(net, "net").requireNonNegative("net");
            Objects.requireNonNull(fxRate, "fxRate");
            if (fxRate.signum() <= 0) {
                throw new IllegalArgumentException("fxRate must be positive");
            }
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            Objects.requireNonNull(providerResult, "providerResult");
            Objects.requireNonNull(bankResult, "bankResult");
            Money computedNet = gross.subtract(fee).add(fxAdjustment);
            if (!computedNet.sameValue(net)) {
                throw new IllegalArgumentException("net must equal gross - fee + fxAdjustment");
            }
        }
    }

    public record PostingInstruction(
            String instructionId,
            String paymentId,
            String tenantId,
            String legalEntityId,
            PostingTarget target,
            Money amount,
            String commercialReferenceId,
            String sourceEventId,
            Instant effectiveAt) {
        public PostingInstruction {
            instructionId = requireText(instructionId, "instructionId");
            paymentId = requireText(paymentId, "paymentId");
            tenantId = requireText(tenantId, "tenantId");
            legalEntityId = requireText(legalEntityId, "legalEntityId");
            Objects.requireNonNull(target, "target");
            Objects.requireNonNull(amount, "amount").requirePositive("amount");
            commercialReferenceId = requireText(commercialReferenceId, "commercialReferenceId");
            sourceEventId = requireText(sourceEventId, "sourceEventId");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
        }
    }

    /** Exact, idempotent local payment state machine. */
    public static final class PaymentAggregate {
        private final PaymentIntent intent;
        private final Map<String, AppliedPaymentOperation> appliedOperations = new LinkedHashMap<>();
        private final Map<PostingTarget, PostingInstruction> postingInstructions = new EnumMap<>(PostingTarget.class);
        private PaymentStatus status = PaymentStatus.CREATED;
        private Money captured;
        private SettlementFacts settlement;
        private AuditEntry settlementReconciliation;

        public PaymentAggregate(PaymentIntent intent) {
            this.intent = Objects.requireNonNull(intent, "intent");
            this.captured = new Money(BigDecimal.ZERO, intent.amount().currency());
        }

        public synchronized PaymentStatus authorize(String operationId, Money amount) {
            String fingerprint = "AUTHORIZE:" + amount;
            PaymentStatus replay = replay(operationId, fingerprint);
            if (replay != null) {
                return replay;
            }
            requireStatus(PaymentStatus.CREATED);
            if (!intent.amount().sameValue(amount)) {
                throw new IllegalArgumentException("authorization must equal intent amount");
            }
            return record(operationId, fingerprint, PaymentStatus.AUTHORIZED);
        }

        public synchronized PaymentStatus capture(String operationId, Money amount) {
            String fingerprint = "CAPTURE:" + amount;
            PaymentStatus replay = replay(operationId, fingerprint);
            if (replay != null) {
                return replay;
            }
            if (status != PaymentStatus.AUTHORIZED && status != PaymentStatus.PARTIALLY_CAPTURED) {
                throw new IllegalStateException("capture requires AUTHORIZED or PARTIALLY_CAPTURED");
            }
            Objects.requireNonNull(amount, "amount").requirePositive("capture amount");
            Money next = captured.add(amount);
            if (next.isGreaterThan(intent.amount())) {
                throw new IllegalArgumentException("capture exceeds authorized amount");
            }
            captured = next;
            return record(operationId, fingerprint,
                    captured.sameValue(intent.amount()) ? PaymentStatus.CAPTURED : PaymentStatus.PARTIALLY_CAPTURED);
        }

        public synchronized PaymentStatus cancel(String operationId) {
            PaymentStatus replay = replay(operationId, "CANCEL");
            if (replay != null) {
                return replay;
            }
            requireStatus(PaymentStatus.AUTHORIZED);
            return record(operationId, "CANCEL", PaymentStatus.CANCELLED);
        }

        public synchronized PaymentStatus fail(String operationId) {
            PaymentStatus replay = replay(operationId, "FAIL");
            if (replay != null) {
                return replay;
            }
            if (status == PaymentStatus.SETTLED || status == PaymentStatus.CANCELLED) {
                throw new IllegalStateException("terminal payment cannot fail");
            }
            return record(operationId, "FAIL", PaymentStatus.FAILED);
        }

        public synchronized PaymentStatus settle(String operationId, SettlementFacts facts) {
            String fingerprint = "SETTLE:" + facts;
            PaymentStatus replay = replay(operationId, fingerprint);
            if (replay != null) {
                return replay;
            }
            if (status != PaymentStatus.CAPTURED && status != PaymentStatus.PARTIALLY_CAPTURED) {
                throw new IllegalStateException("settlement requires captured value");
            }
            Objects.requireNonNull(facts, "facts");
            if (!facts.gross().sameValue(captured)) {
                throw new IllegalArgumentException("settlement gross must equal captured amount");
            }
            settlement = facts;
            if (facts.providerResult() == ExternalFactStatus.UNKNOWN
                    || facts.bankResult() == ExternalFactStatus.UNKNOWN) {
                return record(operationId, fingerprint, PaymentStatus.BLOCKED_UNKNOWN);
            }
            if (facts.providerResult() != ExternalFactStatus.CONFIRMED
                    || facts.bankResult() != ExternalFactStatus.CONFIRMED) {
                return record(operationId, fingerprint, PaymentStatus.FAILED);
            }
            return record(operationId, fingerprint, PaymentStatus.SETTLED);
        }

        /** Unknown settlement facts may advance only through an independently evidenced reconciliation. */
        public synchronized PaymentStatus reconcileSettlement(
                String operationId,
                SettlementFacts reconciledFacts,
                String independentActor,
                String evidenceId,
                Instant reconciledAt) {
            String fingerprint = "RECONCILE_SETTLEMENT:" + reconciledFacts + ":" + evidenceId;
            PaymentStatus replay = replay(operationId, fingerprint);
            if (replay != null) {
                return replay;
            }
            if (status != PaymentStatus.BLOCKED_UNKNOWN || settlement == null) {
                throw new IllegalStateException("payment has no unknown settlement to reconcile");
            }
            Objects.requireNonNull(reconciledFacts, "reconciledFacts");
            if (!sameSettlementIdentity(settlement, reconciledFacts)) {
                throw new IllegalArgumentException("reconciled settlement changed immutable financial facts");
            }
            if (reconciledFacts.providerResult() == ExternalFactStatus.UNKNOWN
                    || reconciledFacts.bankResult() == ExternalFactStatus.UNKNOWN) {
                throw new IllegalStateException("reconciliation must produce known provider and bank results");
            }
            independentActor = requireText(independentActor, "independentActor");
            evidenceId = requireText(evidenceId, "evidenceId");
            Objects.requireNonNull(reconciledAt, "reconciledAt");
            settlement = reconciledFacts;
            PaymentStatus reconciledStatus = reconciledFacts.providerResult() == ExternalFactStatus.CONFIRMED
                            && reconciledFacts.bankResult() == ExternalFactStatus.CONFIRMED
                    ? PaymentStatus.SETTLED
                    : PaymentStatus.FAILED;
            settlementReconciliation = new AuditEntry(
                    1L,
                    intent.paymentId(),
                    "SETTLEMENT_RECONCILED_" + reconciledStatus,
                    independentActor,
                    evidenceId,
                    reconciledAt);
            return record(operationId, fingerprint, reconciledStatus);
        }

        /** Emits, but does not execute, an exactly-once instruction for the authoritative invoice/wallet system. */
        public synchronized PostingInstruction postingInstruction(
                PostingTarget target,
                String sourceEventId,
                Instant effectiveAt) {
            if (status != PaymentStatus.SETTLED) {
                throw new IllegalStateException("posting requires reconciled settlement");
            }
            Objects.requireNonNull(target, "target");
            PostingTarget expectedTarget = intent.purpose() == PaymentPurpose.WALLET_TOP_UP
                    ? PostingTarget.WALLET
                    : PostingTarget.INVOICE;
            if (target != expectedTarget) {
                throw new IllegalArgumentException(
                        "posting target " + target + " conflicts with payment purpose " + intent.purpose());
            }
            sourceEventId = requireText(sourceEventId, "sourceEventId");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            PostingInstruction existing = postingInstructions.get(target);
            if (existing != null) {
                if (!existing.sourceEventId().equals(sourceEventId) || !existing.effectiveAt().equals(effectiveAt)) {
                    throw new IllegalArgumentException("posting instruction idempotency conflict");
                }
                return existing;
            }
            PostingInstruction created = new PostingInstruction(
                    intent.paymentId() + ":" + target.name(),
                    intent.paymentId(),
                    intent.tenantId(),
                    intent.legalEntityId(),
                    target,
                    captured,
                    intent.commercialReferenceId(),
                    sourceEventId,
                    effectiveAt);
            postingInstructions.put(target, created);
            return created;
        }

        public PaymentIntent intent() {
            return intent;
        }

        public synchronized PaymentStatus status() {
            return status;
        }

        public synchronized Money captured() {
            return captured;
        }

        public synchronized SettlementFacts settlement() {
            return settlement;
        }

        public synchronized AuditEntry settlementReconciliation() {
            return settlementReconciliation;
        }

        public synchronized List<PostingInstruction> postingInstructions() {
            return List.copyOf(postingInstructions.values());
        }

        private PaymentStatus replay(String operationId, String fingerprint) {
            AppliedPaymentOperation applied = appliedOperations.get(requireText(operationId, "operationId"));
            if (applied == null) {
                return null;
            }
            if (!applied.fingerprint().equals(fingerprint)) {
                throw new IllegalArgumentException("payment operation idempotency conflict");
            }
            return applied.status();
        }

        private PaymentStatus record(String operationId, String fingerprint, PaymentStatus nextStatus) {
            status = nextStatus;
            appliedOperations.put(operationId, new AppliedPaymentOperation(fingerprint, nextStatus));
            return nextStatus;
        }

        private record AppliedPaymentOperation(String fingerprint, PaymentStatus status) {
        }

        private void requireStatus(PaymentStatus expected) {
            if (status != expected) {
                throw new IllegalStateException("expected " + expected + " but was " + status);
            }
        }

        private static boolean sameSettlementIdentity(SettlementFacts first, SettlementFacts second) {
            return first.providerId().equals(second.providerId())
                    && first.settlementId().equals(second.settlementId())
                    && first.gross().sameValue(second.gross())
                    && first.fee().sameValue(second.fee())
                    && first.fxAdjustment().sameValue(second.fxAdjustment())
                    && first.net().sameValue(second.net())
                    && first.fxRate().compareTo(second.fxRate()) == 0
                    && first.effectiveAt().equals(second.effectiveAt());
        }
    }

    public record ReconciliationInput(
            String reconciliationId,
            String tenantId,
            String legalEntityId,
            String paymentId,
            Money providerPayment,
            Money invoiceApplication,
            Money ledgerPosting,
            SettlementFacts settlement,
            Money bankDeposit,
            Instant asOf) {
        public ReconciliationInput {
            reconciliationId = requireText(reconciliationId, "reconciliationId");
            tenantId = requireText(tenantId, "tenantId");
            legalEntityId = requireText(legalEntityId, "legalEntityId");
            paymentId = requireText(paymentId, "paymentId");
            Objects.requireNonNull(providerPayment, "providerPayment").requireNonNegative("providerPayment");
            Objects.requireNonNull(invoiceApplication, "invoiceApplication").requireNonNegative("invoiceApplication");
            Objects.requireNonNull(ledgerPosting, "ledgerPosting").requireNonNegative("ledgerPosting");
            Objects.requireNonNull(settlement, "settlement");
            Objects.requireNonNull(bankDeposit, "bankDeposit").requireNonNegative("bankDeposit");
            Objects.requireNonNull(asOf, "asOf");
        }
    }

    public record ReconciliationCase(
            String caseId,
            ReconciliationCaseStatus status,
            String owner,
            String reason,
            ReconciliationInput input,
            List<String> evidenceIds,
            Instant openedAt,
            Instant resolvedAt) {
        public ReconciliationCase {
            caseId = requireText(caseId, "caseId");
            Objects.requireNonNull(status, "status");
            owner = requireText(owner, "owner");
            reason = requireText(reason, "reason");
            Objects.requireNonNull(input, "input");
            evidenceIds = immutableEvidence(evidenceIds, "evidenceIds");
            Objects.requireNonNull(openedAt, "openedAt");
            if (status == ReconciliationCaseStatus.RESOLVED && resolvedAt == null) {
                throw new IllegalArgumentException("resolved case requires resolvedAt");
            }
        }
    }

    public record ReconciliationDecision(
            ReconciliationStatus status,
            String reason,
            ReconciliationCase workItem) {
        public ReconciliationDecision {
            Objects.requireNonNull(status, "status");
            reason = requireText(reason, "reason");
            if (status != ReconciliationStatus.MATCHED && workItem == null) {
                throw new IllegalArgumentException("non-matching result requires suspense work item");
            }
        }
    }

    /** Four-way provider/invoice/ledger/settlement reconciliation plus independent bank confirmation. */
    public static final class ReconciliationEngine {
        private final Map<String, ReconciliationInput> submissions = new LinkedHashMap<>();
        private final Map<String, ReconciliationDecision> decisions = new LinkedHashMap<>();
        private final Map<String, ReconciliationCase> workQueue = new LinkedHashMap<>();

        public synchronized ReconciliationDecision reconcile(
                ReconciliationInput input,
                String owner,
                List<String> evidenceIds) {
            Objects.requireNonNull(input, "input");
            ReconciliationInput prior = submissions.get(input.reconciliationId());
            if (prior != null) {
                if (!prior.equals(input)) {
                    throw new IllegalArgumentException("reconciliation idempotency conflict");
                }
                return decisions.get(input.reconciliationId());
            }
            owner = requireText(owner, "owner");
            List<String> evidence = immutableEvidence(evidenceIds, "evidenceIds");

            ReconciliationStatus status;
            String reason;
            SettlementFacts settlement = input.settlement();
            if (settlement.providerResult() == ExternalFactStatus.UNKNOWN
                    || settlement.bankResult() == ExternalFactStatus.UNKNOWN) {
                status = ReconciliationStatus.BLOCKED_UNKNOWN;
                reason = "UNKNOWN_PROVIDER_OR_BANK_RESULT";
            } else if (settlement.providerResult() != ExternalFactStatus.CONFIRMED
                    || settlement.bankResult() != ExternalFactStatus.CONFIRMED) {
                status = ReconciliationStatus.SUSPENSE;
                reason = "FAILED_EXTERNAL_FACT";
            } else if (!input.providerPayment().sameValue(input.invoiceApplication())
                    || !input.providerPayment().sameValue(input.ledgerPosting())
                    || !input.providerPayment().sameValue(settlement.gross())
                    || !settlement.net().sameValue(input.bankDeposit())) {
                status = ReconciliationStatus.SUSPENSE;
                reason = "FOUR_WAY_OR_BANK_DIFFERENCE";
            } else {
                status = ReconciliationStatus.MATCHED;
                reason = "EXACT_MATCH";
            }

            ReconciliationCase workItem = null;
            if (status != ReconciliationStatus.MATCHED) {
                workItem = new ReconciliationCase(
                        "recon-case:" + input.reconciliationId(),
                        ReconciliationCaseStatus.OPEN,
                        owner,
                        reason,
                        input,
                        evidence,
                        input.asOf(),
                        null);
                workQueue.put(workItem.caseId(), workItem);
            }
            ReconciliationDecision decision = new ReconciliationDecision(status, reason, workItem);
            submissions.put(input.reconciliationId(), input);
            decisions.put(input.reconciliationId(), decision);
            return decision;
        }

        public synchronized ReconciliationCase resolve(
                String caseId,
                ReconciliationInput correctedInput,
                String checker,
                List<String> evidenceIds,
                Instant resolvedAt) {
            ReconciliationCase existing = requireOpenCase(caseId);
            checker = requireText(checker, "checker");
            List<String> evidence = immutableEvidence(evidenceIds, "evidenceIds");
            Objects.requireNonNull(correctedInput, "correctedInput");
            if (!existing.input().tenantId().equals(correctedInput.tenantId())
                    || !existing.input().legalEntityId().equals(correctedInput.legalEntityId())
                    || !existing.input().paymentId().equals(correctedInput.paymentId())) {
                throw new IllegalArgumentException("corrected facts must retain tenant/legal-entity/payment binding");
            }
            if (!factsMatch(correctedInput)) {
                throw new IllegalStateException("case cannot resolve until all external and four-way facts match");
            }
            ReconciliationCase resolved = new ReconciliationCase(
                    existing.caseId(),
                    ReconciliationCaseStatus.RESOLVED,
                    checker,
                    "RECONCILED_WITH_EVIDENCE",
                    correctedInput,
                    evidence,
                    existing.openedAt(),
                    Objects.requireNonNull(resolvedAt, "resolvedAt"));
            workQueue.put(caseId, resolved);
            return resolved;
        }

        public synchronized List<ReconciliationCase> openWorkQueue() {
            return workQueue.values().stream()
                    .filter(item -> item.status() == ReconciliationCaseStatus.OPEN)
                    .toList();
        }

        private ReconciliationCase requireOpenCase(String caseId) {
            ReconciliationCase existing = workQueue.get(requireText(caseId, "caseId"));
            if (existing == null || existing.status() != ReconciliationCaseStatus.OPEN) {
                throw new IllegalStateException("open reconciliation case not found");
            }
            return existing;
        }

        private static boolean factsMatch(ReconciliationInput input) {
            SettlementFacts settlement = input.settlement();
            return settlement.providerResult() == ExternalFactStatus.CONFIRMED
                    && settlement.bankResult() == ExternalFactStatus.CONFIRMED
                    && input.providerPayment().sameValue(input.invoiceApplication())
                    && input.providerPayment().sameValue(input.ledgerPosting())
                    && input.providerPayment().sameValue(settlement.gross())
                    && settlement.net().sameValue(input.bankDeposit());
        }
    }

    public record RefundEvidenceLink(
            RefundEvidenceType type,
            String referenceId,
            String contentSha256) {
        public RefundEvidenceLink {
            Objects.requireNonNull(type, "type");
            referenceId = requireText(referenceId, "referenceId");
            contentSha256 = requireText(contentSha256, "contentSha256").toLowerCase(Locale.ROOT);
            if (!contentSha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("contentSha256 must contain exactly 64 hexadecimal characters");
            }
        }
    }

    /** Typed, digest-bound links to every source fact required for a refund decision. */
    public record RefundEvidenceBundle(String bundleSha256, List<RefundEvidenceLink> links) {
        public RefundEvidenceBundle {
            bundleSha256 = requireText(bundleSha256, "bundleSha256").toLowerCase(Locale.ROOT);
            if (!bundleSha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("bundleSha256 must contain exactly 64 hexadecimal characters");
            }
            if (links == null || links.isEmpty()) {
                throw new IllegalArgumentException("refund evidence links must not be empty");
            }
            EnumSet<RefundEvidenceType> seen = EnumSet.noneOf(RefundEvidenceType.class);
            List<RefundEvidenceLink> copy = new ArrayList<>();
            for (RefundEvidenceLink link : links) {
                Objects.requireNonNull(link, "refund evidence link");
                if (!seen.add(link.type())) {
                    throw new IllegalArgumentException("refund evidence type must be unique: " + link.type());
                }
                copy.add(link);
            }
            if (!seen.equals(EnumSet.allOf(RefundEvidenceType.class))) {
                throw new IllegalArgumentException(
                        "refund evidence must link quote, usage, ledger, payment, and outcome");
            }
            links = List.copyOf(copy);
        }

        public RefundEvidenceLink link(RefundEvidenceType type) {
            Objects.requireNonNull(type, "type");
            return links.stream()
                    .filter(link -> link.type() == type)
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException("required refund evidence link is missing: " + type));
        }
    }

    public record RepairChargeRequest(
            String quoteId,
            String taskId,
            Money taskBudget,
            Money chargedToDate,
            Money proposedIncrement,
            boolean normalModelSelfRepair,
            RefundEvidenceLink quoteEvidence) {
        public RepairChargeRequest {
            quoteId = requireText(quoteId, "quoteId");
            taskId = requireText(taskId, "taskId");
            Objects.requireNonNull(taskBudget, "taskBudget").requireNonNegative("taskBudget");
            Objects.requireNonNull(chargedToDate, "chargedToDate").requireNonNegative("chargedToDate");
            Objects.requireNonNull(proposedIncrement, "proposedIncrement").requireNonNegative("proposedIncrement");
            Objects.requireNonNull(quoteEvidence, "quoteEvidence");
            if (!taskBudget.currency().equals(chargedToDate.currency())
                    || !taskBudget.currency().equals(proposedIncrement.currency())) {
                throw new IllegalArgumentException("repair charge money must use the task budget currency");
            }
            if (quoteEvidence.type() != RefundEvidenceType.QUOTE
                    || !quoteEvidence.referenceId().equals(quoteId)) {
                throw new IllegalArgumentException("repair charge must bind the original quote evidence");
            }
            if (chargedToDate.isGreaterThan(taskBudget)) {
                throw new IllegalArgumentException("chargedToDate already exceeds task budget");
            }
        }
    }

    public record RepairChargeDecision(
            boolean authorized,
            Money customerChargeIncrement,
            Money resultingCustomerCharge,
            String reason) {
        public RepairChargeDecision {
            Objects.requireNonNull(customerChargeIncrement, "customerChargeIncrement")
                    .requireNonNegative("customerChargeIncrement");
            Objects.requireNonNull(resultingCustomerCharge, "resultingCustomerCharge")
                    .requireNonNegative("resultingCustomerCharge");
            reason = requireText(reason, "reason");
        }
    }

    /** Normal model self-repair is included in the authorized task budget and adds no customer charge. */
    public static final class RepairChargeGuard {
        private RepairChargeGuard() {
        }

        public static RepairChargeDecision authorize(RepairChargeRequest request) {
            Objects.requireNonNull(request, "request");
            Money zero = new Money(BigDecimal.ZERO, request.taskBudget().currency());
            if (request.normalModelSelfRepair()) {
                return new RepairChargeDecision(
                        true,
                        zero,
                        request.chargedToDate(),
                        "NORMAL_MODEL_SELF_REPAIR_INCLUDED_IN_TASK_BUDGET");
            }
            Money proposedTotal = request.chargedToDate().add(request.proposedIncrement());
            if (proposedTotal.isGreaterThan(request.taskBudget())) {
                return new RepairChargeDecision(
                        false,
                        zero,
                        request.chargedToDate(),
                        "BUDGET_EXCEEDED_REQUIRES_NEW_QUOTE");
            }
            return new RepairChargeDecision(
                    true,
                    request.proposedIncrement(),
                    proposedTotal,
                    "WITHIN_AUTHORIZED_TASK_BUDGET");
        }
    }

    public record RefundAssessment(
            Responsibility responsibility,
            CustomerValue customerValue,
            ScopeDisposition scopeDisposition,
            AcceptanceDisposition acceptanceDisposition,
            Money capturedAmount,
            Money deliveredValue,
            Money contractualCeiling,
            RefundEvidenceBundle evidence) {
        public RefundAssessment {
            Objects.requireNonNull(responsibility, "responsibility");
            Objects.requireNonNull(customerValue, "customerValue");
            Objects.requireNonNull(scopeDisposition, "scopeDisposition");
            Objects.requireNonNull(acceptanceDisposition, "acceptanceDisposition");
            Objects.requireNonNull(capturedAmount, "capturedAmount").requireNonNegative("capturedAmount");
            Objects.requireNonNull(deliveredValue, "deliveredValue").requireNonNegative("deliveredValue");
            Objects.requireNonNull(contractualCeiling, "contractualCeiling").requireNonNegative("contractualCeiling");
            Objects.requireNonNull(evidence, "evidence");
            if (deliveredValue.isGreaterThan(capturedAmount)) {
                throw new IllegalArgumentException("delivered value cannot exceed captured amount");
            }
        }
    }

    public record RefundDecision(
            Money maximumRefund,
            Set<RefundMode> allowedModes,
            RefundMode recommendedMode,
            String evidenceBundleSha256,
            String reason) {
        public RefundDecision {
            Objects.requireNonNull(maximumRefund, "maximumRefund").requireNonNegative("maximumRefund");
            allowedModes = allowedModes == null || allowedModes.isEmpty()
                    ? Set.of()
                    : Collections.unmodifiableSet(EnumSet.copyOf(allowedModes));
            Objects.requireNonNull(recommendedMode, "recommendedMode");
            if (!allowedModes.contains(recommendedMode)) {
                throw new IllegalArgumentException("recommended refund mode must be allowed");
            }
            evidenceBundleSha256 = requireText(evidenceBundleSha256, "evidenceBundleSha256");
            reason = requireText(reason, "reason");
        }
    }

    /** Policy calculation separates responsibility and delivered customer value from refund execution. */
    public static final class RefundPolicy {
        private RefundPolicy() {
        }

        public static RefundDecision decide(RefundAssessment assessment) {
            Objects.requireNonNull(assessment, "assessment");
            if (assessment.responsibility() == Responsibility.UNKNOWN
                    || assessment.customerValue() == CustomerValue.UNKNOWN
                    || assessment.scopeDisposition() == ScopeDisposition.UNKNOWN
                    || assessment.acceptanceDisposition() == AcceptanceDisposition.UNKNOWN) {
                throw new IllegalStateException(
                        "unknown responsibility, value, scope, or acceptance blocks refund decision");
            }
            Money valueBasedCeiling = assessment.capturedAmount().subtract(assessment.deliveredValue());
            Money maximum = valueBasedCeiling.isLessThan(assessment.contractualCeiling())
                    ? valueBasedCeiling
                    : assessment.contractualCeiling();
            if (assessment.responsibility() == Responsibility.CUSTOMER
                    && assessment.customerValue() == CustomerValue.FULL) {
                return new RefundDecision(
                        new Money(BigDecimal.ZERO, maximum.currency()),
                        Set.of(RefundMode.NO_CHARGE),
                        RefundMode.NO_CHARGE,
                        assessment.evidence().bundleSha256(),
                        "CUSTOMER_RECEIVED_FULL_VALUE");
            }
            if (maximum.amount().signum() == 0) {
                return new RefundDecision(
                        maximum,
                        Set.of(RefundMode.NO_CHARGE),
                        RefundMode.NO_CHARGE,
                        assessment.evidence().bundleSha256(),
                        "NO_REFUNDABLE_BASIS");
            }
            Set<RefundMode> modes = assessment.responsibility() == Responsibility.PROVIDER
                    ? EnumSet.of(RefundMode.PROVIDER_REFUND, RefundMode.WALLET_CREDIT)
                    : EnumSet.of(
                            RefundMode.PROVIDER_REFUND,
                            RefundMode.WALLET_CREDIT,
                            RefundMode.INVOICE_CREDIT_NOTE);
            boolean automaticPlatformNoValue = assessment.responsibility() == Responsibility.PLATFORM
                    && assessment.customerValue() == CustomerValue.NONE
                    && assessment.acceptanceDisposition() == AcceptanceDisposition.REJECTED;
            return new RefundDecision(
                    maximum,
                    modes,
                    automaticPlatformNoValue ? RefundMode.PROVIDER_REFUND : RefundMode.WALLET_CREDIT,
                    assessment.evidence().bundleSha256(),
                    automaticPlatformNoValue ? "PLATFORM_NO_VALUE_AUTO_REFUND" : "POLICY_ELIGIBLE");
        }
    }

    public record RefundCommand(
            String refundId,
            String paymentId,
            String tenantId,
            String legalEntityId,
            RefundMode mode,
            Money amount,
            String maker,
            RefundEvidenceBundle evidence,
            Instant requestedAt) {
        public RefundCommand {
            refundId = requireText(refundId, "refundId");
            paymentId = requireText(paymentId, "paymentId");
            tenantId = requireText(tenantId, "tenantId");
            legalEntityId = requireText(legalEntityId, "legalEntityId");
            Objects.requireNonNull(mode, "mode");
            Objects.requireNonNull(amount, "amount").requirePositive("amount");
            maker = requireText(maker, "maker");
            Objects.requireNonNull(evidence, "evidence");
            if (!paymentId.equals(evidence.link(RefundEvidenceType.PAYMENT).referenceId())) {
                throw new IllegalArgumentException("refund evidence must bind the original payment");
            }
            Objects.requireNonNull(requestedAt, "requestedAt");
        }
    }

    public record AuditEntry(
            long sequence,
            String aggregateId,
            String action,
            String actor,
            String evidenceId,
            Instant occurredAt) {
        public AuditEntry {
            if (sequence <= 0) {
                throw new IllegalArgumentException("sequence must be positive");
            }
            aggregateId = requireText(aggregateId, "aggregateId");
            action = requireText(action, "action");
            actor = requireText(actor, "actor");
            evidenceId = requireText(evidenceId, "evidenceId");
            Objects.requireNonNull(occurredAt, "occurredAt");
        }
    }

    public static final class RefundSaga {
        private final RefundCommand command;
        private final Set<RefundLeg> requiredLegs;
        private final EnumMap<RefundLeg, ExternalFactStatus> legResults = new EnumMap<>(RefundLeg.class);
        private final EnumMap<RefundLeg, String> legActors = new EnumMap<>(RefundLeg.class);
        private final List<AuditEntry> audit = new ArrayList<>();
        private RefundSagaStatus status;
        private String checker;

        private RefundSaga(RefundCommand command, boolean approvalRequired) {
            this.command = command;
            this.requiredLegs = switch (command.mode()) {
                case PROVIDER_REFUND -> EnumSet.of(RefundLeg.PROVIDER, RefundLeg.LEDGER);
                case WALLET_CREDIT -> EnumSet.of(RefundLeg.LEDGER);
                case INVOICE_CREDIT_NOTE -> EnumSet.of(RefundLeg.INVOICE, RefundLeg.LEDGER);
                case NO_CHARGE -> throw new IllegalArgumentException("NO_CHARGE does not create a reversal saga");
            };
            this.status = approvalRequired ? RefundSagaStatus.AWAITING_APPROVAL : RefundSagaStatus.APPROVED;
            append(
                    "REFUND_REQUESTED",
                    command.maker(),
                    command.evidence().bundleSha256(),
                    command.requestedAt());
        }

        public RefundCommand command() {
            return command;
        }

        public synchronized RefundSagaStatus status() {
            return status;
        }

        public synchronized String checker() {
            return checker;
        }

        public synchronized Map<RefundLeg, ExternalFactStatus> legResults() {
            return Collections.unmodifiableMap(new EnumMap<>(legResults));
        }

        public synchronized List<AuditEntry> audit() {
            return List.copyOf(audit);
        }

        private void approve(String approvingChecker, String evidenceId, Instant approvedAt) {
            if (status != RefundSagaStatus.AWAITING_APPROVAL) {
                throw new IllegalStateException("refund is not awaiting approval");
            }
            approvingChecker = requireText(approvingChecker, "checker");
            if (command.maker().equals(approvingChecker)) {
                throw new IllegalArgumentException("maker and checker must be different actors");
            }
            checker = approvingChecker;
            status = RefundSagaStatus.APPROVED;
            append("REFUND_APPROVED", approvingChecker, evidenceId, approvedAt);
        }

        private void applyLeg(
                RefundLeg leg,
                ExternalFactStatus result,
                String actor,
                String evidenceId,
                Instant occurredAt,
                boolean reconciliation) {
            Objects.requireNonNull(leg, "leg");
            Objects.requireNonNull(result, "result");
            if (!requiredLegs.contains(leg)) {
                throw new IllegalArgumentException("leg is not required for refund mode");
            }
            if (status == RefundSagaStatus.AWAITING_APPROVAL) {
                throw new IllegalStateException("refund requires checker approval");
            }
            if (status == RefundSagaStatus.COMPLETED || status == RefundSagaStatus.CANCELLED) {
                ExternalFactStatus existing = legResults.get(leg);
                if (existing == result) {
                    return;
                }
                throw new IllegalStateException("terminal refund leg cannot change");
            }
            ExternalFactStatus existing = legResults.get(leg);
            if (existing != null) {
                if (existing == result) {
                    return;
                }
                if (!reconciliation || existing != ExternalFactStatus.UNKNOWN) {
                    throw new IllegalStateException("conflicting leg result requires reconciliation of UNKNOWN");
                }
                if (Objects.equals(legActors.get(leg), actor)) {
                    throw new IllegalStateException("unknown result reconciliation requires an independent actor");
                }
            }
            legResults.put(leg, result);
            legActors.put(leg, requireText(actor, "actor"));
            append(reconciliation ? "REFUND_LEG_RECONCILED" : "REFUND_LEG_RECORDED", actor, evidenceId, occurredAt);
            if (legResults.containsValue(ExternalFactStatus.UNKNOWN)) {
                status = RefundSagaStatus.BLOCKED_UNKNOWN;
            } else if (legResults.containsValue(ExternalFactStatus.FAILED)) {
                status = RefundSagaStatus.FAILED;
            } else if (requiredLegs.stream().allMatch(item -> legResults.get(item) == ExternalFactStatus.CONFIRMED)) {
                status = RefundSagaStatus.COMPLETED;
            } else if (legResults.isEmpty()) {
                status = RefundSagaStatus.APPROVED;
            } else {
                status = RefundSagaStatus.PARTIALLY_COMPLETED;
            }
        }

        private void cancel(String actor, String evidenceId, Instant occurredAt) {
            if (legResults.values().stream().anyMatch(result -> result == ExternalFactStatus.CONFIRMED)) {
                throw new IllegalStateException("refund with a confirmed leg cannot be cancelled");
            }
            if (legResults.values().stream().anyMatch(result -> result == ExternalFactStatus.UNKNOWN)) {
                throw new IllegalStateException("refund with an unknown external result cannot be cancelled");
            }
            if (status == RefundSagaStatus.COMPLETED || status == RefundSagaStatus.CANCELLED) {
                throw new IllegalStateException("terminal refund cannot be cancelled");
            }
            status = RefundSagaStatus.CANCELLED;
            append("REFUND_CANCELLED", actor, evidenceId, occurredAt);
        }

        private void append(String action, String actor, String evidenceId, Instant occurredAt) {
            audit.add(new AuditEntry(audit.size() + 1L, command.refundId(), action, actor, evidenceId, occurredAt));
        }
    }

    /** Enforces cumulative refund ceiling, partial refunds, maker/checker, and independently recoverable legs. */
    public static final class RefundBook {
        private record RefundScope(String tenantId, String legalEntityId, String paymentId) {
            private RefundScope {
                tenantId = requireText(tenantId, "tenantId");
                legalEntityId = requireText(legalEntityId, "legalEntityId");
                paymentId = requireText(paymentId, "paymentId");
            }
        }

        private final Money largeRefundThreshold;
        private final Map<String, RefundSaga> sagas = new LinkedHashMap<>();
        private final Map<RefundScope, Money> reservedByPayment = new HashMap<>();
        private final Map<RefundScope, Money> refundableBasisByPayment = new HashMap<>();

        public RefundBook(Money largeRefundThreshold) {
            this.largeRefundThreshold = Objects.requireNonNull(largeRefundThreshold, "largeRefundThreshold")
                    .requireNonNegative("largeRefundThreshold");
        }

        public synchronized RefundSaga open(RefundCommand command, RefundDecision decision) {
            Objects.requireNonNull(command, "command");
            Objects.requireNonNull(decision, "decision");
            RefundSaga existing = sagas.get(command.refundId());
            if (existing != null) {
                if (!existing.command().equals(command)) {
                    throw new IllegalArgumentException("refund idempotency conflict");
                }
                return existing;
            }
            if (!decision.allowedModes().contains(command.mode()) || command.mode() == RefundMode.NO_CHARGE) {
                throw new IllegalArgumentException("refund mode is not allowed by policy");
            }
            if (!decision.evidenceBundleSha256().equals(command.evidence().bundleSha256())) {
                throw new IllegalArgumentException("refund command evidence differs from policy evidence");
            }
            if (!largeRefundThreshold.currency().equals(command.amount().currency())) {
                throw new IllegalArgumentException("large refund threshold currency mismatch");
            }
            RefundScope scope = new RefundScope(
                    command.tenantId(), command.legalEntityId(), command.paymentId());
            Money boundBasis = refundableBasisByPayment.get(scope);
            if (boundBasis != null && !boundBasis.sameValue(decision.maximumRefund())) {
                throw new IllegalArgumentException(
                        "refundable basis is immutable for the tenant/legal-entity/payment scope");
            }
            Money reserved = reservedByPayment.getOrDefault(
                    scope, new Money(BigDecimal.ZERO, command.amount().currency()));
            Money next = reserved.add(command.amount());
            if (next.isGreaterThan(decision.maximumRefund())) {
                throw new IllegalArgumentException("cumulative refunds exceed refundable basis");
            }
            RefundSaga saga = new RefundSaga(command, command.amount().isGreaterThan(largeRefundThreshold));
            sagas.put(command.refundId(), saga);
            refundableBasisByPayment.putIfAbsent(scope, decision.maximumRefund());
            reservedByPayment.put(scope, next);
            return saga;
        }

        public synchronized RefundSaga approve(
                String refundId,
                String checker,
                String evidenceId,
                Instant approvedAt) {
            RefundSaga saga = requireSaga(refundId);
            saga.approve(checker, evidenceId, approvedAt);
            return saga;
        }

        public synchronized RefundSaga recordLeg(
                String refundId,
                RefundLeg leg,
                ExternalFactStatus result,
                String actor,
                String evidenceId,
                Instant occurredAt) {
            RefundSaga saga = requireSaga(refundId);
            saga.applyLeg(leg, result, actor, evidenceId, occurredAt, false);
            return saga;
        }

        public synchronized RefundSaga reconcileUnknownLeg(
                String refundId,
                RefundLeg leg,
                ExternalFactStatus reconciledResult,
                String independentActor,
                String evidenceId,
                Instant occurredAt) {
            if (reconciledResult == ExternalFactStatus.UNKNOWN) {
                throw new IllegalArgumentException("reconciled result must be known");
            }
            RefundSaga saga = requireSaga(refundId);
            saga.applyLeg(leg, reconciledResult, independentActor, evidenceId, occurredAt, true);
            return saga;
        }

        public synchronized RefundSaga cancel(
                String refundId,
                String actor,
                String evidenceId,
                Instant occurredAt) {
            RefundSaga saga = requireSaga(refundId);
            saga.cancel(actor, evidenceId, occurredAt);
            RefundCommand command = saga.command();
            RefundScope scope = new RefundScope(
                    command.tenantId(), command.legalEntityId(), command.paymentId());
            Money reserved = Objects.requireNonNull(
                    reservedByPayment.get(scope), "cancelled refund must have a reservation");
            Money remaining = reserved.subtract(command.amount());
            if (remaining.amount().signum() == 0) {
                reservedByPayment.remove(scope);
            } else {
                reservedByPayment.put(scope, remaining);
            }
            return saga;
        }

        public synchronized Money reservedForPayment(
                String tenantId,
                String legalEntityId,
                String paymentId,
                String currency) {
            RefundScope scope = new RefundScope(tenantId, legalEntityId, paymentId);
            return reservedByPayment.getOrDefault(scope, new Money(BigDecimal.ZERO, currency));
        }

        private RefundSaga requireSaga(String refundId) {
            RefundSaga saga = sagas.get(requireText(refundId, "refundId"));
            if (saga == null) {
                throw new IllegalArgumentException("refund saga not found");
            }
            return saga;
        }
    }

    public record DisputeCommand(
            String disputeId,
            String paymentId,
            String tenantId,
            String legalEntityId,
            Money amount,
            String providerCaseReference,
            List<String> evidenceIds,
            Instant openedAt) {
        public DisputeCommand {
            disputeId = requireText(disputeId, "disputeId");
            paymentId = requireText(paymentId, "paymentId");
            tenantId = requireText(tenantId, "tenantId");
            legalEntityId = requireText(legalEntityId, "legalEntityId");
            Objects.requireNonNull(amount, "amount").requirePositive("amount");
            providerCaseReference = requireText(providerCaseReference, "providerCaseReference");
            evidenceIds = immutableEvidence(evidenceIds, "evidenceIds");
            Objects.requireNonNull(openedAt, "openedAt");
        }
    }

    public static final class DisputeCase {
        private final DisputeCommand command;
        private final List<AuditEntry> audit = new ArrayList<>();
        private DisputeStatus status = DisputeStatus.OPEN;
        private DisputeResolution proposedResolution;
        private String maker;

        private DisputeCase(DisputeCommand command) {
            this.command = command;
            append("DISPUTE_OPENED", "provider-webhook", command.evidenceIds().get(0), command.openedAt());
        }

        public DisputeCommand command() {
            return command;
        }

        public synchronized DisputeStatus status() {
            return status;
        }

        public synchronized DisputeResolution proposedResolution() {
            return proposedResolution;
        }

        public synchronized List<AuditEntry> audit() {
            return List.copyOf(audit);
        }

        private void propose(
                DisputeResolution resolution,
                String proposingMaker,
                String evidenceId,
                Instant occurredAt) {
            if (status != DisputeStatus.OPEN && status != DisputeStatus.BLOCKED_UNKNOWN) {
                throw new IllegalStateException("dispute is not open for proposal");
            }
            proposedResolution = Objects.requireNonNull(resolution, "resolution");
            maker = requireText(proposingMaker, "maker");
            status = resolution == DisputeResolution.UNKNOWN
                    ? DisputeStatus.BLOCKED_UNKNOWN
                    : DisputeStatus.AWAITING_APPROVAL;
            append("DISPUTE_RESOLUTION_PROPOSED", maker, evidenceId, occurredAt);
        }

        private void approve(String checker, String evidenceId, Instant occurredAt) {
            if (status != DisputeStatus.AWAITING_APPROVAL) {
                throw new IllegalStateException("known dispute resolution is not awaiting approval");
            }
            checker = requireText(checker, "checker");
            if (checker.equals(maker)) {
                throw new IllegalArgumentException("maker and checker must be different actors");
            }
            status = DisputeStatus.RESOLVED;
            append("DISPUTE_RESOLUTION_APPROVED", checker, evidenceId, occurredAt);
        }

        private void append(String action, String actor, String evidenceId, Instant occurredAt) {
            audit.add(new AuditEntry(audit.size() + 1L, command.disputeId(), action, actor, evidenceId, occurredAt));
        }
    }

    public static final class DisputeBook {
        private final Map<String, DisputeCase> cases = new LinkedHashMap<>();

        public synchronized DisputeCase open(DisputeCommand command) {
            Objects.requireNonNull(command, "command");
            DisputeCase existing = cases.get(command.disputeId());
            if (existing != null) {
                if (!existing.command().equals(command)) {
                    throw new IllegalArgumentException("dispute idempotency conflict");
                }
                return existing;
            }
            DisputeCase created = new DisputeCase(command);
            cases.put(command.disputeId(), created);
            return created;
        }

        public synchronized DisputeCase propose(
                String disputeId,
                DisputeResolution resolution,
                String maker,
                String evidenceId,
                Instant occurredAt) {
            DisputeCase dispute = requireCase(disputeId);
            dispute.propose(resolution, maker, evidenceId, occurredAt);
            return dispute;
        }

        public synchronized DisputeCase approve(
                String disputeId,
                String checker,
                String evidenceId,
                Instant occurredAt) {
            DisputeCase dispute = requireCase(disputeId);
            dispute.approve(checker, evidenceId, occurredAt);
            return dispute;
        }

        private DisputeCase requireCase(String disputeId) {
            DisputeCase dispute = cases.get(requireText(disputeId, "disputeId"));
            if (dispute == null) {
                throw new IllegalArgumentException("dispute not found");
            }
            return dispute;
        }
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static List<String> immutableEvidence(List<String> evidenceIds, String field) {
        if (evidenceIds == null || evidenceIds.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be empty");
        }
        LinkedHashSet<String> normalized = new LinkedHashSet<>();
        evidenceIds.forEach(value -> normalized.add(requireText(value, "evidenceId")));
        return List.copyOf(normalized);
    }
}
