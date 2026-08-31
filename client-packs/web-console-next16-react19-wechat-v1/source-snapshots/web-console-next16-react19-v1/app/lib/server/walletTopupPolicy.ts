/**
 * 充值请求与交接响应的校验规则。
 *
 * <p>单独成模块而不是写在路由里，是为了能被 walletTopupPolicy.verify.mjs
 * 真正执行——这两个函数是「用户点了付款按钮却什么都没发生」与
 * 「同一笔钱被开出两张可付款订单」之间仅有的东西，不能只靠人读一遍。
 */

export class WalletTopupPolicyError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, retryable: boolean) {
    super(message);
    this.name = "WalletTopupPolicyError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

/**
 * 充值只走大陆收单渠道。
 *
 * <p>刻意不与订阅结账共用一份 provider 集合：那份包含 Stripe，而 D-01
 * （大陆主体 + CNY）下 Stripe 不为充值收单。共用一份，将来订阅那边放宽
 * 就会悄悄把充值也放宽——那等于把钱收到另一个主体的账上。
 */
export const TOPUP_PROVIDERS: ReadonlySet<string> = new Set([
  "ALIPAY_CHECKOUT",
  "WECHAT_PAY_NATIVE",
]);

const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/;

// 订单号是我们生成的 "topup-" + UUID。收得比 UUID 宽是为了不在格式演化时
// 把老单号挡在外面，但仍只允许路径安全的字符——这个值会被拼进上游 URL，
// 放行斜杠等于把代理路径的白名单让给调用方。
const ORDER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function requireTopupIdempotencyKey(raw: string | null): string {
  if (raw === null || !IDEMPOTENCY_PATTERN.test(raw)) {
    throw new WalletTopupPolicyError(
      400, "IDEMPOTENCY_KEY_INVALID", "充值请求标识无效。", false);
  }
  return raw;
}

export function requireTopupOrderId(raw: string): string {
  if (!ORDER_PATTERN.test(raw)) {
    throw new WalletTopupPolicyError(
      400, "TOPUP_ORDER_ID_INVALID", "充值订单号无效。", false);
  }
  return raw;
}

/**
 * 只挡明显不成立的金额：不是正整数分。
 *
 * <p>真正的上下限与单日累计上限在 V73 的 elmos_wallet_create_topup_order 里。
 * 在这里复制一份，就等于在两个地方各留一个会过期的数字——限额一改，前端会
 * 先于服务端拒绝，而用户看到的理由是错的。
 */
export function requireTopupAmountMinor(body: unknown): number {
  const amountMinor = typeof body === "object" && body !== null && !Array.isArray(body)
    ? (body as Record<string, unknown>).amountMinor
    : null;
  if (typeof amountMinor !== "number"
      || !Number.isSafeInteger(amountMinor)
      || amountMinor <= 0) {
    throw new WalletTopupPolicyError(
      400, "TOPUP_AMOUNT_INVALID",
      "充值金额必须是大于零的整数（单位：分）。", false);
  }
  return amountMinor;
}

type HandoffShape = {
  paymentProvider?: unknown;
  checkoutUrl?: unknown;
  qrCodeUrl?: unknown;
};

/**
 * 交接响应必须<b>恰好</b>是跳转型或扫码型之一。
 *
 * @returns 问题描述；没有问题时返回 null
 *
 * <p>两个都没有：前端只会显示一个什么都不做的按钮，用户以为系统坏了，
 * 而我们这边一条错误日志都没有。
 * <p>两个都有：说明上游对这笔走哪条路自己都没定，前端选哪个都可能选错。
 * 两种都必须挡下，所以判据是 hasRedirect === hasQrCode。
 */
export function describeTopupHandoffProblem(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return "充值交接响应不是对象";
  }
  const body = payload as HandoffShape;
  const provider = body.paymentProvider;
  if (typeof provider !== "string" || !TOPUP_PROVIDERS.has(provider)) {
    return "充值交接响应缺少可识别的 paymentProvider";
  }
  const hasRedirect = typeof body.checkoutUrl === "string" && body.checkoutUrl.length > 0;
  const hasQrCode = typeof body.qrCodeUrl === "string" && body.qrCodeUrl.length > 0;
  if (hasRedirect === hasQrCode) {
    return hasRedirect
      ? "充值交接同时给了跳转地址与二维码，无法判定支付方式"
      : "充值交接既没有跳转地址也没有二维码";
  }
  if (provider === "WECHAT_PAY_NATIVE" && !hasQrCode) {
    return "微信 Native 支付必须返回二维码内容";
  }
  if (provider !== "WECHAT_PAY_NATIVE" && !hasRedirect) {
    return `${provider} 必须返回跳转地址`;
  }
  return null;
}

/**
 * 上游也会夹逼，这里先夹一次是为了不把 limit=1000000 的请求送过去。
 *
 * <p>缺失与空串必须走 fallback 而不是走 Number()：Number(null) 和 Number("")
 * 都是 0，而 0 是一个合法的下界，于是一个没带 limit 的请求会被翻译成
 * limit=0——「取零条流水」。症状是用户的流水页面空着，没有报错，看起来像
 * 「你还没有任何交易」。这条分支是本模块的 verify 脚本抓出来的。
 */
export function boundedLedgerParam(
  raw: string | null, fallback: number, max: number,
): number {
  if (raw === null || raw.trim() === "") return fallback;
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < 0) return fallback;
  return Math.min(parsed, max);
}
