"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { formatQuota } from "../lib/pricingCatalog";
import styles from "./CreditWalletPanel.module.css";

type Amount = string | number;
type CreditBalance = {
  organizationId: string;
  balance: Amount;
  reserved: Amount;
  spendable: Amount;
  status: "ACTIVE" | "FROZEN" | "CLOSED";
};
type CreditLedgerEntry = {
  ledgerEntryId: string;
  actorId: string;
  direction: "CREDIT" | "DEBIT";
  quantity: Amount;
  balanceAfter: Amount;
  entryType: "PURCHASE" | "GENERATION" | "REFUND" | "CORRECTION";
  sourceOrderId: string | null;
  projectId: string | null;
  jobId: string | null;
  expiresAt: string | null;
  occurredAt: string;
};
type CommercialOrder = {
  orderId: string;
  orderType: "CREDIT_PACK" | "PROJECT_GENERATION_ONCE";
  sku: string;
  currency: "CNY";
  amountMinor: Amount;
  creditQuantity: Amount;
  status: "CREATED" | "PENDING_PAYMENT" | "PAID" | "FULFILLED" | "EXPIRED"
    | "FAILED" | "RECONCILIATION_REQUIRED";
  createdAt: string;
  expiresAt: string;
  fulfilledAt: string | null;
  failureCode: string | null;
};
type ApiError = { code?: string; message?: string };

const ledgerLabels: Record<CreditLedgerEntry["entryType"], string> = {
  PURCHASE: "充值入账",
  GENERATION: "生成消费",
  REFUND: "退款调整",
  CORRECTION: "账务纠正",
};
const orderLabels: Record<CommercialOrder["status"], string> = {
  CREATED: "订单已创建",
  PENDING_PAYMENT: "等待付款",
  PAID: "付款已确认",
  FULFILLED: "已入账",
  EXPIRED: "已过期",
  FAILED: "创建失败",
  RECONCILIATION_REQUIRED: "待人工对账",
};

function quantity(value: Amount): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function moment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime())
    ? parsed.toLocaleString("zh-CN", { hour12: false })
    : "—";
}

function isPending(order: CommercialOrder): boolean {
  return order.status === "CREATED" || order.status === "PENDING_PAYMENT"
    || order.status === "PAID";
}

async function responseJson<T>(response: Response): Promise<T & ApiError> {
  return await response.json().catch(() => ({})) as T & ApiError;
}

/** Server-confirmed Credit facts only; a return page is never treated as payment proof. */
export function CreditWalletPanel() {
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const [ledger, setLedger] = useState<CreditLedgerEntry[]>([]);
  const [orders, setOrders] = useState<CommercialOrder[]>([]);
  const [state, setState] = useState<"LOADING" | "READY" | "AUTH" | "UNAVAILABLE">("LOADING");
  const [message, setMessage] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setState("LOADING");
    try {
      const [balanceResponse, ledgerResponse, orderResponse] = await Promise.all([
        fetch("/api/billing/credits", { cache: "no-store", credentials: "same-origin" }),
        fetch("/api/billing/credits/ledger", { cache: "no-store", credentials: "same-origin" }),
        fetch("/api/billing/orders", { cache: "no-store", credentials: "same-origin" }),
      ]);
      if ([balanceResponse, ledgerResponse, orderResponse]
        .some((response) => response.status === 401 || response.status === 403)) {
        setBalance(null);
        setLedger([]);
        setOrders([]);
        setState("AUTH");
        return;
      }
      if (!balanceResponse.ok || !ledgerResponse.ok || !orderResponse.ok) {
        const failed = [balanceResponse, ledgerResponse, orderResponse]
          .find((response) => !response.ok)!;
        const failure = await responseJson<ApiError>(failed);
        setMessage(failure.message || failure.code || "Credit 服务暂时不可用。");
        setState("UNAVAILABLE");
        return;
      }
      const nextBalance = await responseJson<CreditBalance>(balanceResponse);
      const nextLedger = await responseJson<CreditLedgerEntry[]>(ledgerResponse);
      const nextOrders = await responseJson<CommercialOrder[]>(orderResponse);
      if (!Array.isArray(nextLedger) || !Array.isArray(nextOrders)) {
        throw new Error("CREDIT_WALLET_RESPONSE_INVALID");
      }
      setBalance(nextBalance);
      setLedger(nextLedger);
      setOrders(nextOrders.filter((order) => order.orderType === "CREDIT_PACK"));
      setMessage("");
      setState("READY");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Credit 服务暂时不可用。");
      setState("UNAVAILABLE");
    }
  }, []);

  useEffect(() => {
    void load();
    const changed = () => void load(true);
    window.addEventListener("elmos:billing-changed", changed);
    return () => window.removeEventListener("elmos:billing-changed", changed);
  }, [load]);

  const pendingOrderIds = useMemo(
    () => orders.filter(isPending).map((order) => order.orderId).sort().join(","),
    [orders],
  );

  useEffect(() => {
    if (!pendingOrderIds) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden") void load(true);
    }, 4_000);
    return () => window.clearInterval(timer);
  }, [load, pendingOrderIds]);

  const recentOrders = orders.slice(0, 5);
  const recentLedger = ledger.slice(0, 5);

  return (
    <section className={styles.panel} aria-labelledby="credit-wallet-title">
      <div className={styles.heading}>
        <div>
          <span className="overline">CREDIT WALLET</span>
          <h2 id="credit-wallet-title">组织 Credit 余额与充值记录</h2>
          <p>成员购买的 Credit 进入当前组织池；只有支付回调验证并履约后才会显示到账。</p>
        </div>
        <button className="button button-secondary" type="button"
          onClick={() => void load()} disabled={state === "LOADING"}>
          {state === "LOADING" ? "读取中…" : "刷新"}
        </button>
      </div>

      {state === "AUTH" && <p className={styles.message}>登录后可查看余额、订单和充值流水。</p>}
      {state === "UNAVAILABLE" && (
        <p className={`${styles.message} ${styles.error}`} role="alert">
          未能确认当前 Credit 状态：{message || "服务未配置"}
        </p>
      )}
      {state === "READY" && balance && (
        <>
          <div className={styles.summary} aria-label="Credit 余额">
            <div><span>可用 Credit</span><strong>{formatQuota(quantity(balance.spendable))}</strong></div>
            <div><span>执行中冻结</span><strong>{formatQuota(quantity(balance.reserved))}</strong></div>
            <div><span>账面总额</span><strong>{formatQuota(quantity(balance.balance))}</strong></div>
          </div>
          {balance.status !== "ACTIVE" && (
            <p className={`${styles.message} ${styles.error}`} role="alert">
              Credit 账户状态为 {balance.status}，当前不能充值或消费。
            </p>
          )}
          <div className={styles.columns}>
            <div className={styles.column}>
              <h3>最近充值订单</h3>
              {recentOrders.length === 0 ? <p className={styles.empty}>尚无 Credit 充值订单。</p> : (
                <div className={styles.list}>
                  {recentOrders.map((order) => (
                    <div className={styles.row} key={order.orderId}>
                      <div>
                        <strong>{formatQuota(quantity(order.creditQuantity))} Credits</strong>
                        <small title={order.orderId}>{moment(order.createdAt)} · {order.orderId}</small>
                      </div>
                      <strong className={isPending(order) ? styles.pending : ""}>
                        {orderLabels[order.status]}
                      </strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className={styles.column}>
              <h3>最近 Credit 流水</h3>
              {recentLedger.length === 0 ? <p className={styles.empty}>尚无 Credit 入账或消费流水。</p> : (
                <div className={styles.list}>
                  {recentLedger.map((entry) => (
                    <div className={styles.row} key={entry.ledgerEntryId}>
                      <div>
                        <strong>{ledgerLabels[entry.entryType]}</strong>
                        <small>{moment(entry.occurredAt)} · 余额 {formatQuota(quantity(entry.balanceAfter))}</small>
                      </div>
                      <strong className={entry.direction === "CREDIT" ? styles.positive : styles.negative}>
                        {entry.direction === "CREDIT" ? "+" : "−"}{formatQuota(quantity(entry.quantity))}
                      </strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
