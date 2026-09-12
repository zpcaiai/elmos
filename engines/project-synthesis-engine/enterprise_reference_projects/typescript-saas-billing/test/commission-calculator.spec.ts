/**
 * Partner & Affiliate Commission Engine Unit Tests
 */

import {
  PartnerAgreement,
  CommissionModelType,
  PartnerStatus,
} from '../src/modules/affiliates/domain/entities/partner-agreement.entity';
import { CommissionCalculatorService } from '../src/modules/affiliates/domain/services/commission-calculator.service';

describe('Partner & Affiliate Commission Engine', () => {
  let calculator: CommissionCalculatorService;

  beforeEach(() => {
    calculator = new CommissionCalculatorService();
  });

  it('should compute flat percentage rev-share accurately for referred customer', () => {
    const agreement = new PartnerAgreement({
      id: 'agr-partner-1',
      partnerId: 'partner-agency-alpha',
      partnerName: 'Alpha Digital Agency',
      modelType: CommissionModelType.FLAT_PERCENTAGE,
      flatRatePercentage: 0.20, // 20%
    });

    agreement.registerReferredCustomer('cust-acme-corp');
    expect(agreement.isCustomerReferred('cust-acme-corp')).toBe(true);

    const commission = calculator.calculateInvoiceCommission(agreement, {
      invoiceId: 'inv-acme-101',
      customerId: 'cust-acme-corp',
      invoiceSubtotal: 1000,
      taxAmount: 82.50, // Tax is excluded from commissionable base
      isFirstPayment: false,
      paymentDate: new Date('2026-03-01'),
    });

    expect(commission.commissionableBase).toBe(1000);
    expect(commission.commissionRate).toBe(0.20);
    expect(commission.revShareAmount).toBe(200);
    expect(commission.bountyAmount).toBe(0);
    expect(commission.totalCommissionEarned).toBe(200);
  });

  it('should award one-time bounty on customer first payment under hybrid model', () => {
    const agreement = new PartnerAgreement({
      id: 'agr-partner-2',
      partnerId: 'partner-consultant-beta',
      partnerName: 'Beta Cloud Consulting',
      modelType: CommissionModelType.HYBRID,
      flatRatePercentage: 0.15, // 15%
      bountyAmount: 500,        // $500 one-time first payment bonus
    });

    agreement.registerReferredCustomer('cust-globex');

    const firstInvoice = calculator.calculateInvoiceCommission(agreement, {
      invoiceId: 'inv-globex-001',
      customerId: 'cust-globex',
      invoiceSubtotal: 2000,
      taxAmount: 160,
      isFirstPayment: true,
      paymentDate: new Date('2026-04-01'),
    });

    // Rev share: 15% of 2000 = $300; Bounty: $500; Total = $800
    expect(firstInvoice.revShareAmount).toBe(300);
    expect(firstInvoice.bountyAmount).toBe(500);
    expect(firstInvoice.totalCommissionEarned).toBe(800);

    // Second invoice: recurring 15% rev share only, no bounty
    const secondInvoice = calculator.calculateInvoiceCommission(agreement, {
      invoiceId: 'inv-globex-002',
      customerId: 'cust-globex',
      invoiceSubtotal: 2000,
      taxAmount: 160,
      isFirstPayment: false,
      paymentDate: new Date('2026-05-01'),
    });

    expect(secondInvoice.revShareAmount).toBe(300);
    expect(secondInvoice.bountyAmount).toBe(0);
    expect(secondInvoice.totalCommissionEarned).toBe(300);
  });

  it('should apply proportional clawback upon customer refund within window', () => {
    const agreement = new PartnerAgreement({
      id: 'agr-partner-3',
      partnerId: 'partner-gamma',
      partnerName: 'Gamma SaaS Affiliates',
      modelType: CommissionModelType.FLAT_PERCENTAGE,
      flatRatePercentage: 0.25,
      clawbackRule: {
        clawbackWindowDays: 60,
        fullClawbackOnRefund: false,
        fullClawbackOnChargeback: true,
      },
    });

    agreement.registerReferredCustomer('cust-wayne-ent');

    calculator.calculateInvoiceCommission(agreement, {
      invoiceId: 'inv-wayne-500',
      customerId: 'cust-wayne-ent',
      invoiceSubtotal: 4000,
      taxAmount: 0,
      isFirstPayment: false,
      paymentDate: new Date(),
    });

    // 50% partial refund after 10 days
    const clawback = calculator.calculateClawback({
      agreement,
      invoiceId: 'inv-wayne-500',
      refundAmount: 2000, // 50% of invoice subtotal
      refundDate: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000),
      isDispute: false,
    });

    expect(clawback).not.toBeNull();
    // Total earned was $1,000 (25% of 4000), 50% refund -> $500 clawback
    expect(clawback!.clawbackAmount).toBe(500);
    expect(clawback!.reason).toBe('REFUND_PROPORTIONAL_CLAWBACK');
  });
});
