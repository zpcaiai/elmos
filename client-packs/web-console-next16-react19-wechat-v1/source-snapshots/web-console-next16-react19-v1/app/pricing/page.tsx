import type { Metadata } from "next";
import Link from "next/link";
import { Icon } from "../components/Icon";
import { formatCny, formatQuota, pricingCatalog } from "../lib/pricingCatalog";
import styles from "./PricingPage.module.css";
import { PlanBillingAction, SubscriptionManager } from "./BillingActions";
import { UsageDashboard } from "./UsageDashboard";

export const metadata: Metadata = {
  title: "套餐与用量",
  description: "ELMOS 人民币免费体验、专业月付与专业年付套餐",
};

export default function PricingPage() {
  const catalogOrderable = pricingCatalog.status === "PUBLISHED"
    && pricingCatalog.sellerLegalEntityStatus === "CONFIGURED"
    && pricingCatalog.taxStatus === "CONFIGURED"
    && pricingCatalog.paymentStatus === "CONFIGURED"
    && pricingCatalog.costValidationStatus === "VALIDATED";

  return (
    <div className={`page-stack ${styles.page}`}>
      <section className={styles.hero}>
        <div>
          <span className="overline">ELMOS SELF-SERVE · CNY</span>
          <h1>先验证价值，再为持续交付付费。</h1>
          <p>
            参考主流 AI 开发工具的免费与专业版结构，以人民币提供清晰的 token、
            credits 和项目额度。没有“无限使用”的模糊承诺，也不会自动产生超额费用。
          </p>
        </div>
        <div className={styles.heroFacts} aria-label="套餐摘要">
          <div><strong>14 天</strong><span>免费体验</span></div>
          <div><strong>¥129</strong><span>专业月付</span></div>
          <div><strong>省 ¥258</strong><span>专业年付</span></div>
        </div>
      </section>

      <section className={styles.statusNotice} role="status">
        <Icon name="clock" size={17} />
        <div>
          <strong>套餐目录已实现，收款尚未开放</strong>
          <span>
            当前目录版本 {pricingCatalog.catalogVersion} 为 DRAFT；支付、税务与开票均为
            NOT_CONFIGURED。
          </span>
        </div>
        <Link href="/commercialization">查看控制面 <Icon name="arrow" size={14} /></Link>
      </section>

      <SubscriptionManager />

      <UsageDashboard
        allowLocalCredentials={process.env.ELMOS_LOCAL_RUNNER_ENABLED === "true"}
        emailAlertsEnabled={process.env.ELMOS_USAGE_EMAIL_ALERTS_ENABLED === "true"}
      />

      <section aria-labelledby="pricing-plans-title">
        <div className="section-heading">
          <div>
            <span className="overline">PLANS</span>
            <h2 id="pricing-plans-title">选择适合当前阶段的计划</h2>
          </div>
          <span className="quiet-label">全部以人民币结算 · 税费口径待配置</span>
        </div>
        <div className={styles.planGrid}>
          {pricingCatalog.plans.map((plan) => (
            <article
              className={`${styles.planCard} ${plan.featured ? styles.featured : ""}`}
              key={plan.planId}
            >
              {plan.featured && <span className={styles.recommended}>推荐</span>}
              <span className="overline">{plan.eyebrow}</span>
              <h3>{plan.name}</h3>
              <p className={styles.planDescription}>{plan.description}</p>
              <div className={styles.priceLine}>
                <strong>{formatCny(plan.priceFen)}</strong>
                <span>/ {plan.billingLabel}</span>
              </div>
              {plan.planId === "elmos-pro-annual" && (
                <p className={styles.savings}>
                  折合 {formatCny(plan.effectiveMonthlyFen)}/月，比连续月付节省 ¥258.00
                </p>
              )}
              {plan.planId === "elmos-free-trial" && (
                <p className={styles.savings}>一次性额度 · 到期不自动扣费</p>
              )}
              {plan.planId === "elmos-pro-monthly" && (
                <p className={styles.savings}>随时按月评估 · 不自动超额计费</p>
              )}

              <div className={styles.quotaPanel} aria-label={`${plan.name}用量额度`}>
                <div>
                  <span>模型 Token</span>
                  <strong>{formatQuota(plan.tokens)}</strong>
                  <small>{plan.allowanceWindow === "MONTHLY" ? "每月重置" : "14 天总额"}</small>
                </div>
                <div>
                  <span>平台 Credits</span>
                  <strong>{formatQuota(plan.credits)}</strong>
                  <small>{plan.allowanceWindow === "MONTHLY" ? "每月重置" : "14 天总额"}</small>
                </div>
              </div>

              {plan.allowanceWindow === "MONTHLY" && (
                <div className={styles.annualCeiling}>
                  {plan.planId === "elmos-pro-annual" ? "年度合同上限" : "连续使用 12 个月"}：
                  {formatQuota(plan.annualTokens)} token · {formatQuota(plan.annualCredits)} credits
                </div>
              )}

              <ul className={styles.featureList}>
                {plan.features.map((feature) => (
                  <li key={feature}><Icon name="check" size={15} />{feature}</li>
                ))}
              </ul>
              <div className={styles.planAction}>
                <PlanBillingAction plan={plan} orderable={catalogOrderable} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.meterSection} aria-labelledby="credit-meter-title">
        <div className={styles.meterIntro}>
          <span className="overline">USAGE METER</span>
          <h2 id="credit-meter-title">Token 与 Credit 如何扣减</h2>
          <p>
            Token 衡量模型实际推理量；Credit 衡量 ELMOS 的分析、隔离执行和验证资源。
            使用模型的工作会同时扣减已确认 token 与对应操作 credits。
          </p>
        </div>
        <div className={styles.rateTable} role="table" aria-label="Credit 扣减表">
          <div className={styles.rateHead} role="row">
            <span role="columnheader">操作</span>
            <span role="columnheader">单价</span>
          </div>
          {pricingCatalog.creditRates.map((rate) => (
            <div className={styles.rateRow} role="row" key={rate.operationKey}>
              <span role="cell">{rate.label}</span>
              <strong role="cell">{rate.credits} credits / {rate.unit}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.rules} aria-labelledby="usage-rules-title">
        <div>
          <span className="overline">BILLING GUARDRAILS</span>
          <h2 id="usage-rules-title">用量规则</h2>
        </div>
        <ul>
          {pricingCatalog.limitations.map((limitation) => (
            <li key={limitation}><Icon name="shield" size={16} />{limitation}</li>
          ))}
        </ul>
        <a className="text-link" href="/api/pricing" target="_blank" rel="noreferrer">
          查看套餐 API <Icon name="external" size={14} />
        </a>
      </section>
    </div>
  );
}
