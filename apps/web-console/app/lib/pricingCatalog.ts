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
  paymentProvider: "STRIPE_CHECKOUT";
  costValidationStatus: "NOT_RUN" | "VALIDATED";
  overagePolicy: "HARD_STOP_NO_AUTOMATIC_CHARGE";
  allowanceScope: "ORGANIZATION" | "ACTOR";
  plans: readonly PricingPlan[];
  tokenClasses: readonly TokenClassDefinition[];
  creditRates: readonly CreditRate[];
  limitations: readonly string[];
};

function exactCatalog(value: typeof rawPricingCatalog): PricingCatalog {
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
