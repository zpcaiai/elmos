"use client";

import { FormEvent, useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { useAccountSession } from "../components/AccountSessionProvider";
import type {
  AuditExportPage,
  AuditExportRow,
  OperationsConsoleView,
  OperationsIncident,
  OperationsRemediation,
} from "../lib/operationsContracts";
import styles from "./OperationsAdmin.module.css";

const lines = [
  ["ALL", "全部业务线"],
  ["SPRING_MODERNIZATION", "Spring 老项目翻新"],
  ["LANGUAGE_TRANSLATION", "全库跨语言转换"],
  ["PROJECT_SYNTHESIS", "多语言项目生成"],
  ["REPOSITORY_WORKSPACE", "代码仓库工作区"],
  ["MIGRATION_GOVERNANCE", "迁移能力与验证"],
  ["DATABASE_DATA", "数据库与数据平台"],
  ["CLIENT_MODERNIZATION", "客户端现代化"],
  ["CLOUD_INFRASTRUCTURE", "云与基础设施"],
  ["SECURITY_COMPLIANCE", "安全与合规"],
  ["DELIVERY_GOVERNANCE", "交付治理"],
  ["COMMERCIALIZATION", "商业化控制面"],
  ["PRICING_USAGE", "套餐与用量"],
  ["SKILLS_QUALIFICATION", "Skills 与验证"],
  ["ENTERPRISE_MODERNIZATION", "企业现代化"],
  ["MAINFRAME_MODERNIZATION", "主机现代化"],
  ["SYSTEM_INTEGRATION", "系统集成"],
  ["PRODUCT_OVERVIEW", "产品总览"],
  ["ADMIN_OPERATIONS", "管理端"],
] as const;

const lineLabels = Object.fromEntries(lines);
const roleRank = { VIEWER: 1, OPERATOR: 2, APPROVER: 3 } as const;

// 200 rows per page, so this bounds one download at 200k rows. Without a
// ceiling a mistyped window turns into an unbounded request loop.
const MAX_EXPORT_PAGES = 1_000;

const EXPORT_COLUMNS = [
  "occurredAt", "source", "eventId", "sessionId", "eventKind", "action",
  "businessLine", "route", "target", "durationMs", "result", "errorCode",
] as const;

/**
 * RFC 4180 quoting. Every field is quoted rather than only the ones that need
 * it: audit values are free-form, and a value that happens to contain a comma
 * or newline would otherwise shift every later column in the row.
 */
function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '""';
  return `"${String(value).replace(/"/g, '""')}"`;
}

function downloadCsv(rows: AuditExportRow[], days: string) {
  const header = EXPORT_COLUMNS.join(",");
  const body = rows
    .map((row) => EXPORT_COLUMNS.map((column) => csvCell(row[column])).join(","))
    .join("\r\n");
  // The BOM keeps Excel from mangling non-ASCII targets on open.
  const blob = new Blob([`﻿${header}\r\n${body}\r\n`], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `elmos-audit-${days}d-${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

type LoadState = "LOCKED" | "LOADING" | "READY" | "ERROR";
type AdminAction =
  | "EVALUATE"
  | "ACKNOWLEDGE_ALERT"
  | "ASSIGN_INCIDENT"
  | "RESOLVE_INCIDENT"
  | "APPROVE_REMEDIATION"
  | "REJECT_REMEDIATION"
  | "PREPARE_SCM"
  | "ENFORCE_RETENTION";

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
  const account = useAccountSession();
  const [token, setToken] = useState("");
  const [hours, setHours] = useState("24");
  const [businessLine, setBusinessLine] = useState("ALL");
  const [result, setResult] = useState("ALL");
  const [state, setState] = useState<LoadState>("LOCKED");
  const [view, setView] = useState<OperationsConsoleView | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [exportDays, setExportDays] = useState("7");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportNotice, setExportNotice] = useState("");

  const summary = view?.activity ?? null;
  const periodLabel = useMemo(() => {
    if (!summary) return "尚未读取";
    return `${formatTime(summary.from)} — ${formatTime(summary.to)}`;
  }, [summary]);

  /**
   * Walk the export cursor to the end and hand back a CSV file.
   *
   * The proxy caps each response, so a full export is many requests. Two
   * things are deliberate here: the page ceiling below stops a mistyped window
   * from looping forever, and a partial download is never offered as a
   * complete file -- if the walk stops early the operator is told how far it
   * got, because an audit artifact that silently ends mid-window is worse than
   * no artifact.
   */
  async function downloadAuditExport() {
    if (account.status !== "authenticated" && token.trim().length < 24) {
      setExportError("请输入至少 24 字符的短期管理令牌。");
      return;
    }
    setExportBusy(true);
    setExportError("");
    setExportNotice("");
    const rows: AuditExportRow[] = [];
    let cursor: { at: string; id: string } | null = null;
    let truncated = false;
    try {
      for (let page = 0; ; page++) {
        if (page >= MAX_EXPORT_PAGES) {
          truncated = true;
          break;
        }
        const query = new URLSearchParams({
          days: exportDays,
          businessLine,
          result,
          limit: "200",
        });
        if (cursor) {
          query.set("afterOccurredAt", cursor.at);
          query.set("afterEventId", cursor.id);
        }
        const response = await fetch(`/api/admin/audit-export?${query}`, {
          headers: token.trim() ? { Authorization: `Bearer ${token.trim()}` } : undefined,
          credentials: "same-origin",
          cache: "no-store",
        });
        const payload = await response.json() as AuditExportPage & { message?: string };
        if (!response.ok) throw new Error(payload.message || "审计导出读取失败。");
        rows.push(...payload.rows);
        if (!payload.hasMore || !payload.nextOccurredAt || !payload.nextEventId) break;
        cursor = { at: payload.nextOccurredAt, id: payload.nextEventId };
      }
      if (rows.length === 0) {
        setExportNotice("所选窗口内没有审计记录。");
        return;
      }
      downloadCsv(rows, exportDays);
      setExportNotice(
        truncated
          ? `已导出前 ${rows.length} 行后停止：窗口过大，请缩短天数或收窄业务线后重新导出。`
          : `已导出 ${rows.length} 行。`,
      );
    } catch (downloadError) {
      setExportError(
        downloadError instanceof Error ? downloadError.message : "审计导出读取失败。",
      );
    } finally {
      setExportBusy(false);
    }
  }

  async function loadData() {
    if (account.status !== "authenticated" && token.trim().length < 24) {
      setState("ERROR");
      setError("请输入至少 24 字符的短期管理令牌。");
      return;
    }
    setState("LOADING");
    setError("");
    try {
      const query = new URLSearchParams({ hours, businessLine, result, limit: "60" });
      const response = await fetch(`/api/admin/operations?${query}`, {
        headers: token.trim()
          ? { Authorization: `Bearer ${token.trim()}` }
          : undefined,
        credentials: "same-origin",
        cache: "no-store",
      });
      const payload = await response.json() as OperationsConsoleView & { message?: string };
      if (!response.ok) throw new Error(payload.message || "管理端数据读取失败。");
      setView(payload);
      setState("READY");
    } catch (loadError) {
      setView(null);
      setState("ERROR");
      setError(loadError instanceof Error ? loadError.message : "管理端数据读取失败。");
    }
  }

  async function load(event?: FormEvent) {
    event?.preventDefault();
    await loadData();
  }

  async function mutate(action: AdminAction, body: Record<string, unknown> = {}) {
    setBusyAction(action);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/admin/operations", {
        method: "POST",
        headers: {
          ...(token.trim() ? { Authorization: `Bearer ${token.trim()}` } : {}),
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({ action, ...body }),
      });
      const payload = await response.json() as { message?: string; status?: string; decision?: string };
      if (!response.ok) throw new Error(payload.message || "管理操作执行失败。");
      setNotice(`操作已完成：${payload.status ?? payload.decision ?? action}`);
      await loadData();
    } catch (actionError) {
      setState("READY");
      setError(actionError instanceof Error ? actionError.message : "管理操作执行失败。");
    } finally {
      setBusyAction("");
    }
  }

  function lock() {
    setToken("");
    setView(null);
    setError("");
    setNotice("");
    setState("LOCKED");
  }

  function can(required: keyof typeof roleRank): boolean {
    return Boolean(view && roleRank[view.role] >= roleRank[required]);
  }

  return (
    <div className="page-stack">
      <section className={styles.hero}>
        <div>
          <span className="overline">OPERATIONS · GOVERNED AUTOMATION</span>
          <h1>生产运营管理端</h1>
          <p>统一查看业务操作、SLO、告警、事件和修复提案。自动化负责检测、诊断与生成摘要绑定的修复计划；审批、源码变更、测试、SCM 与部署保持权限分离。</p>
        </div>
        <div className={styles.heroStatus}>
          <span className={styles.statusDot} />
          <div>
            <strong>{state === "READY" ? `已连接 · ${view?.role}` : "数据链路已锁定"}</strong>
            <small>{periodLabel}</small>
          </div>
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
            placeholder={account.status === "authenticated" ? "已使用企业账户，无需填写" : "仅保存在当前页面内存"}
            aria-label="短期管理令牌"
            disabled={account.status === "authenticated"}
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

      {state === "READY" && (
        <section className={styles.panel} aria-label="审计导出">
          <h2><Icon name="file" size={18} /> 审计导出</h2>
          <p>
            导出所选窗口内的原始审计与遥测记录（CSV）。按游标逐页读取，
            结果与上方筛选的业务线、结果保持一致；时间窗口在此单独选择。
          </p>
          <div className={styles.inlineActions}>
            <label>
              <span>窗口</span>
              <select
                value={exportDays}
                onChange={(event) => setExportDays(event.target.value)}
                aria-label="导出时间窗口"
                disabled={exportBusy}
              >
                <option value="1">最近 1 天</option>
                <option value="7">最近 7 天</option>
                <option value="30">最近 30 天</option>
                <option value="90">最近 90 天</option>
                <option value="366">最近 366 天</option>
              </select>
            </label>
            <button
              className="secondary-button"
              type="button"
              onClick={downloadAuditExport}
              disabled={exportBusy}
            >
              <Icon name={exportBusy ? "refresh" : "box"} size={17} />
              {exportBusy ? "导出中…" : "导出 CSV"}
            </button>
          </div>
          {exportError && <p className={styles.bad} role="alert">{exportError}</p>}
          {exportNotice && <p className={styles.good} role="status">{exportNotice}</p>}
        </section>
      )}

      {state === "LOCKED" && (
        <section className={styles.locked}>
          <span><Icon name="lock" size={24} /></span>
          <div><strong>管理数据默认锁定</strong><p>生产优先使用企业账户的 admin 权限；本地或获批 break-glass 才使用短期令牌。角色均由服务端决定，页面不能自行提升。</p></div>
        </section>
      )}

      {error && (
        <section className={styles.error} role="alert">
          <Icon name="shield" size={21} />
          <div><strong>管理操作未完成</strong><p>{error}</p></div>
        </section>
      )}
      {notice && <section className={styles.notice} role="status">{notice}</section>}

      {summary && view && (
        <>
          <section className={styles.actionStrip}>
            <div>
              <strong>自动化控制</strong>
              <small>{view.control.automationMode} · 源码修改 {view.control.sourceMutationMode}</small>
            </div>
            <span>待发送通知 {view.control.pendingNotifications}</span>
            <button
              className="primary-button"
              type="button"
              disabled={!can("OPERATOR") || Boolean(busyAction)}
              onClick={() => mutate("EVALUATE")}
            >
              立即评估全部 SLO
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!can("APPROVER") || Boolean(busyAction)}
              onClick={() => mutate("ENFORCE_RETENTION", { retentionDays: 30 })}
            >
              执行 30 天保留
            </button>
          </section>

          <section className={styles.metrics} aria-label="运营指标">
            <article><span>操作事件</span><strong>{summary.totalEvents.toLocaleString("zh-CN")}</strong><small>审计 + 可删除性能遥测</small></article>
            <article><span>活跃会话</span><strong>{summary.activeSessions.toLocaleString("zh-CN")}</strong><small>服务端 HMAC 会话</small></article>
            <article><span>失败率</span><strong>{summary.failureRate.toFixed(2)}%</strong><small>{summary.failedEvents} 次失败</small></article>
            <article><span>P95 耗时</span><strong>{summary.p95DurationMs === null ? "—" : `${summary.p95DurationMs} ms`}</strong><small>API 与页面性能</small></article>
          </section>

          <div className={styles.dashboardGrid}>
            <section className={styles.panel}>
              <header><div><span className="overline">BUSINESS LINES</span><h2>所有业务线表现</h2></div><small>失败率与 P95 耗时</small></header>
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
            <header><div><span className="overline">SLO & ALERTS</span><h2>SLO 与告警</h2></div><small>{view.control.policies.length} 条业务线策略</small></header>
            <div className={styles.cardGrid}>
              {view.control.alerts.length === 0 ? <Empty label="当前没有告警" /> : view.control.alerts.map((alert) => (
                <article className={styles.controlCard} key={alert.alertId}>
                  <div><span className={styles.severity}>{alert.severity}</span><strong>{lineLabels[alert.businessLine] ?? alert.businessLine}</strong></div>
                  <code>{alert.signal}</code>
                  <p>{alert.observedValue} / 预算 {alert.thresholdValue} · {alert.status}</p>
                  {alert.status !== "RESOLVED" && alert.status !== "ACKNOWLEDGED" && (
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={!can("OPERATOR") || Boolean(busyAction)}
                      onClick={() => mutate("ACKNOWLEDGE_ALERT", {
                        alertId: alert.alertId,
                        expectedVersion: alert.version,
                      })}
                    >
                      确认告警
                    </button>
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className={styles.panel}>
            <header><div><span className="overline">INCIDENTS</span><h2>生产事件</h2></div><small>负责人、状态和并发版本均受控</small></header>
            <div className={styles.cardGrid}>
              {view.control.incidents.length === 0 ? <Empty label="当前没有生产事件" /> : view.control.incidents.map((incident) => (
                <IncidentCard
                  key={incident.incidentId}
                  incident={incident}
                  actorId={view.actorId}
                  disabled={!can("OPERATOR") || Boolean(busyAction)}
                  mutate={mutate}
                />
              ))}
            </div>
          </section>

          <section className={styles.panel}>
            <header><div><span className="overline">QUICK FIX GOVERNANCE</span><h2>性能优化与 Bug 修复提案</h2></div><small>预览、审批、SCM 准备、验证、回滚</small></header>
            <div className={styles.cardGrid}>
              {view.control.remediations.length === 0 ? <Empty label="尚无修复提案；先运行 SLO 评估" /> : view.control.remediations.map((proposal) => (
                <RemediationCard
                  key={proposal.proposalId}
                  proposal={proposal}
                  disabled={!can("APPROVER") || Boolean(busyAction)}
                  mutate={mutate}
                />
              ))}
            </div>
          </section>

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

          <section className={styles.evidence}>
            <strong>外部门禁</strong>
            <span>通知投递：{view.control.notificationDeliveryEvidence}</span>
            <span>生产部署：{view.control.productionDeploymentEvidence}</span>
            <span>保留执行：{view.control.retentionRuns.length ? "有本地/当前环境证据" : "NOT_RUN"}</span>
          </section>
        </>
      )}
    </div>
  );
}

function IncidentCard({
  incident,
  actorId,
  disabled,
  mutate,
}: {
  incident: OperationsIncident;
  actorId: string;
  disabled: boolean;
  mutate: (action: AdminAction, body?: Record<string, unknown>) => Promise<void>;
}) {
  return (
    <article className={styles.controlCard}>
      <div><span className={styles.severity}>{incident.severity}</span><strong>{incident.summaryCode}</strong></div>
      <p>{lineLabels[incident.businessLine] ?? incident.businessLine} · {incident.status}</p>
      <small>负责人：{incident.ownerActorId}</small>
      {incident.status !== "RESOLVED" && (
        <div className={styles.inlineActions}>
          <button
            className="secondary-button"
            type="button"
            disabled={disabled}
            onClick={() => mutate("ASSIGN_INCIDENT", {
              incidentId: incident.incidentId,
              ownerActorId: actorId,
              expectedVersion: incident.version,
            })}
          >
            接手
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={disabled}
            onClick={() => mutate("RESOLVE_INCIDENT", {
              incidentId: incident.incidentId,
              resolutionCode: "OPERATOR_VERIFIED_RESOLUTION",
              expectedVersion: incident.version,
            })}
          >
            标记已解决
          </button>
        </div>
      )}
    </article>
  );
}

function RemediationCard({
  proposal,
  disabled,
  mutate,
}: {
  proposal: OperationsRemediation;
  disabled: boolean;
  mutate: (action: AdminAction, body?: Record<string, unknown>) => Promise<void>;
}) {
  return (
    <article className={styles.controlCard}>
      <div><span className={styles.kind}>{proposal.remediationKind}</span><strong>{proposal.titleCode}</strong></div>
      <code>{proposal.recipeId}</code>
      <p>{proposal.status} · 风险 {proposal.riskLevel}</p>
      <small title={proposal.preconditionDigest}>前置摘要：{proposal.preconditionDigest.slice(0, 24)}…</small>
      {proposal.status === "PROPOSED" && (
        <div className={styles.inlineActions}>
          <button
            className="primary-button"
            type="button"
            disabled={disabled}
            onClick={() => mutate("APPROVE_REMEDIATION", {
              proposalId: proposal.proposalId,
              expectedVersion: proposal.version,
            })}
          >
            批准
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={disabled}
            onClick={() => mutate("REJECT_REMEDIATION", {
              proposalId: proposal.proposalId,
              expectedVersion: proposal.version,
            })}
          >
            拒绝
          </button>
        </div>
      )}
      {proposal.status === "APPROVED" && (
        <button
          className="primary-button"
          type="button"
          disabled={disabled}
          onClick={() => mutate("PREPARE_SCM", {
            proposalId: proposal.proposalId,
            expectedVersion: proposal.version,
          })}
        >
          生成摘要绑定 SCM 计划
        </button>
      )}
      {proposal.artifactDigest && <small title={proposal.artifactDigest}>产物摘要：{proposal.artifactDigest.slice(0, 24)}…</small>}
    </article>
  );
}

function Empty({ label }: { label: string }) {
  return <div className={styles.empty}><Icon name="database" size={22} /><span>{label}</span></div>;
}
