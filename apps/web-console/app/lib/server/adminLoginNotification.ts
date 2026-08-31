import { randomUUID } from "node:crypto";
import {
  closeSync,
  constants as fileConstants,
  fstatSync,
  openSync,
  readFileSync,
} from "node:fs";
import { isAbsolute } from "node:path";

import {
  AccountSessionError,
  ADMINISTRATOR_EMAIL,
  isPlatformAdministrator,
  type AccountPrincipal,
} from "./accountSession";

const resendEmailsEndpoint = "https://api.resend.com/emails";
const maximumProviderResponseBytes = 8 * 1024;

export type AdministratorLoginAuthentication =
  | "OIDC"
  | "LOCAL_DEVELOPMENT_CREDENTIAL";

export type AdministratorLoginNotificationReceipt = {
  eventId: string;
  providerMessageId: string;
  acceptedAt: string;
};

type NotificationEnvironment = {
  ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED?: string;
  ELMOS_ADMIN_LOGIN_EMAIL_FROM?: string;
  ELMOS_RESEND_API_KEY?: string;
  ELMOS_RESEND_API_KEY_FILE?: string;
};

type NotificationOptions = {
  environment?: NotificationEnvironment;
  fetchImpl?: typeof fetch;
  now?: Date;
  eventId?: string;
};

function notificationError(code: string, message: string): AccountSessionError {
  return new AccountSessionError(503, code, message);
}

function configuredApiKey(environment: NotificationEnvironment): string {
  const inline = environment.ELMOS_RESEND_API_KEY?.trim() ?? "";
  const configuredFile = environment.ELMOS_RESEND_API_KEY_FILE?.trim() ?? "";
  if (!inline && !configuredFile) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_NOT_CONFIGURED",
      "管理员登录邮件通知尚未配置。",
    );
  }
  if (inline && configuredFile) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID",
      "管理员登录邮件通知密钥来源配置冲突。",
    );
  }
  if (inline) {
    if (inline.length < 24 || inline.length > 4_096 || /\s/.test(inline)) {
      throw notificationError(
        "ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID",
        "管理员登录邮件通知配置无效。",
      );
    }
    return inline;
  }
  if (!isAbsolute(configuredFile) || /[\0\r\n]/.test(configuredFile)) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID",
      "管理员登录邮件通知配置无效。",
    );
  }
  let descriptor: number | undefined;
  try {
    descriptor = openSync(
      configuredFile,
      fileConstants.O_RDONLY | fileConstants.O_NOFOLLOW,
    );
    const info = fstatSync(descriptor);
    const effectiveUserId = typeof process.geteuid === "function" ? process.geteuid() : undefined;
    if (
      !info.isFile()
      || info.size > 4_096
      || (info.mode & 0o077) !== 0
      || (effectiveUserId !== undefined && info.uid !== effectiveUserId)
    ) {
      throw notificationError(
        "ADMIN_LOGIN_NOTIFICATION_SECRET_FILE_UNSAFE",
        "管理员登录邮件通知密钥文件不安全。",
      );
    }
    const value = readFileSync(descriptor, "utf8").trim();
    if (value.length < 24 || value.length > 4_096 || /\s/.test(value)) {
      throw notificationError(
        "ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID",
        "管理员登录邮件通知配置无效。",
      );
    }
    return value;
  } catch (error) {
    if (error instanceof AccountSessionError) throw error;
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_SECRET_FILE_UNAVAILABLE",
      "管理员登录邮件通知密钥文件不可用。",
    );
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

function configuredSender(environment: NotificationEnvironment): string {
  const sender = environment.ELMOS_ADMIN_LOGIN_EMAIL_FROM?.trim() ?? "";
  const address = sender.match(/<([^<>]+)>$/)?.[1] ?? sender;
  if (
    !sender
    || sender.length > 320
    || /[\0\r\n]/.test(sender)
    || !/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(address)
  ) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID",
      "管理员登录邮件发件地址无效。",
    );
  }
  return sender;
}

function safeClientLabel(request: Request): string {
  return (request.headers.get("user-agent") ?? "未提供")
    .replace(/[\0-\x1f\x7f]/g, " ")
    .trim()
    .slice(0, 160) || "未提供";
}

async function providerMessageId(response: Response): Promise<string> {
  const declaredLength = Number(response.headers.get("content-length") ?? "");
  if (Number.isFinite(declaredLength) && declaredLength > maximumProviderResponseBytes) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_RESPONSE_INVALID",
      "管理员登录邮件服务返回无效响应。",
    );
  }
  const raw = await response.text();
  if (raw.length > maximumProviderResponseBytes) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_RESPONSE_INVALID",
      "管理员登录邮件服务返回无效响应。",
    );
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_RESPONSE_INVALID",
      "管理员登录邮件服务返回无效响应。",
    );
  }
  const id = payload && typeof payload === "object" && !Array.isArray(payload)
    ? (payload as Record<string, unknown>).id
    : undefined;
  if (typeof id !== "string" || !/^[A-Za-z0-9-]{16,128}$/.test(id)) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_RESPONSE_INVALID",
      "管理员登录邮件服务未返回有效投递凭据。",
    );
  }
  return id;
}

export async function notifyAdministratorLogin(
  request: Request,
  principal: AccountPrincipal,
  authentication: AdministratorLoginAuthentication,
  options: NotificationOptions = {},
): Promise<AdministratorLoginNotificationReceipt> {
  if (!isPlatformAdministrator(principal)) {
    throw new AccountSessionError(
      403,
      "ADMIN_EMAIL_REQUIRED",
      `管理员入口仅允许 ${ADMINISTRATOR_EMAIL}。`,
    );
  }
  const environment: NotificationEnvironment = options.environment ?? {
    ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED:
      process.env.ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED,
    ELMOS_ADMIN_LOGIN_EMAIL_FROM: process.env.ELMOS_ADMIN_LOGIN_EMAIL_FROM,
    ELMOS_RESEND_API_KEY: process.env.ELMOS_RESEND_API_KEY,
    ELMOS_RESEND_API_KEY_FILE: process.env.ELMOS_RESEND_API_KEY_FILE,
  };
  if (environment.ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED !== "true") {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_NOT_CONFIGURED",
      "管理员登录邮件通知尚未启用，未建立管理员会话。",
    );
  }
  const apiKey = configuredApiKey(environment);
  const from = configuredSender(environment);
  const occurredAt = options.now ?? new Date();
  const eventId = options.eventId ?? randomUUID();
  if (!/^[A-Za-z0-9-]{16,128}$/.test(eventId)) {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_EVENT_INVALID",
      "管理员登录通知事件无效。",
    );
  }
  const acceptedAt = occurredAt.toISOString();
  const text = [
    "ELMOS 检测到管理员账户登录。",
    `管理员邮箱：${ADMINISTRATOR_EMAIL}`,
    `登录时间：${acceptedAt}`,
    `认证方式：${authentication}`,
    `客户端：${safeClientLabel(request)}`,
    `安全事件：${eventId}`,
    "如果这不是您本人操作，请立即撤销身份提供商会话并轮换相关凭据。",
  ].join("\n");

  let response: Response;
  try {
    response = await (options.fetchImpl ?? fetch)(resendEmailsEndpoint, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "Idempotency-Key": `elmos-admin-login-${eventId}`,
        "User-Agent": "ELMOS-Web-Console/0.1",
      },
      body: JSON.stringify({
        from,
        to: [ADMINISTRATOR_EMAIL],
        subject: "[ELMOS 安全提醒] 管理员账户已登录",
        text,
        headers: { "X-ELMOS-Login-Event-ID": eventId },
        tags: [{ name: "event", value: "admin-login" }],
      }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(7_000),
    });
  } catch {
    throw notificationError(
      "ADMIN_LOGIN_NOTIFICATION_UNAVAILABLE",
      "管理员登录邮件通知暂不可用，未建立管理员会话。",
    );
  }
  if (!response.ok) {
    throw notificationError(
      response.status === 429
        ? "ADMIN_LOGIN_NOTIFICATION_RATE_LIMITED"
        : "ADMIN_LOGIN_NOTIFICATION_REJECTED",
      "管理员登录邮件通知未被服务商接受，未建立管理员会话。",
    );
  }
  return {
    eventId,
    providerMessageId: await providerMessageId(response),
    acceptedAt,
  };
}
