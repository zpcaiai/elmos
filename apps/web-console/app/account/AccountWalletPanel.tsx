"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useAccountSession } from "../components/AccountSessionProvider";
import styles from "./AccountOrganizationStudio.module.css";

/**
 * 用户侧钱包：余额、充值、流水。
 *
 * <p>与订阅并存而不是取代它。一个租户可以同时有套餐和余额——任务优先走套餐
 * 配额，配额不够才动余额（见 V74 的 elmos_wallet_admit_job）。所以这个面板
 * 刻意不说「你的额度」，只说「你的余额」：把两种额度混成一个数字，用户就
 * 无法理解为什么充了钱而任务还是被拒（配额没了但计费开关是关的），
 * 或者为什么没充钱任务也能跑（配额还有）。
 */

type Amount = string | number | null;

type WalletView = {
  currency: string;
  balanceMinor: Amount;
  reservedMinor: Amount;
  spendableMinor: Amount;
  status: string;
  minTopupMinor: Amount;
  maxTopupMinor: Amount;
};

type LedgerEntry = {
  entryId: string;
  seq: number;
  direction: string;
  amountMinor: Amount;
  balanceAfterMinor: Amount;
  entryType: string;
  sourceType: string;
  sourceRef: string;
  actorId: string;
  reason: string | null;
  occurredAt: string | null;
};

type TopupHandoff = {
  topupOrderId: string;
  outTradeNo: string;
  currency: string;
  amountMinor: Amount;
  status: string;
  expiresAt: string | null;
  paymentProvider: string;
  checkoutUrl: string | null;
  qrCodeUrl: string | null;
};

type ErrorPayload = { code?: string; errorCode?: string; message?: string };

const entryLabels: Record<string, string> = {
  TOPUP_SETTLED: "充值入账",
  CONSUME: "任务消费",
  REFUND: "退款",
  ADMIN_ADJUSTMENT: "人工调整",
  TRIAL_GRANT: "试用赠送",
};

function toNumber(minor: Amount): number | null {
  if (minor === null || minor === undefined) return null;
  const value = typeof minor === "number" ? minor : Number(minor);
  return Number.isFinite(value) ? value : null;
}

function yuan(minor: Amount): string {
  const value = toNumber(minor);
  if (value === null) return "—";
  return (value / 100).toLocaleString("zh-CN", {
    style: "currency",
    currency: "CNY",
    minimumFractionDigits: 2,
  });
}

function moment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("zh-CN", { hour12: false });
}

export function AccountWalletPanel() {
  const account = useAccountSession();
  const [wallet, setWallet] = useState<WalletView | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [handoff, setHandoff] = useState<TopupHandoff | null>(null);
  const [amountYuan, setAmountYuan] = useState("");
  const [feedback, setFeedback] = useState("");
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);

  /**
   * 幂等键按「这一笔充值」生成一次并保留到这一笔结束为止。
   *
   * <p>每次提交换一个键，网络超时后的重试就会向支付渠道开出第二笔可付款的
   * 订单——而超时正是最不知道上一笔成没成的时候。金额一改就是另一笔，作废。
   */
  const idempotencyKey = useRef("");
  const keyAmount = useRef(-1);

  const load = useCallback(async () => {
    setBusy(true);
    setFailure("");
    try {
      const [walletResponse, ledgerResponse] = await Promise.all([
        fetch("/api/wallet", { cache: "no-store", credentials: "same-origin" }),
        fetch("/api/wallet/ledger?limit=50", { cache: "no-store", credentials: "same-origin" }),
      ]);
      const walletPayload = await walletResponse.json().catch(() => null) as
        (WalletView & ErrorPayload) | null;
      if (!walletResponse.ok) {
        setWallet(null);
        setFailure(walletPayload?.code ?? walletPayload?.message ?? "WALLET_UNAVAILABLE");
        return;
      }
      setWallet(walletPayload);
      const ledgerPayload = await ledgerResponse.json().catch(() => null);
      setLedger(Array.isArray(ledgerPayload) ? ledgerPayload as LedgerEntry[] : []);
    } catch {
      setFailure("WALLET_UNREACHABLE");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (account.status === "authenticated") void load();
  }, [account.status, load]);

  /**
   * 付款完成由支付回调把订单推到 CREDITED，前端只能轮询等它到。
   *
   * <p>刻意不在「已付款」时就把余额加上去：那样界面会短暂显示一个数据库里
   * 还不存在的余额，而如果回调最终没到（这正是需要对账的那种情况），
   * 用户看到的是钱到了、下一次刷新又没了。宁可慢一点也别说谎。
   */
  useEffect(() => {
    if (!handoff || handoff.status === "CREDITED" || handoff.status === "EXPIRED") return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(
          `/api/wallet/topup/${encodeURIComponent(handoff.topupOrderId)}`,
          { cache: "no-store", credentials: "same-origin" });
        if (!response.ok || cancelled) return;
        const order = await response.json().catch(() => null) as { status?: string } | null;
        if (!order?.status || cancelled) return;
        if (order.status !== handoff.status) {
          setHandoff((current) => current && { ...current, status: order.status as string });
        }
        if (order.status === "CREDITED") {
          idempotencyKey.current = "";
          keyAmount.current = -1;
          setFeedback("充值已入账。");
          await load();
        }
      } catch {
        // 轮询失败不打扰用户：下一轮会再试，真到不了会停在「已付款待入账」，
        // 那本身就是给运营看的信号。
      }
    }, 4000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [handoff, load]);

  async function submitTopup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback("");
    setFailure("");
    const parsed = Number(amountYuan);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setFailure("请输入大于零的充值金额。");
      return;
    }
    const amountMinor = Math.round(parsed * 100);
    if (amountMinor <= 0) {
      setFailure("请输入大于零的充值金额。");
      return;
    }
    if (keyAmount.current !== amountMinor || !idempotencyKey.current) {
      keyAmount.current = amountMinor;
      idempotencyKey.current = `topup-${crypto.randomUUID()}`;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/wallet/topup", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey.current,
        },
        body: JSON.stringify({ amountMinor }),
      });
      const payload = await response.json().catch(() => null) as
        (TopupHandoff & ErrorPayload) | null;
      if (!response.ok) {
        // 键不作废：这一笔可能已经在服务端建好了，换键重试会开出第二笔可付款的单。
        setFailure(payload?.message ?? payload?.code ?? `充值未能发起（HTTP ${response.status}）。`);
        return;
      }
      setHandoff(payload);
      setFeedback(payload?.qrCodeUrl
        ? "已生成付款二维码，请用微信扫码完成付款。"
        : "已生成付款链接，请在新页面完成付款。");
    } catch {
      setFailure("充值请求结果未知，请不要重复提交——刷新后查看是否已有待付款订单。");
    } finally {
      setBusy(false);
    }
  }

  if (account.status !== "authenticated") return null;

  const minTopup = toNumber(wallet?.minTopupMinor ?? null);
  const maxTopup = toNumber(wallet?.maxTopupMinor ?? null);
  const frozen = Boolean(wallet && wallet.status !== "ACTIVE");

  return (
    <>
      <div className={styles.grid}>
        <article className={styles.panel}>
          <h2>账户余额</h2>
          {failure && <p role="alert">读取或操作失败：{failure}</p>}
          {!wallet ? (
            <p><small>{busy ? "读取中…" : "还没有钱包。首次充值后才会创建。"}</small></p>
          ) : (
            <>
              <p style={{ fontSize: 28, margin: "0 0 4px" }}>{yuan(wallet.spendableMinor)}</p>
              <small>可用余额（已扣除执行中任务的冻结）</small>
              <h3>明细</h3>
              <label><span>账面余额</span><strong>{yuan(wallet.balanceMinor)}</strong></label>
              <label>
                <span>执行中冻结</span>
                <strong>{yuan(wallet.reservedMinor)}</strong>
              </label>
              <small>
                冻结是任务开始时按预估扣下的，任务结束后按实际用量结算，
                多冻的会退回可用余额。它还在你的账面余额里，只是暂时不能用于新任务。
              </small>
              {frozen && (
                <p role="alert">
                  钱包当前状态为 {wallet.status}，无法充值或消费。请联系运营。
                </p>
              )}
            </>
          )}
          <button className="button" type="button" onClick={() => void load()} disabled={busy}>
            {busy ? "读取中…" : "刷新"}
          </button>
        </article>

        <article className={styles.panel}>
          <h2>充值</h2>
          <p>
            <small>
              余额与套餐并存：任务优先消耗套餐配额，配额不足时才动余额。
              充值不会改变你的套餐。
            </small>
          </p>
          <form onSubmit={submitTopup}>
            <label>
              <span>
                金额（元）
                {minTopup !== null && maxTopup !== null
                  && ` · 单笔 ${yuan(minTopup)} — ${yuan(maxTopup)}`}
              </span>
              <input
                value={amountYuan}
                onChange={(event) => setAmountYuan(event.target.value)}
                aria-label="充值金额（元）"
                inputMode="decimal"
                placeholder="100"
                disabled={busy || frozen}
                required
              />
            </label>
            <button className="button primary" type="submit" disabled={busy || frozen}>
              {busy ? "提交中…" : "发起充值"}
            </button>
          </form>
          {feedback && <div className={styles.feedback} role="status">{feedback}</div>}

          {handoff && (
            <div className={styles.token}>
              <small>订单 {handoff.topupOrderId} · {yuan(handoff.amountMinor)} · {handoff.status}</small>
              {handoff.checkoutUrl && (
                <a className="button" href={handoff.checkoutUrl}
                   target="_blank" rel="noopener noreferrer">
                  前往付款
                </a>
              )}
              {handoff.qrCodeUrl && (
                <>
                  <small>微信扫码付款（二维码内容）：</small>
                  <code>{handoff.qrCodeUrl}</code>
                </>
              )}
              <small>
                {handoff.status === "PAID"
                  ? "已收到付款，正在入账——入账由支付回调完成，通常几秒内。"
                  : `付款有效期至 ${moment(handoff.expiresAt)}。超时后这笔订单作废，可以重新发起。`}
              </small>
            </div>
          )}
        </article>
      </div>

      <article className={styles.members}>
        <div>
          <h2>账户流水</h2>
          <small>最近 {ledger.length} 条 · 只读</small>
        </div>
        {ledger.length === 0 ? (
          <p><small>还没有流水。充值入账、任务消费、退款和人工调整都会记在这里。</small></p>
        ) : (
          <div className={styles.memberList}>
            {ledger.map((entry) => (
              <div className={styles.member} key={entry.entryId}>
                <div>
                  <strong>{entryLabels[entry.entryType] ?? entry.entryType}</strong>
                  <small title={entry.sourceRef}>
                    {moment(entry.occurredAt)}
                    {entry.reason ? ` · ${entry.reason}` : ""}
                  </small>
                </div>
                <strong style={{ textAlign: "right" }}>
                  {entry.direction === "CREDIT" ? "+" : "−"}{yuan(entry.amountMinor)}
                </strong>
                <small>余额 {yuan(entry.balanceAfterMinor)}</small>
              </div>
            ))}
          </div>
        )}
        <small>
          {/*
            这里刻意只记真实的资金移动。任务开始时的冻结与结束时的释放是预留
            状态的变化，不是钱的移动——把它们也记进来，同一列「余额」在不同
            的行上就会是两个意思，账本也就无法靠重放自证。
          */}
          流水只记录真实的资金移动。任务执行期间的冻结与释放不在这里，
          它们反映在上方的「执行中冻结」里。
        </small>
      </article>
    </>
  );
}
