"use client";

import { FormEvent, useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import type { UserActivitySummary } from "../lib/operationsContracts";
import styles from "./OperationsAdmin.module.css";

const lines = [
  ["ALL", "全部业务线"],
  ["SPRING_MODERNIZATION", "Spring 老项目翻新"],
  ["LANGUAGE_TRANSLATION", "全库跨语言转换"],
  ["PROJECT_SYNTHESIS", "多语言项目生成"],
  ["REPOSITORY_WORKSPACE", "代码仓库工作区"],
  ["MIGRATION_GOVERNANCE", "迁移能力与验证"],
  ["COMMERCIALIZATION", "商业化控制面"],
  ["PRICING_USAGE", "套餐与用量"],
  ["SKILLS_QUALIFICATION", "Skills 与验证"],
  ["PRODUCT_OVERVIEW", "产品总览"],
  ["ADMIN_OPERATIONS", "管理端"],
] as const;

const lineLabels = Object.fromEntries(lines);

type LoadState = "LOCKED" | "LOADING" | "READY" | "ERROR";

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function displayTarget(value: string): string {
  return value.length > 54 ? `${value.slice(0, 51)}…` : value;
}

export function OperationsAdmin() {
  const [token, setToken] = useState("");
  const [hours, setHours] = useState("24");
  const [businessLine, setBusinessLine] = useState("ALL");
  const [result, setResult] = useState("ALL");
  const [state, setState] = useState<LoadState>("LOCKED");
  const [summary, setSummary] = useState<UserActivitySummary | null>(null);
  const [error, setError] = useState("");

  const periodLabel = useMemo(() => {
    if (!summary) return "尚未读取";
    return `${formatTime(summary.from)} — ${formatTime(summary.to)}`;
  }, [summary]);

  async function load(event?: FormEvent) {
    event?.preventDefault();
    if (token.trim().length < 24) {
      setState("ERROR");
      setError("请输入至少 24 字符的短期管理令牌。");
      return;
    }
    setState("LOADING");
    setError("");
    try {
      const query = new URLSearchParams({ hours, businessLine, result, limit: "60" });
      const response = await fetch(`/api/admin/operations?${query}`, {
        headers: { Authorization: `Bearer ${token.trim()}` },
        cache: "no-store",
      });
      const payload = await response.json() as UserActivitySummary & { message?: string };
      if (!response.ok) throw new Error(payload.message || "管理端数据读取失败。");
      setSummary(payload);
      setState("READY");
    } catch (loadError) {
      setSummary(null);
      setState("ERROR");
      setError(loadError instanceof Error ? loadError.message : "管理端数据读取失败。");
    }
  }

  function lock() {
    setToken("");
    setSummary(null);
    setError("");
    setState("LOCKED");
  }

  return (
    <div className="page-stack">
      <section className={styles.hero}>
        <div>
          <span className="overline">OPERATIONS · PRIVACY SAFE</span>
          <h1>运营管理端</h1>
          <p>用追加式操作日志定位性能退化与失败路径。日志只保存动作契约和技术指标，不保存输入内容、Token、请求体或错误原文。</p>
        </div>
        <div className={styles.heroStatus}>
          <span className={styles.statusDot} />
          <div><strong>{state === "READY" ? "数据链路已连接" : "数据链路已锁定"}</strong><small>{periodLabel}</small></div>
        </div>
      </section>

      <form className={styles.accessBar} onSubmit={load} data-telemetry-ignore="true">
        <label className={styles.tokenField}>
          <span>短期管理令牌</span>
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="仅保存在当前页面内存"
            aria-label="短期管理令牌"
          />
        </label>
        <label>
          <span>时间范围</span>
          <select value={hours} onChange={(event) => setHours(event.target.value)} aria-label="时间范围">
            <option value="1">最近 1 小时</option>
            <option value="24">最近 24 小时</option>
            <option value="168">最近 7 天</option>
            <option value="720">最近 30 天</option>
          </select>
        </label>
        <label>
          <span>业务线</span>
          <select value={businessLine} onChange={(event) => setBusinessLine(event.target.value)} aria-label="业务线">
            {lines.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          <span>结果</span>
          <select value={result} onChange={(event) => setResult(event.target.value)} aria-label="操作结果">
            <option value="ALL">全部结果</option>
            <option value="SUCCESS">成功</option>
            <option value="FAILURE">失败</option>
            <option value="CANCELLED">已取消</option>
          </select>
        </label>
        <button className="primary-button" type="submit" disabled={state === "LOADING"}>
          <Icon name={state === "LOADING" ? "refresh" : "search"} size={17} />
          {state === "LOADING" ? "读取中…" : "读取数据"}
        </button>
        {state === "READY" && <button className="secondary-button" type="button" onClick={lock}>锁定</button>}
      </form>

      {state === "LOCKED" && (
        <section className={styles.locked}>
          <span><Icon name="lock" size={24} /></span>
          <div><strong>管理数据默认锁定</strong><p>输入由运维人员签发的短期令牌后读取。令牌不会写入操作日志、localStorage 或页面 URL。</p></div>
        </section>
      )}

      {state === "ERROR" && (
        <section className={styles.error} role="alert">
          <Icon name="shield" size={21} />
          <div><strong>未能读取管理数据</strong><p>{error}</p></div>
        </section>
      )}

      {summary && (
        <>
          <section className={styles.metrics} aria-label="运营指标">
            <article><span>操作事件</span><strong>{summary.totalEvents.toLocaleString("zh-CN")}</strong><small>追加式记录</small></article>
            <article><span>活跃会话</span><strong>{summary.activeSessions.toLocaleString("zh-CN")}</strong><small>匿名会话标识</small></article>
            <article><span>失败率</span><strong>{summary.failureRate.toFixed(2)}%</strong><small>{summary.failedEvents} 次失败</small></article>
            <article><span>P95 耗时</span><strong>{summary.p95DurationMs === null ? "—" : `${summary.p95DurationMs} ms`}</strong><small>含 API 与页面性能</small></article>
          </section>

          <div className={styles.dashboardGrid}>
            <section className={styles.panel}>
              <header><div><span className="overline">BUSINESS LINES</span><h2>业务线表现</h2></div><small>失败率与 P95 耗时</small></header>
              {summary.businessLines.length === 0 ? <Empty label="所选范围内暂无事件" /> : (
                <div className={styles.lineList}>
                  {summary.businessLines.map((line) => (
                    <article key={line.businessLine}>
                      <div><strong>{lineLabels[line.businessLine] ?? line.businessLine}</strong><small>{line.eventCount} 次操作 · {line.sessionCount} 个会话</small></div>
                      <span className={line.failureRate > 5 ? styles.bad : styles.good}>{line.failureRate.toFixed(2)}%</span>
                      <em>{line.p95DurationMs === null ? "—" : `${line.p95DurationMs} ms`}</em>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className={styles.panel}>
              <header><div><span className="overline">ERROR SIGNALS</span><h2>高频错误</h2></div><small>只记录稳定错误码</small></header>
              {summary.topErrors.length === 0 ? <Empty label="所选范围内没有失败事件" /> : (
                <div className={styles.errorList}>
                  {summary.topErrors.map((item) => (
                    <article key={item.errorCode}>
                      <span>{item.count}</span>
                      <div><strong>{item.errorCode}</strong><small>最近：{formatTime(item.lastSeenAt)}</small></div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className={styles.panel}>
            <header><div><span className="overline">RECENT ACTIVITY</span><h2>最近操作</h2></div><small>{summary.persistence} · 外部生产证据 {summary.externalEvidence}</small></header>
            {summary.recentEvents.length === 0 ? <Empty label="所选范围内暂无事件" /> : (
              <div className={styles.tableWrap}>
                <table>
                  <thead><tr><th>时间</th><th>业务线</th><th>动作</th><th>目标</th><th>结果</th><th>耗时</th></tr></thead>
                  <tbody>
                    {summary.recentEvents.map((item) => (
                      <tr key={item.eventId}>
                        <td>{formatTime(item.occurredAt)}</td>
                        <td>{lineLabels[item.businessLine] ?? item.businessLine}</td>
                        <td><code>{item.action}</code></td>
                        <td title={item.target}>{displayTarget(item.target)}</td>
                        <td><span className={item.result === "FAILURE" ? styles.resultBad : styles.resultGood}>{item.result}</span>{item.errorCode && <small>{item.errorCode}</small>}</td>
                        <td>{item.durationMs === null ? "—" : `${item.durationMs} ms`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className={styles.empty}><Icon name="database" size={22} /><span>{label}</span></div>;
}
