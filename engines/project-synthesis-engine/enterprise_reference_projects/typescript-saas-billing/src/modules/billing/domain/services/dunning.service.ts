import { InvoiceAggregate, InvoiceStatus } from '../entities/invoice.entity';
import { SubscriptionAggregate, SubscriptionStatus } from '../entities/subscription.entity';
import { CustomerAggregate } from '../entities/customer.entity';

export enum DunningAction {
  RETRY_PAYMENT = 'RETRY_PAYMENT',
  SEND_REMINDER_EMAIL = 'SEND_REMINDER_EMAIL',
  MARK_PAST_DUE = 'MARK_PAST_DUE',
  CANCEL_SUBSCRIPTION = 'CANCEL_SUBSCRIPTION',
  NONE = 'NONE',
}

export interface DunningDecision {
  invoiceId: string;
  attemptNumber: number;
  action: DunningAction;
  nextRetryDate?: Date;
  shouldNotifyCustomer: boolean;
  message: string;
}

export class DunningService {
  /**
   * Evaluates the dunning policy schedule for an unpaid invoice.
   * Schedule:
   * Attempt 1 (Day 1): Retry + Reminder
   * Attempt 2 (Day 3): Retry + Warning
   * Attempt 3 (Day 7): Mark subscription PAST_DUE
   * Attempt 4 (Day 14): Cancel subscription immediately & Mark Uncollectible
   */
  evaluateDunningStep(params: {
    invoice: InvoiceAggregate;
    subscription?: SubscriptionAggregate;
    customer: CustomerAggregate;
    daysSinceFailure: number;
  }): DunningDecision {
    const { invoice, subscription, customer, daysSinceFailure } = params;

    if (invoice.status === InvoiceStatus.PAID || invoice.status === InvoiceStatus.VOID) {
      return {
        invoiceId: invoice.invoiceId,
        attemptNumber: customer.delinquencyCounter,
        action: DunningAction.NONE,
        shouldNotifyCustomer: false,
        message: `Invoice is ${invoice.status}, no dunning needed.`,
      };
    }

    const failureCount = customer.recordPaymentFailure();

    if (daysSinceFailure >= 14 || failureCount >= 4) {
      // Final penalty: Cancel subscription and mark uncollectible
      if (subscription && subscription.status !== SubscriptionStatus.CANCELED) {
        subscription.cancel(true);
      }
      invoice.markUncollectible();

      return {
        invoiceId: invoice.invoiceId,
        attemptNumber: failureCount,
        action: DunningAction.CANCEL_SUBSCRIPTION,
        shouldNotifyCustomer: true,
        message: 'Account canceled due to non-payment after 14 days.',
      };
    }

    if (daysSinceFailure >= 7 || failureCount >= 3) {
      if (subscription) {
        subscription.markPastDue();
      }
      return {
        invoiceId: invoice.invoiceId,
        attemptNumber: failureCount,
        action: DunningAction.MARK_PAST_DUE,
        nextRetryDate: new Date(Date.now() + 7 * 86400000),
        shouldNotifyCustomer: true,
        message: 'Subscription marked PAST_DUE. Grace period expires in 7 days.',
      };
    }

    if (daysSinceFailure >= 3 || failureCount >= 2) {
      return {
        invoiceId: invoice.invoiceId,
        attemptNumber: failureCount,
        action: DunningAction.RETRY_PAYMENT,
        nextRetryDate: new Date(Date.now() + 4 * 86400000),
        shouldNotifyCustomer: true,
        message: 'Payment retry failed. Urgent warning issued to customer.',
      };
    }

    // First failure (Day 1)
    return {
      invoiceId: invoice.invoiceId,
      attemptNumber: failureCount,
      action: DunningAction.RETRY_PAYMENT,
      nextRetryDate: new Date(Date.now() + 2 * 86400000),
      shouldNotifyCustomer: true,
      message: 'Initial payment failure. Automated retry scheduled in 2 days.',
    };
  }
}
