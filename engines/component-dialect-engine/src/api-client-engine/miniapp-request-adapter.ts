/**
 * @file miniapp-request-adapter.ts
 * @description Enterprise WeChat / Alipay MiniApp HTTP Network Adapter.
 * Implements:
 * 1. Concurrent Request Scheduler: Throttles requests to $\le 10$ to prevent WeChat's hard limit crash.
 * 2. Token Refresh Interceptor: Handles 401 responses, pauses queue, refreshes token, and retries requests.
 * 3. Offline Action Queue: Persists mutations to `wx.setStorage` when offline, auto-replays on network recovery.
 * 4. Exponential Backoff with Jitter: Robust retry policy for mobile intermittent cellular networks.
 * Conforms to Batch 32 Skill 1202 (b32-api-client-data-cache).
 */

import {
  UniversalApiClientIR,
  QueryOperationIR,
  MutationOperationIR,
  ApiClientTransformResult,
} from './api-client-ir-types';

export class MiniAppRequestAdapter {
  /**
   * Emit production-ready MiniApp Network Client TypeScript file (`apiClient.ts`).
   */
  public emitMiniAppClient(clientIR: UniversalApiClientIR): ApiClientTransformResult {
    const lines: string[] = [
      `/**`,
      ` * Auto-generated WeChat MiniApp Network Engine`,
      ` * Client: ${clientIR.clientName}`,
      ` * Max Concurrent: ${clientIR.maxConcurrentRequests} (WeChat hard limit = 10)`,
      ` */`,
      '',
      `export interface RequestTask<T = any> {`,
      `  url: string;`,
      `  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';`,
      `  data?: any;`,
      `  header?: Record<string, string>;`,
      `  resolve: (value: T) => void;`,
      `  reject: (reason: any) => void;`,
      `  retryCount: number;`,
      `  priority: number;`,
      `}`,
      '',
      `export class MiniAppNetworkClient {`,
      `  private baseUrl: string = '${clientIR.baseUrl}';`,
      `  private maxConcurrent: number = ${clientIR.maxConcurrentRequests || 10};`,
      `  private activeRequests: number = 0;`,
      `  private queue: RequestTask[] = [];`,
      `  private isRefreshingToken: boolean = false;`,
      `  private pendingTokenRequests: Array<() => void> = [];`,
      `  private isOnline: boolean = true;`,
      `  private offlineQueueKey: string = 'elmos_offline_mutation_queue';`,
      '',
      `  constructor() {`,
      `    this.setupNetworkMonitor();`,
      `  }`,
      '',
      `  private setupNetworkMonitor() {`,
      `    if (typeof wx !== 'undefined' && wx.onNetworkStatusChange) {`,
      `      wx.getNetworkType({`,
      `        success: (res: any) => {`,
      `          this.isOnline = res.networkType !== 'none';`,
      `        },`,
      `      });`,
      `      wx.onNetworkStatusChange((res: any) => {`,
      `        const wasOffline = !this.isOnline;`,
      `        this.isOnline = res.isConnected;`,
      `        if (wasOffline && this.isOnline) {`,
      `          this.flushOfflineQueue();`,
      `        }`,
      `      });`,
      `    }`,
      `  }`,
      '',
      `  public request<T = any>(options: {`,
      `    url: string;`,
      `    method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';`,
      `    data?: any;`,
      `    header?: Record<string, string>;`,
      `    priority?: number;`,
      `  }): Promise<T> {`,
      `    return new Promise<T>((resolve, reject) => {`,
      `      const task: RequestTask<T> = {`,
      `        url: options.url.startsWith('http') ? options.url : \`\${this.baseUrl}\${options.url}\`,`,
      `        method: options.method || 'GET',`,
      `        data: options.data,`,
      `        header: {`,
      `          'Content-Type': 'application/json',`,
      `          ...options.header,`,
      `        },`,
      `        resolve,`,
      `        reject,`,
      `        retryCount: 0,`,
      `        priority: options.priority || 5,`,
      `      };`,
      '',
      `      this.enqueue(task);`,
      `    });`,
      `  }`,
      '',
      `  private enqueue(task: RequestTask) {`,
      `    // Priority queue sort (higher priority executes first)`,
      `    this.queue.push(task);`,
      `    this.queue.sort((a, b) => b.priority - a.priority);`,
      `    this.schedule();`,
      `  }`,
      '',
      `  private schedule() {`,
      `    if (this.activeRequests >= this.maxConcurrent || this.queue.length === 0) {`,
      `      return;`,
      `    }`,
      '',
      `    if (this.isRefreshingToken) {`,
      `      return;`,
      `    }`,
      '',
      `    const task = this.queue.shift();`,
      `    if (!task) return;`,
      '',
      `    this.activeRequests++;`,
      `    this.executeTask(task);`,
      `  }`,
      '',
      `  private executeTask(task: RequestTask) {`,
      `    // Inject authorization token`,
      `    const token = typeof wx !== 'undefined' ? wx.getStorageSync('auth_token') : null;`,
      `    if (token) {`,
      `      task.header = task.header || {};`,
      `      task.header['Authorization'] = \`Bearer \${token}\`;`,
      `    }`,
      '',
      `    if (typeof wx === 'undefined') {`,
      `      this.activeRequests--;`,
      `      task.reject(new Error('wx runtime not available'));`,
      `      this.schedule();`,
      `      return;`,
      `    }`,
      '',
      `    wx.request({`,
      `      url: task.url,`,
      `      method: task.method,`,
      `      data: task.data,`,
      `      header: task.header,`,
      `      timeout: ${clientIR.timeoutMs},`,
      `      success: (res: any) => {`,
      `        if (res.statusCode >= 200 && res.statusCode < 300) {`,
      `          task.resolve(res.data);`,
      `        } else if (res.statusCode === 401) {`,
      `          this.handle401(task);`,
      `        } else if (this.isRetryable(res.statusCode) && task.retryCount < ${clientIR.defaultRetryPolicy.maxRetries}) {`,
      `          this.retryTask(task);`,
      `        } else {`,
      `          task.reject(new Error(\`Request failed with status: \${res.statusCode}\`));`,
      `        }`,
      `      },`,
      `      fail: (err: any) => {`,
      `        if (!this.isOnline && task.method !== 'GET') {`,
      `          this.saveToOfflineQueue(task);`,
      `          task.reject(new Error('Network offline; mutation saved to offline queue.'));`,
      `        } else if (task.retryCount < ${clientIR.defaultRetryPolicy.maxRetries}) {`,
      `          this.retryTask(task);`,
      `        } else {`,
      `          task.reject(err);`,
      `        }`,
      `      },`,
      `      complete: () => {`,
      `        this.activeRequests--;`,
      `        this.schedule();`,
      `      },`,
      `    });`,
      `  }`,
      '',
      `  private isRetryable(statusCode: number): boolean {`,
      `    return [${clientIR.defaultRetryPolicy.retryOnStatus.join(', ')}].includes(statusCode);`,
      `  }`,
      '',
      `  private retryTask(task: RequestTask) {`,
      `    task.retryCount++;`,
      `    // Exponential backoff with full jitter`,
      `    const baseDelay = ${clientIR.defaultRetryPolicy.initialDelayMs} * Math.pow(${clientIR.defaultRetryPolicy.backoffMultiplier}, task.retryCount - 1);`,
      `    const jitter = Math.random() * baseDelay;`,
      `    const delay = Math.min(baseDelay + jitter, ${clientIR.defaultRetryPolicy.maxDelayMs});`,
      '',
      `    setTimeout(() => {`,
      `      this.enqueue(task);`,
      `    }, delay);`,
      `  }`,
      '',
      `  private handle401(task: RequestTask) {`,
      `    this.queue.unshift(task); // Put back to front of queue`,
      `    if (!this.isRefreshingToken) {`,
      `      this.isRefreshingToken = true;`,
      `      this.refreshToken()`,
      `        .then(() => {`,
      `          this.isRefreshingToken = false;`,
      `          this.schedule();`,
      `        })`,
      `        .catch((err) => {`,
      `          this.isRefreshingToken = false;`,
      `          // Purge queue on refresh failure`,
      `          while (this.queue.length > 0) {`,
      `            const t = this.queue.shift();`,
      `            t?.reject(err);`,
      `          }`,
      `        });`,
      `    }`,
      `  }`,
      '',
      `  private async refreshToken(): Promise<void> {`,
      `    const refreshToken = wx.getStorageSync('refresh_token');`,
      `    if (!refreshToken) throw new Error('No refresh token available');`,
      '',
      `    return new Promise<void>((resolve, reject) => {`,
      `      wx.request({`,
      `        url: \`\${this.baseUrl}/api/v1/auth/refresh\`,`,
      `        method: 'POST',`,
      `        data: { refreshToken },`,
      `        success: (res: any) => {`,
      `          if (res.statusCode === 200 && res.data?.token) {`,
      `            wx.setStorageSync('auth_token', res.data.token);`,
      `            resolve();`,
      `          } else {`,
      `            reject(new Error('Token refresh failed'));`,
      `          }`,
      `        },`,
      `        fail: reject,`,
      `      });`,
      `    });`,
      `  }`,
      '',
      `  private saveToOfflineQueue(task: RequestTask) {`,
      `    try {`,
      `      const list = wx.getStorageSync(this.offlineQueueKey) || [];`,
      `      list.push({`,
      `        url: task.url,`,
      `        method: task.method,`,
      `        data: task.data,`,
      `        header: task.header,`,
      `        timestamp: Date.now(),`,
      `      });`,
      `      wx.setStorageSync(this.offlineQueueKey, list);`,
      `    } catch (e) {`,
      `      console.error('[MiniAppNetworkClient] Failed to persist offline mutation:', e);`,
      `    }`,
      `  }`,
      '',
      `  private flushOfflineQueue() {`,
      `    try {`,
      `      const list = wx.getStorageSync(this.offlineQueueKey) || [];`,
      `      if (!list || list.length === 0) return;`,
      `      wx.removeStorageSync(this.offlineQueueKey);`,
      `      for (const item of list) {`,
      `        this.request(item);`,
      `      }`,
      `    } catch (e) {`,
      `      console.error('[MiniAppNetworkClient] Failed to flush offline queue:', e);`,
      `    }`,
      `  }`,
      `}`,
      '',
      `export const miniappClient = new MiniAppNetworkClient();`,
      '',
    ];

    // Emit Endpoint Convenience Methods
    lines.push(`// Generated API Query & Mutation Methods`);
    for (const [qId, qOp] of Object.entries(clientIR.queries)) {
      const paramNames = qOp.parameters.map((p) => `${p.name}: ${p.type}`);
      const fnParams = paramNames.length > 0 ? `{ ${qOp.parameters.map((p) => p.name).join(', ')} }: { ${paramNames.join(', ')} }` : '';
      lines.push(`export async function fetch${this.capitalize(qOp.name || qId)}(${fnParams}): Promise<${qOp.responseType}> {`);

      let pathExpr = `'${qOp.path}'`;
      for (const p of qOp.parameters.filter((param) => param.in === 'path')) {
        pathExpr = pathExpr.replace(`:${p.name}`, `\${${p.name}}`);
      }
      if (pathExpr.includes('${')) pathExpr = `\`${pathExpr.slice(1, -1)}\``;

      const queryParams = qOp.parameters.filter((p) => p.in === 'query');
      const dataArg = queryParams.length > 0 ? `, data: { ${queryParams.map((p) => p.name).join(', ')} }` : '';

      lines.push(`  return miniappClient.request<${qOp.responseType}>({`);
      lines.push(`    url: ${pathExpr},`);
      lines.push(`    method: '${qOp.method}'${dataArg},`);
      lines.push(`  });`);
      lines.push(`}`);
      lines.push('');
    }

    for (const [mId, mOp] of Object.entries(clientIR.mutations)) {
      const bodyType = mOp.requestBodyType || 'void';
      const bodyArg = bodyType !== 'void' ? `body: ${bodyType}` : '';
      lines.push(`export async function mutate${this.capitalize(mOp.name || mId)}(${bodyArg}): Promise<${mOp.responseType}> {`);
      lines.push(`  return miniappClient.request<${mOp.responseType}>({`);
      lines.push(`    url: '${mOp.path}',`);
      lines.push(`    method: '${mOp.method}',`);
      if (bodyType !== 'void') {
        lines.push(`    data: body,`);
      }
      lines.push(`  });`);
      lines.push(`}`);
      lines.push('');
    }

    return {
      targetFramework: 'miniapp-request',
      clientClassCode: lines.join('\n'),
      warnings: [],
      metrics: {
        queriesCount: Object.keys(clientIR.queries).length,
        mutationsCount: Object.keys(clientIR.mutations).length,
        optimisticUpdatesCount: 0,
        invalidationsCount: 0,
      },
    };
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
