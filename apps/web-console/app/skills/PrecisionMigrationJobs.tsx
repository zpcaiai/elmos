"use client";

import { useCallback, useEffect, useState } from "react";

import { StatusChip } from "../components/StatusChip";

type Artifact = { uri?: string; digest?: string; size_bytes?: number; media_type?: string };
type PrecisionJob = {
  job_id: string;
  status: string;
  progress: number;
  retry_of?: string | null;
  artifacts?: Artifact[];
  result?: { execution_state?: string; result_digest?: string } | null;
};

const terminal = new Set(["SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"]);

function artifactName(artifact: Artifact): string | null {
  if (!artifact.uri) return null;
  try {
    return decodeURIComponent(new URL(artifact.uri).pathname.split("/").pop() ?? "");
  } catch {
    return null;
  }
}

export function PrecisionMigrationJobs() {
  const [skill, setSkill] = useState("pm-b02-repository-modernization-assessment");
  const [mode, setMode] = useState("assess");
  const [workspacePath, setWorkspacePath] = useState("");
  const [runnerToken, setRunnerToken] = useState("");
  const [tenantId, setTenantId] = useState("local-tenant");
  const [actorId, setActorId] = useState("local-operator");
  const [job, setJob] = useState<PrecisionJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const localAuthHeaders = useCallback((): Record<string, string> => {
    if (!runnerToken.trim()) return {};
    return {
      authorization: `Bearer ${runnerToken.trim()}`,
      "x-elmos-tenant": tenantId.trim(),
      "x-elmos-actor": actorId.trim(),
    };
  }, [actorId, runnerToken, tenantId]);

  const load = useCallback(async (jobId: string) => {
    const response = await fetch(`/api/precision-migration/jobs/${encodeURIComponent(jobId)}`, {
      cache: "no-store",
      headers: localAuthHeaders(),
    });
    const payload = await response.json() as PrecisionJob & { reason?: string };
    if (!response.ok) throw new Error(payload.reason ?? "JOB_STATUS_FAILED");
    setJob(payload);
    return payload;
  }, [localAuthHeaders]);

  useEffect(() => {
    if (!job || terminal.has(job.status)) return;
    const timer = window.setInterval(() => void load(job.job_id).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "JOB_STATUS_FAILED");
    }), 1_500);
    return () => window.clearInterval(timer);
  }, [job, load]);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/precision-migration/jobs", {
        method: "POST",
        headers: { "content-type": "application/json", ...localAuthHeaders() },
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          skill: skill.trim(),
          mode,
          inputs: {
            assets: [],
            parameters: workspacePath.trim() ? { workspace_path: workspacePath.trim() } : {},
          },
          policy: {
            unresolved_differences: "block",
            allow_test_weakening: false,
            require_provenance: true,
            risk_level: "medium",
          },
          evidence: [],
          semantic_losses: [],
          approvals: [],
        }),
      });
      const payload = await response.json() as PrecisionJob & { reason?: string };
      if (!response.ok) throw new Error(payload.reason ?? "JOB_SUBMIT_FAILED");
      setJob(payload);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "JOB_SUBMIT_FAILED");
    } finally {
      setBusy(false);
    }
  }

  async function action(kind: "cancel" | "retry") {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/precision-migration/jobs/${encodeURIComponent(job.job_id)}`, {
        method: kind === "cancel" ? "DELETE" : "POST",
        headers: { ...(kind === "retry" ? { "content-type": "application/json" } : {}), ...localAuthHeaders() },
        body: kind === "retry" ? JSON.stringify({ action: "retry" }) : undefined,
      });
      const payload = await response.json() as PrecisionJob & { reason?: string };
      if (!response.ok) throw new Error(payload.reason ?? `JOB_${kind.toUpperCase()}_FAILED`);
      setJob(payload);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `JOB_${kind.toUpperCase()}_FAILED`);
    } finally {
      setBusy(false);
    }
  }

  async function download(artifact: Artifact) {
    if (!job) return;
    const name = artifactName(artifact);
    if (!name) return;
    setError("");
    try {
      const response = await fetch(`/api/precision-migration/jobs/${encodeURIComponent(job.job_id)}/artifacts/${encodeURIComponent(name)}`, {
        headers: localAuthHeaders(),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { reason?: string };
        throw new Error(payload.reason ?? "ARTIFACT_DOWNLOAD_FAILED");
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ARTIFACT_DOWNLOAD_FAILED");
    }
  }

  return <section className="surface-card precision-job-card" aria-labelledby="precision-job-title">
    <div className="card-heading"><div><span className="overline">TENANT-ISOLATED RUNNER</span><h2 id="precision-job-title">精密迁移作业</h2></div><StatusChip status={job?.status ?? "NOT_RUN"} compact /></div>
    <p>作业身份来自企业会话；服务端实施租户隔离、活动/存储配额、非覆盖输出、取消、重试、哈希链审计和可恢复归档。</p>
    <div className="form-stack precision-job-form">
      <label><span>Runtime Skill</span><input value={skill} onChange={(event) => setSkill(event.target.value)} required pattern="pm-[a-z0-9-]+" /></label>
      <div className="form-grid">
        <label><span>模式</span><select value={mode} onChange={(event) => setMode(event.target.value)}><option value="assess">assess</option><option value="validate">validate</option><option value="certify">certify</option><option value="transform">transform</option><option value="repair">repair</option></select></label>
        <label><span>只读工作区路径</span><input value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="评估 handler 必填；必须位于批准根目录" /></label>
      </div>
      <details className="precision-local-auth">
        <summary>本地开发认证（生产环境使用企业会话）</summary>
        <div className="form-grid">
          <label><span>本地租户</span><input value={tenantId} onChange={(event) => setTenantId(event.target.value)} autoComplete="off" /></label>
          <label><span>本地 Actor</span><input value={actorId} onChange={(event) => setActorId(event.target.value)} autoComplete="off" /></label>
          <label className="precision-auth-token"><span>本地短期 Runner 令牌</span><input type="password" value={runnerToken} onChange={(event) => setRunnerToken(event.target.value)} autoComplete="off" /></label>
        </div>
        <small>令牌仅保存在当前页面内存中，不写入浏览器存储、作业请求或证据产物。</small>
      </details>
      <div className="business-actions"><button className="button button-primary" type="button" disabled={busy || !skill.trim()} onClick={() => void submit()}>提交作业</button>{job && !terminal.has(job.status) ? <button className="button button-secondary" type="button" disabled={busy} onClick={() => void action("cancel")}>取消</button> : null}{job && terminal.has(job.status) ? <button className="button button-secondary" type="button" disabled={busy} onClick={() => void action("retry")}>重试</button> : null}</div>
    </div>
    {error ? <p className="field-error" role="alert">{error}</p> : null}
    {job ? <div className="precision-job-result" aria-live="polite">
      <div><span>Job ID</span><code>{job.job_id}</code></div>
      <div><span>进度</span><strong>{job.progress}%</strong></div>
      <div><span>执行状态</span><strong>{job.result?.execution_state ?? job.status}</strong></div>
      {job.retry_of ? <div><span>重试来源</span><code>{job.retry_of}</code></div> : null}
      {job.artifacts?.length ? <div className="precision-artifacts"><span>证据产物</span>{job.artifacts.map((artifact) => {
        const name = artifactName(artifact);
        return name ? <button className="precision-artifact-link" type="button" key={artifact.digest ?? name} onClick={() => void download(artifact)}>{name}<small>{artifact.digest?.slice(0, 20)}… · {artifact.size_bytes} bytes</small></button> : null;
      })}</div> : null}
    </div> : null}
    <small className="form-note">UI 只能触发清单中的受控 handler；`INSTALLED` 条目会返回 `REQUIRES_ADAPTER`，不会执行请求携带的命令。</small>
  </section>;
}
