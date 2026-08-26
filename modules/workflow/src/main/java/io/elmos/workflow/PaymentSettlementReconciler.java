package io.elmos.workflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Pure detail-level reconciliation between an internal settlement statement
 * and an externally observed payment-provider statement.
 *
 * <p>All monetary values are exact minor-unit decimals with explicit currency
 * and half-open accounting period. Unknown provider outcomes, rejected
 * provider outcomes, mismatches, and segregation-of-duties violations are
 * non-final. This class does not call a provider, move funds, close a period,
 * or create production/certification evidence.</p>
 */
public final class PaymentSettlementReconciler {
    public static final int MONEY_SCALE = 6;
    public static final int MONEY_PRECISION = 30;

    public enum ProviderOutcome {
        CONFIRMED,
        REJECTED,
        UNKNOWN
    }

    public enum ReconciliationStatus {
        RECONCILED,
        UNRECONCILED,
        UNKNOWN
    }

    public enum ReasonCode {
        MATCHED,
        RECONCILER_IS_LEDGER_PREPARER,
        RECONCILER_IS_PROVIDER_RECORDER,
        LEDGER_PREPARER_IS_PROVIDER_RECORDER,
        PROVIDER_RESULT_REJECTED,
        PROVIDER_RESULT_UNKNOWN,
        CURRENCY_MISMATCH,
        PERIOD_MISMATCH,
        GROSS_AMOUNT_MISMATCH,
        REFUND_AMOUNT_MISMATCH,
        FEE_AMOUNT_MISMATCH,
        NET_AMOUNT_MISMATCH
    }

    /** Half-open period: {@code [startInclusive, endExclusive)}. */
    public record SettlementPeriod(Instant startInclusive, Instant endExclusive) {
        public SettlementPeriod {
            Objects.requireNonNull(startInclusive, "startInclusive");
            Objects.requireNonNull(endExclusive, "endExclusive");
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException("ELMOS_MTF_SETTLEMENT_PERIOD_INVALID");
            }
        }
    }

    /**
     * Gross, refund, fee, and net detail. Refunds and fees are unsigned
     * deductions; therefore {@code net = gross - refunds - fees} exactly.
     */
    public record SettlementAmounts(
            BigDecimal grossMinor,
            BigDecimal refundMinor,
            BigDecimal feeMinor,
            BigDecimal netMinor
    ) {
        public SettlementAmounts {
            grossMinor = exactNonNegative(grossMinor, "GROSS");
            refundMinor = exactNonNegative(refundMinor, "REFUND");
            feeMinor = exactNonNegative(feeMinor, "FEE");
            netMinor = exact(netMinor, "NET");
            BigDecimal expectedNet = grossMinor.subtract(refundMinor).subtract(feeMinor);
            if (expectedNet.compareTo(netMinor) != 0) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_SETTLEMENT_AMOUNTS_NOT_CONSERVED");
            }
        }
    }

    public record LedgerSettlement(
            String settlementId,
            String currency,
            SettlementPeriod period,
            SettlementAmounts amounts,
            String preparedByActorId
    ) {
        public LedgerSettlement {
            settlementId = requireIdentifier(settlementId, "SETTLEMENT");
            currency = requireCurrency(currency);
            Objects.requireNonNull(period, "period");
            Objects.requireNonNull(amounts, "amounts");
            preparedByActorId = requireIdentifier(
                    preparedByActorId, "LEDGER_PREPARER_ACTOR");
        }
    }

    /**
     * Provider observation. Non-confirmed observations deliberately carry no
     * amounts so callers cannot accidentally treat rejected or unknown values
     * as authoritative financial detail.
     */
    public record ProviderSettlement(
            String providerReference,
            String currency,
            SettlementPeriod period,
            ProviderOutcome outcome,
            SettlementAmounts amounts,
            String recordedByActorId
    ) {
        public ProviderSettlement {
            providerReference = requireIdentifier(providerReference, "PROVIDER_REFERENCE");
            currency = requireCurrency(currency);
            Objects.requireNonNull(period, "period");
            Objects.requireNonNull(outcome, "outcome");
            recordedByActorId = requireIdentifier(
                    recordedByActorId, "PROVIDER_RECORDER_ACTOR");
            if ((outcome == ProviderOutcome.CONFIRMED) != (amounts != null)) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_PROVIDER_SETTLEMENT_DETAIL_INVALID");
            }
        }
    }

    public record ReconciliationRequest(
            String reconciliationId,
            String idempotencyKey,
            LedgerSettlement ledgerSettlement,
            ProviderSettlement providerSettlement,
            String reconciledByActorId
    ) {
        public ReconciliationRequest {
            reconciliationId = requireIdentifier(reconciliationId, "RECONCILIATION");
            idempotencyKey = requireIdentifier(idempotencyKey, "IDEMPOTENCY_KEY");
            Objects.requireNonNull(ledgerSettlement, "ledgerSettlement");
            Objects.requireNonNull(providerSettlement, "providerSettlement");
            reconciledByActorId = requireIdentifier(
                    reconciledByActorId, "RECONCILER_ACTOR");
        }
    }

    /** Ledger minus provider for every exact amount component. */
    public record AmountDelta(
            BigDecimal grossMinor,
            BigDecimal refundMinor,
            BigDecimal feeMinor,
            BigDecimal netMinor
    ) {
        public AmountDelta {
            grossMinor = exact(grossMinor, "GROSS_DELTA");
            refundMinor = exact(refundMinor, "REFUND_DELTA");
            feeMinor = exact(feeMinor, "FEE_DELTA");
            netMinor = exact(netMinor, "NET_DELTA");
        }

        public boolean isZero() {
            return grossMinor.signum() == 0
                    && refundMinor.signum() == 0
                    && feeMinor.signum() == 0
                    && netMinor.signum() == 0;
        }
    }

    public record ReconciliationResult(
            ReconciliationStatus status,
            List<ReasonCode> reasonCodes,
            AmountDelta amountDelta
    ) {
        public ReconciliationResult {
            Objects.requireNonNull(status, "status");
            reasonCodes = List.copyOf(Objects.requireNonNull(reasonCodes, "reasonCodes"));
            if (reasonCodes.isEmpty()) {
                throw new IllegalArgumentException("ELMOS_MTF_RECONCILIATION_REASON_REQUIRED");
            }
            if (status == ReconciliationStatus.RECONCILED
                    && (!reasonCodes.equals(List.of(ReasonCode.MATCHED))
                            || amountDelta == null
                            || !amountDelta.isZero())) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_RECONCILED_RESULT_INVALID");
            }
            if (status != ReconciliationStatus.RECONCILED
                    && reasonCodes.contains(ReasonCode.MATCHED)) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_NONFINAL_RESULT_CANNOT_MATCH");
            }
        }

        /** Only a fully matched result may advance a financial close. */
        public boolean mayFinalizeSettlement() {
            return status == ReconciliationStatus.RECONCILED;
        }
    }

    private PaymentSettlementReconciler() {}

    public static ReconciliationResult reconcile(ReconciliationRequest request) {
        Objects.requireNonNull(request, "request");
        LedgerSettlement ledger = request.ledgerSettlement();
        ProviderSettlement provider = request.providerSettlement();
        List<ReasonCode> reasons = new ArrayList<>();

        addSegregationOfDutiesReasons(request, reasons);

        if (provider.outcome() == ProviderOutcome.UNKNOWN) {
            reasons.add(ReasonCode.PROVIDER_RESULT_UNKNOWN);
        } else if (provider.outcome() == ProviderOutcome.REJECTED) {
            reasons.add(ReasonCode.PROVIDER_RESULT_REJECTED);
        }
        boolean currencyMatches = ledger.currency().equals(provider.currency());
        if (!currencyMatches) {
            reasons.add(ReasonCode.CURRENCY_MISMATCH);
        }
        boolean periodMatches = ledger.period().equals(provider.period());
        if (!periodMatches) {
            reasons.add(ReasonCode.PERIOD_MISMATCH);
        }

        if (provider.outcome() != ProviderOutcome.CONFIRMED) {
            ReconciliationStatus status = provider.outcome() == ProviderOutcome.UNKNOWN
                    ? ReconciliationStatus.UNKNOWN
                    : ReconciliationStatus.UNRECONCILED;
            return new ReconciliationResult(status, reasons, null);
        }

        AmountDelta delta = null;
        if (currencyMatches && periodMatches) {
            delta = difference(ledger.amounts(), provider.amounts());
            if (delta.grossMinor().signum() != 0) {
                reasons.add(ReasonCode.GROSS_AMOUNT_MISMATCH);
            }
            if (delta.refundMinor().signum() != 0) {
                reasons.add(ReasonCode.REFUND_AMOUNT_MISMATCH);
            }
            if (delta.feeMinor().signum() != 0) {
                reasons.add(ReasonCode.FEE_AMOUNT_MISMATCH);
            }
            if (delta.netMinor().signum() != 0) {
                reasons.add(ReasonCode.NET_AMOUNT_MISMATCH);
            }
        }

        if (reasons.isEmpty()) {
            return new ReconciliationResult(
                    ReconciliationStatus.RECONCILED,
                    List.of(ReasonCode.MATCHED),
                    delta);
        }
        return new ReconciliationResult(
                ReconciliationStatus.UNRECONCILED,
                reasons,
                delta);
    }

    private static void addSegregationOfDutiesReasons(
            ReconciliationRequest request,
            List<ReasonCode> reasons
    ) {
        String ledgerPreparer = request.ledgerSettlement().preparedByActorId();
        String providerRecorder = request.providerSettlement().recordedByActorId();
        String reconciler = request.reconciledByActorId();
        if (reconciler.equals(ledgerPreparer)) {
            reasons.add(ReasonCode.RECONCILER_IS_LEDGER_PREPARER);
        }
        if (reconciler.equals(providerRecorder)) {
            reasons.add(ReasonCode.RECONCILER_IS_PROVIDER_RECORDER);
        }
        if (ledgerPreparer.equals(providerRecorder)) {
            reasons.add(ReasonCode.LEDGER_PREPARER_IS_PROVIDER_RECORDER);
        }
    }

    private static AmountDelta difference(
            SettlementAmounts ledger,
            SettlementAmounts provider
    ) {
        return new AmountDelta(
                ledger.grossMinor().subtract(provider.grossMinor()),
                ledger.refundMinor().subtract(provider.refundMinor()),
                ledger.feeMinor().subtract(provider.feeMinor()),
                ledger.netMinor().subtract(provider.netMinor()));
    }

    private static BigDecimal exactNonNegative(BigDecimal value, String field) {
        BigDecimal exact = exact(value, field);
        if (exact.signum() < 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_NEGATIVE");
        }
        return exact;
    }

    private static BigDecimal exact(BigDecimal value, String field) {
        if (value == null) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_REQUIRED");
        }
        try {
            BigDecimal exact = value.setScale(MONEY_SCALE, RoundingMode.UNNECESSARY);
            int integerDigits = Math.max(0, exact.precision() - exact.scale());
            if (exact.precision() > MONEY_PRECISION
                    || integerDigits > MONEY_PRECISION - MONEY_SCALE) {
                throw new ArithmeticException("decimal exceeds numeric(30,6)");
            }
            return exact;
        } catch (ArithmeticException exception) {
            throw new IllegalArgumentException(
                    "ELMOS_MTF_" + field + "_PRECISION_INVALID", exception);
        }
    }

    private static String requireCurrency(String currency) {
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("ELMOS_MTF_SETTLEMENT_CURRENCY_INVALID");
        }
        return currency;
    }

    private static String requireIdentifier(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 160
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]*")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return value;
    }
}
