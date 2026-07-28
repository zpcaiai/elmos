"use client";

import { type FormEvent, useEffect, useState } from "react";
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

type ReadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "current"; snapshot: CurrentUsageSnapshot }
  | { kind: "stale"; snapshot: CurrentUsageSnapshot; error: UsageApiError }
  | { kind: "error"; error: UsageApiError };

const emptyCredentials: Credentials = { tenantId: "", actorId: "", token: "" };

function percent(usageBps: number): string {
  return `${(usageBps / 100).toFixed(2)}%`;
}

function localTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
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
          <small>已消耗 {unit}</small>
        </div>
        <em className={measure.hardStop ? styles.danger : ""}>{percent(measure.usageBps)}</em>
      </div>
      <div
        className={styles.progress}
        role="progressbar"
        aria-label={`${label}消耗进度`}
        aria-valuemin={0}
        aria-valuemax={measure.limit}
        aria-valuenow={Math.min(measure.consumed, measure.limit)}
        aria-valuetext={meterLabel(label, measure.consumed, measure.limit, measure.usageBps)}
      >
        <span
          className={measure.hardStop ? styles.progressDanger : ""}
          style={{ width: `${visualPercent}%` }}
        />
      </div>
      <div className={styles.meterFoot}>
        <span>剩余 <strong>{formatQuota(measure.remaining)}</strong></span>
        <span>总额度 {formatQuota(measure.limit)}</span>
      </div>
    </article>
  );
}

export function UsageDashboard() {
  const [form, setForm] = useState<Credentials>(emptyCredentials);
  const [session, setSession] = useState<Credentials | null>(null);
  const [readState, setReadState] = useState<ReadState>({ kind: "idle" });

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
          headers: {
            "Authorization": `Bearer ${session.token}`,
            "X-ELMOS-Tenant": session.tenantId,
            "X-ELMOS-Actor": session.actorId,
          },
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

  const connect = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const credentials = {
      tenantId: form.tenantId.trim(),
      actorId: form.actorId.trim(),
      token: form.token,
    };
    setReadState({ kind: "loading" });
    setSession(credentials);
  };

  const disconnect = () => {
    setSession(null);
    setForm(emptyCredentials);
    setReadState({ kind: "idle" });
  };

  const snapshot = readState.kind === "current" || readState.kind === "stale"
    ? readState.snapshot
    : null;
  const error = readState.kind === "error" || readState.kind === "stale"
    ? readState.error
    : null;

  return (
    <section className={styles.dashboard} aria-labelledby="live-usage-title">
      <div className={styles.intro}>
        <span className="overline">LIVE USAGE</span>
        <h2 id="live-usage-title">实时查看 Token 与 Credit 消耗</h2>
        <p>
          连接当前账户后每 5 秒读取一次已对账的不可变用量事件。
          页面隐藏时暂停刷新，返回页面后立即同步；访问令牌仅保存在当前页面内存中。
        </p>
      </div>

      {!session && (
        <form className={styles.connection} onSubmit={connect}>
          <label>
            <span>租户标识</span>
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
            <span>用户标识</span>
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
            <span>短期访问令牌</span>
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
            连接实时用量 <Icon name="arrow" size={15} />
          </button>
        </form>
      )}

      {session && (
        <div className={styles.sessionBar}>
          <div>
            <span className={styles.liveDot} aria-hidden="true" />
            <strong>{readState.kind === "loading" ? "正在同步" : "已连接实时用量"}</strong>
            <small>{session.tenantId} · {session.actorId}</small>
          </div>
          <button className="button button-secondary" type="button" onClick={disconnect}>断开连接</button>
        </div>
      )}

      <div className={styles.announcement} aria-live="polite" aria-atomic="true">
        {readState.kind === "idle" && "输入当前账户的短期凭证后显示可信用量。"}
        {readState.kind === "loading" && "正在读取最新用量。"}
        {error && `${error.code}：${error.message}`}
        {readState.kind === "current" && (
          snapshot?.status === "CURRENT"
            ? "已同步全部已对账用量。"
            : `当前有 ${snapshot?.unreconciledEventCount ?? 0} 条未对账事件，进度仅包含已确认用量。`
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
    </section>
  );
}
