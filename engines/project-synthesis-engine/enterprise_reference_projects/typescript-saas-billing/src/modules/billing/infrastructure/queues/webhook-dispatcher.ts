import * as crypto from 'crypto';

export interface WebhookPayload {
  eventId: string;
  eventType: string;
  tenantId: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface WebhookDeliveryAttempt {
  attemptNumber: number;
  statusCode?: number;
  error?: string;
  durationMs: number;
  timestamp: Date;
}

export interface WebhookDeliveryResult {
  deliveryId: string;
  targetUrl: string;
  success: boolean;
  attempts: WebhookDeliveryAttempt[];
  signature: string;
}

export class WebhookDispatcher {
  /**
   * Signs a JSON payload with tenant's shared secret using HMAC-SHA256.
   */
  signPayload(payloadString: string, secret: string): string {
    const hmac = crypto.createHmac('sha256', secret);
    hmac.update(payloadString);
    return `sha256=${hmac.digest('hex')}`;
  }

  /**
   * Dispatches a webhook payload with HMAC signature and simulated exponential backoff.
   */
  async dispatch(params: {
    targetUrl: string;
    secret: string;
    payload: WebhookPayload;
    maxRetries?: number;
    sendFn?: (url: string, body: string, signature: string) => Promise<{ status: number; error?: string }>;
  }): Promise<WebhookDeliveryResult> {
    const payloadStr = JSON.stringify(params.payload);
    const signature = this.signPayload(payloadStr, params.secret);
    const maxRetries = params.maxRetries ?? 3;
    const attempts: WebhookDeliveryAttempt[] = [];

    const defaultSend = async (): Promise<{ status: number; error?: string }> => ({ status: 200 });
    const send = params.sendFn ?? defaultSend;

    let success = false;
    for (let i = 1; i <= maxRetries; i++) {
      const start = Date.now();
      try {
        const res = await send(params.targetUrl, payloadStr, signature);
        const duration = Date.now() - start;

        attempts.push({
          attemptNumber: i,
          statusCode: res.status,
          error: res.error,
          durationMs: duration,
          timestamp: new Date(),
        });

        if (res.status >= 200 && res.status < 300) {
          success = true;
          break;
        }
      } catch (err: unknown) {
        attempts.push({
          attemptNumber: i,
          error: err instanceof Error ? err.message : String(err),
          durationMs: Date.now() - start,
          timestamp: new Date(),
        });
      }

      // Exponential wait before next attempt
      if (i < maxRetries) {
        const waitMs = Math.min(1000, 50 * Math.pow(2, i));
        await new Promise((r) => setTimeout(r, waitMs));
      }
    }

    return {
      deliveryId: `del_${params.payload.eventId}`,
      targetUrl: params.targetUrl,
      success,
      attempts,
      signature,
    };
  }
}
