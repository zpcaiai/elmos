/**
 * @file api-client-ir-types.ts
 * @description Universal API Client, Remote Data Cache, and Network Request IR Types.
 * Models Queries, Mutations, Infinite Pagination, Cache Invalidation, Optimistic Updates,
 * Offline Action Queuing, Token Interception, and Concurrent Connection Schedulers.
 * Conforms to Batch 32 Skill 1202 (b32-api-client-data-cache).
 */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';

export type CacheStalenessPolicy = 'cache-first' | 'network-first' | 'stale-while-revalidate' | 'network-only' | 'cache-only';

export interface RetryPolicyIR {
  maxRetries: number;
  initialDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
  retryOnStatus: number[]; // e.g. [408, 429, 500, 502, 503, 504]
  enableJitter: boolean;
}

export interface OptimisticUpdateIR {
  targetQueryKey: string[];
  updaterExpression: string; // e.g. "(old, newItem) => [...old, newItem]"
  rollbackExpression: string; // e.g. "(old, prev) => prev"
}

export interface ApiEndpointParamIR {
  name: string;
  in: 'path' | 'query' | 'header' | 'body';
  required: boolean;
  type: string; // e.g. "string", "number", "CreateUserDto"
  defaultValue?: string;
  description?: string;
}

export interface QueryOperationIR {
  id: string;
  name: string;
  method: HttpMethod;
  path: string; // e.g. "/api/v1/users/:id"
  queryKey: string[]; // e.g. ["users", "detail", ":id"]
  parameters: ApiEndpointParamIR[];
  responseType: string; // e.g. "UserDetailDto"
  staleTimeMs?: number;
  cacheTimeMs?: number;
  refetchOnWindowFocus?: boolean;
  refetchOnReconnect?: boolean;
  refetchIntervalMs?: number;
  retryPolicy?: RetryPolicyIR;
  isInfinitePagination?: boolean;
  paginationConfig?: {
    pageParamName: string; // e.g. "page" or "cursor"
    pageSize: number;
    getNextPageParamExpr: string; // e.g. "(lastPage) => lastPage.nextCursor"
  };
  headers?: Record<string, string>;
}

export interface MutationOperationIR {
  id: string;
  name: string;
  method: HttpMethod; // POST, PUT, PATCH, DELETE
  path: string;
  parameters: ApiEndpointParamIR[];
  requestBodyType?: string;
  responseType: string;
  invalidatesQueryKeys: string[][]; // e.g. [["users", "list"], ["dashboard", "stats"]]
  optimisticUpdates?: OptimisticUpdateIR[];
  retryPolicy?: RetryPolicyIR;
  headers?: Record<string, string>;
}

export interface OfflineQueuePolicyIR {
  enabled: boolean;
  storageDriver: 'localStorage' | 'indexedDB' | 'wx-storage' | 'memory';
  maxQueueSize: number;
  syncOnNetworkResume: boolean;
  conflictResolution: 'client-wins' | 'server-wins' | 'merge-custom';
}

export interface AuthInterceptorIR {
  authType: 'bearer' | 'basic' | 'custom-header' | 'cookie';
  tokenStorageKey: string;
  headerName: string; // default "Authorization"
  tokenPrefix?: string; // default "Bearer "
  autoRefreshToken: boolean;
  refreshTokenEndpoint?: string;
  tokenExpiryStatus: number; // default 401
}

export interface UniversalApiClientIR {
  version: '1.0';
  clientName: string;
  baseUrl: string;
  queries: Record<string, QueryOperationIR>;
  mutations: Record<string, MutationOperationIR>;
  authInterceptor?: AuthInterceptorIR;
  offlineQueue?: OfflineQueuePolicyIR;
  defaultRetryPolicy: RetryPolicyIR;
  maxConcurrentRequests: number; // WeChat MiniApp limit = 10
  timeoutMs: number;
}

export type ApiClientFrameworkId =
  | 'tanstack-query-react'
  | 'tanstack-query-vue'
  | 'swr-react'
  | 'miniapp-request'
  | 'arkui-http'
  | 'axios-client';

export interface ApiClientTransformResult {
  targetFramework: ApiClientFrameworkId;
  clientClassCode: string;
  hooksCode?: string;
  typesCode?: string;
  interceptorCode?: string;
  warnings: string[];
  metrics: {
    queriesCount: number;
    mutationsCount: number;
    optimisticUpdatesCount: number;
    invalidationsCount: number;
  };
}
