"use client";

import { useCallback, useState } from "react";
import { Icon } from "../components/Icon";
import styles from "./OperationsAdmin.module.css";

/**
 * 跨组织的任务执行视图。
 *
 * <p>把「这个任务跑成什么样」和「这个任务花了多少钱」放在同一行——这是改动前
 * 完全没有的视角。任务状态在 execution_jobs，钱在 wallet_reservations，
 * 两边此前从不相见，运营要回答「客户说被多扣了」得开两个页面对着看，
 * 而这两个页面的时间轴还不一定对得上。
 *
 * <p>与上方的「持久作业队列」并存，不取代它：那个走 operations-observability，
 * 每个端点都强制带组织头并对该组织授权，是组织内视图；这个走平台管理员通道，
 * 不带组织头，每次读取写一条审计。两者授权模型不同，合成一个会让
 * 「我在看谁的数据」取决于有没有传某个参数。
 */

type JobRow = {
  jobId: string;
  organizationId: string;
  businessLine: string;
  jobKind: string;
  status: string;
  resultStatus: string | null;
  failureCode: string | null;
  createdAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  settledAmountMinor: string | number | null;
  holdStatus: string | null;
};

const jobStatuses = [
  ["ALL", "全部状态"],
  ["QUEUED", "排队 QUEUED"],
  ["CLAIMED", "已认领 CLAIMED"],
  ["RUNNING", "执行中 RUNNING"],
  ["SUCCEEDED", "成功 SUCCEEDED"],
  ["PARTIAL", "部分成功 PARTIAL"],
  ["FAILED", "失败 FAILED"],
  ["CANCELLED", "已取消 CANCELLED"],
  ["LOST", "丢失 LOST"],
] as const;

function yuan(minor: string | number | null): string {
  if (minor === null || minor === undefined) return "未计费";
  const value = typeof minor === "number" ? minor : Number(minor);
  if (!Number.isFinite(value)) return "未计费";
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

/** 只有真的跑过才算时长；排队时间是我们的延迟，不是租户的。 */
function elapsed(row: JobRow): string {
  if (!row.startedAt) return "—";
  const started = new Date(row.startedAt);
  if (Number.isNaN(started.getTime())) return "—";
  const end = row.finishedAt ? new Date(row.finishedAt) : new Date();
  if (Number.isNaN(end.getTime())) return "—";
  const seconds = Math.max(0, Math.round((end.getTime() - started.getTime()) / 1000));
  return `${seconds}s`;
}

export function PlatformJobsPanel() {
  const [rows, setRows] = useState<JobRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [status, setStatus] = useState<string>("ALL");
  const [organization, setOrganization] = useState("");
  const [denial, setDenial] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setDenial("");
    try {
      const query = new URLSearchParams({ limitPerOrganization: "25" });
      if (status !== "ALL") query.set("status", status);
      if (organization) query.set("organizationId", organization);
      const response = await fetch(`/api/admin/execution-jobs?${query.toString()}`, {
        cache: "no-store",
      });
      const payload = (await response.json().catch(() => null)) as
        | { rows?: JobRow[]; code?: string; message?: string }
        | null;
      if (!response.ok) {
        setRows([]);
        setDenial(payload?.code ?? payload?.message ?? `HTTP_${response.status}`);
        return;
      }
      setRows(payload?.rows ?? []);
      setLoaded(true);
    } catch {
      setRows([]);
      setDenial("PLATFORM_JOBS_UNREACHABLE");
    } finally {
      setBusy(false);
    }
  }, [status, organization]);

  const failing = rows.filter((row) => row.status === "FAILED" || row.status === "LOST");
  const charged = rows.filter((row) => row.settledAmountMinor !== null);

  return (
    <section className={styles.panel} aria-label="全平台任务执行">
      <header>
        <div>
          <span className="overline">PLATFORM EXECUTION</span>
          <h2>全平台任务执行</h2>
        </div>
        <small>
          {loaded
            ? `${rows.length} 条 · 失败/丢失 ${failing.length} · 已扣费 ${charged.length}`
            : "跨组织 · 每组织最多 25 条"}
        </small>
      </header>
      <p>
        跨组织视图，需要平台管理员身份，与上方按租户隔离的作业队列是两条通道。
        每一行同时给出执行结果和这次执行实际扣了多少钱——回答「客户说被多扣了」
        不需要再开第二个页面。
      </p>

      <div className={styles.inlineActions}>
        <label>
          <span>执行状态</span>
          <select
            aria-label="全平台任务状态"
            value={status}
            disabled={busy}
            onChange={(event) => {
              setStatus(event.target.value);
              setRows([]);
              setLoaded(false);
            }}
          >
            {jobStatuses.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>限定组织（可空）</span>
          <input
            value={organization}
            onChange={(event) => {
              setOrganization(event.target.value.trim());
              setRows([]);
              setLoaded(false);
            }}
            aria-label="限定组织 ID"
            placeholder="留空则看全平台"
            pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
            disabled={busy}
          />
        </label>
        <button
          className="secondary-button"
          type="button"
          onClick={() => void load()}
          disabled={busy}
        >
          <Icon name={busy ? "refresh" : "search"} size={17} />
          {busy ? "读取中…" : "读取任务"}
        </button>
      </div>

      {denial && (
        <p className={styles.bad} role="alert">
          被拒绝或读取失败：{denial}。跨组织任务视图需要平台管理员身份，
          与本组织的运营角色是两回事。
        </p>
      )}

      {!loaded ? (
        <div className={styles.empty}>
          <Icon name="database" size={22} />
          <span>点击读取后才会请求；每次读取都会写一条平台管理员审计。</span>
        </div>
      ) : rows.length === 0 ? (
        <div className={styles.empty}>
          <Icon name="database" size={22} />
          <span>没有匹配的任务。</span>
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>组织</th>
                <th>任务</th>
                <th>业务线</th>
                <th>状态</th>
                <th>失败码</th>
                <th>时长</th>
                <th>扣费</th>
                <th>持有</th>
                <th>创建</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.organizationId}:${row.jobId}`}>
                  <td><code>{row.organizationId}</code></td>
                  <td title={row.jobId}>
                    <code>{row.jobId.length > 20 ? `${row.jobId.slice(0, 17)}…` : row.jobId}</code>
                    <br />
                    <small>{row.jobKind}</small>
                  </td>
                  <td>{row.businessLine}</td>
                  <td>
                    <span
                      className={
                        row.status === "FAILED" || row.status === "LOST"
                          ? styles.resultBad
                          : styles.resultGood
                      }
                    >
                      {row.status}
                    </span>
                    {row.resultStatus && <small>{row.resultStatus}</small>}
                  </td>
                  <td>{row.failureCode ?? "—"}</td>
                  <td>{elapsed(row)}</td>
                  <td>{yuan(row.settledAmountMinor)}</td>
                  <td>
                    {/*
                      空表示这个任务根本没有被冻结过——要么入队时计费开关是关的，
                      要么订阅配额覆盖了它。与「冻结后又释放了」是两回事：
                      后者动过钱，前者从头到尾没进过钱包。
                    */}
                    {row.holdStatus ?? "未持有"}
                  </td>
                  <td>{moment(row.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
