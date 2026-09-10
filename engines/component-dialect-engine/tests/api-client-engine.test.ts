/**
 * @file api-client-engine.test.ts
 * @description Comprehensive unit test suite for Cross-Platform API Client & Remote Data Cache Engine.
 * Verifies TanStack Query (React/Vue Query), Vercel SWR, and WeChat MiniApp Request Adapters,
 * query key factories, optimistic updates with rollback, offline queuing, token refresh interceptors,
 * and concurrent request scheduler limits.
 * Conforms to Batch 32 Skill 1202.
 */

import {
  CrossPlatformApiClientEngine,
  TanStackQueryAdapter,
  SwrAdapter,
  MiniAppRequestAdapter,
  UniversalApiClientIR,
} from '../src/api-client-engine';

describe('Cross-Platform API Client & Data Cache Engine', () => {
  const engine = new CrossPlatformApiClientEngine();
  const tanstackAdapter = engine.getTanStackAdapter();
  const swrAdapter = engine.getSwrAdapter();
  const miniappAdapter = engine.getMiniAppAdapter();

  const sampleClientIR: UniversalApiClientIR = {
    version: '1.0',
    clientName: 'ECommerceApiClient',
    baseUrl: 'https://api.elmos.store',
    timeoutMs: 8000,
    maxConcurrentRequests: 10,
    defaultRetryPolicy: {
      maxRetries: 3,
      initialDelayMs: 500,
      maxDelayMs: 4000,
      backoffMultiplier: 2,
      retryOnStatus: [408, 429, 500, 502, 503, 504],
      enableJitter: true,
    },
    queries: {
      getUserDetail: {
        id: 'getUserDetail',
        name: 'UserDetail',
        method: 'GET',
        path: '/api/v1/users/:userId',
        queryKey: ['users', 'detail', ':userId'],
        parameters: [
          { name: 'userId', in: 'path', required: true, type: 'string' },
          { name: 'includeOrders', in: 'query', required: false, type: 'boolean' },
        ],
        responseType: 'UserProfileResponse',
        staleTimeMs: 120000,
      },
      getProductList: {
        id: 'getProductList',
        name: 'ProductList',
        method: 'GET',
        path: '/api/v1/products',
        queryKey: ['products', 'list'],
        parameters: [
          { name: 'category', in: 'query', required: false, type: 'string' },
        ],
        responseType: 'ProductListResponse',
        isInfinitePagination: true,
        paginationConfig: {
          pageParamName: 'page',
          pageSize: 20,
          getNextPageParamExpr: '(lastPage) => lastPage.hasMore ? lastPage.nextPage : undefined',
        },
      },
    },
    mutations: {
      updateUserProfile: {
        id: 'updateUserProfile',
        name: 'UpdateUserProfile',
        method: 'PUT',
        path: '/api/v1/users/:userId',
        parameters: [
          { name: 'userId', in: 'path', required: true, type: 'string' },
        ],
        requestBodyType: 'UpdateUserPayload',
        responseType: 'UserProfileResponse',
        invalidatesQueryKeys: [
          ['users', 'detail', ':userId'],
          ['dashboard', 'stats'],
        ],
        optimisticUpdates: [
          {
            targetQueryKey: ['users', 'detail'],
            updaterExpression: '(old, variables) => ({ ...old, ...variables })',
            rollbackExpression: '(old, prev) => prev',
          },
        ],
      },
    },
  };

  describe('TanStackQueryAdapter', () => {
    it('should parse AST of TanStack Query hooks', () => {
      const code = `
        import { useQuery, useMutation } from '@tanstack/react-query';

        export function useUser(id: string) {
          return useQuery({
            queryKey: ['users', id],
            queryFn: () => fetch('/api/users/' + id).then(r => r.json()),
          });
        }

        export function useAddUser() {
          return useMutation({
            mutationFn: (user: any) => fetch('/api/users', { method: 'POST', body: JSON.stringify(user) }),
            onMutate: async (newUser) => {},
          });
        }
      `;

      const parsed = tanstackAdapter.parseSource(code);
      expect(parsed.length).toBe(2);
      expect(parsed[0]!.hookName).toBe('useUser');
      expect(parsed[0]!.kind).toBe('query');
      expect(parsed[0]!.queryKey).toContain('users');
      expect(parsed[1]!.hookName).toBe('useAddUser');
      expect(parsed[1]!.kind).toBe('mutation');
      expect(parsed[1]!.hasOptimisticUpdate).toBe(true);
    });

    it('should emit typed React Query hooks with queryKey factory and optimistic rollback', () => {
      const res = tanstackAdapter.emitReactQueryHooks(sampleClientIR);
      expect(res.targetFramework).toBe('tanstack-query-react');
      expect(res.clientClassCode).toContain(`export const queryKeys = {`);
      expect(res.clientClassCode).toContain(`getUserDetail: (userId: string, includeOrders: boolean) => ['users', 'detail', userId]`);
      expect(res.clientClassCode).toContain(`export function useUserDetailQuery(`);
      expect(res.clientClassCode).toContain(`export function useProductListQuery(`);
      expect(res.clientClassCode).toContain(`useInfiniteQuery({`);
      expect(res.clientClassCode).toContain(`export function useUpdateUserProfileMutation(`);
      expect(res.clientClassCode).toContain(`onMutate: async (newVariables) => {`);
      expect(res.clientClassCode).toContain(`queryClient.setQueryData(`);
      expect(res.clientClassCode).toContain(`queryClient.invalidateQueries(`);
      expect(res.metrics.queriesCount).toBe(2);
      expect(res.metrics.mutationsCount).toBe(1);
    });
  });

  describe('SwrAdapter', () => {
    it('should parse AST of SWR hooks', () => {
      const code = `
        import useSWR from 'swr';
        import useSWRMutation from 'swr/mutation';

        export function useProduct(id: string) {
          return useSWR('/api/products/' + id, fetcher);
        }

        export function useCreateProduct() {
          return useSWRMutation('/api/products', postFetcher);
        }
      `;

      const parsed = swrAdapter.parseSource(code);
      expect(parsed.length).toBe(2);
      expect(parsed[0]!.hookName).toBe('useProduct');
      expect(parsed[0]!.kind).toBe('swr-query');
      expect(parsed[1]!.hookName).toBe('useCreateProduct');
      expect(parsed[1]!.kind).toBe('swr-mutation');
    });

    it('should emit typed SWR hooks with query parameters and mutation revalidations', () => {
      const res = swrAdapter.emitSwrHooks(sampleClientIR);
      expect(res.targetFramework).toBe('swr-react');
      expect(res.clientClassCode).toContain(`import useSWR, { SWRConfiguration, mutate } from 'swr';`);
      expect(res.clientClassCode).toContain(`export function useUserDetailSWR(`);
      expect(res.clientClassCode).toContain(`export function useUpdateUserProfileSWRMutation(`);
      expect(res.clientClassCode).toContain(`await mutate((k: any) => typeof k === 'string' && k.includes('users/detail/:userId'));`);
    });
  });

  describe('MiniAppRequestAdapter', () => {
    it('should emit WeChat MiniApp Network Client with scheduler, token refresh, and offline queue', () => {
      const res = miniappAdapter.emitMiniAppClient(sampleClientIR);
      expect(res.targetFramework).toBe('miniapp-request');
      expect(res.clientClassCode).toContain(`export class MiniAppNetworkClient {`);
      expect(res.clientClassCode).toContain(`private maxConcurrent: number = 10;`);
      expect(res.clientClassCode).toContain(`wx.onNetworkStatusChange`);
      expect(res.clientClassCode).toContain(`this.flushOfflineQueue();`);
      expect(res.clientClassCode).toContain(`handle401(task: RequestTask)`);
      expect(res.clientClassCode).toContain(`retryTask(task: RequestTask)`);
      expect(res.clientClassCode).toContain(`saveToOfflineQueue(task: RequestTask)`);
      expect(res.clientClassCode).toContain(`export async function fetchUserDetail`);
      expect(res.clientClassCode).toContain(`export async function mutateUpdateUserProfile`);
    });
  });

  describe('CrossPlatformApiClientEngine Orchestration', () => {
    it('should validate API specification and detect missing path variables', () => {
      const report = engine.validateSpecification(sampleClientIR);
      expect(report.isValid).toBe(true);
      expect(report.errors.length).toBe(0);
      expect(report.totalEndpoints).toBe(3);

      const brokenIR: UniversalApiClientIR = {
        ...sampleClientIR,
        queries: {
          brokenQuery: {
            id: 'brokenQuery',
            name: 'Broken',
            method: 'GET',
            path: '/api/v1/items/:missingParam',
            queryKey: ['items'],
            parameters: [], // missingParam not defined!
            responseType: 'any',
          },
        },
      };

      const brokenReport = engine.validateSpecification(brokenIR);
      expect(brokenReport.isValid).toBe(false);
      expect(brokenReport.errors.length).toBeGreaterThan(0);
      expect(brokenReport.errors[0]).toContain("Path parameter 'missingParam'");
    });

    it('should transform Universal API Client IR to React Query, SWR, and MiniApp', () => {
      const tanstackRes = engine.transform(sampleClientIR, 'tanstack-query-react');
      expect(tanstackRes.targetFramework).toBe('tanstack-query-react');

      const swrRes = engine.transform(sampleClientIR, 'swr-react');
      expect(swrRes.targetFramework).toBe('swr-react');

      const miniappRes = engine.transform(sampleClientIR, 'miniapp-request');
      expect(miniappRes.targetFramework).toBe('miniapp-request');
    });
  });
});
