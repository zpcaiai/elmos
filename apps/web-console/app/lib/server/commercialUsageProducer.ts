import { pricingCatalog } from "../pricingCatalog";

type OperationKey =
  | "repository-discovery"
  | "migration-or-translation-plan"
  | "verified-generation-or-migration"
  | "isolated-runner-minute"
  | "evidence-pack-verification"
  | "model-inference";

type TokenClass = "INPUT" | "OUTPUT" | "CACHE_READ" | "CACHE_WRITE";

type Reservation = {
  reservationId: string;
  decision: "RESERVED" | "DENY_TOKEN_LIMIT" | "DENY_CREDIT_LIMIT";
};

const fixedExecutionCredits = pricingCatalog.creditRates.find(
  (rate) => rate.operationKey === "verified-generation-or-migration",
)?.credits;
const runnerMinuteCredits = pricingCatalog.creditRates.find(
  (rate) => rate.operationKey === "isolated-runner-minute",
)?.credits;

export class CommercialUsageProducerError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function enabled(): boolean {
  return process.env.ELMOS_BILLING_ENFORCEMENT_ENABLED === "true";
}

function config(): { apiBase: string; token: string; subscriptionId: string } {
  const apiBase = process.env.ELMOS_COMMERCIAL_API_URL ?? "";
  const token = process.env.ELMOS_METER_SERVICE_TOKEN ?? "";
  const subscriptionId = process.env.ELMOS_METER_SUBSCRIPTION_ID ?? "";
  let parsed: URL;
  try {
    parsed = new URL(apiBase);
  } catch {
    throw new CommercialUsageProducerError(
      "METER_API_NOT_CONFIGURED",
      "Commercial usage API is not configured.",
    );
  }
  const local = ["localhost", "127.0.0.1"].includes(parsed.hostname);
  if ((parsed.protocol !== "https:" && !(local && parsed.protocol === "http:"))
    || token.length < 24
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(subscriptionId)) {
    throw new CommercialUsageProducerError(
      "METER_IDENTITY_NOT_CONFIGURED",
      "Commercial usage producer identity is not configured.",
    );
  }
  return { apiBase: parsed.toString().replace(/\/$/, ""), token, subscriptionId };
}

async function request(
  path: string,
  idempotencyKey: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const configured = config();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(`${configured.apiBase}/commercial/v1/billing${path}`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${configured.token}`,
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify(body),
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(8_000),
      });
      let result: Record<string, unknown>;
      try {
        result = await response.json() as Record<string, unknown>;
      } catch {
        if (response.status >= 500 && attempt < 2) {
          await retryDelay(attempt);
          continue;
        }
        throw new CommercialUsageProducerError(
          "METER_RESPONSE_INVALID",
          "Commercial usage API returned an invalid response.",
        );
      }
      if (response.ok) return result;
      if ((response.status === 429 || response.status >= 500) && attempt < 2) {
        await retryDelay(attempt);
        continue;
      }
      throw new CommercialUsageProducerError(
        typeof result.code === "string" ? result.code : `METER_HTTP_${response.status}`,
        "Commercial usage API rejected the request.",
      );
    } catch (error) {
      if (error instanceof CommercialUsageProducerError) throw error;
      if (attempt < 2) {
        await retryDelay(attempt);
        continue;
      }
      throw new CommercialUsageProducerError(
        "METER_API_UNAVAILABLE",
        "Commercial usage API is unavailable after safe idempotent retries.",
      );
    }
  }
  throw new CommercialUsageProducerError(
    "METER_API_UNAVAILABLE",
    "Commercial usage API is unavailable.",
  );
}

async function retryDelay(attempt: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, attempt === 0 ? 100 : 250));
}

async function reserve(
  taskId: string,
  operationKey: OperationKey,
  tokens: number,
  credits: number,
  suffix: string,
): Promise<Reservation> {
  const configured = config();
  const result = await request("/usage/reservations", `${taskId}:${suffix}:reserve`, {
    subscriptionId: configured.subscriptionId,
    operationKey,
    requestedTokens: tokens,
    requestedCredits: credits,
    expiresInSeconds: 3600,
  });
  const reservation = {
    reservationId: String(result.reservationId ?? ""),
    decision: String(result.decision ?? "") as Reservation["decision"],
  };
  if (!reservation.reservationId || reservation.decision !== "RESERVED") {
    throw new CommercialUsageProducerError(
      reservation.decision || "METER_RESERVATION_DENIED",
      "Usage allowance is insufficient for this task.",
    );
  }
  return reservation;
}

async function settleCredits(
  taskId: string,
  reservation: Reservation,
  credits: number,
  suffix: string,
): Promise<void> {
  await request("/usage/settlements", `${taskId}:${suffix}:settle`, {
    reservationId: reservation.reservationId,
    actualTokens: 0,
    actualCredits: credits,
    tokenClass: null,
    provider: null,
    providerReceiptRef: null,
    providerCostCurrency: null,
    providerCostMinor: null,
    occurredAt: new Date().toISOString(),
  });
}

async function release(
  taskId: string,
  reservation: Reservation,
  suffix: string,
  reasonCode: string,
): Promise<void> {
  await request("/usage/releases", `${taskId}:${suffix}:release`, {
    reservationId: reservation.reservationId,
    reasonCode,
  });
}

export type MeteredExecution = {
  finish(success: boolean): Promise<void>;
};

export async function beginMeteredExecution(taskId: string): Promise<MeteredExecution | null> {
  if (!enabled()) return null;
  if (fixedExecutionCredits !== 40 || runnerMinuteCredits !== 1) {
    throw new CommercialUsageProducerError(
      "METER_CATALOG_RATE_MISMATCH",
      "Commercial usage rates do not match the execution producer.",
    );
  }
  const startedAt = Date.now();
  const fixed = await reserve(
    taskId, "verified-generation-or-migration", 0, fixedExecutionCredits, "execution",
  );
  let runner: Reservation;
  try {
    runner = await reserve(taskId, "isolated-runner-minute", 0, 20, "runner");
  } catch (error) {
    await release(taskId, fixed, "execution", "RUNNER_RESERVATION_DENIED");
    throw error;
  }
  let closed = false;
  let committedOutcome: boolean | null = null;
  return {
    async finish(success: boolean) {
      if (closed) return;
      if (committedOutcome === null) committedOutcome = success;
      const elapsedMinutes = Math.max(1, Math.min(20, Math.ceil((Date.now() - startedAt) / 60_000)));
      await settleCredits(taskId, runner, elapsedMinutes, "runner");
      if (committedOutcome) {
        await settleCredits(taskId, fixed, fixedExecutionCredits, "execution");
      } else {
        await release(taskId, fixed, "execution", "TASK_NOT_COMPLETED");
      }
      closed = true;
    },
  };
}

export async function recordModelTokens(input: {
  taskId: string;
  tokenClass: TokenClass;
  expectedTokens: number;
  actualTokens: number;
  provider: string;
  providerReceiptRef: string;
  providerCostCurrency?: string;
  providerCostMinor?: number;
}): Promise<void> {
  if (!enabled()) return;
  if (!Number.isSafeInteger(input.expectedTokens) || input.expectedTokens <= 0
    || !Number.isSafeInteger(input.actualTokens) || input.actualTokens <= 0
    || input.actualTokens > input.expectedTokens) {
    throw new CommercialUsageProducerError(
      "MODEL_TOKEN_QUANTITY_INVALID",
      "Model token quantities are invalid.",
    );
  }
  const reservation = await reserve(
    input.taskId,
    "model-inference",
    input.expectedTokens,
    0,
    `model-${input.tokenClass.toLowerCase()}`,
  );
  await request(
    "/usage/settlements",
    `${input.taskId}:model-${input.tokenClass.toLowerCase()}:settle`,
    {
      reservationId: reservation.reservationId,
      actualTokens: input.actualTokens,
      actualCredits: 0,
      tokenClass: input.tokenClass,
      provider: input.provider,
      providerReceiptRef: input.providerReceiptRef,
      providerCostCurrency: input.providerCostCurrency ?? null,
      providerCostMinor: input.providerCostMinor ?? null,
      occurredAt: new Date().toISOString(),
    },
  );
}
