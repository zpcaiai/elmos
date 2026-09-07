"use client";

import { FormEvent, useCallback, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import styles from "./OperationsAdmin.module.css";

/**
 * 跨组织的余额、流水与充值对账。
 *
 * <p>这是全平台唯一一处能同时看到多个租户资金的界面，所以它刻意做得笨一点：
 * 不缓存、不预取、不在切换到「财务对账」时自动拉取。原因是每一次读取在服务端
 * 都会写一条审计（platform_admin_access_log），而自动拉取会让审计里那条
 * 「某某查看了全平台余额」不再对应任何人的意图——它只对应一次点导航栏。
 *
 * <p>授权是两道，不是一道：这里的 VIEWER/APPROVER 是控制台会话的角色，
 * 决定 BFF 转不转发；跨组织的那道在数据库里（platform_administrators），
 * 决定控制面答不答。本地这道过了不代表那道会过，所以「被拒绝」是一个
 * 必须能显示出来的正常结果，而不是异常。
 */

type Amount = string | number | null;

type WalletRow = {
  organizationId: string;
  displayName: string | null;
  currency: string;
  balanceMinor: Amount;
  reservedMinor: Amount;
  spendableMinor: Amount;
  walletStatus: string;
  heldReservations: number;
  updatedAt: string | null;
};

type LedgerRow = {
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

type TopupRow = {
  topupOrderId: string;
  organizationId: string;
  actorId: string;
  amountMinor: Amount;
  provider: string;
  outTradeNo: string | null;
  status: string;
  createdAt: string | null;
  paidAt: string | null;
  creditedAt: string | null;
};

/** 分转元。金额全程以整数分传输，只在显示的最后一步换算。 */
function yuan(minor: Amount): string {
  if (minor === null || minor === undefined) return "—";
  const value = typeof minor === "number" ? minor : Number(minor);
  if (!Number.isFinite(value)) return "—";
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

/**
 * 把响应读成「行」或「拒绝」。
 *
 * <p>403 与「空列表」在界面上必须长得不一样：一个是没权限，一个是真的没有数据。
 * 混在一起会让人以为功能坏了，或者更糟——以为平台上一个钱包都没有。
 */
async function readRows<T>(response: Response): Promise<{ rows: T[]; denial: string }> {
  const payload = (await response.json().catch(() => null)) as
    | { rows?: T[]; code?: string; message?: string }
    | null;
  if (!response.ok) {
    return {
      rows: [],
      denial: payload?.code ?? payload?.message ?? `HTTP_${response.status}`,
    };
  }
  return { rows: payload?.rows ?? [], denial: "" };
}

export function PlatformWalletPanel({ canAdjust }: { canAdjust: boolean }) {
  const [wallets, setWallets] = useState<WalletRow[]>([]);
  const [topups, setTopups] = useState<TopupRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [expanded, setExpanded] = useState("");
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [ledgerBusy, setLedgerBusy] = useState(false);
  const [denial, setDenial] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [target, setTarget] = useState("");
  const [amountYuan, setAmountYuan] = useState("");
  const [direction, setDirection] = useState<"CREDIT" | "DEBIT">("CREDIT");
  const [reason, setReason] = useState("");

  /**
   * 幂等键按「这一笔调整」生成一次并保留到成功为止。
   *
   * <p>如果每次提交都换一个键，网络超时后的重试就会变成第二笔真实入账——
   * 而超时恰恰是最不知道上一笔成没成的时候。键留在 ref 里，改了金额或
   * 组织才作废，因为那时它已经是另一笔了。
   */
  const idempotencyKey = useRef("");
  const keySignature = useRef("");

  const load = useCallback(async () => {
    setBusy(true);
    setNotice("");
    try {
      const [walletResponse, topupResponse] = await Promise.all([
        fetch("/api/admin/wallets?limit=100", { cache: "no-store" }),
        fetch("/api/admin/topups?limit=50", { cache: "no-store" }),
      ]);
      const walletPage = await readRows<WalletRow>(walletResponse);
      const topupPage = await readRows<TopupRow>(topupResponse);
      setWallets(walletPage.rows);
      setTopups(topupPage.rows);
      setDenial(walletPage.denial || topupPage.denial);
      setLoaded(true);
      setExpanded("");
      setLedger([]);
    } catch {
      setDenial("PLATFORM_WALLETS_UNREACHABLE");
    } finally {
      setBusy(false);
    }
  }, []);

  const openLedger = useCallback(async (organizationId: string) => {
    if (expanded === organizationId) {
      setExpanded("");
      setLedger([]);
      return;
    }
    setLedgerBusy(true);
    setExpanded(organizationId);
    setLedger([]);
    try {
      const page = await readRows<LedgerRow>(
        await fetch(
          `/api/admin/wallets/${encodeURIComponent(organizationId)}/ledger?limit=50`,
          { cache: "no-store" },
        ),
      );
      setLedger(page.rows);
      if (page.denial) setDenial(page.denial);
    } catch {
      setDenial("PLATFORM_LEDGER_UNREACHABLE");
    } finally {
      setLedgerBusy(false);
    }
  }, [expanded]);

  async function submitAdjustment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    const parsed = Number(amountYuan);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setDenial("ADJUSTMENT_AMOUNT_INVALID");
      return;
    }
    const amountMinor = Math.round(parsed * 100);
    if (amountMinor <= 0) {
      setDenial("ADJUSTMENT_AMOUNT_INVALID");
      return;
    }
    const signature = `${target}|${direction}|${amountMinor}`;
    if (keySignature.current !== signature || !idempotencyKey.current) {
      keySignature.current = signature;
      idempotencyKey.current = `adj-${crypto.randomUUID()}`;
    }
    setBusy(true);
    setDenial("");
    try {
      const response = await fetch("/api/admin/wallets/adjust", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organizationId: target,
          direction,
          amountMinor,
          reason: reason.trim(),
          idempotencyKey: idempotencyKey.current,
        }),
      });
      const payload = (await response.json().catch(() => null)) as
        | { code?: string; message?: string; entryId?: string }
        | null;
      if (!response.ok) {
        // 键刻意不作废：这一笔可能已经在服务端成立了，换键重试会入两次账。
        setDenial(payload?.code ?? payload?.message ?? `HTTP_${response.status}`);
        return;
      }
      idempotencyKey.current = "";
      keySignature.current = "";
      setAmountYuan("");
      setReason("");
      setNotice(`已入账，流水 ${payload?.entryId ?? "(未回传编号)"}。`);
      await load();
    } catch {
      // 未知结果：既不清键也不重试，由人决定。
      setDenial("ADJUSTMENT_RESULT_UNKNOWN");
    } finally {
      setBusy(false);
    }
  }

  const uncredited = topups.filter((order) => order.status === "PAID");

  return (
    <>
      <section className={styles.panel} aria-label="全平台账户余额">
        <header>
          <div>
            <span className="overline">PLATFORM WALLETS</span>
            <h2>各账户余额</h2>
          </div>
          <small>跨组织 · 每次读取都会写审计 · 最多 100 个组织</small>
        </header>
        <p>
          这一栏与「财务对账」的租户视图不同：它不带组织头，看到的是全部租户的钱。
          能不能看由数据库里的平台管理员名单决定，本地角色只决定 BFF 转不转发。
        </p>
        <div className={styles.inlineActions}>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void load()}
            disabled={busy}
          >
            <Icon name={busy ? "refresh" : "search"} size={17} />
            {busy ? "读取中…" : "读取全平台余额"}
          </button>
        </div>
        {denial && <p className={styles.bad} role="alert">被拒绝或读取失败：{denial}</p>}
        {notice && <p className={styles.good} role="status">{notice}</p>}

        {!loaded ? (
          <div className={styles.empty}>
            <Icon name="database" size={22} />
            <span>点击读取后才会请求；页面不会预取全平台资金数据。</span>
          </div>
        ) : wallets.length === 0 ? (
          <div className={styles.empty}>
            <Icon name="database" size={22} />
            <span>没有钱包。租户首次充值或首次收到人工调整后才会出现。</span>
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>组织</th>
                  <th>余额</th>
                  <th>冻结中</th>
                  <th>可用</th>
                  <th>持有笔数</th>
                  <th>状态</th>
                  <th>更新时间</th>
                  <th>流水</th>
                </tr>
              </thead>
              <tbody>
                {wallets.map((row) => (
                  <tr key={row.organizationId}>
                    <td>
                      <strong>{row.displayName ?? row.organizationId}</strong>
                      <br />
                      <code>{row.organizationId}</code>
                    </td>
                    <td>{yuan(row.balanceMinor)}</td>
                    <td>{yuan(row.reservedMinor)}</td>
                    <td>{yuan(row.spendableMinor)}</td>
                    <td>{row.heldReservations}</td>
                    <td>
                      <span className={row.walletStatus === "ACTIVE" ? styles.resultGood : styles.resultBad}>
                        {row.walletStatus}
                      </span>
                    </td>
                    <td>{moment(row.updatedAt)}</td>
                    <td>
                      <button
                        className="secondary-button"
                        type="button"
                        disabled={ledgerBusy}
                        onClick={() => void openLedger(row.organizationId)}
                      >
                        <Icon name={expanded === row.organizationId ? "close" : "file"} size={16} />
                        {expanded === row.organizationId ? "收起" : "查看"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {expanded && (
        <section className={styles.panel} aria-label="账户流水">
          <header>
            <div>
              <span className="overline">LEDGER</span>
              <h2>{expanded} 的流水</h2>
            </div>
            <small>最近 50 条 · 新的在前 · 只读且不可修改</small>
          </header>
          <p className={styles.boundaryNote}>
            流水只记录真实的资金移动（充值入账、消费、退款、人工调整、试用赠送）。
            任务开始时的冻结与结束时的释放是预留状态的变化，不在这里——否则同一列
            「结余」在不同的行上会是两个意思，账本也就无法靠重放自证。
          </p>
          {ledgerBusy ? (
            <div className={styles.empty}>
              <Icon name="refresh" size={22} />
              <span>读取中…</span>
            </div>
          ) : ledger.length === 0 ? (
            <div className={styles.empty}>
              <Icon name="database" size={22} />
              <span>这个组织还没有资金流水。</span>
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>类型</th>
                    <th>方向</th>
                    <th>金额</th>
                    <th>结余</th>
                    <th>来源</th>
                    <th>操作者</th>
                    <th>原因</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.map((entry) => (
                    <tr key={entry.entryId}>
                      <td>{entry.seq}</td>
                      <td><code>{entry.entryType}</code></td>
                      <td>
                        <span className={entry.direction === "CREDIT" ? styles.resultGood : styles.resultBad}>
                          {entry.direction === "CREDIT" ? "入" : "出"}
                        </span>
                      </td>
                      <td>{yuan(entry.amountMinor)}</td>
                      <td>{yuan(entry.balanceAfterMinor)}</td>
                      <td title={entry.sourceRef}>
                        <small>{entry.sourceType}</small>
                        <br />
                        <code>{entry.sourceRef.length > 28 ? `${entry.sourceRef.slice(0, 25)}…` : entry.sourceRef}</code>
                      </td>
                      <td title={entry.actorId}><code>{entry.actorId.slice(0, 12)}…</code></td>
                      <td>{entry.reason ?? "—"}</td>
                      <td>{moment(entry.occurredAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <section className={styles.panel} aria-label="充值对账">
        <header>
          <div>
            <span className="overline">TOP-UP RECONCILIATION</span>
            <h2>充值与挂单</h2>
          </div>
          <small>已付款但未入账：{loaded ? uncredited.length : "—"}</small>
        </header>
        {uncredited.length > 0 && (
          <p className={styles.bad} role="alert">
            有 {uncredited.length} 笔已收款但没有入账。这一栏应该常年为空——非空即事故：
            钱已经收了，而客户的余额没有变。先查支付回调有没有到，再查回调有没有找到这张单。
          </p>
        )}
        {!loaded ? (
          <div className={styles.empty}>
            <Icon name="database" size={22} />
            <span>与余额一同读取。</span>
          </div>
        ) : topups.length === 0 ? (
          <div className={styles.empty}>
            <Icon name="database" size={22} />
            <span>没有充值订单。</span>
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>组织</th>
                  <th>金额</th>
                  <th>渠道</th>
                  <th>商户单号</th>
                  <th>状态</th>
                  <th>创建</th>
                  <th>付款</th>
                  <th>入账</th>
                </tr>
              </thead>
              <tbody>
                {topups.map((order) => (
                  <tr key={order.topupOrderId}>
                    <td><code>{order.organizationId}</code></td>
                    <td>{yuan(order.amountMinor)}</td>
                    <td>{order.provider}</td>
                    <td><code>{order.outTradeNo ?? "—"}</code></td>
                    <td>
                      <span className={order.status === "PAID" ? styles.resultBad : styles.resultGood}>
                        {order.status}
                      </span>
                    </td>
                    <td>{moment(order.createdAt)}</td>
                    <td>{moment(order.paidAt)}</td>
                    <td>{moment(order.creditedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={styles.panel} aria-label="人工调整余额">
        <header>
          <div>
            <span className="overline">MANUAL ADJUSTMENT</span>
            <h2>人工调整余额</h2>
          </div>
          <small>需要 APPROVER + 平台管理员 · 不可撤销</small>
        </header>
        <p>
          这是这个子系统里唯一一个在别处没有对照记录的动作：没有支付流水，没有任务，
          事后能对账的只有管理员打进去的那句原因。所以原因必填，且会写进客户可见的流水。
          写错了不能删——只能再打一笔反向的。
        </p>
        {canAdjust ? (
          <form className={styles.financeActions} onSubmit={submitAdjustment}>
            <label>
              <span>组织 ID</span>
              <input
                value={target}
                onChange={(event) => setTarget(event.target.value.trim())}
                aria-label="被调整的组织 ID"
                placeholder="org-xxxx"
                pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
                title="组织标识，例如 org-pre。"
                disabled={busy}
                required
              />
            </label>
            <label>
              <span>方向</span>
              <select
                aria-label="调整方向"
                value={direction}
                disabled={busy}
                onChange={(event) => setDirection(event.target.value === "DEBIT" ? "DEBIT" : "CREDIT")}
              >
                <option value="CREDIT">增加 CREDIT</option>
                <option value="DEBIT">扣减 DEBIT</option>
              </select>
            </label>
            <label>
              <span>金额（元，正数）</span>
              <input
                value={amountYuan}
                onChange={(event) => setAmountYuan(event.target.value)}
                aria-label="调整金额（元）"
                inputMode="decimal"
                placeholder="100.00"
                disabled={busy}
                required
              />
            </label>
            <label>
              <span>原因（客户可见）</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                aria-label="调整原因"
                placeholder="补偿 2026-08-20 任务重复扣费"
                maxLength={200}
                disabled={busy}
                required
              />
            </label>
            <div>
              <button className="primary-button" type="submit" disabled={busy || !reason.trim()}>
                <Icon name={busy ? "refresh" : "check"} size={17} />
                {busy ? "提交中…" : `提交${direction === "CREDIT" ? "增加" : "扣减"}`}
              </button>
            </div>
          </form>
        ) : (
          <p className={styles.boundaryNote}>
            当前会话角色不足，只能查看。人工改余额需要 APPROVER，且账号还要在平台管理员名单上。
          </p>
        )}
      </section>
    </>
  );
}
