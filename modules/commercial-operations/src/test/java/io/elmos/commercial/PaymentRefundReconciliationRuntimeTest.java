package io.elmos.commercial;

import static io.elmos.commercial.PaymentRefundReconciliationRuntime.AcceptanceDisposition;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.CustomerValue;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.DisputeResolution;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.DisputeStatus;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.ExternalFactStatus;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.Money;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.PaymentEnvironment;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.PaymentConfirmationSource;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.PaymentPurpose;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.PaymentStatus;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.PostingTarget;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.ProviderEventType;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.ReconciliationStatus;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.RefundLeg;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.RefundEvidenceType;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.RefundMode;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.RefundSagaStatus;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.Responsibility;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.ScopeDisposition;
import static io.elmos.commercial.PaymentRefundReconciliationRuntime.WebhookStatus;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class PaymentRefundReconciliationRuntimeTest {
    private static final Instant NOW = Instant.parse("2026-08-26T02:00:00Z");

    @Test
    void providerDtoIsNormalizedBehindVerifiedSecretReferenceBoundary() {
        var gateway = new PaymentRefundReconciliationRuntime.WebhookGateway(
                Set.of("provider-a"), Duration.ofMinutes(5));
        var secret = new PaymentRefundReconciliationRuntime.SecretReference(
                "provider-a", PaymentEnvironment.SANDBOX, "secret://payments/provider-a/webhook-v2");
        var envelope = envelope("event-1", 1, NOW.minusSeconds(10), "digest-1", "valid-signature");
        var adapter = new FakeAdapter();

        var accepted = gateway.accept(
                envelope,
                new FakeProviderDto("provider-token-must-not-cross-boundary", "10.00"),
                adapter,
                secret,
                NOW);

        assertEquals(WebhookStatus.ACCEPTED, accepted.status());
        assertEquals(ProviderEventType.CAPTURED, accepted.event().type());
        assertEquals(Money.of("10.00", "USD"), accepted.event().amount());
        assertFalse(accepted.event().toString().contains("provider-token"));
        var rotated = secret.rotateTo("secret://payments/provider-a/webhook-v3", 2L);
        assertEquals(2L, rotated.rotationVersion());
        assertEquals(1L, secret.rotationVersion());
        assertThrows(IllegalArgumentException.class, () -> secret.rotateTo(rotated.uri(), 1L));
        assertThrows(IllegalArgumentException.class, () ->
                new PaymentRefundReconciliationRuntime.SecretReference(
                        "provider-a", PaymentEnvironment.SANDBOX, "literal-token-value"));
    }

    @Test
    void frontendSuccessIsNeverAuthoritativePaymentEvidence() {
        var frontendClaim = new PaymentRefundReconciliationRuntime.PaymentConfirmationEvidence(
                PaymentConfirmationSource.FRONTEND_SUCCESS_PAGE,
                ExternalFactStatus.CONFIRMED,
                "browser/success?payment=payment-1",
                NOW);
        assertThrows(
                IllegalArgumentException.class,
                () -> PaymentRefundReconciliationRuntime.PaymentConfirmationPolicy.requireAuthoritative(
                        frontendClaim));

        var verifiedProviderClaim = new PaymentRefundReconciliationRuntime.PaymentConfirmationEvidence(
                PaymentConfirmationSource.VERIFIED_PROVIDER_WEBHOOK,
                ExternalFactStatus.CONFIRMED,
                "provider-event-1",
                NOW);
        assertSame(
                verifiedProviderClaim,
                PaymentRefundReconciliationRuntime.PaymentConfirmationPolicy.requireAuthoritative(
                        verifiedProviderClaim));
        assertThrows(
                IllegalStateException.class,
                () -> PaymentRefundReconciliationRuntime.PaymentConfirmationPolicy.requireAuthoritative(
                        new PaymentRefundReconciliationRuntime.PaymentConfirmationEvidence(
                                PaymentConfirmationSource.RECONCILED_SETTLEMENT,
                                ExternalFactStatus.UNKNOWN,
                                "settlement-pending",
                                NOW)));
    }

    @Test
    void webhookAuthenticationEnvironmentFreshnessIdempotencyAndOrderingFailClosed() {
        var gateway = new PaymentRefundReconciliationRuntime.WebhookGateway(
                Set.of("provider-a"), Duration.ofMinutes(5));
        var adapter = new FakeAdapter();
        var secret = secret();
        var raw = new FakeProviderDto("opaque", "10.00");
        var first = envelope("event-1", 1, NOW.minusSeconds(5), "digest-1", "valid-signature");

        assertEquals(WebhookStatus.ACCEPTED, gateway.accept(first, raw, adapter, secret, NOW).status());
        assertEquals(WebhookStatus.DUPLICATE, gateway.accept(first, raw, adapter, secret, NOW).status());
        assertEquals(
                "IDEMPOTENCY_CONFLICT",
                gateway.accept(
                                envelope("event-1", 1, NOW.minusSeconds(5), "different-digest", "valid-signature"),
                                raw,
                                adapter,
                                secret,
                                NOW)
                        .reason());
        assertEquals(
                WebhookStatus.OUT_OF_ORDER,
                gateway.accept(
                                envelope("event-3", 3, NOW.minusSeconds(4), "digest-3", "valid-signature"),
                                raw,
                                adapter,
                                secret,
                                NOW)
                        .status());
        assertEquals(
                "INVALID_SIGNATURE",
                gateway.accept(
                                envelope("event-2", 2, NOW.minusSeconds(4), "digest-2", "invalid"),
                                raw,
                                adapter,
                                secret,
                                NOW)
                        .reason());
        assertEquals(
                "STALE_OR_FUTURE_EVENT",
                gateway.accept(
                                envelope("event-2", 2, NOW.minus(Duration.ofHours(1)), "digest-2", "valid-signature"),
                                raw,
                                adapter,
                                secret,
                                NOW)
                        .reason());

        var unknownProvider = new PaymentRefundReconciliationRuntime.WebhookEnvelope(
                "not-registered",
                PaymentEnvironment.SANDBOX,
                "event-x",
                "payment-1",
                1,
                NOW,
                "digest-x",
                "valid-signature");
        assertEquals(
                "UNKNOWN_PROVIDER",
                gateway.accept(unknownProvider, raw, adapter, secret, NOW).reason());
    }

    @Test
    void paymentStateMachineSupportsExactPartialCaptureCancelSettleAndOnceOnlyPostings() {
        var payment = payment("payment-1", "10.00");

        assertEquals(PaymentStatus.AUTHORIZED, payment.authorize("authorize-1", Money.of("10.00", "USD")));
        assertEquals(PaymentStatus.AUTHORIZED, payment.authorize("authorize-1", Money.of("10.00", "USD")));
        assertThrows(IllegalArgumentException.class, () ->
                payment.authorize("authorize-1", Money.of("9.00", "USD")));
        assertEquals(PaymentStatus.PARTIALLY_CAPTURED, payment.capture("capture-1", Money.of("4.00", "USD")));
        assertEquals(PaymentStatus.CAPTURED, payment.capture("capture-2", Money.of("6.00", "USD")));
        assertThrows(IllegalStateException.class, () ->
                payment.capture("capture-3", Money.of("0.01", "USD")));

        var unknownSettlement = settlement(
                "10.00", "1.00", "0.00", "9.00", ExternalFactStatus.CONFIRMED, ExternalFactStatus.UNKNOWN);
        assertEquals(PaymentStatus.BLOCKED_UNKNOWN, payment.settle("settle-unknown", unknownSettlement));
        assertEquals(PaymentStatus.BLOCKED_UNKNOWN, payment.status());
        assertThrows(IllegalStateException.class, () ->
                payment.postingInstruction(PostingTarget.INVOICE, "event-2", NOW));
        assertThrows(IllegalStateException.class, () -> payment.settle("ordinary-retry", unknownSettlement));

        var confirmedSettlement = settlement(
                "10.00", "1.00", "0.00", "9.00", ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED);
        assertEquals(
                PaymentStatus.SETTLED,
                payment.reconcileSettlement(
                        "reconcile-1",
                        confirmedSettlement,
                        "independent-reconciliation-worker",
                        "evidence/settlement-confirmed.json",
                        NOW.plusSeconds(1)));
        assertNotNull(payment.settlementReconciliation());

        var invoice = payment.postingInstruction(PostingTarget.INVOICE, "event-2", NOW);
        assertSame(invoice, payment.postingInstruction(PostingTarget.INVOICE, "event-2", NOW));
        assertThrows(IllegalArgumentException.class, () ->
                payment.postingInstruction(PostingTarget.INVOICE, "different-event", NOW));
        assertThrows(IllegalArgumentException.class, () ->
                payment.postingInstruction(PostingTarget.WALLET, "event-2", NOW));
        assertEquals(1, payment.postingInstructions().size());

        var cancelled = payment("payment-cancelled", "3.00");
        cancelled.authorize("authorize", Money.of("3.00", "USD"));
        assertEquals(PaymentStatus.CANCELLED, cancelled.cancel("cancel"));
        assertThrows(IllegalStateException.class, () -> cancelled.capture("late-capture", Money.of("1.00", "USD")));

        var walletTopUp = payment("payment-wallet", "5.00", PaymentPurpose.WALLET_TOP_UP);
        walletTopUp.authorize("wallet-authorize", Money.of("5.00", "USD"));
        walletTopUp.capture("wallet-capture", Money.of("5.00", "USD"));
        walletTopUp.settle(
                "wallet-settle",
                settlement("5.00", "0.00", "0.00", "5.00",
                        ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED));
        assertEquals(PostingTarget.WALLET,
                walletTopUp.postingInstruction(PostingTarget.WALLET, "wallet-event", NOW).target());
        assertThrows(IllegalArgumentException.class, () ->
                walletTopUp.postingInstruction(PostingTarget.INVOICE, "wallet-event", NOW));
    }

    @Test
    void settlementRequiresExactFeeFxNetCurrencyAndEffectiveDate() {
        var facts = settlement(
                "100.00", "2.50", "1.25", "98.75", ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED);

        assertEquals(new BigDecimal("1.000000"), facts.fxRate());
        assertEquals(NOW, facts.effectiveAt());
        assertEquals(Money.of("98.75", "USD"), facts.net());
        assertThrows(IllegalArgumentException.class, () -> settlement(
                "100.00", "2.50", "1.25", "99.00", ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED));
    }

    @Test
    void fourWayReconciliationMatchesOrCreatesOwnedSuspenseWithoutSilentRepair() {
        var engine = new PaymentRefundReconciliationRuntime.ReconciliationEngine();
        var matched = reconciliation(
                "recon-1",
                "10.00",
                "10.00",
                "10.00",
                settlement("10.00", "1.00", "0.00", "9.00",
                        ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED),
                "9.00");

        assertEquals(
                ReconciliationStatus.MATCHED,
                engine.reconcile(matched, "finance-ops", List.of("evidence/recon-1.csv")).status());
        assertTrue(engine.openWorkQueue().isEmpty());

        var mismatched = reconciliation(
                "recon-2",
                "10.00",
                "8.00",
                "10.00",
                settlement("10.00", "1.00", "0.00", "9.00",
                        ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED),
                "9.00");
        var suspense = engine.reconcile(mismatched, "finance-owner", List.of("evidence/recon-2.csv"));
        assertEquals(ReconciliationStatus.SUSPENSE, suspense.status());
        assertEquals("finance-owner", suspense.workItem().owner());
        assertEquals(1, engine.openWorkQueue().size());

        var corrected = reconciliation(
                "recon-2-correction",
                "10.00",
                "10.00",
                "10.00",
                settlement("10.00", "1.00", "0.00", "9.00",
                        ExternalFactStatus.CONFIRMED, ExternalFactStatus.CONFIRMED),
                "9.00");
        var resolved = engine.resolve(
                suspense.workItem().caseId(), corrected, "independent-checker", List.of("evidence/corrected.csv"), NOW.plusSeconds(60));
        assertEquals(PaymentRefundReconciliationRuntime.ReconciliationCaseStatus.RESOLVED, resolved.status());
        assertTrue(engine.openWorkQueue().isEmpty());
    }

    @Test
    void unknownProviderOrBankResultRemainsBlockedInOwnedSuspense() {
        var engine = new PaymentRefundReconciliationRuntime.ReconciliationEngine();
        var unknown = reconciliation(
                "recon-unknown",
                "10.00",
                "10.00",
                "10.00",
                settlement("10.00", "1.00", "0.00", "9.00",
                        ExternalFactStatus.UNKNOWN, ExternalFactStatus.UNKNOWN),
                "9.00");

        var result = engine.reconcile(unknown, "reconciliation-owner", List.of("evidence/pending-provider.json"));
        assertEquals(ReconciliationStatus.BLOCKED_UNKNOWN, result.status());
        assertNotNull(result.workItem());
        assertThrows(IllegalStateException.class, () -> engine.resolve(
                result.workItem().caseId(), unknown, "checker", List.of("evidence/still-unknown.json"), NOW));
    }

    @Test
    void refundPolicySeparatesResponsibilityValueModesAndEvidence() {
        var evidence = refundEvidence();
        var eligible = new PaymentRefundReconciliationRuntime.RefundAssessment(
                Responsibility.PLATFORM,
                CustomerValue.PARTIAL,
                ScopeDisposition.IN_SCOPE,
                AcceptanceDisposition.PARTIALLY_ACCEPTED,
                Money.of("100.00", "USD"),
                Money.of("25.00", "USD"),
                Money.of("80.00", "USD"),
                evidence);
        var decision = PaymentRefundReconciliationRuntime.RefundPolicy.decide(eligible);

        assertEquals(Money.of("75.00", "USD"), decision.maximumRefund());
        assertTrue(decision.allowedModes().contains(RefundMode.PROVIDER_REFUND));
        assertTrue(decision.allowedModes().contains(RefundMode.INVOICE_CREDIT_NOTE));

        var noRefund = PaymentRefundReconciliationRuntime.RefundPolicy.decide(
                new PaymentRefundReconciliationRuntime.RefundAssessment(
                        Responsibility.CUSTOMER,
                        CustomerValue.FULL,
                        ScopeDisposition.IN_SCOPE,
                        AcceptanceDisposition.ACCEPTED,
                        Money.of("100.00", "USD"),
                        Money.of("100.00", "USD"),
                        Money.of("100.00", "USD"),
                        evidence));
        assertEquals(Money.of("0.00", "USD"), noRefund.maximumRefund());
        assertEquals(Set.of(RefundMode.NO_CHARGE), noRefund.allowedModes());

        assertThrows(IllegalStateException.class, () -> PaymentRefundReconciliationRuntime.RefundPolicy.decide(
                new PaymentRefundReconciliationRuntime.RefundAssessment(
                        Responsibility.UNKNOWN,
                        CustomerValue.UNKNOWN,
                        ScopeDisposition.UNKNOWN,
                        AcceptanceDisposition.UNKNOWN,
                        Money.of("10.00", "USD"),
                        Money.of("0.00", "USD"),
                        Money.of("10.00", "USD"),
                        evidence)));
    }

    @Test
    void normalModelSelfRepairNeverAddsUnboundedCustomerCharges() {
        var quoteEvidence = refundEvidence().links().stream()
                .filter(link -> link.type() == RefundEvidenceType.QUOTE)
                .findFirst()
                .orElseThrow();
        var normalRepair = new PaymentRefundReconciliationRuntime.RepairChargeRequest(
                "quote-1",
                "task-1",
                Money.of("100.00", "USD"),
                Money.of("40.00", "USD"),
                Money.of("60.00", "USD"),
                true,
                quoteEvidence);

        var first = PaymentRefundReconciliationRuntime.RepairChargeGuard.authorize(normalRepair);
        var replay = PaymentRefundReconciliationRuntime.RepairChargeGuard.authorize(normalRepair);
        assertTrue(first.authorized());
        assertEquals(Money.of("0.00", "USD"), first.customerChargeIncrement());
        assertEquals(Money.of("40.00", "USD"), first.resultingCustomerCharge());
        assertEquals(first, replay);

        var overBudgetChange = new PaymentRefundReconciliationRuntime.RepairChargeRequest(
                "quote-1",
                "task-1",
                Money.of("100.00", "USD"),
                Money.of("95.00", "USD"),
                Money.of("10.00", "USD"),
                false,
                quoteEvidence);
        var blocked = PaymentRefundReconciliationRuntime.RepairChargeGuard.authorize(overBudgetChange);
        assertFalse(blocked.authorized());
        assertEquals(Money.of("0.00", "USD"), blocked.customerChargeIncrement());
        assertEquals("BUDGET_EXCEEDED_REQUIRES_NEW_QUOTE", blocked.reason());
    }

    @Test
    void refundEvidenceRequiresTypedQuoteUsageLedgerPaymentAndOutcomeLinks() {
        var evidence = refundEvidence();
        assertEquals(5, evidence.links().size());
        assertEquals(
                Set.of(
                        RefundEvidenceType.QUOTE,
                        RefundEvidenceType.USAGE,
                        RefundEvidenceType.LEDGER,
                        RefundEvidenceType.PAYMENT,
                        RefundEvidenceType.OUTCOME),
                evidence.links().stream().map(PaymentRefundReconciliationRuntime.RefundEvidenceLink::type)
                        .collect(java.util.stream.Collectors.toSet()));

        assertThrows(IllegalArgumentException.class, () ->
                new PaymentRefundReconciliationRuntime.RefundEvidenceBundle(
                        "f".repeat(64),
                        evidence.links().stream()
                                .filter(link -> link.type() != RefundEvidenceType.OUTCOME)
                                .toList()));
        assertThrows(IllegalArgumentException.class, () ->
                new PaymentRefundReconciliationRuntime.RefundCommand(
                        "refund-mismatched-payment",
                        "payment-1",
                        "tenant-1",
                        "legal-us",
                        RefundMode.PROVIDER_REFUND,
                        Money.of("1.00", "USD"),
                        "maker-a",
                        refundEvidence("different-payment"),
                        NOW));
    }

    @Test
    void refundSagaEnforcesCumulativeCeilingMakerCheckerAndIndependentLegRecovery() {
        var assessment = new PaymentRefundReconciliationRuntime.RefundAssessment(
                Responsibility.PLATFORM,
                CustomerValue.NONE,
                ScopeDisposition.IN_SCOPE,
                AcceptanceDisposition.REJECTED,
                Money.of("100.00", "USD"),
                Money.of("0.00", "USD"),
                Money.of("100.00", "USD"),
                refundEvidence());
        var decision = PaymentRefundReconciliationRuntime.RefundPolicy.decide(assessment);
        assertEquals(RefundMode.PROVIDER_REFUND, decision.recommendedMode());
        assertEquals("PLATFORM_NO_VALUE_AUTO_REFUND", decision.reason());
        var book = new PaymentRefundReconciliationRuntime.RefundBook(Money.of("50.00", "USD"));
        var large = refund("refund-1", RefundMode.PROVIDER_REFUND, "60.00", "maker-a");

        var saga = book.open(large, decision);
        assertEquals(RefundSagaStatus.AWAITING_APPROVAL, saga.status());
        assertThrows(IllegalArgumentException.class, () ->
                book.approve("refund-1", "maker-a", "evidence/self-approval.json", NOW.plusSeconds(1)));
        book.approve("refund-1", "checker-b", "evidence/approval.json", NOW.plusSeconds(2));
        assertEquals(RefundSagaStatus.APPROVED, saga.status());

        book.recordLeg(
                "refund-1", RefundLeg.PROVIDER, ExternalFactStatus.UNKNOWN,
                "provider-adapter", "evidence/provider-timeout.json", NOW.plusSeconds(3));
        assertEquals(RefundSagaStatus.BLOCKED_UNKNOWN, saga.status());
        assertThrows(IllegalStateException.class, () -> book.cancel(
                "refund-1", "maker-a", "evidence/cancel-unknown.json", NOW.plusSeconds(4)));
        assertThrows(IllegalStateException.class, () -> book.reconcileUnknownLeg(
                "refund-1", RefundLeg.PROVIDER, ExternalFactStatus.CONFIRMED,
                "provider-adapter", "evidence/self-reconcile.json", NOW.plusSeconds(4)));
        book.reconcileUnknownLeg(
                "refund-1", RefundLeg.PROVIDER, ExternalFactStatus.CONFIRMED,
                "reconciliation-worker", "evidence/provider-confirmed.json", NOW.plusSeconds(5));
        assertEquals(RefundSagaStatus.PARTIALLY_COMPLETED, saga.status());
        book.recordLeg(
                "refund-1", RefundLeg.LEDGER, ExternalFactStatus.CONFIRMED,
                "ledger-worker", "evidence/ledger-reversal.json", NOW.plusSeconds(6));
        assertEquals(RefundSagaStatus.COMPLETED, saga.status());
        assertEquals(5, saga.audit().size());

        var remaining = refund("refund-2", RefundMode.WALLET_CREDIT, "40.00", "maker-c");
        var partial = book.open(remaining, decision);
        book.recordLeg(
                "refund-2", RefundLeg.LEDGER, ExternalFactStatus.CONFIRMED,
                "ledger-worker", "evidence/wallet-credit.json", NOW.plusSeconds(7));
        assertEquals(RefundSagaStatus.COMPLETED, partial.status());
        assertEquals(
                Money.of("100.00", "USD"),
                book.reservedForPayment("tenant-1", "legal-us", "payment-1", "USD"));
        assertThrows(IllegalArgumentException.class, () ->
                book.open(refund("refund-3", RefundMode.WALLET_CREDIT, "0.01", "maker-d"), decision));

        var inflatedBasis = new PaymentRefundReconciliationRuntime.RefundDecision(
                Money.of("101.00", "USD"),
                decision.allowedModes(),
                decision.recommendedMode(),
                decision.evidenceBundleSha256(),
                "TAMPERED_HIGHER_BASIS");
        assertThrows(IllegalArgumentException.class, () ->
                book.open(refund("refund-4", RefundMode.WALLET_CREDIT, "0.01", "maker-e"), inflatedBasis));

        var otherTenant = new PaymentRefundReconciliationRuntime.RefundCommand(
                "refund-tenant-2",
                "payment-1",
                "tenant-2",
                "legal-us",
                RefundMode.WALLET_CREDIT,
                Money.of("1.00", "USD"),
                "maker-f",
                refundEvidence(),
                NOW.plusSeconds(8));
        book.open(otherTenant, decision);
        assertEquals(
                Money.of("1.00", "USD"),
                book.reservedForPayment("tenant-2", "legal-us", "payment-1", "USD"));
        assertEquals(
                Money.of("100.00", "USD"),
                book.reservedForPayment("tenant-1", "legal-us", "payment-1", "USD"));
    }

    @Test
    void disputesAreEvidenceBoundUnknownSafeAndMakerCheckerApproved() {
        var book = new PaymentRefundReconciliationRuntime.DisputeBook();
        var command = new PaymentRefundReconciliationRuntime.DisputeCommand(
                "dispute-1",
                "payment-1",
                "tenant-1",
                "legal-us",
                Money.of("10.00", "USD"),
                "provider-case-9",
                List.of("evidence/provider-dispute.json"),
                NOW);
        var dispute = book.open(command);

        book.propose(
                "dispute-1", DisputeResolution.UNKNOWN, "maker-a",
                "evidence/provider-pending.json", NOW.plusSeconds(1));
        assertEquals(DisputeStatus.BLOCKED_UNKNOWN, dispute.status());
        assertThrows(IllegalStateException.class, () ->
                book.approve("dispute-1", "checker-b", "evidence/no-result.json", NOW.plusSeconds(2)));

        book.propose(
                "dispute-1", DisputeResolution.CHALLENGE_WITH_EVIDENCE, "maker-a",
                "evidence/challenge-pack.json", NOW.plusSeconds(3));
        assertEquals(DisputeStatus.AWAITING_APPROVAL, dispute.status());
        assertThrows(IllegalArgumentException.class, () ->
                book.approve("dispute-1", "maker-a", "evidence/self-approval.json", NOW.plusSeconds(4)));
        book.approve("dispute-1", "checker-b", "evidence/checker-approval.json", NOW.plusSeconds(5));
        assertEquals(DisputeStatus.RESOLVED, dispute.status());
        assertEquals(4, dispute.audit().size());

        var chargebackCommand = new PaymentRefundReconciliationRuntime.DisputeCommand(
                "dispute-chargeback",
                "payment-1",
                "tenant-1",
                "legal-us",
                Money.of("4.00", "USD"),
                "provider-case-chargeback",
                List.of("evidence/provider-chargeback.json"),
                NOW.plusSeconds(6));
        var acceptedChargeback = book.open(chargebackCommand);
        book.propose(
                "dispute-chargeback", DisputeResolution.ACCEPT_CHARGEBACK, "maker-c",
                "evidence/accept-chargeback.json", NOW.plusSeconds(7));
        assertEquals(DisputeResolution.ACCEPT_CHARGEBACK, acceptedChargeback.proposedResolution());
        book.approve(
                "dispute-chargeback", "checker-d",
                "evidence/chargeback-approval.json", NOW.plusSeconds(8));
        assertEquals(DisputeStatus.RESOLVED, acceptedChargeback.status());
    }

    private static PaymentRefundReconciliationRuntime.SecretReference secret() {
        return new PaymentRefundReconciliationRuntime.SecretReference(
                "provider-a", PaymentEnvironment.SANDBOX, "secret://payments/provider-a/webhook-v2");
    }

    private static PaymentRefundReconciliationRuntime.WebhookEnvelope envelope(
            String eventId,
            long sequence,
            Instant occurredAt,
            String digest,
            String signature) {
        return new PaymentRefundReconciliationRuntime.WebhookEnvelope(
                "provider-a",
                PaymentEnvironment.SANDBOX,
                eventId,
                "payment-1",
                sequence,
                occurredAt,
                digest,
                signature);
    }

    private static PaymentRefundReconciliationRuntime.PaymentAggregate payment(String paymentId, String amount) {
        return payment(paymentId, amount, PaymentPurpose.INVOICE_PAYMENT);
    }

    private static PaymentRefundReconciliationRuntime.PaymentAggregate payment(
            String paymentId, String amount, PaymentPurpose purpose) {
        return new PaymentRefundReconciliationRuntime.PaymentAggregate(
                new PaymentRefundReconciliationRuntime.PaymentIntent(
                        paymentId,
                        "tenant-1",
                        "legal-us",
                        purpose,
                        "invoice-1",
                        Money.of(amount, "USD"),
                        NOW.minusSeconds(60)));
    }

    private static PaymentRefundReconciliationRuntime.SettlementFacts settlement(
            String gross,
            String fee,
            String fxAdjustment,
            String net,
            ExternalFactStatus providerResult,
            ExternalFactStatus bankResult) {
        return new PaymentRefundReconciliationRuntime.SettlementFacts(
                "provider-a",
                "settlement-1",
                Money.of(gross, "USD"),
                Money.of(fee, "USD"),
                Money.of(fxAdjustment, "USD"),
                Money.of(net, "USD"),
                new BigDecimal("1.000000"),
                NOW,
                providerResult,
                bankResult);
    }

    private static PaymentRefundReconciliationRuntime.ReconciliationInput reconciliation(
            String reconciliationId,
            String provider,
            String invoice,
            String ledger,
            PaymentRefundReconciliationRuntime.SettlementFacts settlement,
            String bank) {
        return new PaymentRefundReconciliationRuntime.ReconciliationInput(
                reconciliationId,
                "tenant-1",
                "legal-us",
                "payment-1",
                Money.of(provider, "USD"),
                Money.of(invoice, "USD"),
                Money.of(ledger, "USD"),
                settlement,
                Money.of(bank, "USD"),
                NOW);
    }

    private static PaymentRefundReconciliationRuntime.RefundCommand refund(
            String refundId,
            RefundMode mode,
            String amount,
            String maker) {
        return new PaymentRefundReconciliationRuntime.RefundCommand(
                refundId,
                "payment-1",
                "tenant-1",
                "legal-us",
                mode,
                Money.of(amount, "USD"),
                maker,
                refundEvidence(),
                NOW);
    }

    private static PaymentRefundReconciliationRuntime.RefundEvidenceBundle refundEvidence() {
        return refundEvidence("payment-1");
    }

    private static PaymentRefundReconciliationRuntime.RefundEvidenceBundle refundEvidence(String paymentId) {
        return new PaymentRefundReconciliationRuntime.RefundEvidenceBundle(
                "f".repeat(64),
                List.of(
                        new PaymentRefundReconciliationRuntime.RefundEvidenceLink(
                                RefundEvidenceType.QUOTE, "quote-1", "a".repeat(64)),
                        new PaymentRefundReconciliationRuntime.RefundEvidenceLink(
                                RefundEvidenceType.USAGE, "usage-1", "b".repeat(64)),
                        new PaymentRefundReconciliationRuntime.RefundEvidenceLink(
                                RefundEvidenceType.LEDGER, "ledger-entry-1", "c".repeat(64)),
                        new PaymentRefundReconciliationRuntime.RefundEvidenceLink(
                                RefundEvidenceType.PAYMENT, paymentId, "d".repeat(64)),
                        new PaymentRefundReconciliationRuntime.RefundEvidenceLink(
                                RefundEvidenceType.OUTCOME, "outcome-1", "e".repeat(64))));
    }

    private record FakeProviderDto(String privateProviderField, String amount) {
    }

    private static final class FakeAdapter
            implements PaymentRefundReconciliationRuntime.PaymentProviderAdapter<FakeProviderDto> {
        @Override
        public String providerId() {
            return "provider-a";
        }

        @Override
        public PaymentEnvironment environment() {
            return PaymentEnvironment.SANDBOX;
        }

        @Override
        public boolean authenticate(
                PaymentRefundReconciliationRuntime.WebhookEnvelope envelope,
                PaymentRefundReconciliationRuntime.SecretReference secretReference) {
            return "valid-signature".equals(envelope.signature())
                    && secretReference.uri().startsWith("secret://");
        }

        @Override
        public PaymentRefundReconciliationRuntime.ProviderEvent normalize(FakeProviderDto providerDto) {
            return new PaymentRefundReconciliationRuntime.ProviderEvent(
                    "provider-a",
                    "event-1",
                    "payment-1",
                    ProviderEventType.CAPTURED,
                    Money.of(providerDto.amount(), "USD"),
                    NOW,
                    "provider-reference-1");
        }
    }
}
