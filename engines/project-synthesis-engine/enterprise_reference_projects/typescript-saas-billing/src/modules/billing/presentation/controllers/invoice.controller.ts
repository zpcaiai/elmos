import {
  Controller,
  Get,
  Post,
  Body,
  Param,
  Headers,
  UseGuards,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { TenantIsolationGuard } from '../guards/tenant-isolation.guard';
import { GenerateInvoiceDto, RecordPaymentDto } from '../dtos/invoice.dto';
import {
  InvoiceRepository,
  CustomerRepository,
  SubscriptionRepository,
} from '../../domain/repositories/billing-repository.interface';
import { InvoiceCalculatorService } from '../../domain/services/invoice-calculator.service';

@Controller('api/v1/invoices')
@UseGuards(TenantIsolationGuard)
export class InvoiceController {
  constructor(
    private readonly invoiceRepo: InvoiceRepository,
    private readonly customerRepo: CustomerRepository,
    private readonly subscriptionRepo: SubscriptionRepository,
    private readonly invoiceCalculator: InvoiceCalculatorService
  ) {}

  @Post('generate')
  async generateInvoice(
    @Headers('x-tenant-id') tenantId: string,
    @Body() dto: GenerateInvoiceDto
  ) {
    const customer = await this.customerRepo.findById(tenantId, dto.customerId);
    if (!customer) {
      throw new NotFoundException(`Customer ${dto.customerId} not found`);
    }

    const subscription = await this.subscriptionRepo.findById(tenantId, dto.subscriptionId);
    if (!subscription) {
      throw new NotFoundException(`Subscription ${dto.subscriptionId} not found`);
    }

    const invoiceId = `inv_${Date.now()}`;
    const invoiceNumber = `INV-${tenantId.substring(0, 4).toUpperCase()}-${Date.now()}`;

    const invoice = this.invoiceCalculator.generateBillingCycleInvoice({
      invoiceId,
      invoiceNumber,
      customer,
      subscription,
      periodStart: subscription.currentPeriodStart,
      periodEnd: subscription.currentPeriodEnd,
      taxRatePercent: dto.taxRatePercent ?? 8.25,
    });

    await this.invoiceRepo.save(invoice);
    return { success: true, data: invoice };
  }

  @Get(':id')
  async getInvoice(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') id: string
  ) {
    const invoice = await this.invoiceRepo.findById(tenantId, id);
    if (!invoice) {
      throw new NotFoundException(`Invoice ${id} not found`);
    }
    return { success: true, data: invoice };
  }

  @Post(':id/payments')
  async recordPayment(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') id: string,
    @Body() dto: RecordPaymentDto
  ) {
    const invoice = await this.invoiceRepo.findById(tenantId, id);
    if (!invoice) {
      throw new NotFoundException(`Invoice ${id} not found`);
    }

    invoice.recordPaymentAttempt({
      attemptId: `pay_${Date.now()}`,
      timestamp: new Date(),
      amountCents: dto.amountCents,
      paymentMethodId: dto.paymentMethodId,
      status: 'SUCCESS',
      gatewayTransactionId: dto.gatewayTransactionId ?? `gw_${Date.now()}`,
    });

    await this.invoiceRepo.save(invoice);
    return { success: true, data: invoice };
  }
}
