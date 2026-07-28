export type PricingPlan = {
  planId: "elmos-free-trial" | "elmos-pro-monthly" | "elmos-pro-annual";
  name: string;
  eyebrow: string;
  description: string;
  priceFen: number;
  billingLabel: string;
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
  features: readonly string[];
};

export type CreditRate = {
  operationKey: string;
  label: string;
  credits: number;
  unit: string;
};

export const pricingCatalog = {
  schemaVersion: "1.0.0",
  catalogVersion: "2026-07-28.1",
  status: "DRAFT",
  currency: "CNY",
  sellerLegalEntityStatus: "NOT_CONFIGURED",
  taxStatus: "NOT_CONFIGURED",
  paymentStatus: "NOT_CONFIGURED",
  overagePolicy: "HARD_STOP_NO_AUTOMATIC_CHARGE",
  plans: [
    {
      planId: "elmos-free-trial",
      name: "免费体验",
      eyebrow: "先完成一次真实体验",
      description: "适合评估一个小型仓库，从发现、规划到查看验证结果。",
      priceFen: 0,
      billingLabel: "14 天",
      effectiveMonthlyFen: 0,
      termDays: 14,
      allowanceWindow: "TRIAL_TERM",
      tokens: 2_000_000,
      credits: 60,
      annualTokens: 2_000_000,
      annualCredits: 60,
      activeProjects: 1,
      concurrentJobs: 1,
      artifactRetentionDays: 7,
      featured: false,
      features: ["无需绑定银行卡", "标准模型与核心工作流", "1 个活动项目", "1 个并发作业", "证据保留 7 天"],
    },
    {
      planId: "elmos-pro-monthly",
      name: "专业月付",
      eyebrow: "灵活按月使用",
      description: "适合个人开发者和正在推进单个现代化项目的小团队负责人。",
      priceFen: 12_900,
      billingLabel: "每月",
      effectiveMonthlyFen: 12_900,
      termDays: 31,
      allowanceWindow: "MONTHLY",
      tokens: 20_000_000,
      credits: 600,
      annualTokens: 240_000_000,
      annualCredits: 7_200,
      activeProjects: 10,
      concurrentJobs: 3,
      artifactRetentionDays: 30,
      featured: false,
      features: ["完整模型目录", "迁移、转换与项目生成", "10 个活动项目", "3 个并发作业", "邮件支持"],
    },
    {
      planId: "elmos-pro-annual",
      name: "专业年付",
      eyebrow: "长期项目首选",
      description: "适合持续迁移多个系统的客户，价格更低且每月额度提高 25%。",
      priceFen: 129_000,
      billingLabel: "每年",
      effectiveMonthlyFen: 10_750,
      termDays: 365,
      allowanceWindow: "MONTHLY",
      tokens: 25_000_000,
      credits: 750,
      annualTokens: 300_000_000,
      annualCredits: 9_000,
      activeProjects: 25,
      concurrentJobs: 5,
      artifactRetentionDays: 90,
      featured: true,
      features: ["月付档全部能力", "每月额度提高 25%", "25 个活动项目", "5 个并发作业", "优先支持与 90 天证据保留"],
    },
  ] satisfies readonly PricingPlan[],
  creditRates: [
    { operationKey: "repository-discovery", label: "仓库发现与分析", credits: 5, unit: "次" },
    { operationKey: "migration-or-translation-plan", label: "迁移或转换规划", credits: 15, unit: "次" },
    { operationKey: "verified-generation-or-migration", label: "受控生成或迁移执行", credits: 40, unit: "次" },
    { operationKey: "isolated-runner-minute", label: "隔离 Runner", credits: 1, unit: "分钟" },
    { operationKey: "evidence-pack-verification", label: "证据包验证", credits: 10, unit: "次" },
  ] satisfies readonly CreditRate[],
  limitations: [
    "Token 按模型提供方确认的输入 token 与输出 token 求和扣减。",
    "Credits 按不可变的已接受操作用量事件扣减；组合任务会累计各项费用。",
    "免费体验额度在 14 天结束时失效；付费额度按订阅周年日每月重置，均不结转。",
    "额度用尽后硬停止，不自动产生超额费用；支付、税务与开票当前仍为 NOT_CONFIGURED。",
  ],
} as const;

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
