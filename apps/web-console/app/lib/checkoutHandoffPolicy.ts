export type CheckoutSurface = "DIRECT_PROVIDER" | "ELMPAY_HOSTED";

export type CheckoutProvider =
  | "STRIPE_CHECKOUT"
  | "ALIPAY_CHECKOUT"
  | "WECHAT_PAY_NATIVE";

type HandoffShape = {
  paymentProvider?: unknown;
  checkoutSurface?: unknown;
  checkoutUrl?: unknown;
  qrCodeUrl?: unknown;
};

const PROVIDERS = new Set<CheckoutProvider>([
  "STRIPE_CHECKOUT", "ALIPAY_CHECKOUT", "WECHAT_PAY_NATIVE",
]);
const SURFACES = new Set<CheckoutSurface>(["DIRECT_PROVIDER", "ELMPAY_HOSTED"]);

export function describeCheckoutHandoffProblem(
  payload: unknown,
  allowStripe = true,
): string | null {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return "支付交接响应不是对象";
  }
  const body = payload as HandoffShape;
  const provider = body.paymentProvider;
  if (typeof provider !== "string" || !PROVIDERS.has(provider as CheckoutProvider)
      || (!allowStripe && provider === "STRIPE_CHECKOUT")) {
    return "支付交接响应缺少可识别的 paymentProvider";
  }
  const surface = body.checkoutSurface;
  if (typeof surface !== "string" || !SURFACES.has(surface as CheckoutSurface)) {
    return "支付交接响应缺少可识别的 checkoutSurface";
  }
  const hasRedirect = typeof body.checkoutUrl === "string" && body.checkoutUrl.length > 0;
  const hasQr = typeof body.qrCodeUrl === "string" && body.qrCodeUrl.length > 0;
  if (hasRedirect === hasQr) {
    return hasRedirect ? "支付交接同时给了跳转地址与二维码" : "支付交接没有付款入口";
  }
  if (surface === "ELMPAY_HOSTED") {
    if (provider === "STRIPE_CHECKOUT" || !hasRedirect) {
      return "ELMPay 托管收银台必须使用大陆支付通道和跳转地址";
    }
    return trustedCheckoutUrl(provider as CheckoutProvider, surface as CheckoutSurface,
      body.checkoutUrl as string)
      ? null : "ELMPay 托管收银台地址非法";
  }
  if (provider === "WECHAT_PAY_NATIVE") {
    if (!hasQr) return "微信 Native 支付必须返回二维码内容";
    return (body.qrCodeUrl as string).startsWith("weixin://wxpay/bizpayurl?")
      ? null : "微信 Native 支付二维码内容非法";
  }
  if (!hasRedirect) return `${provider} 必须返回跳转地址`;
  return trustedCheckoutUrl(provider as CheckoutProvider, surface as CheckoutSurface,
    body.checkoutUrl as string)
    ? null : "支付跳转地址不在通道白名单内";
}

/** 返回规范化后的可信 URL；任何不确定状态都返回 null。 */
export function trustedCheckoutUrl(
  provider: CheckoutProvider,
  surface: CheckoutSurface,
  raw: string,
): string | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  const loopback = url.hostname === "localhost" || url.hostname === "127.0.0.1"
    || url.hostname === "[::1]";
  if (url.username || url.password
      || (url.protocol !== "https:" && !(loopback && url.protocol === "http:"))) return null;
  if (surface === "ELMPAY_HOSTED") {
    if (provider === "STRIPE_CHECKOUT" || url.search !== "") return null;
    const fields = new URLSearchParams(url.hash.startsWith("#") ? url.hash.slice(1) : "");
    const keys = [...fields.keys()];
    if (keys.length !== 2 || new Set(keys).size !== 2
        || !fields.get("session") || !fields.get("token")
        || !keys.includes("session") || !keys.includes("token")) return null;
    return url.toString();
  }
  if (url.hash !== "") return null;
  if (provider === "STRIPE_CHECKOUT"
      && !(url.hostname === "stripe.com" || url.hostname.endsWith(".stripe.com"))) return null;
  if (provider === "ALIPAY_CHECKOUT"
      && url.hostname !== "openapi.alipay.com" && url.hostname !== "openapi.alipaydev.com") {
    return null;
  }
  if (provider === "WECHAT_PAY_NATIVE") return null;
  return url.toString();
}
