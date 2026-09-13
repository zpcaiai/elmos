import { Injectable, CanActivate, ExecutionContext, UnauthorizedException } from '@nestjs/common';

@Injectable()
export class TenantIsolationGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const tenantId = request.headers['x-tenant-id'];

    if (!tenantId || typeof tenantId !== 'string' || tenantId.trim() === '') {
      throw new UnauthorizedException('Missing or invalid required header: X-Tenant-ID');
    }

    request.tenantId = tenantId.trim();
    return true;
  }
}
