"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { formatQuota } from "../lib/pricingCatalog";
import {
  type CurrentUsageSnapshot,
  parseCurrentUsageSnapshot,
  parseUsageApiError,
  type UsageApiError,
} from "../lib/usageSnapshot";
import styles from "./UsageDashboard.module.css";

type Credentials = {
  tenantId: string;
  actorId: string;
  token: string;
};

type Session = { kind: "account" } | { kind: "local"; credentials: Credentials };

type ReadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "current"; snapshot: CurrentUsageSnapshot }
  | { kind: "stale"; snapshot: CurrentUsageSnapshot; error: UsageApiError }
  | { kind: "error"; error: UsageApiError };

type UsageHistoryPoint = {
  bucketStartsAt: string;
  meterId: "model-token-v1" | "platform-credit-v1";
  operationKey: string;
  tokenClass: "INPUT" | "OUTPUT" | "CACHE_READ" | "CACHE_WRITE" | null;
  actorId: string;
  provider: string | null;
  debited: number;
  credited: number;
  net: number;
};

type AlertPreference = {
  preferenceId: string;
  actorId: string;
  scope: "ACTOR" | "ORGANIZATION";
  thresholdBps: number[];
  emailEnabled: boolean;
  inAppEnabled: boolean;
  version: number;
};

type InsightsState =
  | { kind: "idle" | "loading" }
  | { kind: "ready"; history: UsageHistoryPoint[]; preference: AlertPreference }
  | { kind: "error"; message: string };

const emptyCredentials: Credentials = { tenantId: "", actorId: "", token: "" };
const alertThresholds = [5000, 8000, 9500, 10000] as const;

function percent(usageBps: number): string {
  return `${(usageBps / 100).toFixed(2)}%`;
}

function localTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

function localDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
}

function requestHeaders(session: Session): HeadersInit {
  if (session.kind === "account") return {};
  return {
    "Authorization": `Bearer ${session.credentials.token}`,
    "X-ELMOS-Tenant": session.credentials.tenantId,
    "X-ELMOS-Actor": session.credentials.actorId,
  };
}

function meterLabel(
  label: string,
  consumed: number,
  limit: number,
  usageBps: number,
): string {
  return `${label}：已使用 ${formatQuota(consumed)}，额度 ${formatQuota(limit)}，消耗进度 ${percent(usageBps)}`;
}

function UsageMeter({
  label,
  unit,
  measure,
}: {
  label: string;
  unit: string;
  measure: CurrentUsageSnapshot["tokens"];
}) {
  const visualPercent = Math.min(100, measure.usageBps / 100);
  return (
    <article className={styles.meterCard}>
      <div className={styles.meterHeading}>
        <div>
          <span>{label}</span>
          <strong>{formatQuota(measure.consumed)}</strong>
          <small>已结算 {unit}</small>
        </div>
        <em className={measure.hardStop ? styles.danger : ""}>{percent(measure.usageBps)}</em>
      </div>
      <div
        className={styles.progress}
        role="progressbar"
        aria-label={`${label}消耗进度`}
        aria-valuemin={0}
        aria-valuemax={measure.limit}
        aria-valuenow={Math.min(measure.consumed + measure.reserved, measure.limit)}
        aria-valuetext={meterLabel(label, measure.consumed, measure.limit, measure.usageBps)}
      >
        <span
          className={measure.hardStop ? styles.progressDanger : ""}
          style={{ width: `${visualPercent}%` }}
        />
      </div>
      <div className={styles.meterFoot}>
        <span>剩余 <strong>{formatQuota(measure.remaining)}</strong></span>
        {measure.reserved > 0 && <span>处理中 {formatQuota(measure.reserved)}</span>}
        <span>总额度 {formatQuota(measure.limit)}</span>
      </div>
    </article>
  );
}

function parseHistory(value: unknown): UsageHistoryPoint[] {
  if (typeof value !== "object" || value === null || !("items" in value)
    || !Array.isArray((value as { items: unknown }).items)) {
    throw new Error("USAGE_HISTORY_CONTRACT_INVALID");
  }
  return (value as { items: UsageHistoryPoint[] }).items;
}

function parsePreference(value: unknown): AlertPreference {
  if (typeof value !== "object" || value === null
    || !Array.isArray((value as { thresholdBps?: unknown }).thresholdBps)) {
    throw new Error("USAGE_ALERT_CONTRACT_INVALID");
  }
  return value as AlertPreference;
}

export function UsageDashboard({
  allowLocalCredentials = false,
  emailAlertsEnabled = false,
}: {
  allowLocalCredentials?: boolean;
  emailAlertsEnabled?: boolean;
}) {
  const [form, setForm] = useState<Credentials>(emptyCredentials);
  const [session, setSession] = useState<Session | null>(
    allowLocalCredentials ? null : { kind: "account" },
  );
  const [readState, setReadState] = useState<ReadState>(
    allowLocalCredentials ? { kind: "idle" } : { kind: "loading" },
  );
  const [insights, setInsights] = useState<InsightsState>({ kind: "idle" });
  const [savingAlerts, setSavingAlerts] = useState(false);

  useEffect(() => {
    if (!session) return;
    let disposed = false;
    let stopped = false;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    let lastSnapshot: CurrentUsageSnapshot | null = null;

    const schedule = (seconds: number) => {
      if (disposed) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void refresh(), seconds * 1_000);
    };

    const refresh = async () => {
      if (disposed || stopped) return;
      if (document.visibilityState === "hidden") {
        schedule(5);
        return;
      }
      controller?.abort();
      controller = new AbortController();
      if (!lastSnapshot) setReadState({ kind: "loading" });
      try {
        const response = await fetch("/api/usage/current", {
          method: "GET",
          cache: "no-store",
          headers: requestHeaders(session),
          signal: controller.signal,
        });
        const body: unknown = await response.json();
        if (!response.ok) {
          const error = parseUsageApiError(body, response.status);
          if (response.status === 401 || response.status === 403 || !error.retryable) {
            stopped = true;
            setReadState(lastSnapshot
              ? { kind: "stale", snapshot: lastSnapshot, error }
              : { kind: "error", error });
            return;
          }
          setReadState(lastSnapshot
            ? { kind: "stale", snapshot: lastSnapshot, error }
            : { kind: "error", error });
          schedule(5);
          return;
        }
        let snapshot: CurrentUsageSnapshot;
        try {
          snapshot = parseCurrentUsageSnapshot(body);
        } catch {
          stopped = true;
          const contractError: UsageApiError = {
            code: "USAGE_RESPONSE_CONTRACT_INVALID",
            message: "实时计量响应不符合当前客户端契约，已停止自动刷新。",
            retryable: false,
            status: "ERROR",
          };
          setReadState(lastSnapshot
            ? { kind: "stale", snapshot: lastSnapshot, error: contractError }
            : { kind: "error", error: contractError });
          return;
        }
        lastSnapshot = snapshot;
        setReadState({ kind: "current", snapshot });
        schedule(Math.max(2, snapshot.refreshAfterSeconds));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const transportError: UsageApiError = {
          code: "USAGE_TRANSPORT_ERROR",
          message: "暂时无法连接实时计量服务；已保留最近一次可信读数。",
          retryable: true,
          status: "ERROR",
        };
        setReadState(lastSnapshot
          ? { kind: "stale", snapshot: lastSnapshot, error: transportError }
          : { kind: "error", error: transportError });
        schedule(5);
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        window.clearTimeout(timer);
        void refresh();
      } else {
        controller?.abort();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void refresh();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [session]);

  useEffect(() => {
    if (!session || session.kind !== "account") return;
    let disposed = false;
    const load = async () => {
      setInsights({ kind: "loading" });
      const to = new Date();
      const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1_000);
      const query = new URLSearchParams({
        from: from.toISOString(),
        to: to.toISOString(),
        bucket: "DAY",
      });
      try {
        const [historyResponse, alertResponse] = await Promise.all([
          fetch(`/api/usage/history?${query}`, { cache: "no-store" }),
          fetch("/api/usage/alerts", { cache: "no-store" }),
        ]);
        const [historyBody, alertBody]: [unknown, unknown] = await Promise.all([
          historyResponse.json(),
          alertResponse.json(),
        ]);
        if (!historyResponse.ok || !alertResponse.ok) {
          throw new Error("USAGE_INSIGHTS_UNAVAILABLE");
        }
        if (!disposed) {
          setInsights({
            kind: "ready",
            history: parseHistory(historyBody),
            preference: parsePreference(alertBody),
          });
        }
      } catch {
        if (!disposed) setInsights({ kind: "error", message: "历史明细与提醒设置暂不可用。" });
      }
    };
    void load();
    return () => { disposed = true; };
  }, [session]);

  const snapshot = readState.kind === "current" || readState.kind === "stale"
    ? readState.snapshot
    : null;
  const error = readState.kind === "error" || readState.kind === "stale"
    ? readState.error
    : null;

  const forecast = useMemo(() => {
    if (insights.kind !== "ready" || !snapshot) return null;
    const byDay = new Map<string, number>();
    for (const point of insights.history) {
      if (point.meterId !== "model-token-v1") continue;
      const day = point.bucketStartsAt.slice(0, 10);
      byDay.set(day, (byDay.get(day) ?? 0) + Number(point.net));
    }
    const active = [...byDay.values()].filter((value) => value > 0);
    if (active.length === 0) return { label: "暂无消耗趋势", detail: "有已结算用量后生成预测" };
    const daily = active.reduce((sum, value) => sum + value, 0) / active.length;
    const days = snapshot.tokens.remaining / daily;
    const exhaustion = new Date(Date.now() + days * 24 * 60 * 60 * 1_000);
    const periodEnd = new Date(snapshot.period.endsAt);
    return exhaustion < periodEnd
      ? { label: `预计 ${localDate(exhaustion.toISOString())} 用尽`, detail: `近 30 天活跃日均 ${formatQuota(Math.round(daily))} tokens` }
      : { label: "预计本周期内不会用尽", detail: `近 30 天活跃日均 ${formatQuota(Math.round(daily))} tokens` };
  }, [insights, snapshot]);

  const connect = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSession({
      kind: "local",
      credentials: {
        tenantId: form.tenantId.trim(),
        actorId: form.actorId.trim(),
        token: form.token,
      },
    });
    setReadState({ kind: "loading" });
  };

  const savePreference = async (preference: AlertPreference) => {
    setSavingAlerts(true);
    try {
      const response = await fetch("/api/usage/alerts", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: preference.scope,
          thresholdBps: preference.thresholdBps,
          emailEnabled: preference.emailEnabled,
          inAppEnabled: preference.inAppEnabled,
          expectedVersion: preference.version,
        }),
      });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error("USAGE_ALERT_SAVE_FAILED");
      setInsights((current) => current.kind === "ready"
        ? { ...current, preference: parsePreference(body) }
        : current);
    } catch {
      setInsights({ kind: "error", message: "提醒设置保存失败，请刷新后重试。" });
    } finally {
      setSavingAlerts(false);
    }
  };

  const updatePreference = (change: Partial<AlertPreference>) => {
    setInsights((current) => current.kind === "ready"
      ? { ...current, preference: { ...current.preference, ...change } }
      : current);
  };

  const toggleThreshold = (threshold: number) => {
    if (insights.kind !== "ready") return;
    const current = insights.preference.thresholdBps;
    const next = current.includes(threshold)
      ? current.filter((value) => value !== threshold)
      : [...current, threshold].sort((left, right) => left - right);
    if (next.length > 0) updatePreference({ thresholdBps: next });
  };

  const exportQuery = useMemo(() => {
    const to = new Date();
    const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1_000);
    return new URLSearchParams({
      from: from.toISOString(),
      to: to.toISOString(),
      bucket: "DAY",
    }).toString();
  }, []);

  return (
    <section className={styles.dashboard} aria-labelledby="live-usage-title">
      <div className={styles.intro}>
        <span className="overline">LIVE USAGE</span>
        <h2 id="live-usage-title">实时查看 Token 与 Credit 消耗</h2>
        <p>
          每 5 秒读取一次 PostgreSQL 原子计量账本。已结算与处理中额度分别显示；
          页面隐藏时暂停刷新，返回后立即同步。
        </p>
      </div>

      {allowLocalCredentials && !session && (
        <form className={styles.connection} onSubmit={connect}>
          <label>
            <span>本地租户标识</span>
            <input
              aria-label="用量租户标识"
              value={form.tenantId}
              onChange={(event) => setForm((current) => ({ ...current, tenantId: event.target.value }))}
              pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
              required
              autoComplete="off"
            />
          </label>
          <label>
            <span>本地用户标识</span>
            <input
              aria-label="用量用户标识"
              value={form.actorId}
              onChange={(event) => setForm((current) => ({ ...current, actorId: event.target.value }))}
              pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
              required
              autoComplete="off"
            />
          </label>
          <label className={styles.tokenField}>
            <span>本地短期令牌</span>
            <input
              aria-label="用量短期访问令牌"
              type="password"
              value={form.token}
              onChange={(event) => setForm((current) => ({ ...current, token: event.target.value }))}
              minLength={24}
              required
              autoComplete="off"
            />
          </label>
          <button className="button button-primary" type="submit">
            连接本地用量 <Icon name="arrow" size={15} />
          </button>
        </form>
      )}

      {session && (
        <div className={styles.sessionBar}>
          <div>
            <span className={styles.liveDot} aria-hidden="true" />
            <strong>{readState.kind === "loading" ? "正在同步" : "账户计量已连接"}</strong>
            <small>
              {session.kind === "account"
                ? "安全账户会话 · 租户由身份声明确定"
                : `${session.credentials.tenantId} · ${session.credentials.actorId}`}
            </small>
          </div>
          {session.kind === "local" && (
            <button
              className="button button-secondary"
              type="button"
              onClick={() => {
                setSession(null);
                setForm(emptyCredentials);
                setReadState({ kind: "idle" });
              }}
            >
              断开本地连接
            </button>
          )}
        </div>
      )}

      <div className={styles.announcement} aria-live="polite" aria-atomic="true">
        {readState.kind === "idle" && "连接本地开发凭证后显示可信用量。"}
        {readState.kind === "loading" && "正在读取最新用量。"}
        {error && `${error.code}：${error.message}`}
        {readState.kind === "current" && (
          snapshot?.status === "CURRENT"
            ? "已同步全部已对账用量。"
            : `当前有 ${snapshot?.unreconciledEventCount ?? 0} 条未对账事件。`
        )}
      </div>

      {error && (
        <div className={styles.errorNotice} role="alert">
          <Icon name={error.status === "NOT_CONFIGURED" ? "clock" : "help"} size={17} />
          <div>
            <strong>{error.status === "NOT_CONFIGURED" ? "计量源尚未就绪" : "实时读数暂不可用"}</strong>
            <span>{error.message}</span>
          </div>
        </div>
      )}

      {snapshot && (
        <>
          <div className={styles.snapshotHead}>
            <div>
              <span>当前计划</span>
              <strong>{snapshot.plan.displayName}</strong>
              <small>{snapshot.plan.planId}</small>
            </div>
            <div>
              <span>刷新状态</span>
              <strong className={snapshot.status === "PARTIAL" ? styles.warning : ""}>
                {readState.kind === "stale" ? "STALE" : snapshot.status}
              </strong>
              <small>更新于 {localTime(snapshot.generatedAt)}</small>
            </div>
            <div>
              <span>额度重置</span>
              <strong>{snapshot.period.resetsAt ? localTime(snapshot.period.resetsAt) : "到期后结束"}</strong>
              <small>{localTime(snapshot.period.startsAt)} 起</small>
            </div>
          </div>

          <div className={styles.meterGrid}>
            <UsageMeter label="模型 Token" unit="tokens" measure={snapshot.tokens} />
            <UsageMeter label="平台 Credits" unit="credits" measure={snapshot.credits} />
          </div>

          <div className={styles.evidenceLine}>
            <span><Icon name="check" size={14} />已对账事件 {snapshot.reconciledEventCount}</span>
            <span><Icon name="clock" size={14} />未对账事件 {snapshot.unreconciledEventCount}</span>
            <span>事件水位 {snapshot.eventWatermark ? localTime(snapshot.eventWatermark) : "暂无事件"}</span>
          </div>
        </>
      )}

      {!allowLocalCredentials && snapshot && (
        <section className={styles.insights} aria-labelledby="usage-insights-title">
          <div className={styles.insightsHead}>
            <div>
              <span className="overline">DETAILS & ALERTS</span>
              <h3 id="usage-insights-title">趋势、明细与提醒</h3>
            </div>
            <a className="button button-secondary" href={`/api/usage/export?${exportQuery}`}>
              导出近 30 天 CSV <Icon name="external" size={14} />
            </a>
          </div>

          {insights.kind === "loading" && <p className={styles.insightStatus}>正在读取历史明细。</p>}
          {insights.kind === "error" && <p className={styles.insightError}>{insights.message}</p>}
          {insights.kind === "ready" && (
            <>
              <div className={styles.forecast}>
                <span>额度预测</span>
                <strong>{forecast?.label}</strong>
                <small>{forecast?.detail}</small>
              </div>

              <div className={styles.historyTable} role="table" aria-label="近 30 天用量明细">
                <div className={styles.historyHead} role="row">
                  <span role="columnheader">日期</span>
                  <span role="columnheader">计量项</span>
                  <span role="columnheader">Token 类别</span>
                  <span role="columnheader">用户</span>
                  <span role="columnheader">净用量</span>
                </div>
                {insights.history.slice(-8).reverse().map((point) => (
                  <div
                    className={styles.historyRow}
                    role="row"
                    key={`${point.bucketStartsAt}-${point.meterId}-${point.tokenClass}-${point.actorId}`}
                  >
                    <span role="cell">{localDate(point.bucketStartsAt)}</span>
                    <span role="cell" title={point.operationKey}>
                      {point.meterId === "model-token-v1" ? "Token" : "Credit"}
                    </span>
                    <span role="cell">{point.tokenClass ?? "—"}</span>
                    <span role="cell">{point.actorId}</span>
                    <strong role="cell">{Number(point.net).toLocaleString("zh-CN")}</strong>
                  </div>
                ))}
                {insights.history.length === 0 && (
                  <p className={styles.emptyHistory}>近 30 天暂无已结算用量。</p>
                )}
              </div>

              <div className={styles.alertPanel}>
                <div>
                  <strong>用量阈值提醒</strong>
                  <span>达到所选比例时发送一次提醒；100% 仍由数据库硬停止。</span>
                </div>
                <div className={styles.thresholds}>
                  {alertThresholds.map((threshold) => (
                    <label key={threshold}>
                      <input
                        type="checkbox"
                        checked={insights.preference.thresholdBps.includes(threshold)}
                        onChange={() => toggleThreshold(threshold)}
                      />
                      {threshold / 100}%
                    </label>
                  ))}
                </div>
                <label className={styles.channel}>
                  <input
                    type="checkbox"
                    checked={insights.preference.inAppEnabled}
                    onChange={(event) => updatePreference({ inAppEnabled: event.target.checked })}
                  />
                  站内提醒
                </label>
                <label className={styles.channel}>
                  <input
                    type="checkbox"
                    checked={insights.preference.emailEnabled}
                    disabled={!emailAlertsEnabled}
                    onChange={(event) => updatePreference({ emailEnabled: event.target.checked })}
                  />
                  邮件提醒{emailAlertsEnabled ? "" : "（未配置）"}
                </label>
                <button
                  className="button button-primary"
                  type="button"
                  disabled={savingAlerts}
                  onClick={() => void savePreference(insights.preference)}
                >
                  {savingAlerts ? "保存中" : "保存提醒"}
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </section>
  );
}
