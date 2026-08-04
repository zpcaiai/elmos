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
  RunReplayTimeline,
  TenantQuotaView,
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
type AdminSection = "USERS" | "TASKS" | "REPOSITORIES" | "AUDIT" | "ALERTS" | "USAGE" | "CONFIG";
const adminSections: Array<[AdminSection, string]> = [
  ["USERS", "用户与租户"],
  ["TASKS", "任务队列"],
  ["REPOSITORIES", "仓库"],
  ["AUDIT", "审计"],
  ["ALERTS", "告警与事件"],
  ["USAGE", "用量与性能"],
  ["CONFIG", "配置与门禁"],
];
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
  const [replayRunId, setReplayRunId] = useState("");
  const [replayBusy, setReplayBusy] = useState(false);
  const [replayError, setReplayError] = useState("");
  const [replay, setReplay] = useState<RunReplayTimeline | null>(null);
  const [quota, setQuota] = useState<TenantQuotaView | null>(null);
  const [quotaBusy, setQuotaBusy] = useState(false);
  const [quotaError, setQuotaError] = useState("");
  const [quotaNotice, setQuotaNotice] = useState("");
  const [quotaTokenLimit, setQuotaTokenLimit] = useState("");
  const [quotaCreditLimit, setQuotaCreditLimit] = useState("");
  const [quotaReason, setQuotaReason] = useState("");
  const [adminSection, setAdminSection] = useState<AdminSection>("USERS");

  const summary = view?.activity ?? null;
  const periodLabel = useMemo(() => {
    if (!summary) return "尚未读取";
    return `${formatTime(summary.from)} — ${formatTime(summary.to)}`;
  }, [summary]);
  const taskEvents = useMemo(
    () => (summary?.recentEvents ?? []).filter((event) =>
      ["SPRING_MODERNIZATION", "LANGUAGE_TRANSLATION", "PROJECT_SYNTHESIS"]
        .includes(event.businessLine)
      || /(JOB|RUN|PIPELINE|UPGRADE|TRANSLATION|GENERATION)/.test(event.action)),
    [summary],
  );
  const repositoryEvents = useMemo(
    () => (summary?.recentEvents ?? []).filter((event) =>
      event.businessLine === "REPOSITORY_WORKSPACE"
      || event.action.startsWith("REPOSITORY_")),
    [summary],
  );

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

  /**
   * Reconstructs one run's history.
   *
   * A single request, not a cursor walk: one run's history is bounded by the
   * run. The endpoint returns each section with a `truncated` flag instead of
   * silently shortening, and the rendering below surfaces it -- a replay that
   * looks whole while missing the failed attempt is the one failure mode worth
   * spending screen space on.
   *
   * 404 is deliberately not distinguished from "belongs to another tenant":
   * upstream returns the same status for both so this page cannot leak the
   * difference even by accident.
   */
  async function loadReplay() {
    const runId = replayRunId.trim();
    if (!runId) {
      setReplayError("请输入迁移运行 ID。");
      return;
    }
    if (account.status !== "authenticated" && token.trim().length < 24) {
      setReplayError("请输入至少 24 字符的短期管理令牌。");
      return;
    }
    setReplayBusy(true);
    setReplayError("");
    setReplay(null);
    try {
      const response = await fetch(`/api/admin/run-replay/${encodeURIComponent(runId)}`, {
        headers: token.trim() ? { Authorization: `Bearer ${token.trim()}` } : undefined,
        credentials: "same-origin",
        cache: "no-store",
      });
      const payload = await response.json() as RunReplayTimeline & { message?: string };
      if (!response.ok) {
        throw new Error(
          response.status === 404
            ? "本租户下没有这个运行 ID。"
            : payload.message || "运行历史读取失败。",
        );
      }
      setReplay(payload);
    } catch (replayFailure) {
      setReplayError(
        replayFailure instanceof Error ? replayFailure.message : "运行历史读取失败。",
      );
    } finally {
      setReplayBusy(false);
    }
  }

  /**
   * Reads the tenant's allowance and seeds the adjustment form from it.
   *
   * Seeding matters: the form carries `allocationVersion` back on submit, and
   * an operator who typed a version by hand would eventually type a stale one
   * that happened to match. Filling both limits with the current values also
   * means the common case -- change one number -- cannot accidentally reset the
   * other to zero.
   */
  async function loadQuota() {
    if (account.status !== "authenticated" && token.trim().length < 24) {
      setQuotaError("请输入至少 24 字符的短期管理令牌。");
      return;
    }
    setQuotaBusy(true);
    setQuotaError("");
    setQuotaNotice("");
    try {
      const response = await fetch("/api/admin/tenant-quota", {
        headers: token.trim() ? { Authorization: `Bearer ${token.trim()}` } : undefined,
        credentials: "same-origin",
        cache: "no-store",
      });
      const payload = await response.json() as TenantQuotaView & { message?: string };
      if (!response.ok) throw new Error(payload.message || "配额读取失败。");
      setQuota(payload);
      setQuotaTokenLimit(payload.tokenLimit);
      setQuotaCreditLimit(payload.creditLimit);
    } catch (quotaFailure) {
      setQuota(null);
      setQuotaError(quotaFailure instanceof Error ? quotaFailure.message : "配额读取失败。");
    } finally {
      setQuotaBusy(false);
    }
  }

  /**
   * Submits an adjustment against the version that was read.
   *
   * A 409 means someone else changed the allowance since this screen was drawn.
   * It is surfaced as an instruction to re-read rather than retried, because
   * retrying would apply this operator's intent on top of a change they never
   * saw -- which is the exact outcome the version check exists to prevent.
   */
  async function submitQuotaAdjustment(event: FormEvent) {
    event.preventDefault();
    if (!quota) return;
    setQuotaBusy(true);
    setQuotaError("");
    setQuotaNotice("");
    try {
      const response = await fetch("/api/admin/tenant-quota", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token.trim() ? { Authorization: `Bearer ${token.trim()}` } : {}),
        },
        credentials: "same-origin",
        cache: "no-store",
        body: JSON.stringify({
          quotaAllocationId: quota.quotaAllocationId,
          tokenLimit: quotaTokenLimit.trim(),
          creditLimit: quotaCreditLimit.trim(),
          expectedVersion: quota.allocationVersion,
          reasonCode: quotaReason.trim().toUpperCase(),
        }),
      });
      const payload = await response.json() as TenantQuotaView & { message?: string };
      if (!response.ok) {
        throw new Error(
          response.status === 409
            ? "配额已被其他管理员改动，请重新读取后再调整。"
            : payload.message || "配额调整失败。",
        );
      }
      setQuota(payload);
      setQuotaTokenLimit(payload.tokenLimit);
      setQuotaCreditLimit(payload.creditLimit);
      setQuotaReason("");
      setQuotaNotice(`已调整，当前版本 ${payload.allocationVersion}。`);
    } catch (adjustFailure) {
      setQuotaError(adjustFailure instanceof Error ? adjustFailure.message : "配额调整失败。");
    } finally {
      setQuotaBusy(false);
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

      {state === "READY" && adminSection === "AUDIT" && (
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

      {state === "READY" && adminSection === "AUDIT" && (
        <section className={styles.panel} aria-label="运行历史回放">
          <h2><Icon name="clock" size={18} /> 运行历史回放</h2>
          <p>
            按迁移运行 ID 重建一次运行的完整过程：每一次步骤尝试、沿途产出的证据、
            以及点名这次运行的审计记录。只读重建，不会改动被回放的记录。
          </p>
          <div className={styles.inlineActions}>
            <label>
              <span>运行 ID</span>
              <input
                value={replayRunId}
                onChange={(event) => setReplayRunId(event.target.value)}
                aria-label="迁移运行 ID"
                placeholder="migration-run-…"
                disabled={replayBusy}
              />
            </label>
            <button
              className="secondary-button"
              type="button"
              onClick={loadReplay}
              disabled={replayBusy}
            >
              <Icon name={replayBusy ? "refresh" : "search"} size={17} />
              {replayBusy ? "读取中…" : "回放"}
            </button>
          </div>
          {replayError && <p className={styles.bad} role="alert">{replayError}</p>}

          {replay && (
            <div className={styles.evidence}>
              <p>
                <strong>{replay.migrationRunId}</strong> · 状态 {replay.state} ·
                计划 {replay.migrationPlanId} v{replay.planVersion} · 快照 {replay.snapshotId}
              </p>

              <h3>步骤尝试（{replay.steps.rows.length}）</h3>
              {replay.steps.truncated && (
                <p className={styles.bad} role="alert">
                  步骤过多，仅显示前 {replay.steps.rows.length} 条——这份回放不完整，不能作为完整凭据。
                </p>
              )}
              <div className={styles.tableWrap}>
                <table>
                  <thead>
                    <tr><th>步骤</th><th>第几次</th><th>状态</th><th>开始</th><th>结束</th><th>失败码</th></tr>
                  </thead>
                  <tbody>
                    {replay.steps.rows.map((attempt) => (
                      <tr key={attempt.stepRunId}>
                        <td>{attempt.stepId}</td>
                        <td>{attempt.attempt}</td>
                        <td className={attempt.failureCode ? styles.resultBad : styles.resultGood}>
                          {attempt.state}
                        </td>
                        <td>{attempt.startedAt ?? "未开始"}</td>
                        <td>{attempt.finishedAt ?? "—"}</td>
                        <td>{attempt.failureCode ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>证据（{replay.evidence.rows.length}）</h3>
              {replay.evidence.truncated && (
                <p className={styles.bad} role="alert">
                  证据过多，仅显示前 {replay.evidence.rows.length} 条——这份回放不完整。
                </p>
              )}
              {replay.evidence.rows.length === 0 ? (
                <p className={styles.empty}>这次运行没有留下证据记录。</p>
              ) : (
                <ul className={styles.lineList}>
                  {replay.evidence.rows.map((item) => (
                    <li key={item.evidenceId}>
                      <span className={styles.kind}>{item.evidenceType}</span>
                      {item.producerName} {item.producerVersion} · {item.status} · {item.summary}
                    </li>
                  ))}
                </ul>
              )}

              <h3>审计（{replay.audit.rows.length}）</h3>
              {replay.audit.truncated && (
                <p className={styles.bad} role="alert">
                  审计记录过多，仅显示前 {replay.audit.rows.length} 条——这份回放不完整。
                </p>
              )}
              {replay.audit.rows.length === 0 ? (
                <p className={styles.empty}>
                  没有点名这次运行的审计记录。审计行通过 resource_id 关联，未设置该字段的行不会出现在这里。
                </p>
              ) : (
                <ul className={styles.lineList}>
                  {replay.audit.rows.map((entry) => (
                    <li key={entry.auditId}>
                      <span className={styles.kind}>{entry.action}</span>
                      {entry.actorType} {entry.actorId} · {entry.policyDecision} · {entry.result}
                      {entry.occurredAt ? ` · ${entry.occurredAt}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
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

      {state === "READY" && (
        <nav className={styles.sectionNav} aria-label="管理端功能">
          {adminSections.map(([value, label]) => (
            <button key={value} type="button"
              aria-current={adminSection === value ? "page" : undefined}
              className={adminSection === value ? styles.activeSection : ""}
              onClick={() => setAdminSection(value)}>
              {label}
            </button>
          ))}
        </nav>
      )}

      {summary && view && (
        <>
          {adminSection === "USERS" && (
            <section className={styles.panel}>
              <header>
                <div><span className="overline">IDENTITY & TENANCY</span><h2>用户、角色与租户成员资格</h2></div>
                <small>来源：当前已验证 OIDC 会话</small>
              </header>
              <div className={styles.identityGrid}>
                <article>
                  <span>当前用户</span>
                  <strong>{account.principal?.displayName ?? view.actorId}</strong>
                  <small>{account.principal?.email ?? view.actorId}</small>
                </article>
                <article>
                  <span>当前租户</span>
                  <strong>{account.principal?.organizationId ?? "受控本地租户"}</strong>
                  <small>管理角色 {view.role}</small>
                </article>
                <article>
                  <span>权限</span>
                  <strong>{account.principal?.permissions.length ?? 0}</strong>
                  <small>{account.principal?.permissions.join(" · ") || "由短期管理凭据决定"}</small>
                </article>
              </div>
              <div className={styles.membershipList}>
                {(account.principal?.memberships ?? []).map((membership) => (
                  <article key={membership.organizationId}>
                    <div><strong>{membership.organizationId}</strong><small>{membership.roles.join(" · ")}</small></div>
                    <span>{membership.permissions.length} 项权限</span>
                  </article>
                ))}
                {(account.principal?.memberships.length ?? 0) === 0
                  && <Empty label="外部 IdP 全量用户目录同步尚未执行；不会据当前会话推断其他用户。" />}
              </div>
            </section>
          )}

          {adminSection === "TASKS" && (
            <section className={styles.panel}>
              <header><div><span className="overline">DURABLE JOB CONTROL</span><h2>三条业务线任务</h2></div><small>持久状态、租约、TTL 与结果信号</small></header>
              <EventTable events={taskEvents} empty="所选窗口内没有任务事件" />
              <p className={styles.boundaryNote}>队列容量与租约由 Runner 持久层执行；此页不会通过前端按钮跳过租约、重试门禁或独立验证。</p>
            </section>
          )}

          {adminSection === "REPOSITORIES" && (
            <section className={styles.panel}>
              <header><div><span className="overline">REPOSITORY GOVERNANCE</span><h2>仓库工作区与交付操作</h2></div><small>拉取、变更、Commit、Push、PR</small></header>
              <EventTable events={repositoryEvents} empty="所选窗口内没有仓库操作" />
              <div className={styles.inlineActions}>
                <a className="secondary-button" href="/repositories">打开仓库工作区</a>
              </div>
            </section>
          )}

          {(adminSection === "ALERTS" || adminSection === "CONFIG") && <section className={styles.actionStrip}>
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
              data-operation-id="admin.slo.evaluate"
            >
              立即评估全部 SLO
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!can("APPROVER") || Boolean(busyAction)}
              onClick={() => mutate("ENFORCE_RETENTION", { retentionDays: 30 })}
              data-operation-id="admin.retention.enforce"
            >
              执行 30 天保留
            </button>
          </section>}

          {adminSection === "USAGE" && <section className={styles.panel} aria-label="租户配额">
            <h2><Icon name="database" size={18} /> 租户配额</h2>
            <p>
              读取需要 VIEWER，调整需要 APPROVER。调高会产生费用，调低会中断租户已被允许的工作，
              因此与审批修复提案同级——两个动作故意设成不同门槛，否则只为看一个数字就得共用审批凭据。
            </p>
            <div className={styles.inlineActions}>
              <button
                className="secondary-button"
                type="button"
                onClick={loadQuota}
                disabled={quotaBusy}
              >
                <Icon name={quotaBusy ? "refresh" : "search"} size={17} />
                {quotaBusy ? "读取中…" : "读取当前配额"}
              </button>
            </div>
            {quotaError && <p className={styles.bad} role="alert">{quotaError}</p>}
            {quotaNotice && <p className={styles.good} role="status">{quotaNotice}</p>}

            {quota && (
              <div className={styles.evidence}>
                <p>
                  <strong>{quota.planDisplayName}</strong>（{quota.planId}） · 版本 {quota.allocationVersion} ·
                  周期 {formatTime(quota.periodStartsAt)} — {formatTime(quota.periodEndsAt)}
                </p>
                <div className={styles.tableWrap}>
                  <table>
                    <thead>
                      <tr><th>额度</th><th>上限</th><th>已消耗</th><th>已预留</th><th>下限</th></tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Token</td><td>{quota.tokenLimit}</td>
                        <td>{quota.consumedTokens}</td><td>{quota.reservedTokens}</td>
                        <td>{quota.minimumTokenLimit}</td>
                      </tr>
                      <tr>
                        <td>Credit</td><td>{quota.creditLimit}</td>
                        <td>{quota.consumedCredits}</td><td>{quota.reservedCredits}</td>
                        <td>{quota.minimumCreditLimit}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                {/*
                  The floor is shown before the operator types, not after the
                  server refuses. It is consumed + reserved: a reservation is a
                  promise already made to the tenant, so lowering a limit
                  underneath one would retract work the tenant was told it could
                  perform.
                */}
                <p>下限为「已消耗 + 已预留」，低于它的调整会被拒绝——预留是已经对租户作出的承诺。</p>

                {can("APPROVER") ? (
                  <form className={styles.inlineActions} onSubmit={submitQuotaAdjustment}>
                    <label>
                      <span>Token 上限</span>
                      <input
                        value={quotaTokenLimit}
                        onChange={(event) => setQuotaTokenLimit(event.target.value)}
                        aria-label="调整后的 Token 上限"
                        inputMode="decimal"
                        disabled={quotaBusy}
                        required
                      />
                    </label>
                    <label>
                      <span>Credit 上限</span>
                      <input
                        value={quotaCreditLimit}
                        onChange={(event) => setQuotaCreditLimit(event.target.value)}
                        aria-label="调整后的 Credit 上限"
                        inputMode="decimal"
                        disabled={quotaBusy}
                        required
                      />
                    </label>
                    <label>
                      <span>调整原因代号</span>
                      <input
                        value={quotaReason}
                        onChange={(event) => setQuotaReason(event.target.value)}
                        aria-label="调整原因代号"
                        placeholder="PLAN_UPGRADE"
                        pattern="[A-Za-z][A-Za-z0-9_]{2,47}"
                        title="大写字母、数字与下划线组成的代号，例如 PLAN_UPGRADE。原因会写入只读审计流水与导出。"
                        disabled={quotaBusy}
                        required
                      />
                    </label>
                    <button className="primary-button" type="submit" disabled={quotaBusy}>
                      <Icon name={quotaBusy ? "refresh" : "check"} size={17} />
                      {quotaBusy ? "提交中…" : "按版本 " + quota.allocationVersion + " 提交调整"}
                    </button>
                  </form>
                ) : (
                  <p>当前角色为 {view.role}，只能查看配额；调整需要 APPROVER。</p>
                )}
              </div>
            )}
          </section>}

          {adminSection === "USAGE" && <section className={styles.metrics} aria-label="运营指标">
            <article><span>操作事件</span><strong>{summary.totalEvents.toLocaleString("zh-CN")}</strong><small>审计 + 可删除性能遥测</small></article>
            <article><span>活跃会话</span><strong>{summary.activeSessions.toLocaleString("zh-CN")}</strong><small>服务端 HMAC 会话</small></article>
            <article><span>失败率</span><strong>{summary.failureRate.toFixed(2)}%</strong><small>{summary.failedEvents} 次失败</small></article>
            <article><span>P95 耗时</span><strong>{summary.p95DurationMs === null ? "—" : `${summary.p95DurationMs} ms`}</strong><small>API 与页面性能</small></article>
          </section>}

          {adminSection === "USAGE" && <div className={styles.dashboardGrid}>
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
          </div>}

          {adminSection === "ALERTS" && <section className={styles.panel}>
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
          </section>}

          {adminSection === "ALERTS" && <section className={styles.panel}>
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
          </section>}

          {adminSection === "ALERTS" && <section className={styles.panel}>
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
          </section>}

          {adminSection === "AUDIT" && <section className={styles.panel}>
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
          </section>}

          {adminSection === "CONFIG" && <section className={styles.panel}>
            <header><div><span className="overline">POLICY & READINESS</span><h2>配置、SLO 与外部门禁</h2></div><small>敏感配置值永不回传</small></header>
            <div className={styles.cardGrid}>
              {view.control.policies.map((policy) => (
                <article className={styles.controlCard} key={policy.policyId}>
                  <div><span className={styles.kind}>{policy.enabled ? "ENABLED" : "DISABLED"}</span><strong>{lineLabels[policy.businessLine] ?? policy.businessLine}</strong></div>
                  <code>{policy.policyId}</code>
                  <p>失败率 {(policy.failureRateBudgetBps / 100).toFixed(2)}% · P95 {policy.latencyP95BudgetMs} ms</p>
                  <small>窗口 {policy.evaluationWindowMinutes} 分钟 · 最小样本 {policy.minimumEventCount}</small>
                </article>
              ))}
            </div>
          </section>}

          {adminSection === "CONFIG" && <section className={styles.evidence}>
            <strong>外部门禁</strong>
            <span>通知投递：{view.control.notificationDeliveryEvidence}</span>
            <span>生产部署：{view.control.productionDeploymentEvidence}</span>
            <span>保留执行：{view.control.retentionRuns.length ? "有本地/当前环境证据" : "NOT_RUN"}</span>
          </section>}
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

function EventTable({
  events,
  empty,
}: {
  events: OperationsConsoleView["activity"]["recentEvents"];
  empty: string;
}) {
  if (events.length === 0) return <Empty label={empty} />;
  return (
    <div className={styles.tableWrap}>
      <table>
        <thead><tr><th>时间</th><th>业务线</th><th>动作</th><th>目标</th><th>结果</th><th>耗时</th></tr></thead>
        <tbody>
          {events.map((item) => (
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
  );
}
