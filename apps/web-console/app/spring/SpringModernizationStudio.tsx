"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";

type SourceMode = "PUBLIC_GIT" | "GITHUB_APP" | "MATERIALIZED_SNAPSHOT";
type RunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "BLOCKED" | "CANCELLED";
type RuntimeStatus = "NOT_STARTED" | "STARTING" | "HEALTHY" | "UNHEALTHY" | "STOPPED";
type Stage =
  | "IMPORT_GIT" | "LOCK_SNAPSHOT" | "FINGERPRINT" | "SOURCE_BASELINE"
  | "EXTRACT_FCM" | "OPENREWRITE" | "BUILD_AND_TEST" | "DETERMINISTIC_REPAIR"
  | "INDEPENDENT_VALIDATION" | "PACKAGE_ARTIFACT" | "READY"
  | "START_APPLICATION" | "HEALTH_CHECK" | "STOP_APPLICATION";

type Capability = {
  packKey: string;
  sourceTuple: { springBoot: string; java: string; build: string };
  targetTuple: { springBoot: string; java: string; build: string };
  openRewrite: { rewriteSpring: string; mavenPlugin: string };
  transformerConfigured: boolean;
  transformerReason: string;
  runtimeRunnerConfigured: boolean;
  runtimeRunnerReason: string;
  independentVerifierConfigured: boolean;
  independentVerifierReason: string;
  downloadRequiresIndependentPass: boolean;
  runtimeRequiresIndependentPass: boolean;
};

type Event = {
  sequence: number;
  stage: Stage;
  status: string;
  message: string;
  observedAt: string;
};

type Run = {
  runId: string;
  retryOfRunId?: string | null;
  status: RunStatus;
  stage: Stage;
  runtimeStatus: RuntimeStatus;
  attempt: number;
  repositoryUrl?: string | null;
  requestedRef: string;
  resolvedCommitSha?: string | null;
  snapshotId?: string | null;
  snapshotDigest?: string | null;
  exactTuple: {
    sourceSpringBoot: string;
    sourceJava: string;
    sourceBuildTool: string;
    targetSpringBoot: string;
    targetJava: string;
    targetBuildTool: string;
    rewriteSpring: string;
    rewriteMavenPlugin: string;
  };
  fingerprint?: {
    springBootVersion: string;
    javaVersion: string;
    buildTool: string;
    modules: string[];
    activeCapabilities: string[];
    unknowns: string[];
  } | null;
  fcmArtifact?: string | null;
  downloadAvailable: boolean;
  artifactSha256?: string | null;
  artifactSize?: number | null;
  healthPath?: string | null;
  runtimePort?: number | null;
  failureCode?: string | null;
  failureMessage?: string | null;
  independentValidation?: {
    status: string;
    verifierId: string;
    artifactSha256: string;
    evidencePath: string;
    decidedAt: string;
  } | null;
  events: Event[];
};

type LogResponse = { runId: string; lines: string[]; truncated: boolean };
type ApiError = { errorCode?: string; message?: string; retryable?: boolean };
type ConnectedRepository = {
  repositoryId: string;
  repositoryExternalId: number;
  installationExternalId: number;
  fullName: string;
  defaultBranch: string;
  visibility: string;
};
type RepositoryCatalog = {
  status: "READY" | "NO_AUTHORIZED_REPOSITORIES" | "NOT_CONFIGURED" | "UNAVAILABLE";
  repositories: ConnectedRepository[];
  message?: string;
};

const stageCards: Array<{ stages: Stage[]; title: string; detail: string }> = [
  { stages: ["IMPORT_GIT"], title: "导入 Git 仓库", detail: "仅允许批准的 HTTPS Git host，拒绝 URL 凭证。" },
  { stages: ["LOCK_SNAPSHOT"], title: "锁定 Commit / Snapshot", detail: "解析 40 位 Commit，并生成确定性内容摘要。" },
  { stages: ["FINGERPRINT"], title: "精确版本识别", detail: "只接受 Boot 2.7.18、Java 17、Maven 精确路线。" },
  { stages: ["SOURCE_BASELINE"], title: "源工程基线", detail: "在一次性副本中使用 Java 17 执行完整 Maven verify。" },
  { stages: ["EXTRACT_FCM"], title: "提取 FCM", detail: "在转换前固化能力、来源映射、默认值与未知项。" },
  { stages: ["OPENREWRITE"], title: "OpenRewrite 实际转换", detail: "固定 Rewrite Spring 6.35.0 与插件 6.44.0。" },
  { stages: ["BUILD_AND_TEST", "DETERMINISTIC_REPAIR"], title: "编译 / 测试 / 修复", detail: "Java 21 真实测试；失败时最多一次确定性修复。" },
  { stages: ["PACKAGE_ARTIFACT"], title: "候选项目打包", detail: "生成内容寻址 ZIP，尚不自动开放下载。" },
  { stages: ["INDEPENDENT_VALIDATION"], title: "独立验证", detail: "另一验证器从 ZIP 新目录解包并执行 mvn verify。" },
  { stages: ["READY"], title: "下载新项目", detail: "只有独立 PASS 后才开放下载。" },
  { stages: ["START_APPLICATION", "HEALTH_CHECK"], title: "一键隔离启动", detail: "Java 21 启动、回环健康检查，未配置 Rootless 时拒绝。" },
  { stages: ["STOP_APPLICATION"], title: "日志 / 停止 / 重试", detail: "实时脱敏日志、优雅停止与新的可追溯尝试。" },
];

const orderedStages: Stage[] = [
  "IMPORT_GIT", "LOCK_SNAPSHOT", "FINGERPRINT", "SOURCE_BASELINE", "EXTRACT_FCM",
  "OPENREWRITE", "BUILD_AND_TEST", "DETERMINISTIC_REPAIR", "PACKAGE_ARTIFACT",
  "INDEPENDENT_VALIDATION", "READY", "START_APPLICATION", "HEALTH_CHECK", "STOP_APPLICATION",
];

function randomKey(prefix: string) {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`}`;
}

function shortDigest(value?: string | null) {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "等待生成";
}

function formatBytes(value?: number | null) {
  if (!value) return "等待生成";
  return value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;
}

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as ApiError;
    throw new Error(`${error.errorCode ?? `HTTP_${response.status}`}: ${error.message ?? "请求失败"}`);
  }
  return response.json() as Promise<T>;
}

export function SpringModernizationStudio() {
  const [sourceMode, setSourceMode] = useState<SourceMode>("PUBLIC_GIT");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [requestedRef, setRequestedRef] = useState("main");
  const [expectedCommitSha, setExpectedCommitSha] = useState("");
  const [snapshotId, setSnapshotId] = useState("");
  const [materializedRelativePath, setMaterializedRelativePath] = useState("");
  const [githubRepositories, setGithubRepositories] = useState<ConnectedRepository[]>([]);
  const [githubRepositoryId, setGithubRepositoryId] = useState("");
  const [githubCatalogStatus, setGithubCatalogStatus] =
    useState<RepositoryCatalog["status"]>("NOT_CONFIGURED");
  const [startAfterVerification, setStartAfterVerification] = useState(false);
  const [capability, setCapability] = useState<Capability | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [logs, setLogs] = useState<LogResponse | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");

  const refresh = useCallback(async (runId: string, includeLogs = showLogs) => {
    const next = await api<Run>(`/api/spring-upgrades/${runId}`);
    setRun(next);
    if (includeLogs) setLogs(await api<LogResponse>(`/api/spring-upgrades/${runId}/logs`));
    return next;
  }, [showLogs]);

  useEffect(() => {
    api<Capability>("/api/spring-upgrades/capabilities")
      .then((value) => {
        setCapability(value);
        setCapabilityError("");
      })
      .catch((error: Error) => {
        setCapability(null);
        setCapabilityError(error.message);
        setFeedback(error.message);
      });
  }, []);

  useEffect(() => {
    api<RepositoryCatalog>("/api/github-repositories")
      .then((catalog) => {
        setGithubCatalogStatus(catalog.status);
        setGithubRepositories(catalog.repositories);
        const first = catalog.repositories[0];
        if (first) {
          setGithubRepositoryId((value) => value || first.repositoryId);
        }
      })
      .catch(() => {
        setGithubCatalogStatus("NOT_CONFIGURED");
        setGithubRepositories([]);
      });
  }, []);

  useEffect(() => {
    if (!run || !["QUEUED", "RUNNING"].includes(run.status) && run.runtimeStatus !== "STARTING") return;
    const timer = window.setInterval(() => {
      refresh(run.runId).catch((error: Error) => setFeedback(error.message));
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [refresh, run]);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(""), 6_000);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const githubSourceReady = sourceMode !== "GITHUB_APP"
    || githubCatalogStatus === "READY" && Boolean(githubRepositoryId);
  const runnerReady = Boolean(
    capability?.transformerConfigured
    && capability?.independentVerifierConfigured
    && githubSourceReady,
  );
  const runtimeReady = Boolean(capability?.runtimeRunnerConfigured);
  const lastStageIndex = run ? orderedStages.indexOf(run.stage) : -1;

  const stageStatus = useCallback((stages: Stage[]) => {
    if (!run) return "NOT_RUN";
    const matching = run.events.filter((event) => stages.includes(event.stage));
    if (matching.some((event) => ["FAILED", "BLOCKED", "CANCELLED"].includes(event.status))) return "BLOCKED";
    if (matching.some((event) => event.status === "PASS")) return "READY";
    const greatest = Math.max(...stages.map((stage) => orderedStages.indexOf(stage)));
    if (matching.length > 0 && greatest < lastStageIndex) return "READY";
    if (stages.includes(run.stage) && ["QUEUED", "RUNNING"].includes(run.status)) return "REVIEW";
    if (stages.includes("READY") && run.downloadAvailable) return "READY";
    if (stages.includes("HEALTH_CHECK") && run.runtimeStatus === "HEALTHY") return "READY";
    if (stages.includes("STOP_APPLICATION") && run.runtimeStatus === "STOPPED") return "READY";
    return "NOT_RUN";
  }, [lastStageIndex, run]);

  const currentMessage = useMemo(() => {
    if (!run) return runnerReady
      ? "Runner 与独立验证器已配置，可以提交精确路线。"
      : capabilityError || capability?.transformerReason || "正在读取 Runner 能力。";
    if (run.failureCode) return `${run.failureCode} · ${run.failureMessage ?? "流程已安全阻断"}`;
    return run.events.at(-1)?.message ?? "等待执行状态";
  }, [capability, capabilityError, run, runnerReady]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFeedback("");
    try {
      const next = await api<Run>("/api/spring-upgrades", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          sourceMode,
          repositoryUrl: sourceMode === "PUBLIC_GIT" ? repositoryUrl.trim() : null,
          repositoryId: sourceMode === "GITHUB_APP" ? githubRepositoryId : null,
          requestedRef: sourceMode === "MATERIALIZED_SNAPSHOT"
            ? "snapshot"
            : requestedRef.trim(),
          expectedCommitSha: sourceMode === "GITHUB_APP"
            ? null
            : expectedCommitSha.trim() || null,
          snapshotId: sourceMode === "MATERIALIZED_SNAPSHOT"
            ? snapshotId.trim()
            : null,
          materializedRelativePath: sourceMode === "MATERIALIZED_SNAPSHOT" ? materializedRelativePath.trim() : null,
          startAfterVerification,
          idempotencyKey: randomKey("spring-upgrade"),
        }),
      });
      setRun(next);
      setLogs(null);
      setFeedback("迁移已排队；页面会持续读取真实阶段和证据状态。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  async function lifecycle(path: string, body?: object) {
    if (!run) return;
    setBusy(true);
    try {
      const next = await api<Run>(`/api/spring-upgrades/${run.runId}/${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      setRun(next);
      setFeedback("操作已受理，状态将自动刷新。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggleLogs() {
    if (!run) return;
    const next = !showLogs;
    setShowLogs(next);
    if (next) {
      try {
        setLogs(await api<LogResponse>(`/api/spring-upgrades/${run.runId}/logs`));
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "日志不可用");
      }
    }
  }

  async function downloadArtifact() {
    if (!run?.downloadAvailable || !run.artifactSha256 || !run.artifactSize) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/spring-upgrades/${run.runId}/artifact`, {
        cache: "no-store",
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({})) as ApiError;
        throw new Error(`${error.errorCode ?? `HTTP_${response.status}`}: ${error.message ?? "归档不可用"}`);
      }
      const responseDigest = response.headers.get("x-content-sha256");
      const declaredLength = Number(response.headers.get("content-length"));
      const blob = await response.blob();
      const actualDigest = [...new Uint8Array(await crypto.subtle.digest(
        "SHA-256",
        await blob.arrayBuffer(),
      ))].map((value) => value.toString(16).padStart(2, "0")).join("");
      if (
        responseDigest !== run.artifactSha256
        || actualDigest !== run.artifactSha256
        || blob.size !== run.artifactSize
        || !Number.isSafeInteger(declaredLength)
        || declaredLength !== blob.size
      ) {
        throw new Error("ARTIFACT_INTEGRITY_MISMATCH: 下载字节与独立验证证据不一致");
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "migrated-spring-boot-3.5.3.zip";
      anchor.click();
      URL.revokeObjectURL(url);
      setFeedback("ZIP 的长度和 SHA-256 已在浏览器复算并与独立验证证据一致。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "归档下载失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack business-page">
      <section className="page-header business-hero">
        <div>
          <span className="overline">SPRING MODERNIZATION · REAL JOURNEY</span>
          <h1>Java / Spring 老项目一键迁移</h1>
          <p>从不可变 Git Commit 到 FCM、真实 OpenRewrite、双工具链构建、独立验证、下载与隔离启动。每一步都显示真实状态，未运行绝不显示通过。</p>
        </div>
        <div className="header-actions">
          <StatusChip status={runnerReady ? "READY" : "NOT_CONFIGURED"} />
          <StatusChip status={run?.status ?? "NOT_RUN"} />
        </div>
      </section>

      <section className={`source-notice ${runnerReady ? "" : "runner-warning"}`} role="status">
        <Icon name={runnerReady ? "shield" : "lock"} size={16} />
        <span>{currentMessage}</span>
        <StatusChip status={runnerReady ? "ENFORCED" : "BLOCKED"} compact />
      </section>

      <section className="metric-grid metric-grid-four" aria-label="精确迁移路线">
        <article className="metric-card"><span>源版本</span><strong className="metric-word">Boot 2.7.18</strong><small>Java 17 · Maven 3.9.11</small></article>
        <article className="metric-card"><span>目标版本</span><strong className="metric-word">Boot 3.5.3</strong><small>Java 21 · Maven 3.9.11</small></article>
        <article className="metric-card"><span>OpenRewrite</span><strong className="metric-word">6.35.0</strong><small>Plugin 6.44.0 · 固定 Recipes</small></article>
        <article className="metric-card"><span>独立裁判</span><strong className={`metric-word ${run?.independentValidation?.status === "PASS" ? "" : "warning-text"}`}>{run?.independentValidation?.status ?? "NOT_RUN"}</strong><small>从下载 ZIP 重新验证</small></article>
      </section>

      <div className="business-layout">
        <form className="surface-card business-form" onSubmit={submit}>
          <div className="business-section-heading">
            <div><span className="overline">IMMUTABLE INPUT</span><h2>导入并锁定源仓库</h2></div>
            <StatusChip status={run ? run.status : "DRAFT"} compact />
          </div>
          <div className="business-form-grid">
            <label>
              <span>输入方式</span>
              <select value={sourceMode} onChange={(event) => setSourceMode(event.target.value as SourceMode)}>
                <option value="PUBLIC_GIT">公开 HTTPS Git</option>
                <option value="GITHUB_APP">GitHub App 私有仓库</option>
                <option value="MATERIALIZED_SNAPSHOT">受控 Snapshot Workspace</option>
              </select>
            </label>
            {sourceMode === "PUBLIC_GIT" ? (
              <>
                <label className="spring-field-wide"><span>Git 仓库 URL</span><input required type="url" value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} placeholder="https://github.com/org/repo.git" /></label>
                <label><span>Branch / Tag</span><input required value={requestedRef} onChange={(event) => setRequestedRef(event.target.value)} placeholder="main 或 refs/tags/v1.0.0" /></label>
                <label><span>预期 Commit（可选）</span><input value={expectedCommitSha} onChange={(event) => setExpectedCommitSha(event.target.value.toLowerCase())} pattern="[0-9a-f]{40}" placeholder="40 位 SHA；填写后必须完全匹配" /></label>
              </>
            ) : sourceMode === "GITHUB_APP" ? (
              <>
                <label className="spring-field-wide">
                  <span>已授权 GitHub 仓库</span>
                  <select
                    required
                    value={githubRepositoryId}
                    onChange={(event) => {
                      const repositoryId = event.target.value;
                      setGithubRepositoryId(repositoryId);
                      const selected = githubRepositories.find(
                        (repository) => repository.repositoryId === repositoryId,
                      );
                      if (selected) setRequestedRef(selected.defaultBranch);
                    }}
                    disabled={githubCatalogStatus !== "READY"}
                  >
                    {githubRepositories.length === 0
                      ? <option value="">没有可用的已授权仓库</option>
                      : githubRepositories.map((repository) => (
                          <option
                            key={repository.repositoryId}
                            value={repository.repositoryId}
                          >
                            {repository.fullName} · {repository.visibility}
                          </option>
                        ))}
                  </select>
                </label>
                <label>
                  <span>Branch / Tag</span>
                  <input
                    required
                    value={requestedRef}
                    onChange={(event) => setRequestedRef(event.target.value)}
                    placeholder="main 或 refs/tags/v1.0.0"
                  />
                </label>
                <div className="locked-target">
                  <span>GitHub App 状态</span>
                  <strong>{githubCatalogStatus}</strong>
                  <small>
                    仅使用仓库级、最长 1 小时的短期 Token；Token 不进入
                    Transformer、日志或 Snapshot。
                  </small>
                </div>
              </>
            ) : (
              <>
                <label><span>Snapshot ID</span><input required value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)} /></label>
                <label><span>Workspace 相对路径</span><input required value={materializedRelativePath} onChange={(event) => setMaterializedRelativePath(event.target.value)} placeholder="snapshots/..." /></label>
                <label className="spring-field-wide"><span>绑定 Commit</span><input required value={expectedCommitSha} onChange={(event) => setExpectedCommitSha(event.target.value.toLowerCase())} pattern="[0-9a-f]{40}" placeholder="必须为 40 位 SHA" /></label>
              </>
            )}
            <div className="locked-target spring-field-wide">
              <span>锁定转换路线</span>
              <strong>Spring Boot 2.7.18 / Java 17 → Spring Boot 3.5.3 / Java 21</strong>
              <small>版本不精确匹配会在 FINGERPRINT 阶段 fail closed，不做模糊升级。</small>
            </div>
          </div>
          <label className="spring-start-toggle">
            <input type="checkbox" checked={startAfterVerification} disabled={!runtimeReady} onChange={(event) => setStartAfterVerification(event.target.checked)} />
            <span><strong>验证通过后自动一键启动</strong><small>{runtimeReady ? "独立验证 PASS 后，在每次运行专属的 Rootless 容器中执行。" : capability?.runtimeRunnerReason ?? "独立 Runtime Runner 尚未配置。"}</small></span>
          </label>
          <div className="business-actions">
            <button className="button button-primary" type="submit" disabled={busy || !runnerReady}>
              <Icon name={busy ? "refresh" : "workflow"} size={16} className={busy ? "spinning" : undefined} />
              {runnerReady ? "开始真实迁移" : "隔离 Runner 未配置"}
            </button>
            {run && ["QUEUED", "RUNNING"].includes(run.status) && <button className="button button-secondary" type="button" onClick={() => lifecycle("cancel")} disabled={busy}>取消迁移</button>}
          </div>
        </form>

        <aside className="surface-card business-summary spring-run-summary">
          <div className="business-section-heading"><div><span className="overline">RUN EVIDENCE</span><h2>运行与交付</h2></div><StatusChip status={run?.runtimeStatus ?? "NOT_RUN"} compact /></div>
          <dl className="spring-run-facts">
            <div><dt>Run / Attempt</dt><dd>{run ? `${run.runId.slice(0, 8)} · #${run.attempt}` : "尚未创建"}</dd></div>
            <div><dt>Commit</dt><dd title={run?.resolvedCommitSha ?? undefined}>{shortDigest(run?.resolvedCommitSha)}</dd></div>
            <div><dt>Snapshot</dt><dd title={run?.snapshotDigest ?? undefined}>{shortDigest(run?.snapshotDigest)}</dd></div>
            <div><dt>FCM</dt><dd>{run?.fcmArtifact ?? "NOT_RUN"}</dd></div>
            <div><dt>Artifact</dt><dd>{formatBytes(run?.artifactSize)} · {shortDigest(run?.artifactSha256)}</dd></div>
            <div><dt>Health</dt><dd>{run?.runtimeStatus === "HEALTHY" ? `127.0.0.1:${run.runtimePort}${run.healthPath}` : run?.runtimeStatus ?? "NOT_RUN"}</dd></div>
          </dl>
          {run?.fingerprint && (
            <div className="spring-fingerprint">
              <strong>检测结果</strong>
              <span>{run.fingerprint.springBootVersion} · Java {run.fingerprint.javaVersion} · {run.fingerprint.buildTool}</span>
              <small>能力：{run.fingerprint.activeCapabilities.join("、") || "未识别"}</small>
              {run.fingerprint.unknowns.length > 0 && <small className="warning-text">未知项：{run.fingerprint.unknowns.join("、")}</small>}
            </div>
          )}
          <div className="spring-delivery-actions">
            {run?.downloadAvailable
              ? <button
                  className="button button-primary"
                  type="button"
                  disabled={busy}
                  onClick={() => void downloadArtifact()}
                ><Icon name="file" size={15} />下载新项目 ZIP</button>
              : <button className="button button-primary" disabled><Icon name="lock" size={15} />独立验证后下载</button>}
            <button className="button button-secondary" type="button" disabled={!runtimeReady || !run || !run.downloadAvailable || busy || run.runtimeStatus === "STARTING" || run.runtimeStatus === "HEALTHY"} onClick={() => lifecycle("runtime/start")}><Icon name="server" size={15} />一键启动</button>
            <button className="button button-secondary" type="button" disabled={!run || busy || !["STARTING", "HEALTHY", "UNHEALTHY"].includes(run.runtimeStatus)} onClick={() => lifecycle("runtime/stop")}>停止</button>
            <button className="button button-secondary" type="button" disabled={!run || busy || !["FAILED", "BLOCKED", "CANCELLED"].includes(run.status)} onClick={() => lifecycle("retry", { idempotencyKey: randomKey("retry") })}><Icon name="refresh" size={15} />重试</button>
            <button className="button button-secondary" type="button" disabled={!run} onClick={toggleLogs}><Icon name="file" size={15} />{showLogs ? "收起日志" : "查看日志"}</button>
          </div>
        </aside>
      </div>

      <section className="surface-card journey-card" aria-labelledby="real-spring-journey">
        <div className="business-section-heading">
          <div><span className="overline">EVIDENCE-BOUND PIPELINE</span><h2 id="real-spring-journey">完整真实旅程</h2></div>
          <small>阶段来自 Java Engine Worker 实际事件，不由前端模拟</small>
        </div>
        <ol className="journey-grid spring-real-journey">
          {stageCards.map((card, index) => (
            <li key={card.title}>
              <i>{index + 1}</i>
              <div><strong>{card.title}</strong><span>{card.detail}</span><small>{run?.events.filter((event) => card.stages.includes(event.stage)).at(-1)?.message ?? "等待前置 Gate"}</small></div>
              <StatusChip status={stageStatus(card.stages)} compact />
            </li>
          ))}
        </ol>
      </section>

      {showLogs && (
        <section className="surface-card spring-log-card" aria-live="polite">
          <div className="business-section-heading">
            <div><span className="overline">REDACTED RUN LOG</span><h2>转换与运行日志</h2></div>
            <button className="button button-secondary" type="button" onClick={() => run && refresh(run.runId, true)}><Icon name="refresh" size={14} />刷新</button>
          </div>
          <pre>{logs?.lines.join("\n") || "日志尚未产生。"}</pre>
          {logs?.truncated && <small>仅显示最近的受限日志窗口；敏感模式已经脱敏。</small>}
        </section>
      )}

      <div className={`feedback-toast ${feedback ? "visible" : ""}`} role="status" aria-live="polite" aria-atomic="true">
        <span><Icon name="check" size={17} /></span>{feedback}
      </div>
    </div>
  );
}
