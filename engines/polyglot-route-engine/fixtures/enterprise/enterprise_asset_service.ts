import { Controller, Get, Post, Body, Param, HttpException, HttpStatus } from '@nestjs/common';

export class Asset {
  constructor(
    public serial: string,
    public status: string,
    public value: number,
  ) {}
}

@Controller('api/v1/assets')
export class EnterpriseAssetController {
  @Get(':serial')
  async getAssetBySerial(@Param('serial') serial: string): Promise<Asset> {
    try {
      if (!serial) {
        throw new Error('Asset serial is invalid');
      }
      return new Asset(serial, 'ACTIVE', 100.0);
    } catch (error: any) {
      throw new HttpException(`Failed to retrieve asset: ${error.message}`, HttpStatus.INTERNAL_SERVER_ERROR);
    }
  }

  @Post()
  async createAsset(@Body() asset: Asset): Promise<Asset> {
    try {
      return new Asset(asset.serial, asset.status, asset.value);
    } catch (error: any) {
      throw new HttpException(`Failed to create asset: ${error.message}`, HttpStatus.INTERNAL_SERVER_ERROR);
    }
  }
}
