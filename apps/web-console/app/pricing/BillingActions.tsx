"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import type { PricingPlan } from "../lib/pricingCatalog";
import { Icon } from "../components/Icon";
import styles from "./BillingActions.module.css";

type BillingError = {
  code?: string;
  message?: string;
};

type TrialGrant = {
  planId: string;
  endsAt: string;
  status: string;
};

type Checkout = {
  planId: string;
  checkoutUrl: string;
  status: string;
};

type Subscription = {
  planId: string;
  status: string;
  currentPeriodEnd: string;
  cancelAtPeriodEnd: boolean;
  canCancel: boolean;
};

function idempotencyKey(prefix: string, current: MutableRefObject<string | null>): string {
  if (current.current === null) current.current = `${prefix}-${crypto.randomUUID()}`;
  return current.current;
}

async function json<T>(response: Response): Promise<T & BillingError> {
  try {
    return await response.json() as T & BillingError;
  } catch {
    return {} as T & BillingError;
  }
}

function errorMessage(payload: BillingError, fallback: string): string {
  if (payload.code === "TRIAL_ALREADY_USED") return "该组织或已验证身份已使用过免费体验。";
  if (payload.code === "ACCOUNT_SESSION_REQUIRED") return "请先登录后再管理套餐。";
  return payload.message || fallback;
}

function planName(planId: string): string {
  if (planId === "elmos-free-trial") return "免费体验";
  if (planId === "elmos-pro-monthly") return "专业月付";
  if (planId === "elmos-pro-annual") return "专业年付";
  return planId;
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime())
    ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "long" }).format(parsed)
    : "未知日期";
}

export function PlanBillingAction({
  plan,
  orderable,
}: {
  plan: PricingPlan;
  orderable: boolean;
}) {
  const key = useRef<string | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const trial = plan.planId === "elmos-free-trial";

  const activate = async () => {
    setPending(true);
    setMessage("");
    setFailed(false);
    try {
      const response = await fetch(trial ? "/api/billing/trial" : "/api/billing/checkout", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey(trial ? "trial" : "checkout", key),
        },
        body: trial ? undefined : JSON.stringify({ planId: plan.planId }),
      });
      const payload = await json<TrialGrant & Checkout>(response);
      if (!response.ok) throw new Error(errorMessage(payload, "套餐操作暂时无法完成。"));

      if (trial) {
        setMessage(`体验已开通，有效期至 ${formatDate(payload.endsAt)}。`);
        window.dispatchEvent(new Event("elmos:billing-changed"));
        return;
      }

      let destination: URL;
      try {
        destination = new URL(payload.checkoutUrl);
      } catch {
        throw new Error("支付服务返回了无效的结账地址。");
      }
      if (destination.protocol !== "https:" || !destination.hostname.endsWith(".stripe.com")) {
        throw new Error("支付服务返回了不受信任的结账地址。");
      }
      window.location.assign(destination.toString());
    } catch (error) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "套餐操作暂时无法完成。");
    } finally {
      setPending(false);
    }
  };

  const paidUnavailable = !trial && !orderable;
  return (
    <div className={styles.actionStack}>
      <button
        className={`button ${plan.featured ? "button-primary" : "button-secondary"}`}
        type="button"
        disabled={pending || paidUnavailable}
        onClick={activate}
      >
        {pending ? "正在处理…" : trial ? "开始免费体验" : paidUnavailable ? "等待开放" : "安全结账"}
        {!pending && <Icon name={paidUnavailable ? "clock" : "arrow"} size={15} />}
      </button>
      {message ? (
        <p className={failed ? styles.actionError : styles.actionSuccess} role={failed ? "alert" : "status"}>
          {message}
        </p>
      ) : (
        <p className={styles.actionHint}>
          {trial ? "需登录并具有已验证邮箱或手机号" : paidUnavailable ? "完成支付、税务与成本门禁后开放" : "跳转至 Stripe 安全结账"}
        </p>
      )}
    </div>
  );
}

export function SubscriptionManager() {
  const cancelKey = useRef<string | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [state, setState] = useState<"LOADING" | "READY" | "EMPTY" | "AUTH" | "UNAVAILABLE">("LOADING");
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setState("LOADING");
    try {
      const response = await fetch("/api/billing/subscription", {
        credentials: "same-origin",
        cache: "no-store",
      });
      const payload = await json<Subscription>(response);
      if (response.ok) {
        setSubscription(payload);
        setState("READY");
      } else if (response.status === 401 || response.status === 403) {
        setSubscription(null);
        setState("AUTH");
      } else if (response.status === 404 || payload.code === "ACTIVE_SUBSCRIPTION_NOT_FOUND") {
        setSubscription(null);
        setState("EMPTY");
      } else {
        setSubscription(null);
        setState("UNAVAILABLE");
      }
    } catch {
      setSubscription(null);
      setState("UNAVAILABLE");
    }
  }, []);

  useEffect(() => {
    void load();
    const refresh = () => void load();
    window.addEventListener("elmos:billing-changed", refresh);
    return () => window.removeEventListener("elmos:billing-changed", refresh);
  }, [load]);

  const cancel = async () => {
    setPending(true);
    setMessage("");
    try {
      const response = await fetch("/api/billing/cancel", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Idempotency-Key": idempotencyKey("cancel", cancelKey),
        },
      });
      const payload = await json<{ effectiveAt: string }>(response);
      if (!response.ok) throw new Error(errorMessage(payload, "订阅取消暂时无法完成。"));
      setMessage(`已安排在 ${formatDate(payload.effectiveAt)} 到期取消。`);
      setConfirming(false);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "订阅取消暂时无法完成。");
    } finally {
      setPending(false);
    }
  };

  let copy = "正在读取当前订阅…";
  if (state === "AUTH") copy = "登录后可查看当前套餐、账期和取消状态。";
  if (state === "EMPTY") copy = "当前没有有效套餐，可先开通一次免费体验。";
  if (state === "UNAVAILABLE") copy = "订阅服务尚未配置或暂时不可用，未将未知状态显示为无订阅。";
  if (state === "READY" && subscription) {
    copy = `${planName(subscription.planId)} · ${subscription.status} · 当前账期至 ${formatDate(subscription.currentPeriodEnd)}`;
    if (subscription.cancelAtPeriodEnd) copy += " · 已安排到期取消";
  }

  return (
    <section className={styles.subscriptionPanel} aria-label="当前订阅">
      <div className={styles.subscriptionCopy}>
        <strong>当前订阅</strong>
        <span>{copy}</span>
        {message && <span role="status">{message}</span>}
      </div>
      <div className={styles.subscriptionActions}>
        {state === "UNAVAILABLE" && (
          <button className="button button-secondary" type="button" onClick={() => void load()}>
            重试
          </button>
        )}
        {state === "READY" && subscription?.canCancel && !confirming && (
          <button className="button button-secondary" type="button" onClick={() => setConfirming(true)}>
            到期取消
          </button>
        )}
        {state === "READY" && subscription?.canCancel && confirming && (
          <>
            <button className="button button-secondary" type="button" onClick={() => setConfirming(false)} disabled={pending}>
              保留订阅
            </button>
            <button className="button button-primary" type="button" onClick={cancel} disabled={pending}>
              {pending ? "正在提交…" : "确认到期取消"}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
