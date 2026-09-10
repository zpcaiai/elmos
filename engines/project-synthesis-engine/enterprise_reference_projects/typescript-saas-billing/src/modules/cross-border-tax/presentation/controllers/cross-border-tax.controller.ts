import { Controller, Post, Body } from '@nestjs/common';
import { CrossBorderTaxService } from '../../domain/services/cross-border-tax.service';
import { CrossBorderTaxCalculationResponse } from '../../domain/entities/cross-border-tax.entity';
import { CalculateCrossBorderTaxDto, ValidateTaxIdDto } from '../dtos/cross-border-tax.dto';

@Controller('cross-border-tax')
export class CrossBorderTaxController {
  constructor(private readonly taxService: CrossBorderTaxService) {}

  @Post('calculate')
  public calculateTax(
    @Body() dto: CalculateCrossBorderTaxDto
  ): CrossBorderTaxCalculationResponse {
    return this.taxService.calculateCrossBorderTax(dto);
  }

  @Post('validate-tax-id')
  public validateTaxId(
    @Body() dto: ValidateTaxIdDto
  ): { countryCode: string; valid: boolean } {
    let valid = false;
    const country = dto.countryCode.toUpperCase();

    if (country === 'AU') {
      valid = this.taxService.validateABN(dto.taxRegistrationNumber);
    } else if (country === 'IN') {
      valid = this.taxService.validateGSTIN(dto.taxRegistrationNumber);
    } else if (country === 'GB') {
      valid = /^GB\d{9}$/.test(dto.taxRegistrationNumber.trim().toUpperCase());
    }

    return { countryCode: country, valid };
  }
}
