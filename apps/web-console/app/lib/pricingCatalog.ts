import rawPricingCatalog from "../../../../contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json";

export type PricingPlan = {
  planId: "elmos-free-trial" | "elmos-pro-monthly" | "elmos-pro-annual";
  name: string;
  eyebrow: string;
  description: string;
  priceFen: number;
  billingLabel: string;
  billingPeriod: "TRIAL" | "MONTH" | "YEAR";
  effectiveMonthlyFen: number;
  termDays: number;
  allowanceWindow: "TRIAL_TERM" | "MONTHLY";
  tokens: number;
  credits: number;
  annualTokens: number;
  annualCredits: number;
  activeProjects: number;
  concurrentJobs: number;
  artifactRetentionDays: number;
  featured: boolean;
  trialEligibilityPolicy: "ONE_PER_VERIFIED_ORGANIZATION" | "NOT_APPLICABLE";
  features: readonly string[];
};

export type CreditRate = {
  operationKey: string;
  label: string;
  credits: number;
  unit: string;
  meterVersion: "platform-credit-v1";
};

export type TokenClassDefinition = {
  tokenClass: "INPUT" | "OUTPUT" | "CACHE_READ" | "CACHE_WRITE";
  unit: "token";
  providerReceiptRequired: true;
};

export type PricingCatalog = {
  schemaVersion: "1.1.0";
  catalogVersion: string;
  status: "DRAFT" | "PUBLISHED" | "SUPERSEDED";
  currency: "CNY";
  effectiveFrom: string;
  effectiveUntil: string | null;
  authoritativeSource: string;
  sellerLegalEntityStatus: "NOT_CONFIGURED" | "CONFIGURED";
  taxStatus: "NOT_CONFIGURED" | "CONFIGURED";
  taxPresentation: "UNSPECIFIED" | "TAX_INCLUSIVE" | "TAX_EXCLUSIVE";
  paymentStatus: "NOT_CONFIGURED" | "CONFIGURED";
  // D-01（2026-07-28）选定中国大陆主体 + 支付宝/微信后，
  // 目录 Schema 的 paymentProvider 由 const 扩为 enum，此处同步。
  // STRIPE_CHECKOUT 保留但不启用：Stripe 不为大陆主体收单。
  paymentProvider: "STRIPE_CHECKOUT" | "ALIPAY_CHECKOUT" | "WECHAT_PAY_NATIVE";
  costValidationStatus: "NOT_RUN" | "VALIDATED";
  overagePolicy: "HARD_STOP_NO_AUTOMATIC_CHARGE";
  allowanceScope: "ORGANIZATION" | "ACTOR";
  plans: readonly PricingPlan[];
  tokenClasses: readonly TokenClassDefinition[];
  creditRates: readonly CreditRate[];
  limitations: readonly string[];
};

const PAYMENT_PROVIDERS = [
  "STRIPE_CHECKOUT",
  "ALIPAY_CHECKOUT",
  "WECHAT_PAY_NATIVE",
] as const;
const CATALOG_STATUSES = ["DRAFT", "PUBLISHED", "SUPERSEDED"] as const;
const CONFIGURATION_STATUSES = ["NOT_CONFIGURED", "CONFIGURED"] as const;
const TAX_PRESENTATIONS = [
  "UNSPECIFIED",
  "TAX_INCLUSIVE",
  "TAX_EXCLUSIVE",
] as const;

function assertMember<T extends string>(
  field: string,
  value: unknown,
  allowed: readonly T[],
): T {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    throw new Error(
      `PRICING_CATALOG_INVALID: ${field}=${JSON.stringify(value)} 不在 ` +
        `${allowed.join(" | ")} 之内`,
    );
  }
  return value as T;
}

/**
 * 目录取值域的运行时校验。
 *
 * 原实现是 `value as PricingCatalog` —— 一个无条件的类型断言。
 * JSON 导入会把字面量放宽成 `string`，所以那个断言在编译期不会报任何错，
 * 目录里写成 `PAYPAL` 也照样通过，"精确目录"名不副实。
 *
 * 编译期无法约束放宽后的 JSON，因此改为加载时失败关闭：
 * 取值域漂移会在应用启动时立刻抛错，而不是等到用户点了付费按钮才暴露。
 */
function exactCatalog(value: typeof rawPricingCatalog): PricingCatalog {
  assertMember("status", value.status, CATALOG_STATUSES);
  assertMember("paymentProvider", value.paymentProvider, PAYMENT_PROVIDERS);
  assertMember("sellerLegalEntityStatus", value.sellerLegalEntityStatus, CONFIGURATION_STATUSES);
  assertMember("taxStatus", value.taxStatus, CONFIGURATION_STATUSES);
  assertMember("paymentStatus", value.paymentStatus, CONFIGURATION_STATUSES);
  assertMember("taxPresentation", value.taxPresentation, TAX_PRESENTATIONS);
  assertMember("costValidationStatus", value.costValidationStatus, ["NOT_RUN", "VALIDATED"]);
  if (value.currency !== "CNY") {
    throw new Error(`PRICING_CATALOG_INVALID: currency=${value.currency}`);
  }
  if (!Array.isArray(value.plans) || value.plans.length !== 3) {
    throw new Error("PRICING_CATALOG_INVALID: plans 必须恰好 3 个");
  }
  return value as PricingCatalog;
}

export const pricingCatalog = exactCatalog(rawPricingCatalog);

export function formatCny(amountFen: number): string {
  if (!Number.isSafeInteger(amountFen) || amountFen < 0) {
    throw new Error("CNY_AMOUNT_FEN_INVALID");
  }
  const yuan = Math.floor(amountFen / 100);
  const fen = String(amountFen % 100).padStart(2, "0");
  return `¥${yuan.toLocaleString("zh-CN")}.${fen}`;
}

export function formatQuota(value: number): string {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error("QUOTA_INVALID");
  }
  return value.toLocaleString("zh-CN");
}
