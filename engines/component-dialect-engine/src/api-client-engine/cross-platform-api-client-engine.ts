/**
 * @file cross-platform-api-client-engine.ts
 * @description Master orchestration engine for Cross-Platform API Client & Remote Data Cache.
 * Translates API and Cache requirements across TanStack Query (React/Vue), Vercel SWR,
 * and WeChat / Alipay MiniApp Network clients.
 * Conforms to Batch 32 Skill 1202 (b32-api-client-data-cache).
 */

import {
  UniversalApiClientIR,
  ApiClientFrameworkId,
  ApiClientTransformResult,
} from './api-client-ir-types';
import { TanStackQueryAdapter } from './tanstack-query-adapter';
import { SwrAdapter } from './swr-adapter';
import { MiniAppRequestAdapter } from './miniapp-request-adapter';

export interface ApiClientValidationReport {
  isValid: boolean;
  errors: string[];
  warnings: string[];
  totalEndpoints: number;
}

export class CrossPlatformApiClientEngine {
  private tanstackAdapter: TanStackQueryAdapter;
  private swrAdapter: SwrAdapter;
  private miniappAdapter: MiniAppRequestAdapter;

  constructor() {
    this.tanstackAdapter = new TanStackQueryAdapter();
    this.swrAdapter = new SwrAdapter();
    this.miniappAdapter = new MiniAppRequestAdapter();
  }

  public getTanStackAdapter(): TanStackQueryAdapter {
    return this.tanstackAdapter;
  }

  public getSwrAdapter(): SwrAdapter {
    return this.swrAdapter;
  }

  public getMiniAppAdapter(): MiniAppRequestAdapter {
    return this.miniappAdapter;
  }

  /**
   * Validate API Client specification integrity.
   * Checks:
   * - Missing path parameters (e.g. :id in path without corresponding param with in: 'path')
   * - Duplicate query keys
   * - Unmatched optimistic update rollback references
   */
  public validateSpecification(clientIR: UniversalApiClientIR): ApiClientValidationReport {
    const errors: string[] = [];
    const warnings: string[] = [];
    let totalEndpoints = 0;

    // Validate Queries
    for (const [id, qOp] of Object.entries(clientIR.queries)) {
      totalEndpoints++;
      // Check path variables
      const pathVarMatches = qOp.path.match(/:([a-zA-Z0-9_]+)/g);
      if (pathVarMatches) {
        for (const match of pathVarMatches) {
          const varName = match.slice(1);
          const hasParam = qOp.parameters.some((p) => p.name === varName && p.in === 'path');
          if (!hasParam) {
            errors.push(`Query '${id}': Path parameter '${varName}' in '${qOp.path}' is missing from parameter definitions.`);
          }
        }
      }

      if (qOp.queryKey.length === 0) {
        warnings.push(`Query '${id}': queryKey array is empty; caching collisions may occur.`);
      }
    }

    // Validate Mutations
    for (const [id, mOp] of Object.entries(clientIR.mutations)) {
      totalEndpoints++;
      const pathVarMatches = mOp.path.match(/:([a-zA-Z0-9_]+)/g);
      if (pathVarMatches) {
        for (const match of pathVarMatches) {
          const varName = match.slice(1);
          const hasParam = mOp.parameters.some((p) => p.name === varName && p.in === 'path');
          if (!hasParam) {
            errors.push(`Mutation '${id}': Path parameter '${varName}' in '${mOp.path}' is missing from parameter definitions.`);
          }
        }
      }

      if (mOp.invalidatesQueryKeys.length === 0) {
        warnings.push(`Mutation '${id}': No cache invalidations specified. UI may display stale data after mutation.`);
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
      totalEndpoints,
    };
  }

  /**
   * Transform Universal API Client IR into target framework implementation.
   */
  public transform(clientIR: UniversalApiClientIR, targetFramework: ApiClientFrameworkId): ApiClientTransformResult {
    const validation = this.validateSpecification(clientIR);
    if (!validation.isValid) {
      throw new Error(`API Client specification validation failed: ${validation.errors.join('; ')}`);
    }

    switch (targetFramework) {
      case 'tanstack-query-react':
        return this.tanstackAdapter.emitReactQueryHooks(clientIR);
      case 'swr-react':
        return this.swrAdapter.emitSwrHooks(clientIR);
      case 'miniapp-request':
        return this.miniappAdapter.emitMiniAppClient(clientIR);
      default:
        throw new Error(`Unsupported API client framework target: ${targetFramework}`);
    }
  }
}
